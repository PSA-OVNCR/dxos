# Task 9: ghi ledger — minh chứng chạy thật (20/10/2026)

Môi trường: phiên Claude trên cloud, Python 3.12.3, PostgreSQL 16.15 tại `127.0.0.1:55432` (thông số như `deploy/compose.test.yaml`).

## Đỏ trước khi cài đặt
```
$ python -m pytest core/tests/test_ledger.py core/tests/integration/test_ledger_log.py -q
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!   # chưa có dxos_core.ledger
```

## Xanh sau khi cài đặt
```
$ DXOS_TEST_REQUIRE_DB=1 python -m pytest core/tests/test_ledger.py core/tests/integration/test_ledger_log.py -q
16 passed, 1 warning in 2.32s

$ for i in $(seq 10); do pytest core/tests/integration/test_ledger_log.py -k concurrent -q; done   # RF4, 50 lượt ghi song song
10/10 lần: 1 passed

$ make check
All checks passed!
Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)
================ 108 passed, 64 deselected, 1 warning in 2.85s =================

$ DXOS_TEST_REQUIRE_DB=1 make test-integration
================ 47 passed, 125 deselected, 1 warning in 10.23s ================
```

## Đã kiểm
- 6 test của Plan 01 Task 9: `idx` bắt đầu từ 0 và tăng 1; loại sự kiện lạ bị từ chối; `actor_ref` là HMAC, không chứa `sub`;
  50 lượt ghi song song cho đúng `0..49` (RF4); `leaf_hash == leaf_hash(entry_bytes(e))`; sửa `subject` ở lá 3 (tắt trigger
  bằng owner) thì `verify_log` trả `first_bad_idx=3` (AT-15 phần DB).
- Bổ sung: `EVENT_TYPES` đúng 18 loại spec 12.4; `entry_bytes` đúng 7 trường; body không lưu trong DB, chỉ có `body_sha256`;
  `subject` lưu dạng NFC; `entries_bytes(upto=...)`; xóa một lá thì `verify_log` chỉ đúng chỗ hổng; ghi ledger trong transaction
  của bên gọi rồi rollback thì không để lại lá và chỉ số kế tiếp vẫn liên tục; body có số thực bị từ chối, không ghi gì.

## Giới hạn đã biết
`verify_log` chỉ bắt được việc sửa trường mà không tính lại `leaf_hash`, hoặc xóa dòng. Kẻ có quyền SQL tính lại được `leaf_hash`;
trường hợp đó được phát hiện bằng STH đã ký và đã neo (Task 15, 16; AT-15, AT-16).
