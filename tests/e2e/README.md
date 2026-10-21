# tests/e2e/: kiểm thử đầu-cuối

Chạy với token Keycloak thật trên stack đầy đủ (Caddy → APISIX → trust-core). Không có stack thì mọi test ở đây được
bỏ qua, trừ khi đặt `DXOS_E2E_REQUIRE=1` (khi đó báo lỗi); `ops/e2e/run_e2e.sh` đặt sẵn biến này.

| Tệp | Mốc | Nội dung |
|---|---|---|
| `test_m1_flow.py` | M1 (Plan 01 Task 17) | tải tệp → kiểm dịch → STH → neo → witness; IDOR; che PII; gateway |
| `test_m2_app_a.py` | M2 (Plan 02 Task 15) | App A: EICAR/PDF sạch, quy trình hai bước, AT-07, PII chưa rà → 409, niêm phong, `:check` (AT-05), gói + `verify-bundle --anchor-dir` (AT-17), `issuer.name` và tuyên bố khóa trong repo neo (AT-28), xóa CCCD (AT-27), thu hồi |
| `test_m2_app_b.py` | M2 | App B: 3 chứng nhận qua `records:bulk`, duyệt từng cái, cả 3 `SEALED`, đối soát không cần tệp, email không lộ; cũng là bước e2e của AT-13 |
| `test_m2_attacks.py` | M2 | task của app khác → 404, thiếu `If-Match` → 428, manifest nới chính sách sàn hoặc vượt namespace qua CLI (AT-11, AT-12), 40 request đồng thời + `X-Forwarded-For` giả → 429 (AT-19), OpenBao khóa trước task cuối → 503 (AT-20, chỉ chạy trên máy chủ có `docker`) |

Trước khi chạy bộ M2: cài App A, App B bằng CLI (`ops/e2e/install_apps.sh`, admin1 nộp, admin2 duyệt) và đặt
`DXOS_ORG_NAME` (không phải giá trị mẫu) ở cả `.env` của stack và môi trường chạy test. Người dùng dev cần có trong realm
(client `dxos-test`, kể cả `chuyen_vien_tp1` giữ cả vai trò chuyên viên lẫn trưởng phòng để thử AT-07).
