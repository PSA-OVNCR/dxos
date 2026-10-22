<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Đo RAM hồ sơ p8 trên laptop trưởng nhóm (AT-22, phần laptop) — 22/10/2026

Hồ sơ p8 là hồ sơ dành cho laptop (spec 16.1, 16.4). Kết quả này **không** thay số đo trên VPS (V13 vẫn mở cho p16/VPS).

| Mục | Giá trị |
|---|---|
| Máy | Windows + Docker Desktop (máy ảo WSL2: 16 CPU, `docker info` MemTotal 16 341 225 472 byte; `free -m` trong máy ảo: 15 584 MiB) |
| Stack | `deploy/compose.yaml` + `compose.p8.yaml` + `compose.e2e.yaml`, commit `f577586`, ClamAV thật, `DXOS_OTS_CALENDARS` bật |
| Cách đo | `ops/measure.sh 900` trong container `python:3.12-slim` có docker CLI + procps (`docker stats` + `free -m` của máy ảo), mỗi 5 giây, 120 mẫu, 10:34–10:49 UTC |
| Tải trong lúc đo | E2E M1 + M2 (13 passed, 1 skipped), `bash ops/web_build_docker.sh` + `bash ops/web_live.sh` (10 passed) |
| Tổng hợp | `python ops/capacity_report.py measure-p8.csv` |

Kết quả (nguyên văn phần đỉnh):

| Container | Đỉnh RAM (MiB) |
|---|---:|
| (container dựng web/Playwright, không thuộc stack) | 1 033 |
| dxos-clamav-1 | 1 027 |
| dxos-keycloak-1 | 625 |
| dxos-apisix-1 | 422 |
| dxos-flowable-1 | 395 |
| dxos-seaweedfs-1 | 183 |
| dxos-trust-core-worker-1 | 116 |
| dxos-trust-core-api-1 | 100 |
| dxos-flowable-db-1 | 49 |
| dxos-core-db-1 | 47 |
| dxos-kc-db-1 | 28 |
| dxos-openbao-1 | 25 |
| dxos-caddy-1 | 23 |

- Tổng RAM container tại đỉnh (10:38:38Z, gồm cả container tạo tải): **4 049 MiB**.
- Đỉnh `free -m` used của máy ảo: **5 080 MiB**.
- So với máy 8 GB (8 192 MiB) mà p8 nhắm tới: **62%** (< 80%). Báo cáo của script so với RAM máy ảo 15 584 MiB nên in 33%.
- Kết luận cho laptop: đạt ngưỡng AT-22. Chưa đo được đỉnh khi ClamAV nạp lại chữ ký (p8 đặt `ConcurrentDatabaseReload no`).

Ghi chú: lần `docker compose up --wait --wait-timeout 900` sau khi đổi sang p8 báo `container dxos-clamav-1 is unhealthy`
(thoát 1) vì ClamAV tạo lại với cấu hình p8 nạp chữ ký chậm; vài phút sau ClamAV khỏe và E2E (có EICAR) đạt. Log ở
`E:\PMMNM 2026\_claude-run\m3-7-p8-ots.log` trên máy trưởng nhóm.
