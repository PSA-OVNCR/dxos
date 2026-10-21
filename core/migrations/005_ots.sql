-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 005_ots.sql: biên nhận OpenTimestamps cho STH đã neo (Plan 03 Task 14, P3-D10; Đ2, mặc định tắt).
-- Mỗi hàng là phản hồi nguyên văn của một calendar cho digest SHA-256(canonical(STH)). Tệp ots/<n>.ots trong repo
-- neo được dựng lại tất định từ các hàng này. Chỉ-thêm như anchors: trigger chặn UPDATE/DELETE/TRUNCATE với
-- mọi role; dxos_core chỉ có SELECT, INSERT.

CREATE TABLE core.ots_receipts (
    tree_size  bigint      NOT NULL REFERENCES core.tree_heads (tree_size),
    calendar   text        NOT NULL CHECK (calendar ~ '^https://[^\s,]+$'),
    reply      bytea       NOT NULL CHECK (octet_length(reply) BETWEEN 1 AND 10000),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tree_size, calendar)
);

CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON core.ots_receipts
    FOR EACH ROW EXECUTE FUNCTION core.ledger_append_only();
CREATE TRIGGER ledger_append_only_truncate BEFORE TRUNCATE ON core.ots_receipts
    FOR EACH STATEMENT EXECUTE FUNCTION core.ledger_append_only();

GRANT SELECT, INSERT ON core.ots_receipts TO dxos_core;
