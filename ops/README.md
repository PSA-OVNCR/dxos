# ops/: script vận hành

- `vuot_rao.py`: bảng thử vượt rào, 10 kịch bản tấn công qua cổng thật bằng token dev, in bảng kết quả và 20 lá
  `policy.denied` gần nhất (`make vuot-rao`, Plan 03 Task 11, spec 9.1, H11). Chỉ chạy trên stack có realm dev (client
  `dxos-test`); mật khẩu dev qua biến `DXOS_E2E_PASSWORD`; khác `localhost` phải thêm `--allow-remote`. Mã thoát 0 mọi
  kịch bản bị chặn, 1 có kịch bản lọt, 2 lỗi cấu hình hoặc kết nối. Trên Windows cần `localhost` và `admin.localhost`
  phân giải về 127.0.0.1, và `--ca-file` trỏ tới CA nội bộ của Caddy (giống `ops/e2e/run_e2e.sh`). Chạy thật là việc V28
- `netcheck.py`: kiểm ma trận kết nối mạng (AT-01), Plan 01 Task 4
- `measure.sh`: đo RAM theo container (AT-22), Plan 01 Task 7
- `deploy.sh`: triển khai theo tag, Plan 03 (S9.2)
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
