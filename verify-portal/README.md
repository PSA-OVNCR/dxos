# verify-portal/: cổng đối soát công khai (Tầng 2 [D])

Bất kỳ ai quét QR hoặc nhập mã niêm phong đều kiểm được văn bản. **Tệp được băm SHA-256 ngay trong trình duyệt bằng WebCrypto, không gửi lên máy chủ** (R-2): chỉ `{"sha256": "<hex>"}` (JSON) được gửi.

| Thư mục | Việc | URL (qua Caddy) |
|---|---|---|
| `app/` | Cổng Vue 3 (Plan 03 Task 6, S8.4). Trình duyệt **tự kiểm** gói bằng chứng: chữ ký niêm phong, chứng minh thuộc sổ cái, chữ ký STH, và so STH với repo neo. | `/apps/verify/#<seal_id>` |
| `minimal/` | Trang tĩnh tối giản (Plan 02), tin kết quả kiểm của máy chủ. Giữ làm dự phòng, xem `minimal/README.md`. | `/apps/verify-lite/#<seal_id>` |

## Cổng Vue (`app/`)

- Gói npm `dxos-verify-portal`, thuộc workspace gốc. Dùng `dxos-sdk-js` (`DxosClient`, `verifyBundle`, `rawAnchor`, `sha256Hex`).
- Lệnh: `npm run test -w dxos-verify-portal` (đơn vị), `npm run build -w dxos-verify-portal`, `npx -w dxos-verify-portal playwright test` (AT-25 trên trình duyệt thật, API giả dựng từ vector của witness).
- **Repo neo là biến BUILD**: `VITE_ANCHOR_RAW_BASE=https://raw.githubusercontent.com/<org>/dxos-transparency-log/main` (để trống = không ghim, nhãn là "Hợp lệ — chưa đối chiếu repo neo"). Không bao giờ đọc từ chuỗi `repo` máy chủ trả. Origin tương ứng phải có trong CSP: đặt `DXOS_ANCHOR_RAW_ORIGIN` (ví dụ `https://raw.githubusercontent.com`) cho dịch vụ `caddy`.
- Triển khai: Task 10 dựng bản build vào volume `apps-static` (đường dẫn `verify/`). Trước đó `/apps/verify/` trên stack đang chạy chưa có nội dung (404); dùng `/apps/verify-lite/`.

### Nhãn cuối cùng

Kết quả tự kiểm trên trình duyệt thắng `status` của máy chủ. Máy chủ chỉ được hạ nhãn (thu hồi, chưa sẵn sàng), không nâng nhãn.

| Tự kiểm (`verifyBundle`) | Nhãn |
|---|---|
| hỏng, mã khác `UNSUPPORTED_CRYPTO` | **Không hợp lệ**, bất kể máy chủ báo gì |
| đạt, đã ghim repo neo | Hợp lệ — đã đối chiếu repo neo |
| đạt, không ghim | Hợp lệ — chưa đối chiếu repo neo |
| đạt nhưng máy chủ báo đã thu hồi | Đã thu hồi (thu hồi nằm ngoài phần đã ký) |
| `UNSUPPORTED_CRYPTO` (trình duyệt thiếu Ed25519) | nhãn của máy chủ, kèm "Trình duyệt này không tự kiểm được chữ ký" |
| chưa có gói (máy chủ báo VALID) | Chưa tự kiểm trên trình duyệt (không bao giờ "Hợp lệ" trần) |

- **Repo neo không truy cập được** (mạng, CORS, 5xx): kiểm lại không ghim, nhãn "Hợp lệ — chưa đối chiếu repo neo" kèm "Không truy cập được repo neo — chưa đối chiếu". Repo neo trả 404 hay tệp khác gói là hỏng thật, nhãn "Không hợp lệ".
- `payload.seal_id` trong gói phải bằng mã đang kiểm: gói thật của niêm phong khác không thay được.
- Khi tự kiểm đạt, đơn vị niêm phong, trường công khai và thời điểm lấy từ payload đã ký; nhãn trường (`public_labels`) vẫn là chữ do máy chủ trả.
- 404, 429, 503 `keys-unavailable` và mọi lỗi mạng là "Không tìm thấy" / "Chưa kiểm được", không bao giờ "Không hợp lệ".

### Quy tắc bất biến (R-2, AT-25)

- Không `<form>`, không `FormData`, không đưa `File`/`Blob` của người dùng vào `fetch`. Mã niêm phong chỉ từ fragment và phải khớp `^[A-Z2-7]{26}$`.
- Không `v-html`, `innerHTML`, `eval`, `new Function`, `localStorage`; mọi giá trị hiển thị bằng `{{ }}`. Mỗi ô nhập có `<label>`. Giờ hiển thị theo `Asia/Ho_Chi_Minh`.
- CSP (Caddy, `/apps/verify/*`): `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' {$DXOS_ANCHOR_RAW_ORIGIN}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. Playwright chạy bản build dưới đúng CSP này (`vite preview`).
- Bundle: văn bản gói đưa thẳng cho `verifyBundle`, không qua `JSON.parse`; nút tải dựng Blob từ văn bản máy chủ trả, tên `dxos-seal-<seal_id>.json`.
