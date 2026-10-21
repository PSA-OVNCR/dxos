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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from dxos_core.db.migrate import apply_migrations, set_core_password
from dxos_core.db.pool import SEARCH_PATH, create_pool
from helpers.db import ensure_app

OWNER_DSN = os.environ.get(
    "DXOS_TEST_OWNER_DSN", "postgresql://dxos_owner:changeme-test@127.0.0.1:55432/dxos_test"
)
CORE_PASSWORD = "changeme-test-core"
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
async def core_pool(core_dsn: str) -> AsyncIterator[asyncpg.Pool]:
    pool = await create_pool(core_dsn)
    try:
        yield pool
    finally:
        await pool.close()


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


# ---------------------------------------------------------------- migration 003 (Plan 02 Task 2)
@pytest.fixture
async def other_record_id(core_conn: asyncpg.Connection) -> uuid.UUID:
    """Bản ghi thứ hai (test-app/item), khác ``record_id``."""
    return await _insert_record(core_conn)


@pytest.fixture
async def pending_app(core_conn: asyncpg.Connection) -> tuple[str, str]:
    """App ``test-flow`` 0.1.0 ở trạng thái PENDING (đích khóa ngoại của app_files/app_deployments)."""
    await ensure_app(core_conn, "test-flow", "0.1.0")
    return "test-flow", "0.1.0"


@pytest.fixture
async def sealed_pii_record_id(owner_conn: asyncpg.Connection) -> uuid.UUID:
    """Bản ghi test-app/item có hai trường PII (cccd, phone) và title, đã SEALED (đặt bằng owner)."""
    rid = await owner_conn.fetchval(
        "INSERT INTO records(app_id, collection, data, owner_sub)"
        " VALUES ('test-app', 'item', $1::jsonb, 'u1') RETURNING id",
        '{"title": "x", "cccd": "001099012345", "phone": "0912345678"}')
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", rid)
    return rid


@dataclass
class FreshDb:
    """DB tạm đã áp migration tới một mốc; dùng để thử migration mới trên dữ liệu cũ."""

    dsn: str

    async def _conn(self) -> asyncpg.Connection:
        return await _connect(self.dsn)

    async def insert_record(self) -> uuid.UUID:
        conn = await self._conn()
        try:
            return await _insert_record(conn)
        finally:
            await conn.close()

    async def apply(self, until: str) -> list[str]:
        return await apply_migrations(self.dsn, MIGRATIONS, until=until)

    async def salt_of(self, rid: uuid.UUID) -> str | None:
        conn = await self._conn()
        try:
            return await conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", rid)
        finally:
            await conn.close()


@pytest.fixture
async def fresh_db_at_002(owner_dsn: str) -> FreshDb:
    """DB trống đã áp 001 và 002 (chưa có 003)."""
    db = FreshDb(owner_dsn)
    assert await db.apply("002") == ["001_core.sql", "002_anchors.sql"]
    return db


# ---------------------------------------------------------------- kho S3 + worker (Task 14)
S3_ENDPOINT = os.environ.get("DXOS_TEST_S3_ENDPOINT", "http://127.0.0.1:58333")


@pytest.fixture(scope="session")
def s3_buckets(tmp_path_factory):
    """Một bộ bucket cho cả phiên test: SeaweedFS mất vài giây cho lần ghi đầu vào bucket mới."""
    from dxos_core.objects.storage import ObjectStore
    from dxos_core.settings import Settings

    secret = tmp_path_factory.mktemp("s3") / "key"
    secret.write_text("changeme-test", encoding="utf-8")
    prefix = f"t{uuid.uuid4().hex[:10]}"
    names = {"s3_bucket_staging": f"{prefix}-staging", "s3_bucket_objects": f"{prefix}-objects",
             "s3_bucket_quarantine": f"{prefix}-quarantine"}
    settings = Settings(database_url="unused", s3_endpoint=S3_ENDPOINT, s3_access_key_file=secret,
                        s3_secret_key_file=secret, openbao_token_file=secret, keycloak_issuer="unused",
                        keycloak_jwks_url="unused", actor_hmac_key_file=secret, anchor_repo_dir=secret,
                        **names)
    store = ObjectStore(settings)
    try:
        store.ensure_buckets()
    except Exception as exc:  # noqa: BLE001 (không có S3 thì bỏ qua như khi không có DB)
        msg = f"cần S3 (SeaweedFS) ở {S3_ENDPOINT} cho integration test ({type(exc).__name__})"
        if os.environ.get("DXOS_TEST_REQUIRE_DB") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    yield names
    store.drop_buckets()


@pytest.fixture
def s3_settings(make_settings, core_dsn, fake_clamd, s3_buckets, request):
    host, port = fake_clamd
    if request.config.getoption("--real-clamav"):
        host, _, p = os.environ.get("DXOS_TEST_CLAMD", "127.0.0.1:53310").partition(":")
        port = int(p)
    return make_settings(database_url=core_dsn, s3_endpoint=S3_ENDPOINT, clamd_host=host, clamd_port=port,
                         **s3_buckets)
