<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# viewer/: Secure Viewer (Tầng 2 [P], SHOULD)

Gói `dxos-viewer` 0.9.0 (S2, Plan 04 Task 7; S10.2). Dịch vụ **không trạng thái, chỉ trong RAM**: lấy tệp PDF từ API
của Trust Core, vẽ **một trang** thành ảnh PNG, đóng watermark rồi trả ảnh. Task 8 đã đấu nối vào compose
p16 (service `viewer`, profile `viewer`, chỉ hồ sơ p16), APISIX `/view/*` và App A (nút "Xem" chỉ hiện khi `healthz` trả 200).

## Watermark chỉ để răn đe

Watermark là dòng chữ `DX-OS <8 ký tự đầu của sub> <YYYY-MM-DD HH:MM> ICT` (ASCII, phông Helvetica, cỡ 18, xoay 30°,
lặp lưới 3 × 4, xám 128, độ đục 45%: thấy được cả trên nền sáng lẫn nền tối). Chú thích của PDF được dán phẳng vào nội dung
trước khi chèn watermark nên không chú thích nào che được nó. Nó gắn danh tính và giờ xem vào ảnh để người xem biết việc xem có dấu vết. Nó **chỉ để
răn đe**: không ngăn được chụp màn hình, chụp ảnh màn hình bằng điện thoại hay chép tay; không phải biện pháp chống rò rỉ.

## Điểm vào

Đặt sau APISIX, tiền tố `/view`. Mọi điểm (trừ `healthz`) cần `Authorization: Bearer <token>` của người gọi. Qua cổng thì
**cả `healthz`** cũng cần token (route `/view/*` dùng chuỗi OIDC bearer như `/api/v1/*`); App A gửi token khi hỏi `healthz`.

| Yêu cầu | Trả về |
|---|---|
| `GET /view/v1/healthz` | `{"status":"ok"}` |
| `GET /view/v1/objects/{sha256}/info?variant=` | `{"pages": n}` |
| `GET /view/v1/objects/{sha256}/pages/{n}.png?variant=` | `image/png` (n từ 1), `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` |

`variant` là `original` hoặc `redacted`, chuyển nguyên văn cho `GET /api/v1/objects/{sha256}`; API quyết định ai được
xem bản gốc (chặn theo `reveal_pii` với bộ sưu tập có PII). Lỗi theo RFC 9457 (`application/problem+json`):

| Tình huống | Mã |
|---|---|
| thiếu hoặc sai dạng `Authorization` (chưa gọi API) | 401 |
| API trả 401 | 401 |
| API trả 404 hoặc bất kỳ lỗi 4xx khác; số trang ngoài `1..n`; `sha256` sai dạng | 404, không có ảnh |
| `variant` lạ | 422 |
| API 5xx hoặc không nối được; `whoami` không trả `sub` | 502 |
| API quá `DXOS_VIEWER_TIMEOUT_S` | 504 |
| hết chỗ dựng (tối đa 2 trang cùng lúc; chờ tối đa `DXOS_VIEWER_TIMEOUT_S`), kèm `Retry-After` | 503 |
| lỗi không lường trước (không kèm chi tiết nội bộ) | 500 |
| tệp không phải PDF | 415 |
| PDF hỏng, hoặc quá 200 trang | 422 |
| tệp lớn hơn `DXOS_VIEWER_MAX_BYTES` | 413 |

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DXOS_VIEWER_API_BASE` | `http://apisix:9080` | địa chỉ API (qua APISIX) |
| `DXOS_VIEWER_TIMEOUT_S` | `10` | tổng thời gian cho mỗi lần gọi API; quá hạn trả 504 |
| `DXOS_VIEWER_MAX_BYTES` | `67108864` (64 MiB) | trần dung lượng tệp tải về (giữ trong RAM) |

Viewer không có khóa hay bí mật nào, chỉ nằm trên mạng `net-app`, không chạm kho lưu trữ, Flowable hay OpenBao.

Trong compose (`deploy/compose.yaml`): `read_only: true` không tmpfs/volume (chạy uvicorn và dựng trang không cần đường ghi
nào: đã kiểm bằng `strace` trên tiến trình thật, không có lần mở tệp để ghi), `cap_drop: [ALL]`, `no-new-privileges`,
`mem_limit`/`memswap_limit` 768 MiB, `cpus: 1.0`, `pids_limit: 128`. Viewer **không có giới hạn thời gian dựng** (PDFium không
hủy được); cổng APISIX cắt sau 30 giây, còn giới hạn tài nguyên giữ một PDF bệnh lý trong container này.

## Giới hạn

- Tối đa 200 trang mỗi tệp; ảnh mỗi trang không quá 4000 × 4000 điểm (trang quá lớn bị hạ dpi riêng cho trang đó); 110 dpi.
- Không ghi đĩa: không `tempfile`, không `open(..., 'w')`, không `.write_bytes`/`.write_text` trong `src/`
  (test tĩnh `tests/test_no_disk.py`, kèm test chạy thật chặn mọi lần mở tệp để ghi). Các test này chỉ bắt lỗi
  trong mã Python của Viewer; bảo đảm thật sự là **hệ tệp gốc chỉ đọc** của container (Task 8 bật `read_only`),
  vì mã gốc của PDFium nằm ngoài tầm của test Python.
- Mỗi lần gọi chỉ giữ một trang trong RAM; tối đa 2 lần tải + dựng song song (hỏi `whoami` nằm ngoài chỗ này). Không cache, không nhớ gì giữa hai yêu cầu.
- `src/dxos_viewer/png.py` là bản chép của `core/src/dxos_core/pii/png.py` (gói riêng, không import `dxos_core`);
  test của hai bản (`tests/test_png.py`, `core/tests/test_pii_png.py`) giống nhau trừ dòng import.
- Chỉ bốn phụ thuộc: `fastapi`, `uvicorn[standard]`, `httpx`, `pypdfium2` (phiên bản ghim ở `constraints.txt`).

## Chạy và thử

```bash
pip install -c constraints.txt -e viewer
python -m pytest viewer/tests -q
DXOS_VIEWER_API_BASE=http://127.0.0.1:9080 uvicorn dxos_viewer.app:create_app --factory --port 8000
docker build -f viewer/Dockerfile -t dxos-viewer .
```
