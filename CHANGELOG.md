# Changelog

Mọi thay đổi đáng kể được ghi tại đây, theo định dạng [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/) và [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]
### Added
- Khung kho mã: LICENSE (Apache-2.0), NOTICE, REUSE, CI (reuse, ruff, pytest, gitleaks), mẫu issue.
- Thư viện `dxos-proof`: JSON chuẩn hóa (NFC, UTC, cấm số thực) và cây Merkle RFC 6962 (inclusion proof, consistency proof).
- Khung thư mục cho `core/`, `witness/`, `cli/`, `sdk/js/`, `apps/`, `verify-portal/`, `viewer/`, `deploy/`, `ops/`.
- Hạ tầng `deploy/`: Docker Compose với 9 mạng phân vùng theo `network-matrix.yaml`, hồ sơ p16/p8/dev-lite, Caddy (TLS, host quản trị giới hạn IP), APISIX standalone (OIDC bearer, limit-req, request-id), stub `fake-av` chỉ cho dev-lite.
- `ops/netcheck.py` (kiểm ma trận mạng, AT-01) và `ops/pin_images.py` (ghim digest image).
- Realm Keycloak `dxos` (vai trò `dxos-admin`, client `dxos-spa` PKCE S256, `apisix`, `dxos-installer`, scope audience `dxos-api`) và bản dev có người dùng mẫu; `ops/build_dev_realm.py`.
- Khung `dxos-core` (FastAPI): cấu hình `DXOS_*`, lỗi `application/problem+json`, `/healthz` và `/readyz`, worker có heartbeat; migration `001_core.sql` (schema `core`, ledger và STH chỉ-thêm bằng quyền + trigger, trigger niêm phong bản ghi, role `dxos_core` quyền tối thiểu); image `core/Dockerfile` chạy user không phải root.
