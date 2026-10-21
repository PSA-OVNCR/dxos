# cli/: CLI quản trị `dxos`

Cài, duyệt, vô hiệu hóa ứng dụng bằng manifest; xem sức khỏe, hàng cách ly và ledger; chạy neo thủ công. Wheel riêng
`dxos-cli` (chỉ cần `httpx`, `PyYAML`; không import `dxos-core`). Nói chuyện với host quản trị `https://admin.<miền>`
qua APISIX bằng bearer token của client công khai `dxos-cli` (Keycloak, device flow). Hiện thực ở Plan 02 Task 13 (S7.1).

## Cài
```bash
make dev-install                                   # editable, cùng các gói khác
python -m pip install dist/dxos_cli-*.whl          # hoặc từ wheel của bản phát hành
```

## Dùng
```bash
dxos login --server https://admin.example.vn       # device flow: mở liên kết in ra, xác nhận trên trình duyệt
dxos app install ./apps/app-a                      # nộp manifest.yaml + BPMN, in diff quyền chờ duyệt
dxos app list
dxos app diff <id> <version>
dxos app approve <id> <version>                    # người duyệt phải khác người nộp (bốn mắt)
dxos app disable <id>
dxos health
dxos quarantine list [--limit N]
dxos ledger status
dxos anchor run
```
`dxos health`: mỗi thành phần là `ok` hoặc `down: <lý do>`; `seal_key` là `ok`, `none` (chưa có tuyên bố cho
phiên bản khóa mới nhất, lần niêm phong đầu sẽ tạo), `expired` (cần xoay khóa), `invalid` (tuyên bố khóa trong DB
không qua kiểm hash: niêm phong bị chặn, cần điều tra) hoặc `unknown` (OpenBao không trả lời). Dòng bắt đầu bằng `!`
là vấn đề (`down: …`, `expired`, `invalid`, `unknown`).

Tùy chọn chung (đặt trước hoặc sau lệnh): `--server URL`, `--ca-file PEM`, `--json`.
- `--server` bắt buộc là `https://…` (`http://` chỉ cho `127.0.0.1`, `localhost`, `::1`). Bỏ `--server` thì dùng server
  của token đã lưu.
- `--ca-file` **thay thế** kho CA mặc định: chỉ tin các CA trong tệp PEM (ví dụ CA nội bộ của Caddy khi chạy trên
  `localhost`). Dùng cho cả máy chủ định danh lẫn API quản trị.
- `--json` in JSON thô của API thay cho văn bản.
- `login`: nếu bỏ `--issuer`, issuer được suy từ host `admin.<miền>` thành `https://<miền>/auth/realms/dxos`; host khác
  phải truyền `--issuer`.

## Token
- Thứ tự lấy token: biến `DXOS_TOKEN` (dùng cho mọi server, không có hạn; dành cho CI/e2e), rồi
  `$XDG_CONFIG_HOME/dxos/token.json` (mặc định `~/.config/dxos/token.json`).
- Tệp token quyền `0600`, thư mục `0700`, ghi nguyên tử; có kèm `server` và `issuer` nơi token được cấp.
  **Token đã lưu không bao giờ được gửi tới server khác**: dùng sai `--server` thì thoát mã 3.
- Refresh token (và hạn của nó) nằm cùng tệp. Access token hết hạn, hoặc server trả 401 một lần, thì CLI tự làm mới
  qua token endpoint của đúng issuer đã lưu (tìm lại bằng discovery, `issuer` trong tài liệu phải khớp), ghi lại
  nguyên tử rồi thử lại yêu cầu đúng một lần. Làm mới bị từ chối: thoát mã 3 "chạy lại dxos login"; lỗi mạng/5xx khi làm
  mới: mã 2. Không có refresh token còn hạn thì thoát mã 3 mà không gọi mạng. `DXOS_TOKEN` không bao giờ được làm mới.
- Thư mục `dxos` mà là symlink thì CLI từ chối ghi/đọc (không bị chuyển hướng ghi hay `chmod`); `token.json` là symlink
  thì bị thay bằng tệp thường. `$XDG_CONFIG_HOME` bản thân có thể là symlink.
- CLI không in và không ghi log token.

## `app install`
- Chỉ đọc `manifest.yaml` (`yaml.safe_load`) và tệp manifest tham chiếu (hiện là `workflow.bpmn`).
- Đường dẫn tệp phải tương đối và nằm trong thư mục app; đường dẫn tuyệt đối, `..`, `\`, symlink trỏ ra ngoài bị từ chối.
- Thân yêu cầu tối đa 1 MiB (trần của server).
- Sau khi nộp (202) CLI in `app_id`, `version`, `manifest_sha256` và diff quyền so với phiên bản ACTIVE để người duyệt xem
  trước khi chạy `dxos app approve`.
- `409 install-in-progress` (server đang cài app khác) được tự thử lại tối đa 5 lần, cách nhau 2 giây.

## Mã thoát
| Mã | Ý nghĩa |
|---|---|
| 0 | thành công (`dxos health` cũng 0 khi yêu cầu thành công, dù có thành phần `down: …`; dòng bắt đầu bằng `!`) |
| 1 | API trả 4xx (in `type`, `title`, `detail`, `code`, `path`…), đầu vào hoặc cách dùng sai |
| 2 | lỗi mạng hoặc API trả 5xx |
| 3 | chưa đăng nhập, token (và refresh) hết hạn hoặc bị từ chối, token không dành cho server này |
| 130 | bị ngắt bằng Ctrl-C |

## Test
```bash
python -m pytest cli -q      # dùng respx, không cần dịch vụ thật
```
