# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test migration 001_core.sql: ledger chỉ-thêm, niêm phong, quyền role (Plan 01 Task 8)."""

import shutil
from pathlib import Path

import asyncpg
import pytest
from dxos_core.db.migrate import MigrationError, apply_migrations

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
pytestmark = pytest.mark.integration


# ---------- Các test do Plan 01 Task 8 quy định ----------

async def test_migrations_idempotent(owner_dsn):
    first = await apply_migrations(owner_dsn, MIGRATIONS)
    second = await apply_migrations(owner_dsn, MIGRATIONS)
    assert first == ["001_core.sql", "002_anchors.sql"] and second == []


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
    await owner_conn.execute("UPDATE records SET wf_state='done', seal_state='REVOKED' WHERE id=$1",
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
    assert await core_conn.fetchval("SELECT count(*) FROM schema_migrations") == 2
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("DELETE FROM schema_migrations")


async def test_all_spec_tables_exist(owner_conn):
    names = {r["table_name"] for r in await owner_conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='core'")}
    assert {"apps", "records", "sequences", "uploads", "objects", "object_refs", "pii_findings",
            "seals", "ledger_entries", "tree_heads", "jobs", "schema_migrations", "anchors"} <= names


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
        assert applied == ["001_core.sql", "002_anchors.sql"]
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
