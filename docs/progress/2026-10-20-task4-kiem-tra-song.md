# Plan 01 Task 4: kiểm tra trên stack sống

*Lập 20/10/2026. Trạng thái: **đã chạy trên Docker Desktop (Windows, 16 CPU, 16 GB, Docker 28.4.0, Compose v2.39.2) hồ sơ dev-lite, 20/10/2026 17:40–17:45, commit `f07815e`**.*

Phần đã kiểm chứng (CI và máy phát triển): test tĩnh `tests/infra/test_compose_static.py` cho hồ sơ p16, p8 và dev-lite (ma trận mạng, chỉ Caddy publish cổng, cờ `internal`, AT-24, healthcheck, restart), test `fake-av`, test `netcheck` và `pin_images` với runner giả.

Phần kiểm chứng trên stack sống:

| # | Việc | Lệnh | Kết quả mong đợi | Kết quả thực tế |
|---|---|---|---|---|
| 1 | Ghim digest image | `docker buildx imagetools inspect` cho 10 image | 10 digest | **Đạt**: cả 10 tag tồn tại, digest ghi trong `LICENSES-THIRD-PARTY.md` |
| 2 | Dựng stack | compose dev-lite `up -d --build` | Mọi container `healthy` | **Đạt (lần 2)**: 13/13 healthy |
| 3 | AT-01 bản đầu | netcheck 30 probe (`docker run busybox nc -z`) | 30/30 PASS | **Đạt**: 30/30 PASS (cả 2 lần chạy) |
| 4 | AT-02 phía gateway | `GET /api/v1/healthz` không token | 401 | **Đạt**: 401, log APISIX "No bearer token found" |
| 5 | `/verify` ẩn danh | `GET /verify/v1/healthz` | không phải 401 | **Đạt**: 404 từ stub trust-core |
| 6 | Keycloak sau Caddy | discovery `master` | issuer và token_endpoint giữ `/auth` | **Đạt (lần 2)**: `https://localhost/auth/realms/master/...` |
| 7 | Console admin Keycloak trên host công khai | `GET /auth/admin/` | 404 | **Đạt**: 404 |

**Lỗi phát hiện ở lần 1 và đã sửa (commit `f07815e`):**
- Caddy cắt tiền tố `/auth` → Keycloak sinh `token_endpoint` thiếu `/auth`. Sửa: `KC_HTTP_RELATIVE_PATH=/auth`, Caddy giữ tiền tố.
- Image APISIX không có `curl`; image Flowable (Alpine) không có `bash` → healthcheck báo unhealthy dù dịch vụ chạy. Sửa: dùng `bash /dev/tcp` cho APISIX, `nc -z` cho Flowable. Có test tĩnh chặn tái phát.

**Ghi chú phương pháp:** bước 3–7 chạy bằng script PowerShell tương đương `ops/netcheck.py` và `tests/infra/test_network_live.py` (máy chạy thử chưa cài sẵn môi trường Python cho test). Lần chạy `make test-infra` bằng pytest sẽ làm khi có máy Linux/WSL hoặc VPS.

Điểm rủi ro đã xử lý hoặc còn mở:
- Tag image không tồn tại: **đã loại trừ** (10/10 tag có trên registry).
- APISIX nhận cú pháp `${{BIEN}}` trong `apisix.yaml`: **đạt** (route nạp được, `/api` trả 401 do openid-connect).
- Healthcheck Flowable: **đã sửa** sang `nc -z`.
- OpenBao chưa khởi tạo: bình thường ở Task 4, healthcheck vẫn báo sống. Khởi tạo ở Task 15.
- **Còn mở:** hồ sơ p8/p16 với ClamAV thật và đo RAM (Task 7); route `/admin/v1` trên host quản trị (cần realm `dxos`, Task 5).
