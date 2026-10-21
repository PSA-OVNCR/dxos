# Kiểm sống trang đối soát tối giản (Plan 02 Task 10, Step 3)

Ngày: 2026-10-21. Commit nền: `d7e06b2` (cộng thay đổi của Task 10). Không có Docker trong môi trường này, nên không chạy được `https://localhost/` của stack dev-lite; thay bằng:

- Caddy 2.10.0 (cùng minor với image compose) chạy **Caddyfile thật** của repo, chỉ thay `apisix:9080` bằng uvicorn của API thật, `root * /srv/verify` bằng `verify-portal/minimal`, `root * /srv` bằng một thư mục thử; địa chỉ site `localhost:58444` (TLS nội bộ của Caddy), host admin `admin.localhost:58444` với `DXOS_ADMIN_ALLOWED_IPS=203.0.113.7/32`.
- uvicorn chạy `create_app` của lõi với DB test, signer cục bộ, niêm phong thật do harness `flow` tạo (Flowable, SeaweedFS, fake clamd thật).
- Playwright 1.56.1 (Node) với Chromium cài sẵn, qua https với CSP thật của Caddy.
- Kịch bản dựng bằng một pytest tạm (đã xóa, không commit): tạo niêm phong có tệp (`require_file: true`), đã thu hồi, không cần tệp, chưa có STH phủ lá, và `SEAL_PENDING`.

Cần chụp lại trên dev-lite khi có Docker (`https://localhost/apps/verify/#<seal_id>`).

## Thứ tự route (caddy adapt)

```
$ DXOS_DOMAIN=localhost DXOS_ADMIN_HOST=admin.localhost DXOS_ADMIN_ALLOWED_IPS=private_ranges \
    caddy validate --config deploy/caddy/Caddyfile --adapter caddyfile      -> Valid configuration
host localhost (rút gọn):
  path /apps/verify        -> static_response (redir 308)
  path /auth/admin, /auth/admin/*
  path /auth/*
  path /api/* /admin/* /verify/* /view/*
  path /apps/verify/*      -> subroute (file_server /srv/verify + CSP)
  path /apps/*             -> subroute (file_server /srv)
  (không match)            -> 404
```

## curl (qua Caddy)

