-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 006_pii_scans.sql: kết quả một lần dò PII trên một tệp đã CLEAN (Plan 04 Task 4, S1; I5, P4-D2).
-- Mỗi tệp (theo sha256) có tối đa một hàng. Hàng chỉ cho biết dò xong hay chưa và có bao nhiêu phát hiện;
-- KHÔNG chứa giá trị PII hay mã băm của nó. Các phát hiện nằm ở pii_findings (loại, trang, hộp).
--   DONE       dò xong (findings có thể bằng 0)
--   TOO_LARGE  quá 200 trang: không dò, coi như cần rà tay
--   FAILED     PDFium hoặc bộ dò lỗi trên tệp này: coi như cần rà tay
-- Chưa có hàng nghĩa là việc pii_detect chưa chạy xong; guard pii_reviewed chờ (pii_scan_pending).
-- dxos_core chỉ có SELECT, INSERT: một lần dò không bị sửa hay xóa sau khi ghi.

CREATE TABLE core.pii_scans (
    sha256     core.sha256_hex PRIMARY KEY REFERENCES core.objects (sha256),
    status     text        NOT NULL CHECK (status IN ('DONE', 'TOO_LARGE', 'FAILED')),
    findings   integer     NOT NULL CHECK (findings >= 0),
    detector   text        NOT NULL,
    scanned_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT ON core.pii_scans TO dxos_core;
