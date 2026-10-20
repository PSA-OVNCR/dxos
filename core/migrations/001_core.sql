-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 001_core.sql: schema `core` của DX-OS Trust Core (spec 10.1, Plan 01 Task 8).
-- Chạy bởi role dxos_owner qua `python -m dxos_core.db.migrate`, trong MỘT transaction,
-- với search_path = core, public. KHÔNG sửa tệp này sau khi đã phát hành: tạo 002_*.sql.
--
-- Hai role:
--   dxos_owner  sở hữu schema và bảng, chạy migration.
--   dxos_core   role ứng dụng (api + worker): quyền tối thiểu; KHÔNG UPDATE/DELETE ledger.

-- ---------------------------------------------------------------- role, schema
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dxos_core') THEN
        CREATE ROLE dxos_core LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

REVOKE ALL ON SCHEMA core FROM PUBLIC;
GRANT USAGE ON SCHEMA core TO dxos_core;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO dxos_core', current_database());
    EXECUTE format('ALTER DATABASE %I SET search_path = core, public', current_database());
END
$$;

-- ---------------------------------------------------------------- kiểu dùng chung
CREATE DOMAIN sha256_hex AS text CHECK (VALUE ~ '^[0-9a-f]{64}$');
CREATE DOMAIN app_slug   AS text CHECK (VALUE ~ '^[a-z][a-z0-9-]{1,62}$');
-- Thời điểm dạng chuỗi RFC 3339 UTC (đúng chuỗi đưa vào canonical JSON của lá Merkle).
CREATE DOMAIN rfc3339_utc AS text CHECK (VALUE ~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$');

-- ---------------------------------------------------------------- ứng dụng Tầng 2
CREATE TABLE apps (
    id              app_slug    NOT NULL,
    version         text        NOT NULL,
    manifest        jsonb       NOT NULL,
    manifest_sha256 sha256_hex  NOT NULL,
    status          text        NOT NULL DEFAULT 'PENDING'
                                CHECK (status IN ('PENDING', 'ACTIVE', 'DISABLED')),
    submitted_by    text,
    approved_by     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, version)
);
-- Mỗi app có tối đa một phiên bản ACTIVE.
CREATE UNIQUE INDEX apps_one_active ON apps (id) WHERE status = 'ACTIVE';