```
+ curl -skI https://localhost:58444/apps/verify/
+ sed -n '1p;/[Cc]ontent-[Ss]ecurity-[Pp]olicy/p;/[Xx]-[Cc]ontent-[Tt]ype/p;/[Rr]eferrer/p;/[Cc]ontent-[Tt]ype/p'
HTTP/2 200 
content-security-policy: default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
content-type: text/html; charset=utf-8
referrer-policy: no-referrer
x-content-type-options: nosniff
x-content-type-options: nosniff
+ curl -skI https://localhost:58444/apps/verify/verify.js
+ sed -n '1p;/[Cc]ontent-[Ss]ecurity-[Pp]olicy/p;/[Cc]ontent-[Tt]ype/p'
HTTP/2 200 
content-security-policy: default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
content-type: text/javascript; charset=utf-8
x-content-type-options: nosniff
+ curl -skI https://localhost:58444/apps/verify/verify.css
+ sed -n '1p;/[Cc]ontent-[Ss]ecurity-[Pp]olicy/p;/[Cc]ontent-[Tt]ype/p'
HTTP/2 200 
content-security-policy: default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
content-type: text/css; charset=utf-8
x-content-type-options: nosniff
+ curl -skI https://localhost:58444/apps/verify
+ sed -n '1p;/[Ll]ocation/p'
HTTP/2 308 
location: /apps/verify/
+ sed -n '1p;/[Cc]ontent-[Ss]ecurity-[Pp]olicy/p'
+ curl -skI https://localhost:58444/apps/other.txt
HTTP/2 200 
+ curl -sk -o /dev/null -w '%{http_code}\n' https://localhost:58444/apps/verify/../other.txt --path-as-is
200
+ curl -sk -o /dev/null -w '%{http_code}\n' https://localhost:58444/apps/verify/%2e%2e/other.txt --path-as-is
200
+ curl -sk -o /dev/null -w '%{http_code}\n' https://localhost:58444/apps/verify/nope.html
404
+ curl -sk https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME
+ head -c 600
{"seal_id":"I4NYLQHXCFKRZ5QW3OIFNWM6ME","status":"VALID","app_id":"test-flow","issued_at":"2026-10-21T10:26:38Z","key_version":1,"public_fields":{"ref":"01/TF","title":"Hồ sơ thử"},"require_file":true,"attachments_count":1,"signature_valid":true,"inclusion":{"leaf_index":9,"tree_size":35,"verified":true,"anchored":null},"issuer":{"id":null,"name":"Tổ chức thử nghiệm"},"public_labels":{"title":"Tiêu đề"}}+ echo

+ curl -sk -o /dev/null -w 'GET view via caddy: %{http_code}\n' https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME
GET view via caddy: 200
-- HTTP/1.1 chunked, 400+ byte, qua Caddy
+ curl -sk --http1.1 -i -X POST -H 'Content-Type: application/json' -H 'Transfer-Encoding: chunked' --data-binary @/tmp/t10chunk.json https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME:check -w '\n[curl exit=%{exitcode} http=%{http_code}]\n'
HTTP/1.1 413 Request Entity Too Large
Alt-Svc: h3=":58444"; ma=2592000
Content-Length: 130
Content-Type: application/problem+json
Date: Wed, 21 Oct 2026 10:26:41 GMT
Server: uvicorn
Via: 1.1 Caddy

{"type":"https://dxos.dev/problems/payload-too-large","title":"Payload Too Large","status":413,"detail":"body limit is 256 bytes"}
[curl exit=0 http=413]
-- HTTP/2 stream (không ép header), 400+ byte, qua Caddy
+ curl -sk -i -X POST -H 'Content-Type: application/json' -T - https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME:check -w '\n[curl exit=%{exitcode} http=%{http_code} http_version=%{http_version}]\n'
HTTP/2 413 
alt-svc: h3=":58444"; ma=2592000
content-type: application/problem+json
date: Wed, 21 Oct 2026 10:26:41 GMT
server: uvicorn
via: 1.1 Caddy
content-length: 130

{"type":"https://dxos.dev/problems/payload-too-large","title":"Payload Too Large","status":413,"detail":"body limit is 256 bytes"}
[curl exit=0 http=413 http_version=2]
-- 413 rồi yêu cầu kế tiếp trên cùng phiên curl (HTTP/1.1, giữ kết nối)
+ curl -sk --http1.1 -X POST -H 'Content-Type: application/json' -H 'Transfer-Encoding: chunked' --data-binary @/tmp/t10chunk.json https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME:check -o /dev/null -w '413-then-next: %{http_code}\n' --next -sk --http1.1 https://localhost:58444/verify/v1/seals/I4NYLQHXCFKRZ5QW3OIFNWM6ME -o /dev/null -w 'next: %{http_code} (connects=%{num_connects})\n'
413-then-next: 413
next: 200 (connects=0)
+ curl -sk -o /dev/null -w 'admin host (IP 127.0.0.1 không thuộc DXOS_ADMIN_ALLOWED_IPS) GET /apps/other.txt: %{http_code}\n' --resolve admin.localhost:58444:127.0.0.1 https://admin.localhost:58444/apps/other.txt
admin host (IP 127.0.0.1 không thuộc DXOS_ADMIN_ALLOWED_IPS) GET /apps/other.txt: 200
```

