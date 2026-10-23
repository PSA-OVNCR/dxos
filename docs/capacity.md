<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Năng lực và RAM theo hồ sơ triển khai

Trang này gom số đo RAM theo hồ sơ (spec 16.1, 16.4; tiêu chí AT-22: đỉnh RAM dưới ngưỡng quy định cho hồ sơ p8). **Quy tắc: không có số nào mà không có
nguồn đo.** Cột `Nguồn đo` trỏ tới bản ghi đo trong `docs/progress/`; chưa đo thì ghi "chưa đo" kèm mã việc, không ước lượng.

| Hồ sơ | Máy đo | Đỉnh RAM tổng các container | Đỉnh RAM `free -m` của máy ảo | So với 8 GB (8 192 MiB) | Nguồn đo |
|---|---|---|---|---|---|
| p8 | Laptop Windows + Docker Desktop (WSL2), 22/10/2026 | 4 049 MiB (gồm cả container dựng web tạo tải, 1 033 MiB) | 5 080 MiB | 62% | `docs/progress/2026-10-22-p8-ram-laptop.md` |
| p16 | — | chưa đo (V13) | chưa đo (V13) | chưa đo (V13) | — (cần VPS, việc V13 ở `docs/progress/2026-10-21-tong-ket-tien-do.md`) |

Đọc bảng:
- Hàng p8 là số đo **trên laptop của trưởng nhóm**, không phải VPS; số này không thay số đo trên VPS (`docs/progress/2026-10-22-p8-ram-laptop.md`).
- Hàng p8 đạt ngưỡng AT-22 trên laptop (62%, dưới ngưỡng 80% của máy 8 GB), theo `docs/progress/2026-10-22-p8-ram-laptop.md`. Chưa đo đỉnh khi ClamAV nạp lại chữ ký (cùng nguồn).
- Hàng p16 chưa có số. Khi có VPS, chạy `ops/measure.sh` rồi `python ops/capacity_report.py` (xem [BUILD.md](https://github.com/PSA-OVNCR/dxos/blob/main/BUILD.md)) và ghi kết quả vào một bản ghi mới trong `docs/progress/`, sau đó thay hàng này.
