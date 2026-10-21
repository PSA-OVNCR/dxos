<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# E2E M1 + M2 trên Docker Desktop (máy trưởng nhóm) — 22/10/2026

Cấu hình đã chạy:

| Mục | Giá trị |
|---|---|
| Máy | Windows + Docker Desktop, 32 GB RAM; không phải VPS |
| Commit | `ea96323` |
| Hồ sơ compose | `-f deploy/compose.yaml -f deploy/compose.p16.yaml -f deploy/compose.e2e.yaml` (ClamAV thật; repo neo là bare repo cục bộ, không phải GitHub) |
| Container chạy test | `python:3.12-slim@sha256:a6e34c59…` chạy `ops/e2e/run_e2e.sh`, theo mục A của `docs/handoff/vps-checklist-plan02.md`. Mã nguồn được clone vào một Docker volume, không mount từ ổ Windows: Defender chặn tệp EICAR |

## Các bước

1. Chạy `docker compose … up -d --build --wait`. Kết quả: `readyz` → `{"status":"ready","schema":"004_harden_triggers.sql"}`.
2. Chạy `python ops/keycloak_upgrade.py --profile dev-lite` hai lần.
   - Lần 1 tạo `dxos-cli`, `chuyen_vien_tp1` và `admin2`, gán `manage-realm` cho `service-account-dxos-installer`, bật admin events.
   - Lần 2 in "không thay đổi gì".
3. Kiểm biến `DXOS_ANCHOR_REMOTE` của worker: giá trị là `file:///var/lib/dxos/anchor-remote.git`.
4. Chạy `pytest -m e2e tests/e2e`: **13 passed, 1 skipped**, mất 33,95 giây.

| Test | Kết quả |
|---|---|
| `test_m1_flow::test_m1_end_to_end`: EICAR → INFECTED, PDF sạch → CLEAN, STH → neo → `dxos-witness sync` | PASSED |
| `test_m1_flow`: IDOR và quyền tối thiểu của admin, che PII, gateway, `/admin` không lộ ra host công khai (4 test) | PASSED |
| `test_m2_app_a_end_to_end`: chặn ban hành khi chưa rà PII → niêm phong → trang công khai đã neo | PASSED |
| `test_m2_app_b_batch_certificates` | PASSED |
| `test_m2_attacks`: task của app khác → 404; thiếu `If-Match` → 428; CLI từ chối 3 manifest gian lận; giới hạn tần suất trang xác minh, kể cả khi giả `X-Forwarded-For` (6 test) | PASSED |
| `test_m2_attacks::test_openbao_sealed_before_last_task_is_503_and_flowable_untouched` (AT-20) | SKIPPED: cần `DXOS_E2E_BAO_TOKEN` và unseal key, trưởng nhóm tự nhập |

## Lỗi gặp khi chạy và cách sửa

- **`ops/keycloak_upgrade.py` vỡ trên Windows** với lỗi `UnicodeDecodeError: 'charmap'`.
  - Nguyên nhân: `subprocess` giải mã bằng cp1252, trong khi JSON của kcadm có tên tiếng Việt.
  - Sửa ở `ea96323`: đặt `encoding="utf-8"` và thêm test. Áp dụng tương tự cho `ops/pin_images.py`.
- **Lần chạy đầu không thêm `compose.e2e.yaml`.**
  - Hậu quả: worker không có `DXOS_ANCHOR_REMOTE` nên không neo, và 2 test chờ neo bị trượt.
  - Đây là lỗi của script chạy trên máy, không phải lỗi của mã nguồn.

## Chưa làm

- Chạy trên VPS p16 với Keycloak, Caddy và miền thật (V17 phần B).
- AT-19 và AT-20.
- Neo lên GitHub thật (AT-18).
