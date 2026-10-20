# Thành phần bên thứ ba

Bảng kê giấy phép và nguồn gốc mọi mô-đun bên ngoài. Cập nhật **trong cùng commit** khi thêm phụ thuộc.

**Cột "Cách dùng":**
- **Dịch vụ độc lập:** chạy riêng, không nhúng mã, không phân phối kèm kho này.
- **Thư viện:** được import bởi mã của dự án.
- **Công cụ:** chỉ dùng khi phát triển hoặc CI, không phân phối.

**Cột "Đã kiểm chứng":**
- **Chưa:** giấy phép ghi theo hiểu biết, phải kiểm tra tệp LICENSE gốc trước khi phát hành.
- **Có (ngày):** đã đối chiếu.

## Thư viện và công cụ đang dùng
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| Python (thư viện chuẩn) | ≥ 3.12 | PSF-2.0 | Runtime | Chưa |
| pytest | ≥ 8 | MIT | Công cụ (test) | Chưa |
| pytest-asyncio | ≥ 0.23 | Apache-2.0 | Công cụ (test) | Chưa |
| respx | ≥ 0.21 | BSD-3-Clause | Công cụ (test) | Chưa |
| ruff | ≥ 0.6 | MIT | Công cụ (lint) | Chưa |
| reuse | ≥ 4 | GPL-3.0-or-later | Công cụ (kiểm tra giấy phép, không phân phối) | Chưa |
| PyYAML | ≥ 6 | MIT | Công cụ (test) | Chưa |
| httpx | ≥ 0.27 | BSD-3-Clause | Công cụ (test) | Chưa |
| gitleaks (image Docker) | v8.18.4 | MIT | Công cụ (CI) | Chưa |

## Dịch vụ (image Docker, chạy độc lập, không nhúng mã)
Digest được ghim trong `deploy/` bằng `make pin-images`; cột "Digest" cập nhật cùng commit ghim.

| Thành phần | Image | Giấy phép | Cách dùng | Digest | Đã kiểm chứng |
|---|---|---|---|---|---|
| Caddy | `caddy:2.10` | Apache-2.0 | Dịch vụ độc lập | *(chưa ghim)* | Chưa |
| Apache APISIX | `apache/apisix:3.12.0-debian` | Apache-2.0 | Dịch vụ độc lập | *(chưa ghim)* | Chưa |
| Keycloak | `quay.io/keycloak/keycloak:26.3` | Apache-2.0 | Dịch vụ độc lập | *(chưa ghim)* | Chưa |
| Flowable REST | `flowable/flowable-rest:7.1.0` | Apache-2.0 | Dịch vụ độc lập (spike Task 6 xác nhận image OSS) | *(chưa ghim)* | Chưa |
| PostgreSQL | `postgres:17-alpine` | PostgreSQL | Dịch vụ độc lập (core-db, kc-db, flowable-db) | *(chưa ghim)* | Chưa |
| SeaweedFS | `chrislusf/seaweedfs:3.80` | Apache-2.0 | Dịch vụ độc lập | *(chưa ghim)* | Chưa |
| ClamAV | `clamav/clamav:1.4` | GPL-2.0-only | Dịch vụ độc lập, nói chuyện qua socket clamd (G2) | *(chưa ghim)* | Chưa |
| OpenBao | `openbao/openbao:2.2.0` | MPL-2.0 | Dịch vụ độc lập | *(chưa ghim)* | Chưa |
| BusyBox | `busybox:1.37` | GPL-2.0-only | Công cụ (probe mạng, AT-01) | *(chưa ghim)* | Chưa |
| Python | `python:3.12-slim` | PSF-2.0 (+ Debian) | Image nền: stub trust-core, `fake-av` | *(chưa ghim)* | Chưa |
