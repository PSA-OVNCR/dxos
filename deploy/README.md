# deploy/: hạ tầng Docker Compose

| Tệp | Vai trò |
|---|---|
| `compose.yaml` | Dịch vụ, **9 mạng** phân vùng (spec 6.2), healthcheck, volume |
| `compose.p16.yaml`, `compose.p8.yaml` | Hồ sơ tài nguyên (spec 16.1) |
| `compose.dev-lite.yaml` | Chỉ dùng khi phát triển: ClamAV → `fake-av` (nhãn `dxos.dev-only`) |
| `compose.test.yaml` | Dự án riêng `dxos-test` cho integration test: core-db, OpenBao (dev), fake-av, SeaweedFS; cổng chỉ trên 127.0.0.1 |
| `network-matrix.yaml` | **Nguồn sự thật** cho phân vùng mạng; test tĩnh và `ops/netcheck.py` đọc tệp này |
| `caddy/Caddyfile` | TLS, `/auth` → Keycloak, `/api` `/admin` `/verify` `/view` → APISIX, `/apps` tệp tĩnh; host quản trị giới hạn IP |
| `apisix/` | APISIX standalone (không Admin API, không etcd): route tĩnh, OIDC bearer, limit-req |
| `openbao/openbao.hcl` | OpenBao lưu tệp; khởi tạo và transit ở Plan 01 Task 15 |
| `clamav/clamd.p8.conf` | clamd cho hồ sơ p8 |
| `fake-av/` | Stub giao thức clamd **chỉ nhận EICAR**, DEV-ONLY |

Sửa phân vùng mạng: sửa `network-matrix.yaml` trước, rồi compose, rồi chạy `make test` (test tĩnh) và `make netcheck`.

Mọi image phải ghim `@sha256:` (`make pin-images`) và được ghi vào `LICENSES-THIRD-PARTY.md`.

**Đã chạy sống** hồ sơ dev-lite ngày 20/10/2026 (xem `docs/progress/2026-10-20-task4-kiem-tra-song.md`). Chưa chạy: hồ sơ p8/p16 với ClamAV thật (Task 7),
route `/admin/v1` trên host quản trị (cần realm `dxos`, Task 5).