Ghi chú:
- Dòng `x-content-type-options` lặp trong `HEAD /apps/verify/` là do mẫu `sed` lọc khớp hai lần, không phải header lặp.
- Hai lệnh `..` và `%2e%2e` được Caddy chuẩn hóa về `/apps/other.txt` trước khi định tuyến (200 từ thư mục apps; không đọc ra ngoài gốc nào).
- Chunked > 256 byte qua Caddy → uvicorn, `:check`: 413 `payload-too-large` với HTTP/1.1 chunked và với HTTP/2 stream; curl thoát mã 0; yêu cầu kế tiếp trên cùng phiên trả 200 (`connects=0`, kết nối dùng lại được). Không treo, không reset.
- **Phát hiện ngoài phạm vi Task 10 (có từ Plan 01):** dòng cuối cho thấy host admin trả 200 cho IP `127.0.0.1` dù `DXOS_ADMIN_ALLOWED_IPS=203.0.113.7/32`. Nguyên nhân: Caddy xếp `respond @blocked ...` sau mọi `handle`, mà `handle {}` cuối khớp tất cả nên nhánh 403 không bao giờ chạy. Đề xuất sửa: `handle @blocked { respond "Forbidden" 403 }` (đã kiểm bằng `caddy adapt`: nhánh chặn lên ngay sau redir, trước mọi `handle`). Chưa sửa trong commit này.

### Thân chunked hợp lệ (thử thêm)

`curl` ép header `Transfer-Encoding: chunked` trên HTTP/2 là gói tin không hợp lệ theo RFC 9113 (trình duyệt không bao giờ gửi), và qua Caddy cho kết quả 422 dù thân đúng. Cùng thân đó qua HTTP/1.1 chunked cho 200, và gọi thẳng uvicorn đều 200. Ghi lại để không nhầm là lỗi của API:

```
body length: 77
== https://localhost:58444
-- content-length
{"match":false}  [http=200]
-- chunked (HTTP/1.1)
{"match":false}  [http=200]
-- chunked (default)
{"type":"https://dxos.dev/problems/invalid-request","title":"Body must be {\"sha256\": \"<64 lowercase hex>\"}","status":422}  [http=422]
== http://127.0.0.1:58901
-- content-length
{"match":false}  [http=200]
-- chunked (HTTP/1.1)
{"match":false}  [http=200]
-- chunked (default)
{"match":false}  [http=200]
```

## Playwright (trang thật qua Caddy)

```
PASS tiêu đề
PASS h1
PASS không có kết quả khi chưa có mã
  badge: Hợp lệ | issuer: Đơn vị niêm phong: Tổ chức thử nghiệm
  fields: ["ref","01/TF","Tiêu đề","Hồ sơ thử","Thời điểm niêm phong","17:26:38 21/10/2026 (giờ Việt Nam) — 2026-10-21T10:26:38Z","Mã niêm phong","I4NYLQHXCFKRZ5QW3OIFNWM6ME","Số tệp đính kèm","1"]
  ledger: Sổ cái: đã kiểm niêm phong nằm ở vị trí 9 của cây có 35 mục (máy chủ kiểm). | anchor: Chưa neo công khai.
PASS Hợp lệ
PASS Đơn vị niêm phong hiển thị
PASS Thời điểm niêm phong
PASS nhãn Tiêu đề thay cho title / tên trường khi không có nhãn
PASS ô chọn tệp hiện
PASS chưa có nút gói trước khi khớp tệp
PASS tệp đúng: Khớp  Khớp: tệp này đúng là tệp đã được niêm phong.
PASS nút gói hiện sau khi khớp
PASS đúng 1 request :check, thân chỉ là {sha256}  {"sha256":"fe4a35f0ca98e73ee2f8879ef86a2d3993f0e3d388639716138d275d51eb0ee1"}
PASS không request nào mang nội dung tệp (thân < 300 byte, không chứa byte đầu của tệp)
PASS tải gói: tên tệp  I4NYLQHXCFKRZ5QW3OIFNWM6ME.dxos-bundle.json
PASS gói là JSON có chữ ký + sth  format,status,payload,signature,seal_key,ledger,inclusion,sth,sth_keys,anchored,generated_at
PASS POST :bundle chỉ mang hash
PASS tệp sửa 1 byte: Không khớp  Không khớp: tệp này khác tệp đã được niêm phong (đã bị sửa hoặc là tệp khác).
PASS nút gói ẩn khi không khớp
PASS không cần tệp: không có ô chọn tệp
PASS không cần tệp: có nút gói
PASS GET bundle tải về .dxos-bundle.json
  anchor-line: Chưa neo công khai.
PASS Đã thu hồi
PASS chưa có STH phủ: Hợp lệ + dòng chờ STH  Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp. | Sổ cái: chưa có STH phủ niêm phong này (chờ lần công bố STH kế tiếp).
PASS Không tìm thấy
PASS sai dạng: báo lỗi, không gọi API
PASS XSS: không tạo phần tử img/script từ dữ liệu
PASS XSS: chuỗi hiện nguyên văn
PASS 503: thông báo thử lại, không phải Không hợp lệ
PASS signature_valid=false → Không hợp lệ, issuer null → (không xác định), không nút gói
PASS inclusion.verified=false (có STH) → Không hợp lệ
PASS nhập tay mã + Enter → đặt location.hash
PASS không vi phạm CSP nào trong cả phiên  []
PASS không lỗi console/trang  []
  CSP header: default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
PASS CSP chặn script nội tuyến
PASS 375px: không cuộn ngang
ALL PASS
PASS Chờ niêm phong: không lộ trường, không ô tệp, không nút gói | Văn bản đã được duyệt, niêm phong đang được hoàn tất. Thử lại sau ít phút.
```

