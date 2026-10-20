# core/: DX-OS Trust Core (Tầng 1)

Gói Python `dxos-core` (FastAPI). Chạy thành 2 tiến trình: `trust-core-api` và `trust-core-worker`. Headless, **không chứa logic nghiệp vụ của ứng dụng nào** (bất biến I3).

## Bản đồ mô-đun (`src/dxos_core/`)
| Mô-đun | Trách nhiệm | Plan 01 |
|---|---|---|
| `settings.py`, `app.py`, `errors.py`, `db/` | Cấu hình, khởi tạo FastAPI, lỗi RFC 7807, migration | Task 8 |
| `identity/` | Kiểm tra JWT (RS256, `aud=dxos-api`), vai trò `app:<id>:<role>` | Task 10 |
| `registry/` | Schema manifest, validator (namespace, chính sách sàn, danh mục guard), kho manifest | Task 11 |
| `policy/` | PDP (quyết định quyền), che trường PII | Task 12 |
| `records/` | Records API chung sinh từ manifest | Task 13 |
| `objects/`, `jobs/`, `worker.py` | Upload → kiểm dịch ClamAV → kiểm PDF → lưu theo SHA-256 | Task 14 |
| `ledger/` | Nhật ký chỉ-thêm, cây Merkle, STH ký, neo, endpoint xác minh | Task 9, 15, 16 |
| `kms/` | Ký qua OpenBao transit (ed25519) | Task 15 |
| `workflow/`, `seal/` | Workflow bridge + guard; niêm phong và đối soát | Plan 02 |

`migrations/` chứa các tệp SQL `NNN_*.sql`. `tests/` gồm unit test và integration test (marker `integration`).

## Chạy và kiểm thử
```bash
make dev-install                    # cài dxos-proof và dxos-core ở chế độ editable
make test                           # unit test (không cần DB)
make test-db-up && make test-integration   # integration test với PostgreSQL thật
```
- API: `uvicorn --factory dxos_core.app:create_app` (cấu hình bằng biến `DXOS_*`, xem `settings.py`). `GET /healthz` báo tiến trình sống; `GET /readyz` báo DB kết nối được và đã có migration.
- Worker: `python -m dxos_core.worker`; healthcheck `python -m dxos_core.worker --check`.
- Migration: `DXOS_MIGRATE_DATABASE_URL=<DSN dxos_owner> python -m dxos_core.db.migrate`. Container `trust-core-api` tự chạy bước này khi khởi động (`docker/api-entrypoint.sh`).
- Lỗi HTTP luôn ở dạng `application/problem+json` (RFC 9457), `type` = `https://dxos.dev/problems/<slug>`.

## Cơ sở dữ liệu (`migrations/001_core.sql`)
- Mọi bảng nằm trong schema `core`. Role `dxos_owner` sở hữu bảng và chạy migration; role `dxos_core` là role ứng dụng.
- `ledger_entries`, `tree_heads`: `dxos_core` chỉ có `SELECT, INSERT`; trigger `ledger_append_only` chặn `UPDATE/DELETE/TRUNCATE` kể cả với owner.
- `records`: trigger `record_seal_guard` chặn sửa `data` và xóa khi `seal_state ≠ NONE`; chỉ cho chuyển `NONE→SEAL_PENDING→SEALED→REVOKED` và `NONE→SEALED`.
- `objects`: `sha256` và `storage_key` không đổi được (quyền theo cột + trigger `object_identity_guard`).
- Tệp migration đã phát hành **không được sửa**: `apply_migrations` so sha256 và dừng nếu khác. Thay đổi schema thì thêm `002_*.sql`.
