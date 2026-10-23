# deploy/: hạ tầng Docker Compose

| Tệp | Vai trò |
|---|---|
| `compose.yaml` | Dịch vụ, **9 mạng** phân vùng (spec 6.2), healthcheck, volume |
| `compose.p16.yaml`, `compose.p8.yaml` | Hồ sơ tài nguyên (spec 16.1). Dịch vụ `viewer` (profile `viewer`) chỉ chạy ở p16: `.env.example` đặt `COMPOSE_PROFILES=viewer`, p8 và dev-lite đổi profile của nó nên không dựng; `profile_only` trong `network-matrix.yaml` ghi quy tắc này cho test |
| `compose.dev-lite.yaml` | Chỉ dùng khi phát triển: ClamAV → `fake-av` (nhãn `dxos.dev-only`) |
| `compose.test.yaml` | Dự án riêng `dxos-test` cho integration test: core-db, OpenBao (dev), fake-av, SeaweedFS; cổng chỉ trên 127.0.0.1 |
| `network-matrix.yaml` | **Nguồn sự thật** cho phân vùng mạng; test tĩnh và `ops/netcheck.py` đọc tệp này |
| `caddy/Caddyfile` | TLS, `/auth` → Keycloak, `/api` `/admin` `/verify` `/view` → APISIX, `/apps` tệp tĩnh; host quản trị giới hạn IP |
| `apisix/` | APISIX standalone (không Admin API, không etcd): route tĩnh, OIDC bearer, limit-req |
| `keycloak/realm-dxos.json` | Realm `dxos` cho production: vai trò `dxos-admin`, client `dxos-spa` (PKCE S256), `dxos-admin-ui` (công khai, PKCE S256, chỉ host admin `/ui/`), `apisix`, `dxos-installer` (service account chỉ có `realm-management/manage-realm`), `dxos-cli` (công khai, chỉ device flow); scope `dxos-api-audience`; bật admin events. Secret dạng `${BIEN}` lấy từ `.env` khi nạp |
| `../ops/keycloak_upgrade.py` | Đưa realm **đã có** (Keycloak bỏ qua `--import-realm` khi realm đã tồn tại) lên cấu hình hiện tại; idempotent, in phần lệch không tự sửa. `python ops/keycloak_upgrade.py [--profile dev-lite]` |
| `keycloak/dev-overlay.json` → `realm-dxos-dev.json` | Người dùng dev (có `admin1`, `admin2` để duyệt bốn mắt) và client `dxos-test` (direct grant). **Chỉ dev-lite/test.** Sinh lại bằng `python ops/build_dev_realm.py` |
| `openbao/openbao.hcl` | OpenBao lưu tệp; khởi tạo và transit ở Plan 01 Task 15 |
| `clamav/clamd.p8.conf` | clamd cho hồ sơ p8 |
| `fake-av/` | Stub giao thức clamd **chỉ nhận EICAR**, DEV-ONLY |

Sửa phân vùng mạng: sửa `network-matrix.yaml` trước, rồi compose, rồi chạy `make test` (test tĩnh) và `make netcheck`.

Mọi image phải ghim `@sha256:` (`make pin-images`) và được ghi vào `LICENSES-THIRD-PARTY.md`.

**Đã chạy sống** hồ sơ dev-lite ngày 20/10/2026 (xem `docs/progress/2026-10-20-task4-kiem-tra-song.md`). Chưa chạy: hồ sơ p8/p16 với ClamAV thật (Task 7),
route `/admin/v1` trên host quản trị (cần realm `dxos`, Task 5).