## Ảnh chụp

| Tệp | Nội dung |
|---|---|
| `verify-page-1-valid-needs-file.png` | Hợp lệ, niêm phong cần tệp, chưa chọn tệp |
| `verify-page-2-file-match.png` | Chọn đúng tệp: Khớp, có nút tải gói |
| `verify-page-3-file-mismatch.png` | Tệp sửa 1 byte: Không khớp, không có nút gói |
| `verify-page-4-valid-no-file.png` | Niêm phong không cần tệp: nút gói (GET) |
| `verify-page-5-revoked.png` | Đã thu hồi |
| `verify-page-6-valid-waiting-sth.png` | Chữ ký hợp lệ, chưa có STH phủ lá: "Chữ ký hợp lệ — đang chờ công bố vào sổ cái" + "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp" (chụp lại ở fix round 0) |
| `verify-page-7-mobile.png` | Cùng trang ở 375 px |
| `verify-page-8-pending.png` | Chờ niêm phong |

## Fix round 0 (21/10, sau commit đầu)

Thay đổi: trạng thái trước STH, tên tệp gói, danh sách IP host quản trị (lỗi từ Plan 01), script trình duyệt được commit (opt-in). Các phần trên là lần chạy đầu (https, trang bản đầu); phần dưới là lần chạy lại.

### Danh sách IP của host quản trị (Caddyfile thật, http, client 127.0.0.1; 502 = qua được tới upstream không có mặt)

Trước khi sửa: `DXOS_ADMIN_ALLOWED_IPS=203.0.113.7/32` vẫn cho 127.0.0.1 vào host quản trị (200). Sau khi sửa (`handle @blocked { respond "Forbidden" 403 }`, xếp ngay sau redir và trước mọi handle theo `caddy adapt`):

```
=== DXOS_ADMIN_ALLOWED_IPS=203.0.113.7/32 (client 127.0.0.1)
admin.localhost /                          -> 403
admin.localhost /apps/other.txt            -> 403
admin.localhost /apps/verify               -> 308
admin.localhost /apps/verify/              -> 403
admin.localhost /auth/realms/dxos          -> 403
admin.localhost /admin/v1/ledger/status    -> 403
localhost       /apps/other.txt            -> 200
=== DXOS_ADMIN_ALLOWED_IPS=127.0.0.1/32 (client 127.0.0.1)
admin.localhost /                          -> 404
admin.localhost /apps/other.txt            -> 200
admin.localhost /apps/verify               -> 308
admin.localhost /apps/verify/              -> 200
admin.localhost /auth/realms/dxos          -> 502
admin.localhost /admin/v1/ledger/status    -> 502
localhost       /apps/other.txt            -> 200
```

