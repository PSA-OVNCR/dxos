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
