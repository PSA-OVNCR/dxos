-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 007_pii_redacted.sql: nối tệp gốc với bản che của nó (Plan 04 Task 5, S1; P4-D5).
-- object_refs(role='redacted') chỉ nói bản ghi nào dùng bản che nào, không nói bản che của tệp gốc nào
-- (một bản ghi có thể có nhiều tệp). Cột này là liên kết đó: hàng pii_scans của tệp gốc trỏ tới object
-- bản che (ảnh đã tô đen, scanner_version 'dxos-redact/1'). NULL khi không có bản che: chưa dò, không có
-- phát hiện, TOO_LARGE, FAILED, hoặc dựng bản che lỗi. Chỉ có hàng DONE có phát hiện mới có bản che.
-- Cột được ghi cùng lúc với hàng (dxos_core chỉ có SELECT, INSERT), nên không bao giờ đổi sau đó.

ALTER TABLE core.pii_scans
    ADD COLUMN redacted_sha256 core.sha256_hex REFERENCES core.objects (sha256),
    ADD CONSTRAINT pii_scans_redacted_needs_findings
        CHECK (redacted_sha256 IS NULL OR (status = 'DONE' AND findings > 0));
