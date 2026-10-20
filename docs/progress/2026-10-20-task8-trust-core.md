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

## Chạy sống trên Docker Desktop của trưởng nhóm (20/10/2026 22:50, commit `ee72b95`)
Script `chay-task8.bat` (PowerShell, hồ sơ dev-lite, `up -d --build`). Trích `task8.log`:
```
api=healthy worker=healthy after ~10s          # cả 13 container running|healthy
trust-core-api-1 | migration: đã áp dụng ['001_core.sql']
trust-core-api-1 | migration: đã đặt mật khẩu role dxos_core
trust-core-api-1 | "GET /readyz HTTP/1.1" 200 OK
uid: 10001                     worker uid: 10001          # không chạy bằng root
readyz: {"status":"ready","schema":"001_core.sql"}
secrets: actor-hmac-key,openbao-core-token,s3-access-key,s3-secret-key
owner DSN in PID1 env (expect 0): 0                       # uvicorn không còn DSN dxos_owner
PID1 cmd: /usr/local/bin/python3.12 /usr/local/bin/uvicorn --factory dxos_core.app:create_app ...
core.schema_migrations: 001_core.sql ; 12 tables in core
dxos_core: UPDATE ledger_entries -> ERROR: permission denied for table ledger_entries
no token -> 401
valid token /api/v1/healthz -> {"type":"https://dxos.dev/problems/not-found","title":"Not Found","status":404}
                               http=404 ct=application/problem+json   # token thật đi qua Caddy + APISIX tới trust-core
restart trust-core-api -> healthy, /readyz 200 (migration chạy lại không lỗi)
```
- Docker secret lấy từ biến trong `.env` hoạt động trên Docker Desktop (Compose v2.39).
- `dxos_owner` UPDATE ledger trả `UPDATE 0` vì ledger còn rỗng (trigger theo dòng không chạy khi không có dòng).
  Trường hợp có dòng đã được integration test kiểm (`test_owner_update_blocked_by_trigger`).

## Chưa kiểm
- Chạy trên VPS (hồ sơ p16 với ClamAV thật): chờ có VPS.
- `make test-infra` bằng pytest trên Linux/WSL.