`/apps/verify` (không dấu `/` cuối) vẫn trả 308 cho IP bị chặn: `redir` là directive chạy trước mọi `handle`, chỉ chuyển hướng tới `/apps/verify/` (lúc đó bị 403), không lộ nội dung.

### Playwright lần chạy lại (qua pytest opt-in `core/tests/integration/test_verify_page_browser.py`, Caddy http cục bộ)

```
PASS tiêu đề
PASS h1
PASS không có kết quả khi chưa có mã
  badge: Hợp lệ | issuer: Đơn vị niêm phong: Tổ chức thử nghiệm
  fields: ["ref","01/TF","Tiêu đề","Hồ sơ thử","Thời điểm niêm phong","17:32:13 21/10/2026 (giờ Việt Nam) — 2026-10-21T10:32:13Z","Mã niêm phong","AAO7YGOO2UYLZJ4GVYR7TKXG3M","Số tệp đính kèm","1"]
  ledger: Sổ cái: đã kiểm niêm phong nằm ở vị trí 9 của cây có 35 mục (máy chủ kiểm). | anchor: Chưa neo công khai.
PASS Hợp lệ
PASS Đơn vị niêm phong hiển thị
PASS Thời điểm niêm phong
PASS nhãn Tiêu đề thay cho title / tên trường khi không có nhãn
PASS ô chọn tệp hiện
PASS chưa có nút gói trước khi khớp tệp
PASS tệp đúng: Khớp  Khớp: tệp này đúng là tệp đã được niêm phong.
PASS nút gói hiện sau khi khớp
PASS đúng 1 request :check, thân chỉ là {sha256}  {"sha256":"fe4a35f0ca98e73ee2f8879ef86a2d3993f0e3d388639716138d275d51eb0ee1"}
PASS không request nào mang nội dung tệp (thân < 300 byte, không chứa byte đầu của tệp)
PASS tải gói: tên tệp như máy chủ đặt  dxos-seal-AAO7YGOO2UYLZJ4GVYR7TKXG3M.json
PASS gói là JSON có chữ ký + sth  format,status,payload,signature,seal_key,ledger,inclusion,sth,sth_keys,anchored,generated_at
PASS POST :bundle chỉ mang hash
PASS tệp sửa 1 byte: Không khớp  Không khớp: tệp này khác tệp đã được niêm phong (đã bị sửa hoặc là tệp khác).
PASS nút gói ẩn khi không khớp
PASS không cần tệp: không có ô chọn tệp
PASS không cần tệp: có nút gói
PASS GET bundle tải về dxos-seal-<id>.json  dxos-seal-O7V3DHNYERXPIB6KQKKZWPYC2U.json
  anchor-line: Chưa neo công khai.
PASS Đã thu hồi
PASS chưa có STH phủ: không phải 'Hợp lệ' trần, có lớp wait riêng
PASS chưa có STH phủ: dòng chờ STH, không nút gói  Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp. | Sổ cái: chưa có STH phủ niêm phong này (chờ lần công bố STH kế tiếp).
PASS Không tìm thấy
PASS sai dạng: báo lỗi, không gọi API
PASS XSS: không tạo phần tử img/script từ dữ liệu
PASS XSS: chuỗi hiện nguyên văn
PASS 503: thông báo thử lại, không phải Không hợp lệ
PASS signature_valid=false → Không hợp lệ, issuer null → (không xác định), không nút gói
PASS inclusion.verified=false (có STH) → Không hợp lệ
PASS signature_valid=true + tree_size=null → chờ công bố, không Hợp lệ
PASS thiếu inclusion → Không hợp lệ
PASS nhập tay mã + Enter → đặt location.hash
PASS không vi phạm CSP nào trong cả phiên  []
PASS không lỗi console/trang  []
  CSP header: default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
PASS CSP chặn script nội tuyến
PASS 375px: không cuộn ngang
ALL PASS
PASS Chờ niêm phong: không lộ trường, không ô tệp, không nút gói | Văn bản đã được duyệt, niêm phong đang được hoàn tất. Thử lại sau ít phút.
  /home/claude/dxos/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa
```
