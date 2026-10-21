# verify-portal/minimal: trang đối soát tối giản

Trang tĩnh (HTML + JS thuần + CSS, không build, không thư viện ngoài) do Caddy phục vụ ở `https://<DXOS_DOMAIN>/apps/verify/#<seal_id>`. Tiêu đề "Kiểm tra tính xác thực và toàn vẹn văn bản điện tử" (spec 25.4).

| Tệp | Việc |
|---|---|
| `index.html` | Khung trang, câu pháp lý nguyên văn ở spec 25.1, giới hạn tin cậy |
| `verify.js` | Đọc `seal_id` từ `location.hash`, gọi `/verify/v1/seals/...`, băm tệp bằng WebCrypto |
| `verify.css` | Kiểu (CSP `style-src 'self'` nên không có style nội tuyến) |

## Quy tắc bất biến

- **Tệp không rời trình duyệt (R-2).** `crypto.subtle.digest("SHA-256", ...)` tính tại máy người dùng; chỉ `{"sha256": "<hex>"}` (JSON) được gửi tới `:check` và `:bundle`. Không có `<form>`, không `FormData`, không đưa `File`/`Blob` của người dùng vào `fetch`.
- **Mọi giá trị từ API gán bằng `textContent`.** Nhãn đến từ manifest, giá trị do người dùng nhập, nên cả hai không đáng tin. Không dùng `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `eval`.
- **`seal_id` chỉ từ fragment** (không từ query), phải khớp `^[A-Z2-7]{26}$` trước khi đưa vào URL (`encodeURIComponent`).
- **CSP** (Caddyfile, `handle_path /apps/verify/*`): `default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.

## Trạng thái hiển thị

| API | Trang |
|---|---|
| 404 | Không tìm thấy |
| 503 `keys-unavailable` | "Tạm thời chưa kiểm được chữ ký, thử lại sau" (không bao giờ là "Không hợp lệ") |
| `SEAL_PENDING` | Chờ niêm phong (không lộ trường nào) |
| `signature_valid: false`, hoặc `inclusion.verified: false` khi đã có STH phủ lá | Không hợp lệ |
| `REVOKED` | Đã thu hồi |
| `VALID` | Hợp lệ |

`inclusion.verified` cũng là `false` khi chưa có STH nào phủ lá (`inclusion.tree_size` là `null`, ngay sau khi niêm phong). Khi đó trang vẫn báo "Hợp lệ" (chữ ký đúng) kèm dòng chờ STH và **không** hiện nút tải gói: "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp".

Nút tải gói: niêm phong `require_file: false` dùng `GET .../bundle`; `require_file: true` dùng `POST ...:bundle` với hash của tệp đã khớp. Gói lưu thành `<seal_id>.dxos-bundle.json` (Blob dựng từ **phản hồi của máy chủ**, không phải tệp người dùng).

## Giới hạn tin cậy

Trang tối giản tin kết quả kiểm của máy chủ. Muốn kiểm độc lập: tải gói và chạy `dxos-witness verify-bundle --anchor-dir <repo neo> <gói>.json`. Cổng Vue ở Plan 03 sẽ tự kiểm chữ ký và STH đã neo ngay trên trình duyệt (spec 13.3).

## Kiểm thử

- Tĩnh: `tests/deploy/test_verify_page_static.py` (chạy trong `make check`).
- Sống qua Caddy + API thật, Playwright, ảnh chụp: `docs/evidence/verify-page-live-check.md`.
- Playwright "không request nào mang nội dung tệp" (AT-25) làm chính thức ở Plan 03.
