# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test migration.

001: ledger chỉ-thêm, niêm phong, quyền role (Plan 01 Task 8).
003: quy trình, niêm phong, salt, bằng chứng xóa PII (Plan 02 Task 2).
"""

import asyncio
import json
import shutil
from pathlib import Path

import asyncpg
import pytest
from dxos_core.db.migrate import MigrationError, apply_migrations
from helpers.db import (
    SEAL_SIGNATURE,
    ensure_app,
    insert_intent_and_completion,
    insert_seal,
    insert_seal_request,
    insert_upload,
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
pytestmark = pytest.mark.integration


# ---------- Các test do Plan 01 Task 8 quy định ----------

async def test_migrations_idempotent(owner_dsn):
    first = await apply_migrations(owner_dsn, MIGRATIONS)
    second = await apply_migrations(owner_dsn, MIGRATIONS)
    assert first == ["001_core.sql", "002_anchors.sql", "003_workflow_seal.sql", "004_harden_triggers.sql",
                     "005_ots.sql", "006_pii_scans.sql", "007_pii_redacted.sql"]
    assert second == []


async def test_core_role_cannot_update_ledger(core_conn, seeded_ledger_row):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("UPDATE ledger_entries SET subject='x' WHERE idx=0")


async def test_owner_update_blocked_by_trigger(owner_conn, seeded_ledger_row):
    with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
        await owner_conn.execute("UPDATE ledger_entries SET subject='x' WHERE idx=0")


async def test_sealed_record_data_immutable(owner_conn, sealed_record_id):
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        await owner_conn.execute("UPDATE records SET data='{}' WHERE id=$1", sealed_record_id)


async def test_seal_pending_to_sealed_allowed(owner_conn, pending_record_id):
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", pending_record_id)


async def test_object_sha256_format(owner_conn):
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_conn.execute(
            "INSERT INTO objects(sha256,size,mime_sniffed,status,storage_key)"
            " VALUES('XYZ',1,'application/pdf','CLEAN','k')"
        )


# ---------- Bổ sung: ledger và tree_heads chỉ-thêm ----------

async def test_core_role_cannot_delete_or_truncate_ledger(core_conn, seeded_ledger_row):
    for sql in ("DELETE FROM ledger_entries", "TRUNCATE ledger_entries",
                "UPDATE tree_heads SET signature='x'", "DELETE FROM tree_heads"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await core_conn.execute(sql)


async def test_owner_delete_and_truncate_blocked_by_trigger(owner_conn, seeded_ledger_row):
    await owner_conn.execute(
        "INSERT INTO tree_heads(tree_size, root_hash, ts, key_version, signature)"
        " VALUES (1, $1, '2026-10-20T00:00:00Z', 1, 'sig')", "a" * 64)
    for sql in ("DELETE FROM ledger_entries WHERE idx=0", "TRUNCATE ledger_entries",
                "UPDATE tree_heads SET signature='x'", "DELETE FROM tree_heads"):
        with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
            await owner_conn.execute(sql)
    # TRUNCATE tree_heads: bị khóa ngoại từ anchors (002) hoặc trigger chặn, tùy cái nào tới trước
    with pytest.raises(asyncpg.PostgresError):
        await owner_conn.execute("TRUNCATE tree_heads")
    assert await owner_conn.fetchval("SELECT count(*) FROM ledger_entries") == 1
    assert await owner_conn.fetchval("SELECT count(*) FROM tree_heads") == 1


async def test_ledger_idx_is_plain_bigint_without_sequence(owner_conn):  # D2
    row = await owner_conn.fetchrow(
        "SELECT data_type, column_default, is_identity FROM information_schema.columns"
        " WHERE table_schema='core' AND table_name='ledger_entries' AND column_name='idx'")
    assert (row["data_type"], row["column_default"], row["is_identity"]) == ("bigint", None, "NO")


async def test_core_can_append_and_read_ledger(core_conn, seeded_ledger_row):
    assert await core_conn.fetchval("SELECT subject FROM ledger_entries WHERE idx=0") == "r1"


async def test_ledger_rejects_negative_idx_and_bad_leaf(core_conn):
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(
            "INSERT INTO ledger_entries(idx, ts, type, subject, body_sha256, leaf_hash)"
            " VALUES (-1, '2026-10-20T00:00:00Z', 't', 's', $1, $2)", "0" * 64, b"\x00" * 32)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(
            "INSERT INTO ledger_entries(idx, ts, type, subject, body_sha256, leaf_hash)"
            " VALUES (0, '2026-10-20T00:00:00Z', 't', 's', $1, $2)", "0" * 64, b"\x00" * 31)


# ---------- Bổ sung: niêm phong bản ghi ----------

async def test_unsealed_record_data_mutable(core_conn, record_id):
    await core_conn.execute("UPDATE records SET data='{\"a\": 2}', version=version+1 WHERE id=$1", record_id)


async def test_sealed_record_other_columns_still_mutable(owner_conn, sealed_record_id):
    await owner_conn.execute("UPDATE records SET wf_state='ended:approved', seal_state='REVOKED' WHERE id=$1",
                             sealed_record_id)


@pytest.mark.parametrize("start,target", [
    ("SEALED", "NONE"), ("SEALED", "SEAL_PENDING"), ("SEAL_PENDING", "NONE"), ("NONE", "REVOKED"),
])
async def test_illegal_seal_transitions_rejected(owner_conn, record_id, start, target):
    if start != "NONE":
        await owner_conn.execute("UPDATE records SET seal_state=$2 WHERE id=$1", record_id, start)
    with pytest.raises(asyncpg.RaiseError, match="record_seal_transition"):
        await owner_conn.execute("UPDATE records SET seal_state=$2 WHERE id=$1", record_id, target)


async def test_revoked_is_terminal(owner_conn, sealed_record_id):
    await owner_conn.execute("UPDATE records SET seal_state='REVOKED' WHERE id=$1", sealed_record_id)
    with pytest.raises(asyncpg.RaiseError, match="record_seal_transition"):
        await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", sealed_record_id)


async def test_sealed_record_cannot_be_deleted(owner_conn, sealed_record_id):
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        await owner_conn.execute("DELETE FROM records WHERE id=$1", sealed_record_id)


async def test_seal_state_check(owner_conn):
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_conn.execute(
            "INSERT INTO records(app_id, collection, data, owner_sub, seal_state)"
            " VALUES ('test-app','item','{}','u','BOGUS')")


async def test_core_role_cannot_delete_records(core_conn, record_id):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("DELETE FROM records WHERE id=$1", record_id)


# ---------- Bổ sung: CAS ----------

async def _insert_object(conn, sha="a" * 64):
    await conn.execute(
        "INSERT INTO objects(sha256,size,mime_sniffed,status,storage_key)"
        " VALUES($1,1,'application/pdf','CLEAN',$2)", sha, f"objects/{sha}")


async def test_object_identity_immutable(owner_conn, core_conn):
    await _insert_object(core_conn)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("UPDATE objects SET storage_key='x'")
    with pytest.raises(asyncpg.RaiseError, match="object_immutable"):
        await owner_conn.execute("UPDATE objects SET sha256=$1", "b" * 64)
    await core_conn.execute("UPDATE objects SET scanner_version='ClamAV 1.4'")  # cột được phép


# ---------- Bổ sung: role, schema, search_path ----------

async def test_core_role_is_not_privileged(owner_conn):
    row = await owner_conn.fetchrow(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname='dxos_core'")
    assert tuple(row) == (False, False, False, False)


async def test_core_role_cannot_create_objects_in_schema(core_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("CREATE TABLE core.evil(x int)")


async def test_core_role_cannot_touch_schema_migrations(core_conn):
    assert await core_conn.fetchval("SELECT count(*) FROM schema_migrations") == 7
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("DELETE FROM schema_migrations")


async def test_all_spec_tables_exist(owner_conn):
    names = {r["table_name"] for r in await owner_conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='core'")}
    assert {"apps", "records", "sequences", "uploads", "objects", "object_refs", "pii_findings",
            "seals", "ledger_entries", "tree_heads", "jobs", "schema_migrations", "anchors",
            "app_files", "app_deployments", "task_intents", "task_intent_outcomes", "task_completions",
            "pii_reviews", "seal_requests", "seal_revocations", "seal_revocation_notes", "record_salts",
            "pii_erasures", "key_statements", "ots_receipts", "pii_scans"} <= names


async def test_core_can_enqueue_job(core_conn):
    jid = await core_conn.fetchval("INSERT INTO jobs(kind, payload) VALUES ('scan', '{}') RETURNING id")
    assert jid >= 1


# ---------- Bổ sung: hành vi apply_migrations ----------

def _copy_migrations(tmp_path: Path) -> Path:
    d = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, d)
    return d


async def test_changed_migration_is_detected(owner_dsn, tmp_path):
    d = _copy_migrations(tmp_path)
    await apply_migrations(owner_dsn, d)
    (d / "001_core.sql").write_text((d / "001_core.sql").read_text(encoding="utf-8") + "\n-- sửa\n",
                                    encoding="utf-8")
    with pytest.raises(MigrationError, match="001_core.sql"):
        await apply_migrations(owner_dsn, d)


async def test_failed_migration_rolls_back_and_is_not_recorded(owner_dsn, tmp_path):
    d = _copy_migrations(tmp_path)
    (d / "900_broken.sql").write_text("CREATE TABLE ok_then_fail(x int);\nSELECT 1/0;\n", encoding="utf-8")
    with pytest.raises(asyncpg.DivisionByZeroError):
        await apply_migrations(owner_dsn, d)
    conn = await asyncpg.connect(owner_dsn)
    try:
        applied = await conn.fetchval(
            "SELECT array_agg(filename ORDER BY filename) FROM core.schema_migrations")
        assert applied == ["001_core.sql", "002_anchors.sql", "003_workflow_seal.sql",
                           "004_harden_triggers.sql", "005_ots.sql", "006_pii_scans.sql",
                           "007_pii_redacted.sql"]
        assert await conn.fetchval("SELECT to_regclass('core.ok_then_fail')") is None
    finally:
        await conn.close()


async def test_bad_migration_name_rejected(owner_dsn, tmp_path):
    d = _copy_migrations(tmp_path)
    (d / "2_khong-dung-ten.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError, match="2_khong-dung-ten.sql"):
        await apply_migrations(owner_dsn, d)


async def test_database_newer_than_code_rejected(owner_dsn, tmp_path):
    d = _copy_migrations(tmp_path)
    (d / "900_extra.sql").write_text("SELECT 1;", encoding="utf-8")
    await apply_migrations(owner_dsn, d)
    with pytest.raises(MigrationError, match="900_extra.sql"):
        await apply_migrations(owner_dsn, MIGRATIONS)


async def test_apply_until_stops_at_prefix(owner_dsn):
    assert await apply_migrations(owner_dsn, MIGRATIONS, until="001") == ["001_core.sql"]
    assert await apply_migrations(owner_dsn, MIGRATIONS, until="002") == ["002_anchors.sql"]
    assert await apply_migrations(owner_dsn, MIGRATIONS) == [
        "003_workflow_seal.sql", "004_harden_triggers.sql", "005_ots.sql", "006_pii_scans.sql",
        "007_pii_redacted.sql"]


async def test_apply_until_unknown_prefix_rejected(owner_dsn):
    with pytest.raises(MigrationError, match="099"):
        await apply_migrations(owner_dsn, MIGRATIONS, until="099")


# ---------- Migration 003 (Plan 02 Task 2) ----------

# Bảng chỉ-thêm của 003.
APPEND_ONLY_003 = ("app_files", "app_deployments", "task_intents", "task_intent_outcomes", "task_completions",
                   "pii_reviews", "seal_requests", "seal_revocations", "pii_erasures", "key_statements")
ERASE = ("INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by)"
         " VALUES ($1, $2, 'data_subject_request', 'u')")
STRIP = "UPDATE records SET data = data - $2::text WHERE id=$1"
SET_SALT = "UPDATE record_salts SET salt=$2 WHERE record_id=$1"


async def _seed_003(owner_conn, record_id) -> None:
    """Mỗi bảng chỉ-thêm của 003 có đúng một dòng (để UPDATE/DELETE thực sự chạm hàng)."""
    await ensure_app(owner_conn, "test-flow", "0.1.0")
    await owner_conn.execute(
        "INSERT INTO app_files VALUES ('test-flow', '0.1.0', 'bpmn/a.bpmn', $1, '<x/>')", "0" * 64)
    await owner_conn.execute(
        "INSERT INTO app_deployments(app_id, version, deployment_id, process_definition_id, rendered_sha256)"
        " VALUES ('test-flow', '0.1.0', 'd1', 'p:1:1', $1)", "1" * 64)
    await insert_intent_and_completion(owner_conn, record_id, task_id="t1")
    await owner_conn.execute(
        "INSERT INTO pii_reviews(record_id, review_digest, reviewed_by) VALUES ($1, $2, 'u')",
        record_id, "2" * 64)
    await insert_seal_request(owner_conn, record_id, seal_id="A" * 26)
    await insert_seal(owner_conn, record_id, seal_id="A" * 26)
    await owner_conn.execute(
        "INSERT INTO seal_revocations(seal_id, reason_code, revoked_by) VALUES ($1, 'superseded', 'u')",
        "A" * 26)
    await owner_conn.execute(ERASE, record_id, ["a"])
    await owner_conn.execute(
        "INSERT INTO key_statements(key, version, statement, statement_sha256)"
        " VALUES ('seal-key', 1, '{}', $1)", "3" * 64)
    for t in APPEND_ONLY_003:
        assert await owner_conn.fetchval(f"SELECT count(*) FROM {t}") == 1, t  # noqa: S608


async def _plain_column(conn, table: str) -> str:
    """Một cột không phải identity (UPDATE cột identity bị PostgreSQL chặn trước cả trigger)."""
    return await conn.fetchval(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name=$1"
        " AND is_identity='NO' ORDER BY ordinal_position LIMIT 1", table)


async def test_new_tables_are_insert_only(owner_conn, core_conn, record_id):
    """C12: mỗi bảng có một dòng; lệnh cấm chạy bằng owner để chính trigger bị thử, không chỉ thiếu GRANT."""
    await _seed_003(owner_conn, record_id)
    for sql in ("UPDATE task_completions SET decision='reject'", "DELETE FROM task_intents",
                "UPDATE seal_requests SET app_id='x'", "DELETE FROM app_files",
                "UPDATE pii_reviews SET reviewed_by='x'", "DELETE FROM app_deployments",
                "UPDATE seal_revocations SET reason_code='other'",
                "UPDATE pii_erasures SET reason_code='agreement'", "DELETE FROM key_statements"):
        with pytest.raises(asyncpg.PostgresError):        # app_id='x' trượt domain app_slug trước cả trigger
            await owner_conn.execute(sql)
    # Kiểm chặt từng bảng: UPDATE không đổi giá trị (không vướng CHECK nào) và DELETE → chỉ trigger chặn.
    for t in APPEND_ONLY_003:
        col = await _plain_column(owner_conn, t)
        for sql in (f"UPDATE {t} SET {col} = {col}", f"DELETE FROM {t}"):  # noqa: S608
            with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
                await owner_conn.execute(sql)
            with pytest.raises(asyncpg.InsufficientPrivilegeError):             # dxos_core không có GRANT
                await core_conn.execute(sql)
        with pytest.raises(asyncpg.PostgresError):      # trigger TRUNCATE hoặc khóa ngoại, cái nào tới trước
            await owner_conn.execute(f"TRUNCATE {t}")
        assert await owner_conn.fetchval(f"SELECT count(*) FROM {t}") == 1, t  # noqa: S608


async def test_truncate_trigger_on_every_append_only_table(owner_conn):
    names = {r["t"] for r in await owner_conn.fetch(
        "SELECT c.relname AS t FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid"
        " JOIN pg_proc p ON p.oid = g.tgfoid WHERE p.proname = 'ledger_append_only'"
        " AND (g.tgtype & 32) <> 0")}                                       # TRIGGER_TYPE_TRUNCATE
    assert set(APPEND_ONLY_003) <= names


async def test_seal_must_match_its_request(core_conn, record_id, other_record_id):
    with pytest.raises(asyncpg.ForeignKeyViolationError):                       # chưa có yêu cầu
        await insert_seal(core_conn, record_id, seal_id="A" * 26)
    await insert_seal_request(core_conn, record_id, seal_id="A" * 26)
    with pytest.raises(asyncpg.ForeignKeyViolationError):                       # yêu cầu thuộc bản ghi khác
        await insert_seal(core_conn, other_record_id, seal_id="A" * 26)
    with pytest.raises(asyncpg.CheckViolationError):                            # chữ ký rỗng
        await insert_seal(core_conn, record_id, seal_id="A" * 26, signature="")
    await insert_seal(core_conn, record_id, seal_id="A" * 26)
    await insert_seal_request(core_conn, other_record_id, seal_id="B" * 26)
    with pytest.raises(asyncpg.PostgresError):                                  # mỗi bản ghi một niêm phong
        await insert_seal(core_conn, record_id, seal_id="B" * 26)


async def test_one_seal_per_record_by_unique_index(owner_conn, record_id):
    """C12: có yêu cầu khớp cho niêm phong thứ hai, nên chỉ index duy nhất có thể chặn lần chèn đó."""
    await insert_seal_request(owner_conn, record_id, seal_id="A" * 26)
    await insert_seal(owner_conn, record_id, seal_id="A" * 26)
    # Bỏ UNIQUE(record_id) của seal_requests (chỉ trong DB tạm của test) để có yêu cầu thứ hai cùng bản ghi.
    await owner_conn.execute("ALTER TABLE seal_requests DROP CONSTRAINT seal_requests_one_per_record")
    await insert_seal_request(owner_conn, record_id, seal_id="B" * 26)
    with pytest.raises(asyncpg.UniqueViolationError, match="seals_one_per_record"):
        await insert_seal(owner_conn, record_id, seal_id="B" * 26)


async def test_one_seal_request_per_record(core_conn, record_id):
    await insert_seal_request(core_conn, record_id, seal_id="A" * 26)
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert_seal_request(core_conn, record_id, seal_id="B" * 26)


@pytest.mark.parametrize("sig", [SEAL_SIGNATURE[:-2], SEAL_SIGNATURE[:-2] + "A=", "!" * 86 + "=="])
async def test_seal_signature_must_be_ed25519_base64(core_conn, record_id, sig):
    await insert_seal_request(core_conn, record_id, seal_id="A" * 26)
    with pytest.raises(asyncpg.CheckViolationError):
        await insert_seal(core_conn, record_id, seal_id="A" * 26, signature=sig)


async def test_seal_leaf_index_required(core_conn, record_id):
    await insert_seal_request(core_conn, record_id, seal_id="A" * 26)
    with pytest.raises(asyncpg.NotNullViolationError):
        await core_conn.execute(
            "INSERT INTO seals(seal_id, app_id, record_id, payload, signature, key_version)"
            " VALUES ($1, 'test-app', $2, '{}', $3, 1)", "A" * 26, record_id, SEAL_SIGNATURE)


async def test_revocation_reason_is_a_code(core_conn, record_id):
    await insert_seal_request(core_conn, record_id, seal_id="A" * 26)
    await insert_seal(core_conn, record_id, seal_id="A" * 26)
    revoke = "INSERT INTO seal_revocations(seal_id, reason_code, revoked_by) VALUES ($1, $2, 'u')"
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(revoke, "A" * 26, "vì tôi muốn")
    await core_conn.execute(revoke, "A" * 26, "issued_in_error")
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute("INSERT INTO seal_revocation_notes VALUES ($1, '')", "A" * 26)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute("INSERT INTO seal_revocation_notes VALUES ($1, $2)", "A" * 26, "x" * 501)
    await core_conn.execute("INSERT INTO seal_revocation_notes VALUES ($1, 'ghi chú')", "A" * 26)
    await core_conn.execute("DELETE FROM seal_revocation_notes WHERE seal_id=$1", "A" * 26)   # xóa được (I5)


async def test_data_and_uploads_frozen_while_in_workflow(core_conn, record_id):
    await core_conn.execute("UPDATE records SET wf_state='running', wf_instance_id='i1' WHERE id=$1",
                            record_id)
    with pytest.raises(asyncpg.RaiseError, match="record_in_workflow"):
        await core_conn.execute("UPDATE records SET data='{\"x\":1}'::jsonb WHERE id=$1", record_id)
    with pytest.raises(asyncpg.RaiseError, match="record_not_open"):
        await insert_upload(core_conn, record_id)
    await core_conn.execute("UPDATE records SET wf_state='ended:rejected', version=version+1 WHERE id=$1",
                            record_id)
    await core_conn.execute("UPDATE records SET data='{\"x\":1}'::jsonb WHERE id=$1", record_id)   # mở lại
    await insert_upload(core_conn, record_id)


async def test_upload_rejected_on_sealed_record(owner_conn, sealed_record_id, pending_record_id):
    for rid in (sealed_record_id, pending_record_id):
        with pytest.raises(asyncpg.RaiseError, match="record_not_open"):
            await insert_upload(owner_conn, rid)


async def test_upload_waits_for_concurrent_start(core_pool, record_id):          # rà soát lần 2, #3
    async with core_pool.acquire() as a, core_pool.acquire() as b:
        tx = a.transaction()
        await tx.start()
        await a.execute("SELECT 1 FROM records WHERE id=$1 FOR UPDATE", record_id)
        await a.execute("UPDATE records SET wf_state='running', wf_instance_id='i1' WHERE id=$1", record_id)
        pending = asyncio.create_task(insert_upload(b, record_id))      # phải chờ, không lọt qua snapshot cũ
        await asyncio.sleep(0.3)
        assert not pending.done()
        await tx.commit()
        with pytest.raises(asyncpg.RaiseError, match="record_not_open"):
            await pending


async def test_wf_state_values_checked(core_conn, record_id):
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute("UPDATE records SET wf_state='done' WHERE id=$1", record_id)
    for ok in ("running", "ended:approved", "ended:Rejected_2-x", None):
        await core_conn.execute("UPDATE records SET wf_state=$2 WHERE id=$1", record_id, ok)
    for bad in ("ended:", "ended:1x", "RUNNING", "ended:a b"):
        with pytest.raises(asyncpg.CheckViolationError):
            await core_conn.execute("UPDATE records SET wf_state=$2 WHERE id=$1", record_id, bad)


async def test_records_have_workflow_pin_columns(core_conn, record_id):
    await core_conn.execute(
        "UPDATE records SET wf_app_version='0.1.0', wf_definition_id='p:1:1' WHERE id=$1", record_id)


async def test_app_files_path_rejects_traversal(core_conn, pending_app):
    add = "INSERT INTO app_files VALUES ('test-flow', $1, $2, $3, '<x/>')"
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(
            "INSERT INTO app_files VALUES ('test-flow', '0.1.0', 'bpmn/../x', $1, '<x/>')", "0" * 64)
    for bad in ("/etc/passwd", "Bpmn/x", "a..b", ""):
        with pytest.raises(asyncpg.CheckViolationError):
            await core_conn.execute(add, "0.1.0", bad, "0" * 64)
    await core_conn.execute(add, "0.1.0", "bpmn/test-review.bpmn", "0" * 64)
    with pytest.raises(asyncpg.ForeignKeyViolationError):                       # bản app không tồn tại
        await core_conn.execute(add, "9.9.9", "bpmn/a.bpmn", "0" * 64)


async def test_task_intent_outcome_values(core_conn, record_id):
    intent = await insert_intent_and_completion(core_conn, record_id, task_id="t1")
    with pytest.raises(asyncpg.UniqueViolationError):                           # tối đa một kết quả
        await core_conn.execute(
            "INSERT INTO task_intent_outcomes(intent_id, outcome) VALUES ($1, 'abandoned')", intent)
    with pytest.raises(asyncpg.UniqueViolationError):                           # task hoàn thành một lần
        await core_conn.execute(
            "INSERT INTO task_completions(task_id, intent_id, record_id, wf_instance_id, task_key, actor_sub,"
            " decision) VALUES ('t1', $1, $2, 'i1', 'review', 'u1', 'approve')", intent, record_id)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(
            "INSERT INTO task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub, actor_roles,"
            " decision) VALUES ('t2', $1, 'i1', 'review', 'u1', '{}', 'Bad Decision')", record_id)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute("INSERT INTO task_intent_outcomes(intent_id, outcome) VALUES ($1, 'maybe')",
                                intent)


# ---------- Bổ sung 21/10: salt, bằng chứng xóa PII, tuyên bố khóa ----------

async def test_salt_cannot_be_updated_even_by_owner(owner_conn, core_conn, record_id):
    with pytest.raises(asyncpg.RaiseError):
        await owner_conn.execute(SET_SALT, record_id, "A" * 22 + "==")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute(SET_SALT, record_id, "A" * 22 + "==")
    with pytest.raises(asyncpg.RaiseError, match="salt_immutable"):
        await owner_conn.execute("TRUNCATE record_salts")
    await owner_conn.execute("DELETE FROM record_salts WHERE record_id=$1", record_id)


async def test_core_can_delete_and_recreate_salt(core_conn, record_id):
    await core_conn.execute("DELETE FROM record_salts WHERE record_id=$1", record_id)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute("INSERT INTO record_salts(record_id, salt) VALUES ($1, 'ngắn')", record_id)
    await core_conn.execute("INSERT INTO record_salts(record_id, salt) VALUES ($1, $2)",
                            record_id, "B" * 22 + "==")


async def test_every_record_gets_a_salt_at_insert(core_conn, record_id):          # record_id chèn hàng thô
    await core_conn.execute(
        "INSERT INTO records(app_id, collection, owner_sub) VALUES ('test-app', 'item', 'u')")
    assert await core_conn.fetchval(
        "SELECT count(*) FROM records r LEFT JOIN record_salts s ON s.record_id = r.id"
        " WHERE s.record_id IS NULL") == 0
    salts = [r["salt"] for r in await core_conn.fetch("SELECT salt FROM record_salts")]
    assert len(salts) == len(set(salts)) == 2 and all(len(s) == 24 and s.endswith("==") for s in salts)


async def test_migration_backfills_salts(fresh_db_at_002):       # áp 001, 002; chèn một bản ghi; rồi áp 003
    rid = await fresh_db_at_002.insert_record()
    await fresh_db_at_002.apply("003")
    assert await fresh_db_at_002.salt_of(rid)


async def test_migration_runs_on_plan01_data(fresh_db_at_002):
    """Dữ liệu kiểu dev stack Plan 01: wf_state tự do được đưa về NULL; 003 áp được."""
    rid = await fresh_db_at_002.insert_record()
    conn = await asyncpg.connect(fresh_db_at_002.dsn)
    try:
        await conn.execute("UPDATE core.records SET wf_state='done', wf_instance_id='x' WHERE id=$1", rid)
        await fresh_db_at_002.apply("003")
        assert await conn.fetchval("SELECT wf_state FROM core.records WHERE id=$1", rid) is None
    finally:
        await conn.close()


async def _data(conn, rid) -> dict:
    return json.loads(await conn.fetchval("SELECT data::text FROM records WHERE id=$1", rid))


async def test_sealed_data_changes_only_with_erasure_row(owner_conn, sealed_pii_record_id):
    """Bản ghi đã niêm phong có title, cccd, phone. Mọi lần thử sai đều bị trigger chặn."""
    rid, conn = sealed_pii_record_id, owner_conn
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):                # không có hàng bằng chứng
        await conn.execute(STRIP, rid, "cccd")
    wrong_updates = (
        "UPDATE records SET data = data - 'title' WHERE id=$1",                   # bớt khóa khác khóa đã ghi
        # bớt khóa đã ghi nhưng sửa giá trị khác
        "UPDATE records SET data = (data - 'cccd') || '{\"title\": \"khác\"}' WHERE id=$1",
        "UPDATE records SET data = (data - 'cccd') || '{\"x\": 1}' WHERE id=$1",   # bớt + thêm khóa
        "UPDATE records SET data = '{}' WHERE id=$1",                             # xóa sạch
    )
    for sql in wrong_updates:
        with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
            async with conn.transaction():
                await conn.execute(ERASE, rid, ["cccd"])
                await conn.execute(sql, rid)
    assert await conn.fetchval("SELECT count(*) FROM pii_erasures WHERE record_id=$1", rid) == 0
    async with conn.transaction():                                                # tx1 đúng: chỉ bớt cccd
        await conn.execute(ERASE, rid, ["cccd"])
        await conn.execute(STRIP, rid, "cccd")
    # tx2 (C12): bằng chứng của tx1 không dùng lại được để bớt trường PII thứ hai
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        await conn.execute(STRIP, rid, "phone")
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        async with conn.transaction():
            await conn.execute(STRIP, rid, "phone")
    assert await _data(conn, rid) == {"title": "x", "phone": "0912345678"}
    async with conn.transaction():                                                # tx3 có bằng chứng mới
        await conn.execute(ERASE, rid, ["phone"])
        await conn.execute(STRIP, rid, "phone")
    assert await _data(conn, rid) == {"title": "x"}


async def test_erasure_of_several_fields_at_once(owner_conn, sealed_pii_record_id):
    rid = sealed_pii_record_id
    async with owner_conn.transaction():
        await owner_conn.execute(ERASE, rid, ["cccd", "phone"])
        await owner_conn.execute("UPDATE records SET data = data - '{cccd,phone}'::text[] WHERE id=$1", rid)
    assert await _data(owner_conn, rid) == {"title": "x"}


async def test_erasure_exception_keeps_other_seal_rules(owner_conn, sealed_pii_record_id):
    rid = sealed_pii_record_id
    with pytest.raises(asyncpg.RaiseError, match="record_seal_transition"):   # ngoại lệ không mở luật khác
        async with owner_conn.transaction():
            await owner_conn.execute(ERASE, rid, ["cccd"])
            await owner_conn.execute(
                "UPDATE records SET data = data - 'cccd', seal_state='NONE' WHERE id=$1", rid)
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        async with owner_conn.transaction():
            await owner_conn.execute(ERASE, rid, ["cccd"])
            await owner_conn.execute("DELETE FROM records WHERE id=$1", rid)


async def test_erasure_does_not_bypass_workflow_guard(owner_conn, record_id):
    await owner_conn.execute(
        "UPDATE records SET data='{\"cccd\": \"1\"}', wf_state='running' WHERE id=$1", record_id)
    with pytest.raises(asyncpg.RaiseError, match="record_in_workflow"):
        async with owner_conn.transaction():
            await owner_conn.execute(ERASE, record_id, ["cccd"])
            await owner_conn.execute(STRIP, record_id, "cccd")


async def test_pii_erasure_values_checked(core_conn, record_id):
    sql = "INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by) VALUES ($1, $2, $3, 'u')"
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(sql, record_id, ["cccd"], "vì thích")
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(sql, record_id, [], "agreement")
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(sql, record_id, [f"f{i}" for i in range(65)], "agreement")
    async with core_conn.transaction():
        await core_conn.execute(sql, record_id, ["cccd"], "retention_expired")
        assert await core_conn.fetchval("SELECT txid FROM pii_erasures") == await core_conn.fetchval(
            "SELECT txid_current()")


async def test_key_statements_constraints(core_conn):
    sql = "INSERT INTO key_statements(key, version, statement, statement_sha256) VALUES ($1, $2, '{}', $3)"
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(sql, "other-key", 1, "0" * 64)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(sql, "seal-key", 0, "0" * 64)
    await core_conn.execute(sql, "seal-key", 1, "0" * 64)
    with pytest.raises(asyncpg.UniqueViolationError):
        await core_conn.execute(sql, "seal-key", 1, "1" * 64)
    cols = {r["column_name"] for r in await core_conn.fetch(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema='core' AND table_name='key_statements'")}
    assert "signature" not in cols                                                # spec 25.3: không tự ký



# ---------- Migration 004 (Plan 02 Task 2, sửa vòng 1): bảng tạm không che được trigger ----------
# pg_temp được tìm trước mọi schema khi tên bảng không kèm schema. Trước 004, dxos_core (có TEMP qua PUBLIC)
# tạo bảng tạm trùng tên là vượt được ba trigger. 004 ghi rõ schema `core.` và ghim search_path; thêm vào đó
# thu hồi TEMP của PUBLIC. Các test dưới cấp TEMP riêng cho dxos_core để chứng minh phần sửa tên bảng
# đứng độc lập với việc thu hồi TEMP.

async def _grant_temp_to_core(owner_conn) -> None:
    await owner_conn.execute(
        "DO $$ BEGIN EXECUTE format('GRANT TEMPORARY ON DATABASE %I TO dxos_core', current_database());"
        " END $$")


async def test_core_role_cannot_create_temp_tables(core_conn):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("CREATE TEMP TABLE x (a int)")


async def test_owner_keeps_temp(owner_conn):
    await owner_conn.execute("CREATE TEMP TABLE x (a int)")


async def test_temp_pii_erasures_cannot_unseal_data(owner_conn, core_conn, sealed_pii_record_id):
    await _grant_temp_to_core(owner_conn)
    rid = sealed_pii_record_id
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        async with core_conn.transaction():
            await core_conn.execute(
                "CREATE TEMP TABLE pii_erasures (record_id uuid, txid bigint, fields text[]) ON COMMIT DROP")
            await core_conn.execute(
                "INSERT INTO pg_temp.pii_erasures VALUES ($1, txid_current(), '{title}')", rid)
            await core_conn.execute("UPDATE core.records SET data = data - 'title' WHERE id=$1", rid)
    assert "title" in await _data(owner_conn, rid)


async def test_temp_records_cannot_open_sealed_record_for_upload(owner_conn, core_conn, sealed_record_id):
    await _grant_temp_to_core(owner_conn)
    await core_conn.execute("CREATE TEMP TABLE records (id uuid, wf_state text, seal_state text)")
    await core_conn.execute("INSERT INTO pg_temp.records VALUES ($1, NULL, 'NONE')", sealed_record_id)
    with pytest.raises(asyncpg.RaiseError, match="record_not_open"):
        await core_conn.execute(
            "INSERT INTO core.uploads(record_id, staging_key, original_name_hash, size)"
            " VALUES ($1, 'k', $2, 1)", sealed_record_id, "b" * 64)


async def test_temp_record_salts_cannot_swallow_salt(owner_conn, core_conn):
    await _grant_temp_to_core(owner_conn)
    await core_conn.execute("CREATE TEMP TABLE record_salts (record_id uuid, salt text)")
    rid = await core_conn.fetchval(
        "INSERT INTO core.records(app_id, collection, owner_sub)"
        " VALUES ('test-app', 'item', 'u') RETURNING id")
    assert await owner_conn.fetchval("SELECT salt FROM core.record_salts WHERE record_id=$1", rid)
    assert await core_conn.fetchval("SELECT count(*) FROM pg_temp.record_salts") == 0


async def test_every_core_plpgsql_function_pins_search_path(owner_conn):
    rows = await owner_conn.fetch(
        "SELECT p.proname, p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
        " JOIN pg_language l ON l.oid = p.prolang WHERE n.nspname = 'core' AND l.lanname = 'plpgsql'")
    names = {r["proname"] for r in rows}
    assert {"record_seal_guard", "record_salt_init", "upload_record_open", "object_identity_guard",
            "ledger_append_only", "salt_no_update", "record_workflow_guard", "pii_erasure_txid"} <= names
    for r in rows:
        assert r["proconfig"] == ["search_path=pg_catalog, core, pg_temp"], r["proname"]


# ---------- Migration 004: txid của bằng chứng xóa do DB đặt ----------

async def test_core_cannot_choose_erasure_txid(core_conn, record_id):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute(
            "INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by, txid)"
            " VALUES ($1, '{cccd}', 'agreement', 'u', 1)", record_id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute(
            "INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by, erased_at)"
            " VALUES ($1, '{cccd}', 'agreement', 'u', now())", record_id)
    await core_conn.execute(ERASE, record_id, ["cccd"])                          # cột cho phép: vẫn ghi được


async def test_erasure_txid_is_forced_to_current_transaction(owner_conn, record_id):
    async with owner_conn.transaction():
        await owner_conn.execute(
            "INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by, txid)"
            " VALUES ($1, '{cccd}', 'agreement', 'u', 12345)", record_id)
        assert await owner_conn.fetchval("SELECT txid FROM pii_erasures") == await owner_conn.fetchval(
            "SELECT txid_current()")


async def test_evidence_with_forged_txid_does_not_unlock(owner_conn, core_conn, sealed_pii_record_id):
    """Bằng chứng ghi ở transaction khác, dù cố đặt đúng txid của transaction đang xóa, không mở khóa được."""
    rid = sealed_pii_record_id
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        async with core_conn.transaction():
            victim_txid = await core_conn.fetchval("SELECT txid_current()")
            await owner_conn.execute(                                         # transaction khác, đã commit
                "INSERT INTO pii_erasures(record_id, fields, reason_code, erased_by, txid)"
                " VALUES ($1, '{cccd}', 'agreement', 'u', $2)", rid, victim_txid)
            await core_conn.execute(STRIP, rid, "cccd")
    assert "cccd" in await _data(owner_conn, rid)


async def test_seal_request_unique_constraint_is_named(owner_conn):
    assert await owner_conn.fetchval(
        "SELECT count(*) FROM pg_constraint"
        " WHERE conname = 'seal_requests_one_per_record' AND contype = 'u'") == 1


async def test_pii_scans_grants_and_constraints(core_conn):
    """006: dxos_core chỉ SELECT, INSERT; status lạ, findings âm, khóa trùng và khóa ngoại bị từ chối."""
    insert = "INSERT INTO pii_scans(sha256, status, findings, detector) VALUES ($1, $2, $3, 'd')"
    obj = ("INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
           " VALUES ($1, 1, 'application/pdf', 'CLEAN', $2)")
    await core_conn.execute(obj, "a" * 64, "k")
    await core_conn.execute(insert, "a" * 64, "DONE", 0)
    with pytest.raises(asyncpg.UniqueViolationError):
        await core_conn.execute(insert, "a" * 64, "DONE", 0)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await core_conn.execute(insert, "b" * 64, "DONE", 0)
    await core_conn.execute(obj, "c" * 64, "k2")
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(insert, "c" * 64, "LATER", 0)
    with pytest.raises(asyncpg.CheckViolationError):
        await core_conn.execute(insert, "c" * 64, "DONE", -1)
    for stmt in ("UPDATE pii_scans SET findings = 5", "DELETE FROM pii_scans"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await core_conn.execute(stmt)


async def test_pii_scans_redacted_link_constraints(core_conn):
    """007: liên kết tới bản che chỉ hợp lệ với hàng DONE có phát hiện và phải trỏ tới object có thật."""
    insert = ("INSERT INTO pii_scans(sha256, status, findings, detector, redacted_sha256)"
              " VALUES ($1, $2, $3, 'd', $4)")
    obj = ("INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
           " VALUES ($1, 1, 'application/pdf', 'CLEAN', $2)")
    for sha in ("a", "b", "c", "d"):
        await core_conn.execute(obj, sha * 64, "k" + sha)
    for status, findings in (("DONE", 0), ("TOO_LARGE", 0), ("FAILED", 0)):
        with pytest.raises(asyncpg.CheckViolationError):
            await core_conn.execute(insert, "a" * 64, status, findings, "b" * 64)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await core_conn.execute(insert, "a" * 64, "DONE", 2, "e" * 64)
    await core_conn.execute(insert, "a" * 64, "DONE", 2, "b" * 64)
    await core_conn.execute(insert, "c" * 64, "DONE", 0, None)
    linked = await core_conn.fetchval("SELECT redacted_sha256 FROM pii_scans WHERE sha256=$1", "a" * 64)
    assert linked == "b" * 64
