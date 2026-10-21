-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 003_workflow_seal.sql: quy trình, niêm phong, tệp đi kèm app (Plan 02 Task 2; spec 10.1 phần B, 25.2, 25.3).
-- Chạy được trên DB đã có dữ liệu của Plan 01 (dev stack). KHÔNG sửa tệp này sau khi đã phát hành.
--
-- Mọi bảng mới đều chỉ-thêm (trigger ledger_append_only chặn UPDATE, DELETE, TRUNCATE với mọi role;
-- dxos_core chỉ có SELECT, INSERT), trừ hai bảng xóa được: record_salts và seal_revocation_notes (I5).

-- ---------------------------------------------------------------- tệp và bản deploy của app
CREATE TABLE app_files (
    app_id  app_slug   NOT NULL,
    version text       NOT NULL,
    path    text       NOT NULL CHECK (path ~ '^[a-z0-9][a-z0-9/_.-]{0,127}$' AND path !~ '\.\.'),
    sha256  sha256_hex NOT NULL,
    content text       NOT NULL,
    PRIMARY KEY (app_id, version, path),
    FOREIGN KEY (app_id, version) REFERENCES apps (id, version)
);

-- Định nghĩa quy trình đã deploy cho từng bản app; workflow:start dùng đúng process_definition_id này.
CREATE TABLE app_deployments (
    app_id                app_slug    NOT NULL,
    version               text        NOT NULL,
    deployment_id         text        NOT NULL,
    process_definition_id text        NOT NULL,
    rendered_sha256       sha256_hex  NOT NULL,
    deployed_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (app_id, version),
    FOREIGN KEY (app_id, version) REFERENCES apps (id, version)
);