-- ---------------------------------------------------------------- bản ghi
CREATE TABLE records (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id         app_slug    NOT NULL,
    collection     text        NOT NULL CHECK (collection ~ '^[a-z][a-z0-9_]{0,62}$'),
    data           jsonb       NOT NULL DEFAULT '{}'::jsonb,
    owner_sub      text        NOT NULL,
    wf_instance_id text,
    wf_state       text,
    seal_state     text        NOT NULL DEFAULT 'NONE'
                               CHECK (seal_state IN ('NONE', 'SEAL_PENDING', 'SEALED', 'REVOKED')),
    version        integer     NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX records_app_collection ON records (app_id, collection);

-- Niêm phong: khi seal_state <> NONE thì `data` không đổi được và bản ghi không xóa được.
-- Chuyển trạng thái hợp lệ: NONE→SEAL_PENDING→SEALED→REVOKED và NONE→SEALED (spec 10.3).
CREATE FUNCTION record_seal_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.seal_state <> 'NONE' THEN
            RAISE EXCEPTION 'record_sealed' USING DETAIL = format('record %s is %s', OLD.id, OLD.seal_state);
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.seal_state <> 'NONE' AND NEW.data IS DISTINCT FROM OLD.data THEN
        RAISE EXCEPTION 'record_sealed' USING DETAIL = format('record %s is %s', OLD.id, OLD.seal_state);
    END IF;
    IF NEW.seal_state IS DISTINCT FROM OLD.seal_state AND NOT (
           (OLD.seal_state = 'NONE'         AND NEW.seal_state IN ('SEAL_PENDING', 'SEALED'))
        OR (OLD.seal_state = 'SEAL_PENDING' AND NEW.seal_state = 'SEALED')
        OR (OLD.seal_state = 'SEALED'       AND NEW.seal_state = 'REVOKED')
    ) THEN
        RAISE EXCEPTION 'record_seal_transition'
            USING DETAIL = format('%s -> %s is not allowed', OLD.seal_state, NEW.seal_state);
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER record_seal_guard BEFORE UPDATE OR DELETE ON records
    FOR EACH ROW EXECUTE FUNCTION record_seal_guard();

-- Cấp số văn bản theo app.
CREATE TABLE sequences (
    app_id app_slug NOT NULL,
    name   text     NOT NULL,
    value  bigint   NOT NULL DEFAULT 0 CHECK (value >= 0),
    PRIMARY KEY (app_id, name)
);

-- ---------------------------------------------------------------- tệp
-- Tên tệp gốc chỉ lưu dạng hash (spec 10.1).
CREATE TABLE uploads (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id          uuid        NOT NULL REFERENCES records (id),
    staging_key        text        NOT NULL,
    original_name_hash sha256_hex  NOT NULL,
    size               bigint      NOT NULL CHECK (size >= 0),
    declared_type      text,
    status             text        NOT NULL DEFAULT 'STAGING'
                                   CHECK (status IN ('STAGING', 'CLEAN', 'INFECTED', 'REJECTED')),
    sha256             sha256_hex,
    reason             text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX uploads_record ON uploads (record_id);

-- Kho theo nội dung (CAS): khóa là sha256; sha256 và storage_key không bao giờ đổi.
CREATE TABLE objects (
    sha256          sha256_hex  PRIMARY KEY,
    size            bigint      NOT NULL CHECK (size >= 0),
    mime_sniffed    text        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('CLEAN', 'INFECTED', 'REJECTED')),
    scanner_version text,
    scanned_at      timestamptz,
    storage_key     text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION object_identity_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.sha256 IS DISTINCT FROM OLD.sha256 OR NEW.storage_key IS DISTINCT FROM OLD.storage_key THEN
        RAISE EXCEPTION 'object_immutable' USING DETAIL = 'sha256 and storage_key never change';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER object_identity_guard BEFORE UPDATE ON objects
    FOR EACH ROW EXECUTE FUNCTION object_identity_guard();

CREATE TABLE object_refs (
    record_id uuid       NOT NULL REFERENCES records (id),
    sha256    sha256_hex NOT NULL REFERENCES objects (sha256),
    role      text       NOT NULL CHECK (role IN ('original', 'redacted')),
    PRIMARY KEY (record_id, sha256, role)
);
CREATE INDEX object_refs_sha256 ON object_refs (sha256);

-- SHOULD: kết quả phát hiện PII; không lưu giá trị rõ.
CREATE TABLE pii_findings (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sha256      sha256_hex  NOT NULL REFERENCES objects (sha256),
    type        text        NOT NULL,
    page        integer     CHECK (page >= 0),
    bbox        jsonb,
    value_hmac  text,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pii_findings_sha256 ON pii_findings (sha256);

-- ---------------------------------------------------------------- niêm phong
-- seal_id: 128 bit ngẫu nhiên, base32 không padding (26 ký tự).
CREATE TABLE seals (
    seal_id     text        PRIMARY KEY CHECK (seal_id ~ '^[A-Z2-7]{26}$'),
    app_id      app_slug    NOT NULL,
    record_id   uuid        NOT NULL REFERENCES records (id),
    payload     jsonb       NOT NULL,
    signature   text        NOT NULL,
    key_version integer     NOT NULL CHECK (key_version >= 1),
    leaf_index  bigint      CHECK (leaf_index >= 0),
    status      text        NOT NULL DEFAULT 'VALID' CHECK (status IN ('VALID', 'REVOKED')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz
);
CREATE INDEX seals_record ON seals (record_id);

-- ---------------------------------------------------------------- ledger (chỉ-thêm)
-- idx do lõi cấp liên tục dưới pg_advisory_xact_lock (D2): bigint thường, KHÔNG bigserial.
-- Không lưu body; chỉ lưu body_sha256. actor_ref là HMAC của `sub`.
CREATE TABLE ledger_entries (
    idx         bigint      PRIMARY KEY CHECK (idx >= 0),
    ts          rfc3339_utc NOT NULL,
    app_id      app_slug,
    actor_ref   text,
    type        text        NOT NULL,
    subject     text        NOT NULL,
    body_sha256 sha256_hex  NOT NULL,
    leaf_hash   bytea       NOT NULL CHECK (length(leaf_hash) = 32)
);

-- STH: chỉ-thêm. Commit neo (Task 16) ghi ở bảng riêng, chỉ-thêm, để không phải UPDATE bảng này.
CREATE TABLE tree_heads (
    tree_size   bigint      PRIMARY KEY CHECK (tree_size >= 0),
    root_hash   sha256_hex  NOT NULL,
    ts          rfc3339_utc NOT NULL,
    key_version integer     NOT NULL CHECK (key_version >= 1),
    signature   text        NOT NULL
);

CREATE FUNCTION ledger_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ledger_append_only' USING DETAIL = format('%s on %s is forbidden', TG_OP, TG_TABLE_NAME);
END
$$;
CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_append_only_truncate BEFORE TRUNCATE ON ledger_entries
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON tree_heads
    FOR EACH ROW EXECUTE FUNCTION ledger_append_only();
CREATE TRIGGER ledger_append_only_truncate BEFORE TRUNCATE ON tree_heads
    FOR EACH STATEMENT EXECUTE FUNCTION ledger_append_only();

-- ---------------------------------------------------------------- hàng đợi việc
CREATE TABLE jobs (
    id         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind       text        NOT NULL,
    payload    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    state      text        NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')),
    attempts   integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    run_after  timestamptz NOT NULL DEFAULT now(),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_ready ON jobs (run_after) WHERE state = 'QUEUED';

-- ---------------------------------------------------------------- quyền của dxos_core
GRANT SELECT, INSERT, UPDATE ON apps, records, sequences, uploads TO dxos_core;
GRANT SELECT, INSERT ON objects, object_refs, pii_findings, seals TO dxos_core;
GRANT UPDATE (status, scanner_version, scanned_at) ON objects TO dxos_core;
GRANT UPDATE (reviewed_by, reviewed_at) ON pii_findings TO dxos_core;
GRANT UPDATE (status, revoked_at) ON seals TO dxos_core;
GRANT SELECT, INSERT ON ledger_entries, tree_heads TO dxos_core;   -- KHÔNG UPDATE, DELETE, TRUNCATE
GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO dxos_core;
GRANT SELECT ON schema_migrations TO dxos_core;
