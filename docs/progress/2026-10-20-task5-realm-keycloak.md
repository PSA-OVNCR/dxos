# Plan 01 Task 5: realm Keycloak `dxos`

*Lập 20/10/2026. Commit `79016d0`.*

## Kiểm chứng
| Môi trường | Cách chạy | Kết quả |
|---|---|---|
| Keycloak 26.3.0 (bản phân phối, `start-dev`, `--http-relative-path=/auth`) trên máy phát triển | `pytest tests/infra/test_keycloak_realm.py` (gồm marker `infra`) | **18/18 đạt** |
| Stack dev-lite trên Docker Desktop (Windows), 20/10/2026 19:15 | script PowerShell tương đương test sống | **Đạt toàn bộ** (bảng dưới) |

| Kiểm tra trên stack | Kết quả |
|---|---|
| Keycloak nạp realm khi khởi động | `Realm 'dxos' imported`, `Import finished successfully`; 13/13 container healthy |
| Token cho 10 người dùng dev qua `https://localhost/auth` | 10/10 HTTP 200; `iss=https://localhost/auth/realms/dxos`; `aud=dxos-api`; đúng vai trò `app:<id>:<role>` / `dxos-admin` |
| Client `dxos-spa` dùng password grant | 400 `unauthorized_client` (đúng: SPA chỉ dùng Authorization Code + PKCE) |
| APISIX `/api/v1/healthz` không token | 401 |
| APISIX với token giả | 401 |
| APISIX với token thật của `chuyen_vien1` | đi qua gateway (404 từ stub trust-core, Task 8 thay bằng API thật) |

## Lỗi phát hiện và đã sửa trước khi commit
Realm khai báo `clientScopes` thì Keycloak **không** tự tạo scope mặc định: token thiếu `realm_access` và `sub`. Sửa: khai báo tường minh `basic`, `profile`, `roles`, `web-origins`, `acr`; test tĩnh `test_every_referenced_client_scope_is_defined` chặn tái phát.

## Còn mở
- Route `/admin/v1` trên host quản trị với token `admin1`: cần trust-core thật (Task 8, Task 10).
