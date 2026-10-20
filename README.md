# DX-OS Trust Core

**Nền tảng lõi headless (Tầng 1) cho mô hình DX-OS Open-Core**: ứng dụng cắm vào được cung cấp SSO, lưu trữ, workflow, đồng thời **bị bắt buộc tuân thủ** các chính sách tin cậy. Mọi kết quả quan trọng đều **kiểm chứng được độc lập**.

Dự án dự thi **Olympic Tin học Sinh viên Việt Nam – Phần mềm nguồn mở 2026**, chủ đề *DX-OS Open-Core*.

> English version: [README_EN.md](README_EN.md)

## Trạng thái
Đang phát triển. Mốc hiện tại: **M0 (nền móng)**. Xem `docs/superpowers/plans/`.

| Thành phần | Trạng thái |
|---|---|
| `libs/dxos-proof`: JSON chuẩn hóa + cây Merkle RFC 6962 | Đã có, kèm kiểm thử |
| `core/`: trust-core (Tầng 1) | Khung thư mục |
| `apps/phong-ho-so`, `apps/chung-nhan` (Tầng 2) | Khung thư mục |
| `deploy/`: hạ tầng Docker Compose | Khung thư mục |

## Kiến trúc tóm tắt
- **Tầng 1, DX-OS Trust Core:**
  - Dịch vụ nguồn mở chạy độc lập: Keycloak (SSO), Apache APISIX (gateway), PostgreSQL, SeaweedFS, Flowable, ClamAV, OpenBao.
  - Phần đội tự viết: `trust-core` (Records API, kiểm dịch tệp, PDP, ledger Merkle, niêm phong) và thư viện `dxos-proof`.
- **Tầng 2:** App A "Phòng hồ sơ số" và App B "Chứng nhận số". Cả hai được cài bằng manifest, **không sửa mã lõi**.
- **Thiết kế chi tiết:** [`docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`](docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md).

## Bắt đầu nhanh (phát triển)
```bash
make dev-install   # cài công cụ và gói Python ở chế độ editable
make check         # lint + kiểm tra giấy phép REUSE + test đơn vị
```
Hướng dẫn build đầy đủ: [BUILD.md](BUILD.md).

## Giấy phép
Mã nguồn của dự án phát hành theo **Giấy phép Apache 2.0** (xem [LICENSE](LICENSE)). Bạn được tự do sử dụng, sửa đổi và phân phối lại, kể cả cho mục đích thương mại, với điều kiện giữ nguyên thông báo bản quyền và giấy phép.

Mỗi tệp mã đều có header `SPDX-License-Identifier`; kiểm tra bằng `reuse lint`.

Các thành phần bên ngoài (Keycloak, APISIX, Flowable, PostgreSQL, SeaweedFS, ClamAV, OpenBao, Caddy…) chạy như dịch vụ độc lập, **không** được phân phối kèm trong kho mã này, và tuân theo giấy phép riêng của từng dự án. Danh sách: [LICENSES-THIRD-PARTY.md](LICENSES-THIRD-PARTY.md).

## Đóng góp và báo lỗi
- Báo lỗi và đề xuất tính năng: mục **Issues** của kho mã.
- Cách đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo lỗ hổng bảo mật: [SECURITY.md](SECURITY.md).
