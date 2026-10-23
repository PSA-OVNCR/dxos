-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 009_pii_redaction_skips.sql: tệp không dựng được bản che vì kết quả vượt giới hạn dung lượng (Plan 04 Task 5,
-- fix round 2; R20). Đây là kết cục cố định, không phải lỗi tạm: việc pii_redact không thử lại và
-- enqueue_missing_scans (từ :pii-review) không xếp lại việc cho tệp có hàng ở đây. Bản gốc vẫn khóa theo
-- reveal_pii, danh sách tệp báo redacted=false. Chỉ-thêm (dxos_core chỉ SELECT, INSERT).

CREATE TABLE core.pii_redaction_skips (
    sha256     core.sha256_hex PRIMARY KEY REFERENCES core.objects (sha256),
    reason     text            NOT NULL CHECK (reason IN ('TOO_LARGE')),
    created_at timestamptz     NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON core.pii_redaction_skips TO dxos_core;
