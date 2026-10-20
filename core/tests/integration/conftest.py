# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture integration: mỗi test có một database PostgreSQL mới, xóa khi xong.

Cần PostgreSQL với role `dxos_owner` có quyền tạo database, ví dụ:
    docker compose -f deploy/compose.test.yaml up -d --wait core-db
Đổi địa chỉ bằng biến DXOS_TEST_OWNER_DSN. Không có DB thì test bị bỏ qua,
trừ khi đặt DXOS_TEST_REQUIRE_DB=1 (CI) thì báo lỗi.
"""

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from dxos_core.db.migrate import apply_migrations, set_core_password
from dxos_core.db.pool import SEARCH_PATH

OWNER_DSN = os.environ.get(
    "DXOS_TEST_OWNER_DSN", "postgresql://dxos_owner:changeme-test@127.0.0.1:55432/dxos_test"
)
CORE_PASSWORD = "changeme-test-core"  # noqa: S105 (chỉ dùng cho DB test)
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _with(dsn: str, *, user: str | None = None, password: str | None = None, db: str | None = None) -> str:
    parts = urlsplit(dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    u = user or parts.username or ""
    p = password if password is not None else (parts.password or "")
    auth = f"{u}:{p}@" if p else f"{u}@"
    path = f"/{db}" if db else parts.path
    return urlunsplit((parts.scheme, f"{auth}{host}{port}", path, parts.query, ""))


async def _connect(dsn: str) -> asyncpg.Connection:
    return await asyncpg.connect(dsn, server_settings={"search_path": SEARCH_PATH}, timeout=5)


@pytest.fixture
async def owner_dsn() -> AsyncIterator[str]:
    """DSN của role dxos_owner tới một database trống (chưa migration)."""
    try:
        admin = await asyncpg.connect(OWNER_DSN, timeout=5)
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        msg = f"cần PostgreSQL cho integration test ({type(exc).__name__})"
        if os.environ.get("DXOS_TEST_REQUIRE_DB") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    name = f"dxos_t_{uuid.uuid4().hex[:12]}"
    await admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _with(OWNER_DSN, db=name)
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


@pytest.fixture
async def migrated_dsn(owner_dsn: str) -> str:
    await apply_migrations(owner_dsn, MIGRATIONS)
    conn = await asyncpg.connect(owner_dsn)
    try:
        await set_core_password(conn, CORE_PASSWORD)
    finally:
        await conn.close()
    return owner_dsn


@pytest.fixture
def core_dsn(migrated_dsn: str) -> str:
    return _with(migrated_dsn, user="dxos_core", password=CORE_PASSWORD)


@pytest.fixture
async def owner_conn(migrated_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    conn = await _connect(migrated_dsn)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def core_conn(core_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    conn = await _connect(core_dsn)
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def seeded_ledger_row(core_conn: asyncpg.Connection) -> int:
    await core_conn.execute(
        "INSERT INTO ledger_entries(idx, ts, app_id, actor_ref, type, subject, body_sha256, leaf_hash)"
        " VALUES (0, '2026-10-20T00:00:00Z', NULL, NULL, 'record.created', 'r1', $1, $2)",
        "0" * 64,
        b"\x00" * 32,
    )
    return 0


async def _insert_record(conn: asyncpg.Connection) -> uuid.UUID:
    return await conn.fetchval(
        "INSERT INTO records(app_id, collection, data, owner_sub)"
        " VALUES ('test-app', 'item', '{\"a\": 1}', 'u1') RETURNING id"
    )


@pytest.fixture
async def record_id(core_conn: asyncpg.Connection) -> uuid.UUID:
    return await _insert_record(core_conn)


@pytest.fixture
async def pending_record_id(owner_conn: asyncpg.Connection) -> uuid.UUID:
    rid = await _insert_record(owner_conn)
    await owner_conn.execute("UPDATE records SET seal_state='SEAL_PENDING' WHERE id=$1", rid)
    return rid


@pytest.fixture
async def sealed_record_id(owner_conn: asyncpg.Connection) -> uuid.UUID:
    rid = await _insert_record(owner_conn)
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", rid)
    return rid
