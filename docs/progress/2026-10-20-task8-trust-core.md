# Task 8: khung trust-core và migration — minh chứng chạy thật (20/10/2026)

Môi trường: phiên Claude trên cloud, Python 3.12.3 (venv), PostgreSQL **16.15** của hệ thống chạy ở `127.0.0.1:55432`
(role `dxos_owner`, mật khẩu `changeme-test`, đúng thông số `deploy/compose.test.yaml`). Môi trường này không kéo được
image Docker nên không dùng `postgres:17-alpine`; CI (job `integration`) chạy với `postgres:17-alpine` đã ghim.

## Đỏ trước khi cài đặt
Tạm gỡ `core/src/dxos_core` và `001_core.sql`:
```
$ python -m pytest core -q
E   ModuleNotFoundError: No module named 'dxos_core'
```

## Xanh sau khi cài đặt
```
$ DXOS_TEST_REQUIRE_DB=1 python -m pytest core -q
57 passed, 1 warning in 5.59s

$ DXOS_TEST_REQUIRE_DB=1 make test-integration
================ 34 passed, 122 deselected, 1 warning in 5.81s =================

$ python -m pytest tests/infra/test_compose_static.py -q
25 passed in 0.79s

$ make check            # ruff + reuse lint + unit test toàn repo
All checks passed!
Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)
================ 105 passed, 51 deselected, 1 warning in 0.87s =================
```
Cảnh báo duy nhất: `StarletteDeprecationWarning` (TestClient của Starlette 1.9 khuyên dùng `httpx2`), không ảnh hưởng mã chạy thật.

Sau khi chạy, không còn database test nào sót lại (mỗi test tạo rồi `DROP DATABASE ... WITH (FORCE)`).

## Đã kiểm
- 7 test bắt buộc của Plan 01 Task 8: migration chạy lại không đổi gì; `dxos_core` UPDATE ledger → `InsufficientPrivilegeError`;
  owner UPDATE ledger → `ledger_append_only`; sửa `data` bản ghi đã niêm phong → `record_sealed`;
  `SEAL_PENDING → SEALED` được phép; `objects.sha256` sai định dạng → `CheckViolationError`; `/healthz` → `ok`.
- Bổ sung: DELETE/TRUNCATE ledger và `tree_heads` bị chặn (quyền + trigger); `idx` là `bigint` không sequence (D2);
  chuyển trạng thái niêm phong sai bị chặn, `REVOKED` là trạng thái cuối, không xóa được bản ghi đã niêm phong;
  `sha256`/`storage_key` của `objects` không đổi được; `dxos_core` không phải superuser, không tạo được bảng trong `core`,
  không xóa được `schema_migrations`; migration bị sửa sau khi áp dụng, tên tệp sai, DB mới hơn mã đều bị từ chối;
  migration lỗi được rollback và không ghi vết; `/readyz` trả 503 `application/problem+json` khi DB không tới được và
  200 `{"status":"ready","schema":"001_core.sql"}` khi đã migration; worker ghi heartbeat khi DB trả lời.
- `docker compose config` hợp lệ với p16, p8, dev-lite.

## Chưa kiểm (cần Docker Desktop hoặc VPS)
- Build `core/Dockerfile` và chạy `trust-core-api`, `trust-core-worker` trong stack (healthy, migration lúc khởi động,
  Docker secret từ biến môi trường `.env`).
- `make test-infra` / netcheck với image thật.
