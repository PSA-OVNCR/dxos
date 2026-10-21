-- SPDX-FileCopyrightText: 2026 PSA_OVNCR
-- SPDX-License-Identifier: Apache-2.0
--
-- 004_harden_triggers.sql: làm cứng trigger của 001–003 (Plan 02 Task 2, sửa vòng 1). KHÔNG sửa 003 (đã phát hành).
--
-- Lỗi được sửa: trigger tra bảng bằng tên không kèm schema. pg_temp luôn được tìm TRƯỚC các schema khác khi tìm
-- bảng, nên một phiên dxos_core (có TEMP qua PUBLIC) tạo bảng tạm `pii_erasures`, `records` hay `record_salts`
-- là vượt được record_seal_guard, upload_record_open, record_salt_init.
-- Cách sửa: mọi bảng ghi rõ `core.`; mọi hàm plpgsql của schema core ghim search_path = pg_catalog, core, pg_temp
-- (pg_temp không bao giờ được tìm cho hàm và toán tử). Thêm lớp phòng thủ: thu hồi TEMP của PUBLIC.

-- ---------------------------------------------------------------- hàm có tra bảng: viết lại, ghi rõ schema
CREATE OR REPLACE FUNCTION core.record_salt_init() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, core, pg_temp
AS $$
BEGIN
    INSERT INTO core.record_salts(record_id, salt)
    VALUES (NEW.id, pg_catalog.encode(pg_catalog.uuid_send(pg_catalog.gen_random_uuid()), 'base64'));
    RETURN NULL;
END
$$;

-- Giữ nguyên luật của 001 và đúng một ngoại lệ của 003 (P2-D23); chỉ đổi cách tra bảng.
CREATE OR REPLACE FUNCTION core.record_seal_guard() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, core, pg_temp
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.seal_state <> 'NONE' THEN
            RAISE EXCEPTION 'record_sealed' USING DETAIL = format('record %s is %s', OLD.id, OLD.seal_state);
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.seal_state <> 'NONE' AND NEW.data IS DISTINCT FROM OLD.data AND NOT EXISTS (
           SELECT 1 FROM core.pii_erasures e
           WHERE e.record_id = OLD.id AND e.txid = pg_catalog.txid_current() AND NEW.data = OLD.data - e.fields
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

CREATE OR REPLACE FUNCTION core.upload_record_open() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, core, pg_temp
AS $$
DECLARE
    r record;
BEGIN
    SELECT wf_state, seal_state INTO r FROM core.records WHERE id = NEW.record_id FOR SHARE;
    IF FOUND AND (r.wf_state = 'running' OR r.seal_state <> 'NONE') THEN
        RAISE EXCEPTION 'record_not_open'
            USING DETAIL = format('record %s: wf_state=%s seal_state=%s', NEW.record_id, r.wf_state, r.seal_state);
    END IF;
    RETURN NEW;   -- không có bản ghi: để khóa ngoại báo lỗi
END
$$;

-- ---------------------------------------------------------------- hàm không tra bảng: chỉ ghim search_path
ALTER FUNCTION core.object_identity_guard() SET search_path = pg_catalog, core, pg_temp;
ALTER FUNCTION core.ledger_append_only() SET search_path = pg_catalog, core, pg_temp;
ALTER FUNCTION core.salt_no_update() SET search_path = pg_catalog, core, pg_temp;
ALTER FUNCTION core.record_workflow_guard() SET search_path = pg_catalog, core, pg_temp;

-- ---------------------------------------------------------------- txid của bằng chứng xóa do DB đặt
-- Trước đây txid chỉ là DEFAULT: bên ghi có thể tự chọn txid. Trigger ghi đè bằng txid của chính transaction ghi,
-- với mọi role; dxos_core chỉ còn quyền INSERT trên các cột nghiệp vụ.
CREATE FUNCTION core.pii_erasure_txid() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, core, pg_temp
AS $$
BEGIN
    NEW.txid := pg_catalog.txid_current();
    RETURN NEW;
END
$$;
CREATE TRIGGER pii_erasure_txid BEFORE INSERT ON core.pii_erasures
    FOR EACH ROW EXECUTE FUNCTION core.pii_erasure_txid();

REVOKE INSERT ON core.pii_erasures FROM dxos_core;
GRANT INSERT (record_id, fields, reason_code, erased_by) ON core.pii_erasures TO dxos_core;

-- ---------------------------------------------------------------- đặt tên ràng buộc một yêu cầu cho mỗi bản ghi
ALTER TABLE core.seal_requests RENAME CONSTRAINT seal_requests_record_id_key TO seal_requests_one_per_record;

-- ---------------------------------------------------------------- phòng thủ thêm: không role nào có TEMP qua PUBLIC
-- dxos_owner (chủ DB) vẫn có TEMP; dxos_core không cần bảng tạm.
DO $$
BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END
$$;
