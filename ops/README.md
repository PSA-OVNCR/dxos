# ops/: script vận hành

- `netcheck.py`: kiểm ma trận kết nối mạng (AT-01), Plan 01 Task 4
- `measure.sh`: đo RAM theo container (AT-22), Plan 01 Task 7
- `deploy.sh`: triển khai theo tag, Plan 03 (S9.2)
- `seed_manifests.py`: nạp manifest tạm thời trước khi có installer, Plan 01 Task 17
- `build_dev_realm.py`: sinh `deploy/keycloak/realm-dxos-dev.json` = realm production + người dùng/client dev, Plan 01 Task 5
- `keycloak_upgrade.py`: đưa realm `dxos` đã có lên cấu hình hiện tại (client `dxos-cli`, `manage-realm` cho
  service account `dxos-installer`, admin events; dev-lite thêm `admin2`), idempotent, Plan 02 Task 11.
  Chạy sau khi kéo bản mới trên stack đã chạy từ trước: `python ops/keycloak_upgrade.py` (p8/p16) hoặc
  `python ops/keycloak_upgrade.py --profile dev-lite`. Mã thoát 2 = còn lệch phải xử lý tay (đã in ra).
