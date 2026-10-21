# Changelog

Mọi thay đổi đáng kể được ghi tại đây, theo định dạng [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/) và [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

## [0.1.0] - 2026-10-22
Mốc M1 (lõi Tier-0 phần 1). Tag gắn trên mã cuối Plan 01 (commit `5b14e7c`) cộng một commit chỉ ghi ngày phát hành.

### Lỗi đã biết (đã sửa ở 0.2.0)
- Danh sách IP của host quản trị trong Caddy (`@blocked`) không có hiệu lực; ở bản này host quản trị không giới hạn IP.
- E2E đầu-cuối của M1 (EICAR → cách ly, PDF sạch → kho, STH → neo → witness) chưa chạy trọn trên mã của bản này
  (4/5 test đạt trên Docker Desktop; test luồng chính bị Windows Defender chặn). Test này đạt trên mã 0.2.0 đang phát
  triển (commit `ea96323`, 22/10/2026).

### Added
- Khung kho mã: LICENSE (Apache-2.0), NOTICE, REUSE, CI (reuse, ruff, pytest, gitleaks), mẫu issue.
- Thư viện `dxos-proof`: JSON chuẩn hóa (NFC, UTC, cấm số thực) và cây Merkle RFC 6962 (inclusion proof, consistency proof).
- Khung thư mục cho `core/`, `witness/`, `cli/`, `sdk/js/`, `apps/`, `verify-portal/`, `viewer/`, `deploy/`, `ops/`.
- Hạ tầng `deploy/`: Docker Compose với 9 mạng phân vùng theo `network-matrix.yaml`, hồ sơ p16/p8/dev-lite, Caddy (TLS, host quản trị giới hạn IP), APISIX standalone (OIDC bearer, limit-req, request-id), stub `fake-av` chỉ cho dev-lite.
- `ops/netcheck.py` (kiểm ma trận mạng, AT-01) và `ops/pin_images.py` (ghim digest image).
- Realm Keycloak `dxos` (vai trò `dxos-admin`, client `dxos-spa` PKCE S256, `apisix`, `dxos-installer`, scope audience `dxos-api`) và bản dev có người dùng mẫu; `ops/build_dev_realm.py`.
- Khung `dxos-core` (FastAPI): cấu hình `DXOS_*`, lỗi `application/problem+json`, `/healthz` và `/readyz`, worker có heartbeat; migration `001_core.sql` (schema `core`, ledger và STH chỉ-thêm bằng quyền + trigger, trigger niêm phong bản ghi, role `dxos_core` quyền tối thiểu); image `core/Dockerfile` chạy user không phải root.
- Ledger chỉ-thêm (`dxos_core.ledger`): 18 loại sự kiện (spec 12.4), chỉ số liên tục dưới khóa advisory, `actor_ref` là HMAC của `sub`, không lưu body, `verify_log` phát hiện lá bị sửa hoặc bị xóa.
- Identity: kiểm token Keycloak (chỉ RS256, `iss`/`aud`/`exp`/`nbf`, JWKS có cache), vai trò `app:<id>:<role>`, `GET /api/v1/whoami`, lỗi 401/503 dạng problem+json.
- Registry: JSON Schema manifest `dxos/v1`, validator (FLOOR_WEAKENED, NAMESPACE_VIOLATION, UNKNOWN_GUARD, SCHEMA_INVALID), kho manifest; manifest App A, App B và `test-app`.
- PDP theo manifest (admin không mặc nhiên đọc dữ liệu app), che PII (CCCD, SĐT, STK, email, họ tên), ghi `policy.denied`.
- Records API chung: cấp số văn bản, `If-Match`, chống IDOR (404), chặn sửa bản ghi đã niêm phong, NFC, phân trang keyset, nhập hàng loạt theo dòng.
- Tệp: upload → quét ClamAV trước → kiểm PDF (PDFium) → kho theo SHA-256; cách ly tệp nhiễm; hàng đợi việc trên PostgreSQL; worker.
- STH ký ed25519 qua OpenBao transit; `GET /verify/v1/sth/latest`, `/verify/v1/sth/consistency`, `/verify/v1/keys`; `deploy/openbao/init.sh`, policy `dxos-core`, `docs/runbook-openbao.md`.
- Neo STH lên repo git có bảo vệ nhánh (job `anchor_sth`, bảng `anchors`), `POST /admin/v1/anchor:run`, `GET /admin/v1/ledger/status`; CLI `dxos-witness` và mẫu repo neo; `docs/runbook-anchor.md`.
- E2E mốc M1 (`tests/e2e`, `ops/e2e/run_e2e.sh`), `ops/seed_manifests.py` (tạm thời), workflow `release` (tar.gz, SBOM CycloneDX, wheel) và `nightly` (ClamAV thật).

### Changed
- Spec 1.0.2: `so_hieu` có `public: true`; `access.update` mặc định `[owner]`.
