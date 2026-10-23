# ops/: script vận hành

- `vuot_rao.py`: bảng thử vượt rào, 10 kịch bản tấn công qua cổng thật bằng token dev, in bảng kết quả và 20 lá
  `policy.denied` gần nhất (`make vuot-rao`, Plan 03 Task 11, spec 9.1, H11). Chỉ chạy trên stack có realm dev (client
  `dxos-test`); mật khẩu dev qua biến `DXOS_E2E_PASSWORD`; khác `localhost` phải thêm `--allow-remote`. Mã thoát 0 mọi
  kịch bản bị chặn, 1 có kịch bản lọt, 2 lỗi cấu hình hoặc kết nối. Trên Windows cần `localhost` và `admin.localhost`
  phân giải về 127.0.0.1, và `--ca-file` trỏ tới CA nội bộ của Caddy (giống `ops/e2e/run_e2e.sh`). Đã chạy trên stack dev 22/10/2026: 10/10 (V28, `docs/progress/2026-10-22-web-live.md`)
- `netcheck.py`: kiểm ma trận kết nối mạng (AT-01), Plan 01 Task 4
- `measure.sh`: đo RAM theo container (AT-22), Plan 01 Task 7
- `deploy.sh`: `ops/deploy.sh <vX.Y.Z> [--profile p16|p8] [--repo-url URL] [--allow-unsigned]` triển khai theo tag trên VPS:
  fetch tag (không `--force`), **chỉ nhận tag đã ký SSH** (`verify-tag` với `deploy/allowed_signers`, thoát 2 nếu không), lấy
  digest image lõi từ Release (`trust-core-image-<X.Y.Z>.txt`), dựng SPA từ mã nguồn của tag, `compose up` với overlay phát
  hành, kiểm `/readyz` và `/verify/v1/keys`, ghi `deploy/deployments.log` (cột `result`, `signed`). Health hỏng thì tự quay
  lui về bản tốt gần nhất. Mã thoát: 0 đạt; 2 từ chối trước khi đổi gì; 3 thiếu điều kiện (digest, compose, fetch); 4 hỏng
  đã quay lui; 5 hỏng và không quay lui được. Xem `docs/runbook-deploy.md` (Plan 03 Task 12, Plan 04 Task 11, S4). Chạy
  thật là việc V29 và V42
- `backup.sh`, `restore.sh`, `at21_drill.sh` (và `backup_lib.sh`, chỉ để `source`): sao lưu mã hóa, khôi phục có chốt chặn, diễn tập
  AT-21 (Plan 04 Task 12, S4, P4-D9). `ops/backup.sh <thư mục ra>` ghi `dxos-backup-<UTC>.tar.enc` (`openssl enc -aes-256-cbc
  -pbkdf2 -iter 600000 -salt`, mật khẩu ở `.secrets/backup-passphrase`) và `.sha256`: `pg_dump -Fc` ba DB và tar hai volume
  (SeaweedFS, OpenBao) qua busybox ghim digest, chỉ đọc; thoát 0/2/3. `ops/restore.sh <gói> --project <tên>` kiểm sha256, giải
  mã và kiểm gói TRƯỚC khi gọi docker, chỉ tạo tài nguyên của project đó và **từ chối `--project dxos`** (thoát 2). `ops/at21_drill.sh`:
  sao lưu, khôi phục vào `dxos-restore`, dựng lõi ở `restore.localhost` (không dựng caddy nên không tranh cổng), mở khóa
  OpenBao, `dxos-witness verify-bundle` một niêm phong chọn trước rồi so `tree_size` và root. Xem `docs/runbook-backup.md`. Chạy
  thật là việc V43
- `seed_manifests.py`: nạp manifest thẳng vào DB, **chỉ dùng cho test lõi** (Plan 01 Task 17); cài app thật dùng
  `e2e/install_apps.sh` (CLI `dxos`, bốn mắt)
- `e2e/install_apps.sh`: cài App A/B bằng CLI `dxos`, người nộp và người duyệt khác nhau; `e2e/run_e2e.sh`: chạy E2E
  M1 + M2 trong container cạnh stack dev-lite (Plan 02 Task 15)
- `at13_reuse.sh`: minh chứng AT-13 trên VPS (cài App B trên image lõi đã phát hành, so digest/StartedAt/hash cấu
  hình gateway/commit trước và sau), ghi `docs/evidence/at13-reuse.txt` (Plan 02 Task 15)
- `openapi.py`: sinh `docs/api/openapi.json` từ ứng dụng FastAPI (`make openapi`), Plan 02 Task 15
- `build_dev_realm.py`: sinh `deploy/keycloak/realm-dxos-dev.json` = realm production + người dùng/client dev, Plan 01 Task 5
- `keycloak_upgrade.py`: đưa realm `dxos` đã có lên cấu hình hiện tại (client `dxos-cli`, `manage-realm` cho
  service account `dxos-installer`, admin events; dev-lite thêm `admin2`), idempotent, Plan 02 Task 11.
  Chạy sau khi kéo bản mới trên stack đã chạy từ trước: `python ops/keycloak_upgrade.py` (p8/p16) hoặc
  `python ops/keycloak_upgrade.py --profile dev-lite`. Mã thoát 2 = còn lệch phải xử lý tay (đã in ra).
