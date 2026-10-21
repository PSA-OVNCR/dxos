# verify-portal/minimal: trang đối soát tối giản

Trang tĩnh (HTML + JS thuần + CSS, không build, không thư viện ngoài) do Caddy phục vụ ở `https://<DXOS_DOMAIN>/apps/verify-lite/#<seal_id>` (từ Plan 03 Task 6; `/apps/verify/` là cổng Vue ở `verify-portal/app/`, xem `../README.md`). Tiêu đề "Kiểm tra tính xác thực và toàn vẹn văn bản điện tử" (spec 25.4).

| Tệp | Việc |
|---|---|
| `index.html` | Khung trang, câu pháp lý nguyên văn ở spec 25.1, giới hạn tin cậy |
| `verify.js` | Đọc `seal_id` từ `location.hash`, gọi `/verify/v1/seals/...`, băm tệp bằng WebCrypto |
| `verify.css` | Kiểu (CSP `style-src 'self'` nên không có style nội tuyến) |

## Quy tắc bất biến

- **Tệp không rời trình duyệt (R-2).** `crypto.subtle.digest("SHA-256", ...)` tính tại máy người dùng; chỉ `{"sha256": "<hex>"}` (JSON) được gửi tới `:check` và `:bundle`. Không có `<form>`, không `FormData`, không đưa `File`/`Blob` của người dùng vào `fetch`.
- **Giới hạn đã biết:** `file.arrayBuffer()` nạp cả tệp vào bộ nhớ để băm (WebCrypto không băm theo luồng), nên tệp rất lớn có thể không băm được trên máy yếu; khi đó trang báo "Không đọc được tệp này" và không gửi gì.
- **Mọi giá trị từ API gán bằng `textContent`.** Nhãn đến từ manifest, giá trị do người dùng nhập, nên cả hai không đáng tin. Không dùng `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `eval`.
- **`seal_id` chỉ từ fragment** (không từ query), phải khớp `^[A-Z2-7]{26}$` trước khi đưa vào URL (`encodeURIComponent`).
- **CSP** (Caddyfile, `handle_path /apps/verify-lite/*`): `default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.

## Trạng thái hiển thị

| API | Trang |
|---|---|
| 404 | Không tìm thấy |
| 503 `keys-unavailable` | "Tạm thời chưa kiểm được chữ ký, thử lại sau" (không bao giờ là "Không hợp lệ") |
| `SEAL_PENDING` | Chờ niêm phong (không lộ trường nào) |
| `signature_valid: false`, hoặc `inclusion.verified: false` khi đã có STH phủ lá | Không hợp lệ |
| `REVOKED` | Đã thu hồi |
| `VALID`, `signature_valid: true`, `inclusion.verified: true` và `inclusion.anchored` khác `null` | Hợp lệ |
| `VALID`, `signature_valid: true`, `inclusion.verified: true`, `inclusion.anchored` là `null` (STH chưa neo công khai) | "Hợp lệ — chưa neo công khai" (lớp CSS `unanchored`, không phải "Hợp lệ" trần) |
| `VALID`, `signature_valid: true`, chưa có STH phủ lá (`inclusion.tree_size` null) | "Chữ ký hợp lệ — đang chờ công bố vào sổ cái" (lớp CSS `wait`, không phải "Hợp lệ") |

Với "Không hợp lệ" trang chỉ hiện huy hiệu và lý do (chữ ký sai, hoặc không thuộc sổ cái); không hiện đơn vị, trường công khai, chi tiết sổ cái, ô chọn tệp hay nút gói.

Ngay sau khi niêm phong, `inclusion.verified` là `false` vì chưa có STH nào phủ lá (`inclusion.tree_size` là `null`). Trang không báo "Không hợp lệ" cũng không báo "Hợp lệ" trần: hiện trạng thái chờ ở trên, dòng "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp" và **không** có nút tải gói. Thiếu `inclusion` hoặc `signature_valid` khác `true` đều là "Không hợp lệ".

Nút tải gói: niêm phong `require_file: false` dùng `GET .../bundle`; `require_file: true` dùng `POST ...:bundle` với hash của tệp đã khớp. Gói lưu thành `dxos-seal-<seal_id>.json`, đúng tên máy chủ đặt ở `Content-Disposition` (cũng là tên trong tài liệu `dxos-witness`); Blob dựng từ **phản hồi của máy chủ**, không phải tệp người dùng.

## Giới hạn tin cậy

Trang tối giản tin kết quả kiểm của máy chủ. Muốn kiểm độc lập: tải gói và chạy `dxos-witness verify-bundle --anchor-dir <repo neo> <gói>.json`. Cổng Vue ở `/apps/verify/` (Plan 03 Task 6) tự kiểm chữ ký và STH đã neo ngay trên trình duyệt (spec 13.3).

## Kiểm thử

- Tĩnh: `tests/deploy/test_verify_page_static.py` (chạy trong `make check`).
- Caddy thật, danh sách IP của host quản trị: `tests/deploy/test_caddy_admin_allowlist_live.py` (cần binary `caddy`: `CADDY_BIN=/đường/dẫn/caddy`; không có thì bỏ qua; đặt `DXOS_REQUIRE_CADDY=1` để thiếu Caddy thành lỗi, như job `caddy-live` của CI).
- Trình duyệt thật (opt-in, bỏ qua khi chưa bật): dựng niêm phong thật + API + Caddy rồi chạy Playwright (Node) `tests/deploy/browser/*.js`:

  ```
  DXOS_TEST_BROWSER=1 CADDY_BIN=/đường/dẫn/caddy PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
  DXOS_SHOT_DIR=docs/evidence DXOS_TEST_REQUIRE_DB=1 \
  python -m pytest core/tests/integration/test_verify_page_browser.py -s
  ```

  Cần `node`, module `playwright` (`npm i -g playwright`; đặt `NODE_PATH` nếu cần) và dịch vụ của `make test-db-up`. Ảnh chụp ghi vào `DXOS_SHOT_DIR`.
- Kết quả đã chạy: `docs/evidence/verify-page-live-check.md`. AT-25 chính thức (Playwright, không request nào mang nội dung tệp) chạy trên cổng Vue: `verify-portal/app/e2e/at25.spec.ts`.
