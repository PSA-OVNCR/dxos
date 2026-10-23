-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 008_pii_redactions.sql: bản che của từng tệp gốc (Plan 04 Task 5, fix round 1; R18b). Thay cho cột
-- pii_scans.redacted_sha256 của 007: pii_scans chỉ-thêm, nên một lần dựng bản che lỗi sẽ để lại hàng
-- "không bao giờ có bản che" không sửa được. Bảng riêng cho phép dựng lại sau (việc pii_redact) mà không
-- động tới hàng pii_scans. Mỗi tệp gốc có tối đa một bản che; hàng chỉ-thêm (dxos_core chỉ SELECT, INSERT).
-- Hàng cũ của 007 được chép sang rồi cột bị bỏ (007 không bị sửa: migrate.py giữ sha256 của tệp đã áp dụng).

CREATE TABLE core.pii_redactions (
    sha256          core.sha256_hex PRIMARY KEY REFERENCES core.objects (sha256),
    redacted_sha256 core.sha256_hex NOT NULL REFERENCES core.objects (sha256),
    created_at      timestamptz     NOT NULL DEFAULT now(),
    CHECK (redacted_sha256 <> sha256)
);

INSERT INTO core.pii_redactions (sha256, redacted_sha256)
    SELECT sha256, redacted_sha256 FROM core.pii_scans WHERE redacted_sha256 IS NOT NULL;

ALTER TABLE core.pii_scans DROP COLUMN redacted_sha256;

GRANT SELECT, INSERT ON core.pii_redactions TO dxos_core;
