---
layout: default
title: DX-OS Trust Core
---
<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# DX-OS Trust Core

Tầng 1 "headless" của hệ điều hành dữ liệu nguồn mở: SSO, gateway, dữ liệu có cấu trúc và phi cấu trúc, workflow,
kiểm dịch tệp, sổ cái Merkle có chữ ký và neo ra ngoài. Hai ứng dụng Tầng 2 dùng nó: **Phòng hồ sơ số** (chính) và
**Chứng nhận số** (nhỏ). Giấy phép Apache-2.0. Bài dự thi Olympic Tin học Sinh viên, Phần mềm nguồn mở 2026, đội PSA_OVNCR.

Mã nguồn: <https://github.com/PSA-OVNCR/dxos>. Trang này chỉ là mục lục; trạng thái cái gì đã chạy, cái gì chưa,
nằm ở README và `docs/progress/` trong kho.

## Bắt đầu

- Tổng quan, trạng thái và bắt đầu nhanh: [README](https://github.com/PSA-OVNCR/dxos/blob/main/README.md)
  ([bản tiếng Anh](https://github.com/PSA-OVNCR/dxos/blob/main/README_EN.md)).
- Kiến trúc trong vài phút đọc (ba tầng, mạng, luồng tải tệp, niêm phong và sổ cái, ranh giới tin cậy):
  [ARCHITECTURE.md](https://github.com/PSA-OVNCR/dxos/blob/main/ARCHITECTURE.md).
- Dựng, kiểm thử, phát hành: [BUILD.md](https://github.com/PSA-OVNCR/dxos/blob/main/BUILD.md).
- Đóng góp: [CONTRIBUTING.md](https://github.com/PSA-OVNCR/dxos/blob/main/CONTRIBUTING.md).

## Viết ứng dụng Tầng 2

- [Hướng dẫn viết một app trong 30 phút](tutorial-app-30-phut.md) (không sửa mã lõi).
- [Hướng dẫn manifest](manifest-guide.md).
- [Checklist cho người thử ngoài đội (AT-26)](at26-checklist.md).

## Vận hành

- [Triển khai lên VPS theo tag](runbook-deploy.md).
- [Mở khóa và quản lý OpenBao](runbook-openbao.md).
- [Sao lưu mã hóa, khôi phục, diễn tập AT-21](runbook-backup.md).
- [Neo sổ cái ra repo công khai và witness](runbook-anchor.md).
- [Xóa dữ liệu cá nhân](runbook-pii-erasure.md).
- [Năng lực và RAM theo hồ sơ](capacity.md).

## Nghiệm thu và pháp lý

- [Ma trận nghiệm thu AT-01..AT-28](acceptance.md).
- [Ánh xạ cơ chế với điều khoản pháp luật, những gì không đạt](legal-mapping.md): diễn giải kỹ thuật của đội, không phải tư vấn pháp lý.
