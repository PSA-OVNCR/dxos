# Plan 01 Task 4: kiểm tra trên stack sống

*Lập 20/10/2026. Trạng thái: **chờ chạy trên máy có Docker** (môi trường phát triển của trợ lý không kéo được image).*

Phần đã kiểm chứng (CI và máy phát triển): test tĩnh `tests/infra/test_compose_static.py` cho hồ sơ p16, p8 và dev-lite (ma trận mạng, chỉ Caddy publish cổng, cờ `internal`, AT-24, healthcheck, restart), test `fake-av`, test `netcheck` và `pin_images` với runner giả.

Phần **chưa** kiểm chứng (cần stack sống):

| # | Việc | Lệnh | Kết quả mong đợi | Kết quả thực tế |
|---|---|---|---|---|
| 1 | Ghim digest image | `make pin-images` (hoặc `python ops/pin_images.py`) | In bảng digest, không lỗi tag | |
| 2 | Dựng stack | `make up PROFILE=dev-lite` | Mọi container `healthy` sau ≤ 5 phút (`make ps`) | |
| 3 | AT-01 bản đầu | `make netcheck` | 30/30 probe PASS | |
| 4 | Test sống | `make test-infra` | 4 test đạt | |
| 5 | Keycloak sau Caddy | mở `https://localhost/auth/` | Trang chào Keycloak, URL giữ tiền tố `/auth` | |
| 6 | Console quản trị chỉ ở host admin | `https://localhost/auth/admin/` → 404; `https://admin.localhost/auth/admin/` → trang đăng nhập | | |

Điểm rủi ro cần để ý khi chạy:
- Tag image không tồn tại (đặc biệt `keycloak:26.3`, `apisix:3.12.0-debian`, `seaweedfs:3.80`, `openbao:2.2.0`): `pin-images` sẽ báo lỗi ngay ở tag đó.
- APISIX không nhận cú pháp `${{BIEN}}` trong `apisix.yaml`: log APISIX báo lỗi nạp route.
- Healthcheck Flowable dùng `bash /dev/tcp`: nếu image không có bash, container báo `unhealthy` (không chặn dịch vụ khác); spike Task 6 xử lý.
- OpenBao chưa khởi tạo: bình thường ở Task 4, healthcheck vẫn báo sống.
