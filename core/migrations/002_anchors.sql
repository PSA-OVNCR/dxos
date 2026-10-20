-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 002_anchors.sql: nơi ghi commit neo của từng STH (Plan 01 Task 16).
-- Tách khỏi tree_heads (chỉ-thêm) để không bao giờ phải UPDATE tree_heads (ruling Task 8).

CREATE TABLE anchors (
    tree_size   bigint      NOT NULL REFERENCES tree_heads (tree_size),
    repo        text        NOT NULL,
    commit_sha  text        NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    anchored_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tree_size, repo)
);

CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON anchors
    FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_append_only_truncate BEFORE TRUNCATE ON anchors
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_append_only();

GRANT SELECT, INSERT ON anchors TO dxos_core;
