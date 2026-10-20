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

## Dịch vụ dự kiến (thêm khi đưa vào `deploy/`, kèm digest image)
Keycloak, Apache APISIX, Flowable, PostgreSQL, SeaweedFS, ClamAV, OpenBao, Caddy. Xem spec mục 17.1.