-- ---------------------------------------------------------------- task
-- Ý định hoàn thành task: ghi và commit TRƯỚC khi gọi Flowable (chịu lỗi DB sau Flowable, spec 15 T6).
CREATE TABLE task_intents (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id        text        NOT NULL,
    record_id      uuid        NOT NULL REFERENCES records (id),
    wf_instance_id text        NOT NULL,
    task_key       text        NOT NULL,
    actor_sub      text        NOT NULL,
    actor_roles    text[]      NOT NULL,
    decision       text        NOT NULL CHECK (decision ~ '^[a-z][a-z0-9_]{0,31}$'),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_intents_record ON task_intents (record_id);
CREATE INDEX task_intents_task ON task_intents (task_id);

-- Mỗi ý định tối đa một kết quả; ý định chưa có dòng ở đây là "chưa có kết quả".
CREATE TABLE task_intent_outcomes (
    intent_id  bigint      PRIMARY KEY REFERENCES task_intents (id),
    outcome    text        NOT NULL CHECK (outcome IN ('completed', 'abandoned', 'guard_failed')),
    decided_at timestamptz NOT NULL DEFAULT now()
);

-- Nguồn của guard not_same_actor:<task>; lưu `sub` (ledger chỉ giữ HMAC).
CREATE TABLE task_completions (
    task_id        text        PRIMARY KEY,
    intent_id      bigint      NOT NULL REFERENCES task_intents (id),
    record_id      uuid        NOT NULL REFERENCES records (id),
    wf_instance_id text        NOT NULL,
    task_key       text        NOT NULL,
    actor_sub      text        NOT NULL,
    decision       text        NOT NULL,
    completed_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_completions_record_instance ON task_completions (record_id, wf_instance_id);

-- Xác nhận rà PII (:pii-review); review_digest có salt (spec 25.2).
CREATE TABLE pii_reviews (
    id            bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id     uuid        NOT NULL REFERENCES records (id),
    review_digest sha256_hex  NOT NULL,
    reviewed_by   text        NOT NULL,
    reviewed_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- niêm phong
-- Ảnh chụp nội dung được duyệt, ghi cùng transaction với task cuối; job niêm phong ký đúng ảnh chụp này.
-- KHÔNG chứa salt.
CREATE TABLE seal_requests (
    seal_id       text        PRIMARY KEY CHECK (seal_id ~ '^[A-Z2-7]{26}$'),
    record_id     uuid        NOT NULL UNIQUE REFERENCES records (id),
    app_id        app_slug    NOT NULL,
    app_version   text        NOT NULL,
    record_digest sha256_hex  NOT NULL,
    attachments   jsonb       NOT NULL,
    public_fields jsonb       NOT NULL,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (seal_id, record_id),
    FOREIGN KEY (app_id, app_version) REFERENCES apps (id, version)
);

-- Bảng seals đang rỗng (Plan 01 chưa niêm phong gì); vẫn kiểm trước khi SET NOT NULL để báo lỗi rõ.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM seals WHERE leaf_index IS NULL) THEN
        RAISE EXCEPTION 'migration_003_seals_without_leaf_index'
            USING DETAIL = 'có niêm phong chưa có leaf_index; xử lý tay trước khi áp 003';
    END IF;
END
$$;
CREATE UNIQUE INDEX seals_one_per_record ON seals (record_id);
ALTER TABLE seals
    ADD CONSTRAINT seals_matches_request FOREIGN KEY (seal_id, record_id)
        REFERENCES seal_requests (seal_id, record_id),
    ADD CONSTRAINT seals_signature_ed25519 CHECK (signature ~ '^[A-Za-z0-9+/]{86}==$'),
    ALTER COLUMN leaf_index SET NOT NULL;

-- Thu hồi: mã lý do cố định (P2-D24), không có chữ tự do.
CREATE TABLE seal_revocations (
    seal_id     text        PRIMARY KEY REFERENCES seals (seal_id),
    reason_code text        NOT NULL
                            CHECK (reason_code IN ('superseded', 'issued_in_error', 'content_error',
                                                   'legal_order', 'other')),
    revoked_by  text        NOT NULL,
    revoked_at  timestamptz NOT NULL DEFAULT now()
);

-- Ghi chú tự do của người thu hồi: XÓA ĐƯỢC (thuộc I5, spec 25.2).
CREATE TABLE seal_revocation_notes (
    seal_id text PRIMARY KEY REFERENCES seals (seal_id),
    note    text NOT NULL CHECK (length(note) BETWEEN 1 AND 500)
);

-- ---------------------------------------------------------------- dữ liệu cá nhân (spec 25.2)
-- Salt 128 bit của từng bản ghi. Xóa được (xóa PII làm cam kết cũ không còn nối được với dữ liệu),
-- KHÔNG UPDATE được với mọi role.
CREATE TABLE record_salts (
    record_id  uuid        PRIMARY KEY REFERENCES records (id),
    salt       text        NOT NULL CHECK (salt ~ '^[A-Za-z0-9+/]{22}==$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION salt_no_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'salt_immutable' USING DETAIL = format('%s on %s is forbidden', TG_OP, TG_TABLE_NAME);
END
$$;
CREATE TRIGGER salt_no_update BEFORE UPDATE ON record_salts
    FOR EACH ROW EXECUTE FUNCTION salt_no_update();
CREATE TRIGGER salt_no_update_truncate BEFORE TRUNCATE ON record_salts
    FOR EACH STATEMENT EXECUTE FUNCTION salt_no_update();

-- Mọi bản ghi có salt ngay lúc tạo, ở mức DB: 16 byte từ bộ sinh ngẫu nhiên của PostgreSQL
-- (gen_random_uuid: 122 bit ngẫu nhiên), base64 24 ký tự. Không cần pgcrypto.
CREATE FUNCTION record_salt_init() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO record_salts(record_id, salt) VALUES (NEW.id, encode(uuid_send(gen_random_uuid()), 'base64'));
    RETURN NULL;
END
$$;
CREATE TRIGGER record_salt_init AFTER INSERT ON records
    FOR EACH ROW EXECUTE FUNCTION record_salt_init();

-- Bổ sung salt cho bản ghi đã có (dev stack Plan 01).
INSERT INTO record_salts(record_id, salt)
SELECT r.id, encode(uuid_send(gen_random_uuid()), 'base64')
FROM records r
WHERE NOT EXISTS (SELECT 1 FROM record_salts s WHERE s.record_id = r.id);

-- Bằng chứng xóa trường PII; txid gắn bằng chứng với đúng transaction xóa (record_seal_guard đọc).
CREATE TABLE pii_erasures (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_id   uuid        NOT NULL REFERENCES records (id),
    fields      text[]      NOT NULL CHECK (cardinality(fields) BETWEEN 1 AND 64),
    reason_code text        NOT NULL
                            CHECK (reason_code IN ('data_subject_request', 'purpose_completed',
                                                   'retention_expired', 'authority_decision', 'agreement')),
    erased_by   text        NOT NULL,
    txid        bigint      NOT NULL DEFAULT txid_current(),
    erased_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX pii_erasures_record_txid ON pii_erasures (record_id, txid);

-- ---------------------------------------------------------------- tuyên bố khóa (spec 25.3)
-- Không có cột chữ ký: tuyên bố không tự ký, được bảo vệ bằng lá ledger key.published và tệp trong repo neo.
CREATE TABLE key_statements (
    key              text        NOT NULL CHECK (key = 'seal-key'),
    version          integer     NOT NULL CHECK (version >= 1),
    statement        jsonb       NOT NULL,
    statement_sha256 sha256_hex  NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key, version)
);

-- ---------------------------------------------------------------- records: quy trình
ALTER TABLE records
    ADD COLUMN wf_app_version   text,
    ADD COLUMN wf_definition_id text;

-- Giá trị wf_state tự do của Plan 01 (không hợp lệ theo luật mới) đưa về NULL trước khi thêm CHECK.
UPDATE records SET wf_state = NULL
WHERE wf_state IS NOT NULL AND wf_state <> 'running' AND wf_state !~ '^ended:[A-Za-z_][A-Za-z0-9_-]{0,63}$';

ALTER TABLE records ADD CONSTRAINT records_wf_state_check
    CHECK (wf_state IS NULL OR wf_state = 'running' OR wf_state ~ '^ended:[A-Za-z_][A-Za-z0-9_-]{0,63}$');

-- Đang chạy quy trình thì `data` bị khóa. Không có ngoại lệ (kể cả xóa PII: lõi trả 409).
CREATE FUNCTION record_workflow_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.wf_state = 'running' AND NEW.data IS DISTINCT FROM OLD.data THEN
        RAISE EXCEPTION 'record_in_workflow' USING DETAIL = format('record %s is in a running workflow', OLD.id);
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER record_workflow_guard BEFORE UPDATE ON records
    FOR EACH ROW EXECUTE FUNCTION record_workflow_guard();

-- Giữ nguyên mọi luật của 001; thêm ĐÚNG MỘT ngoại lệ (P2-D23): bản ghi đã niêm phong được bớt các khóa
-- ghi trong một hàng pii_erasures của CHÍNH transaction này (txid_current), và chỉ bớt đúng các khóa đó.
-- Không dùng cờ phiên: phiên dxos_core nào cũng tự bật được cờ.
CREATE OR REPLACE FUNCTION record_seal_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.seal_state <> 'NONE' THEN
            RAISE EXCEPTION 'record_sealed' USING DETAIL = format('record %s is %s', OLD.id, OLD.seal_state);
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.seal_state <> 'NONE' AND NEW.data IS DISTINCT FROM OLD.data AND NOT EXISTS (
           SELECT 1 FROM pii_erasures e
           WHERE e.record_id = OLD.id AND e.txid = txid_current() AND NEW.data = OLD.data - e.fields
    ) THEN
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

-- ---------------------------------------------------------------- uploads: chỉ khi bản ghi còn mở (P2-D4)
-- FOR SHARE: chờ workflow:start đang giữ FOR UPDATE commit xong rồi đọc giá trị mới; đọc snapshot thì upload
-- có thể lọt vào đúng khoảng start đang gọi Flowable. dxos_core có UPDATE trên records, đủ cho FOR SHARE.
CREATE FUNCTION upload_record_open() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    r record;
BEGIN
    SELECT wf_state, seal_state INTO r FROM records WHERE id = NEW.record_id FOR SHARE;
    IF FOUND AND (r.wf_state = 'running' OR r.seal_state <> 'NONE') THEN
        RAISE EXCEPTION 'record_not_open'
            USING DETAIL = format('record %s: wf_state=%s seal_state=%s', NEW.record_id, r.wf_state, r.seal_state);
    END IF;
    RETURN NEW;   -- không có bản ghi: để khóa ngoại báo lỗi
END
$$;
CREATE TRIGGER upload_record_open BEFORE INSERT ON uploads
    FOR EACH ROW EXECUTE FUNCTION upload_record_open();

-- ---------------------------------------------------------------- chỉ-thêm
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['app_files', 'app_deployments', 'task_intents', 'task_intent_outcomes',
                             'task_completions', 'pii_reviews', 'seal_requests', 'seal_revocations',
                             'pii_erasures', 'key_statements']
    LOOP
        EXECUTE format('CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON %I'
                       ' FOR EACH ROW EXECUTE FUNCTION ledger_append_only()', t);
        EXECUTE format('CREATE TRIGGER ledger_append_only_truncate BEFORE TRUNCATE ON %I'
                       ' FOR EACH STATEMENT EXECUTE FUNCTION ledger_append_only()', t);
    END LOOP;
END
$$;

-- ---------------------------------------------------------------- quyền của dxos_core
GRANT SELECT, INSERT ON app_files, app_deployments, task_intents, task_intent_outcomes, task_completions,
                        pii_reviews, seal_requests, seal_revocations, pii_erasures, key_statements TO dxos_core;
GRANT SELECT, INSERT, DELETE ON record_salts, seal_revocation_notes TO dxos_core;   -- KHÔNG UPDATE
