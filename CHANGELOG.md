# Changelog

Mọi thay đổi đáng kể được ghi tại đây, theo định dạng [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/) và [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]
- Chưa có thay đổi nào ngoài các mục bên dưới.

## [0.2.0] - Chưa phát hành
Mốc M2 (Tier-0 hoàn tất: workflow, niêm phong, đối soát, installer). Spec bản 1.0.3. Trưởng nhóm thay "Chưa phát hành"
bằng ngày khi gắn tag `v0.2.0`; workflow `release` từ chối mục chưa có ngày.

### Added
- Manifest 1.0.3: `policies.seal.revoke_roles`, `policies.pii.erase_roles`, `fields.<f>.label`, đánh số theo năm
  (`reset: yearly`, `{n:0W}`, `DXOS_TIMEZONE`), tham số guard; sự kiện ledger `workflow.started`, `workflow.completed`.
- Migration 003, 004: ý định và kết quả hoàn thành task, xác nhận rà PII, yêu cầu niêm phong theo ảnh chụp, tệp và
  deployment của app, khóa sửa/tải lên khi đang chạy quy trình; salt riêng của từng bản ghi (xóa được), bằng chứng xóa
  PII chỉ thêm, tuyên bố khóa.
- Bộ kiểm BPMN theo danh sách cho phép (cấm biểu thức, DTD, entity), lõi tự dựng lại BPMN trước khi deploy.
- Client REST Flowable; cầu nối quy trình: ghim phiên bản app, guard và khóa lạc quan trước Flowable, kiểm KMS trước
  task cuối (R-1), đối soát lần hoàn thành bị gián đoạn; danh mục guard chung; xác nhận rà PII (`:pii-review`).
- Niêm phong theo ảnh chụp (cam kết có salt, `SEAL_PENDING` và job thử lại, một niêm phong mỗi bản ghi), thu hồi theo
  mã lý do, `:erase-pii` (niêm phong vẫn `VALID`), tuyên bố khóa `dxos-key-statement/1` neo ở `keys/seal-key/v<n>.json`.
- API công khai `/verify/v1/seals/*`: xem niêm phong, `:check` chỉ nhận hash, gói bằng chứng ngoại tuyến;
  `dxos-witness verify-bundle` (AT-17); trang đối soát tối giản `verify-portal/minimal` (hash tính tại trình duyệt).
- Installer: nộp, diff quyền, duyệt bốn mắt (tạo realm role qua service account `dxos-installer`, deploy BPMN), vô
  hiệu hóa; `/admin/v1/health`, `/admin/v1/quarantine`; client Keycloak `dxos-cli` (device flow); `ops/keycloak_upgrade.py`.
- CLI quản trị `dxos` (wheel `dxos-cli`).
- App A "Phòng hồ sơ số" và App B "Chứng nhận số" bản 1.1.0 kèm BPMN; AT-14 quét toàn bộ mã lõi được phát hành.
- E2E mốc M2 (`tests/e2e/test_m2_*.py`), `ops/e2e/install_apps.sh` (cài app bằng CLI, bốn mắt), `ops/at13_reuse.sh`,
  overlay `deploy/compose.release.yaml` (image theo digest), image `trust-core` trên GHCR trong workflow `release`,
  `make openapi` và `docs/api/openapi.json`.
- Tài liệu: `docs/manifest-guide.md`, `docs/legal-mapping.md`, `docs/runbook-pii-erasure.md`; mục "Bản chất pháp lý
  của niêm phong" trong README.

### Changed
- `ops/e2e/run_e2e.sh` cài app bằng CLI thay cho `ops/seed_manifests.py`; `seed_manifests.py` chỉ còn dùng cho test lõi.
- Caddy: host công khai trả 404 cho `/admin`; danh sách IP của host quản trị được thực thi.
- `/admin/v1/ledger/status` chỉ còn trạng thái ledger; trạng thái thành phần chuyển sang `/admin/v1/health`.

### Chưa làm trong bản này
- E2E M2, AT-13, AT-18, AT-19, AT-20 trên stack thật và VPS: chờ chạy (danh sách việc ở `docs/evidence/README.md`).

## [0.1.0] - 2026-10-22
Mốc M1. Tag `v0.1.0` gắn trên mã cuối Plan 01 (commit `5b14e7c`) cộng commit `7247fe8` chỉ ghi ngày phát hành; không
nằm trên nhánh `main` (mã M2 đã vào `main` trước khi gắn tag).

### Lỗi đã biết (đã sửa ở 0.2.0)
- Danh sách IP của host quản trị trong Caddy (`@blocked`) không có hiệu lực; ở bản này host quản trị không giới hạn IP.
- E2E đầu-cuối của M1 chưa chạy trọn trên mã của bản này (4/5 trên Docker Desktop); đạt trên mã 0.2.0 đang phát triển
  (commit `ea96323`, 22/10/2026).

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
