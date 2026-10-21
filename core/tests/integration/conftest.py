# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture integration: mỗi test có một database PostgreSQL mới, xóa khi xong.

Cần PostgreSQL với role `dxos_owner` có quyền tạo database, ví dụ:
    docker compose -f deploy/compose.test.yaml up -d --wait core-db
Đổi địa chỉ bằng biến DXOS_TEST_OWNER_DSN. Không có DB thì test bị bỏ qua,
trừ khi đặt DXOS_TEST_REQUIRE_DB=1 (CI) thì báo lỗi.
"""

import hashlib
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


# ---------------------------------------------------------------- Flowable (Plan 02 Task 4)
FLOWABLE_URL = os.environ.get("DXOS_TEST_FLOWABLE_URL", "http://127.0.0.1:58080/flowable-rest/service")
FLOWABLE_USER = os.environ.get("DXOS_TEST_FLOWABLE_USER", "rest-admin")
FLOWABLE_PASSWORD = os.environ.get("DXOS_TEST_FLOWABLE_PASSWORD", "changeme-test")


@pytest.fixture
async def flowable_client():
    """FlowableClient tới Flowable 7.1.0 thật (compose.test, H2, dùng chung giữa các lần chạy test).

    Không với tới được thì bỏ qua, trừ khi DXOS_TEST_REQUIRE_DB=1 (CI) thì báo lỗi.
    Test phải chịu được dữ liệu cũ: dùng business key riêng mỗi lần và chọn task theo process instance.
    """
    from dxos_core.workflow.flowable import FlowableClient, WorkflowUnavailable

    client = FlowableClient(FLOWABLE_URL, FLOWABLE_USER, FLOWABLE_PASSWORD, timeout_s=15.0)
    try:
        await client.ping()
    except WorkflowUnavailable as exc:
        msg = f"cần Flowable ở {FLOWABLE_URL} cho integration test ({exc})"
        if os.environ.get("DXOS_TEST_REQUIRE_DB") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    return client


# ---------------------------------------------------------------- guard (Plan 02 Task 5)
@pytest.fixture
async def flow_record_with_uploads(core_conn: asyncpg.Connection) -> dict:
    """Kwargs của ``load_guard_input`` cho một bản ghi test-flow/doc (owner ``author-1``, người gọi ``rev-1``
    có role reviewer) với ba upload: một CLEAN (có object_ref ``original``), một INFECTED (không có
    object_ref), một STAGING."""
    from helpers.manifests import P, manifest

    m = manifest("test-flow")
    await ensure_app(core_conn, "test-flow", "0.1.0")
    rid = await core_conn.fetchval(
        "INSERT INTO records(app_id, collection, data, owner_sub)"
        " VALUES ('test-flow', 'doc', $1::jsonb, 'author-1') RETURNING id", '{"title": "Hồ sơ"}')
    clean, infected = "c" * 64, "f" * 64
    await core_conn.execute(
        "INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
        " VALUES ($1, 1, 'application/pdf', 'CLEAN', 'k-clean'),"
        " ($2, 1, 'application/pdf', 'INFECTED', 'k-bad')",
        clean, infected)
    await core_conn.execute("INSERT INTO object_refs(record_id, sha256, role) VALUES ($1, $2, 'original')",
                            rid, clean)
    for status, sha in (("CLEAN", clean), ("INFECTED", infected), ("STAGING", None)):
        await core_conn.execute(
            "INSERT INTO uploads(record_id, staging_key, original_name_hash, size, status, sha256)"
            " VALUES ($1, 'k', $2, 1, $3, $4)", rid, "b" * 64, status, sha)
    record = await core_conn.fetchrow("SELECT * FROM records WHERE id=$1", rid)
    return {"record": record, "spec": m.collections["doc"], "m": m,
            "p": P("rev-1", ["app:test-flow:reviewer"]), "task_assignee": None}


# ---------------------------------------------------------------- ký số (dùng chung; chuyển từ test_sth.py)
@pytest.fixture
def local_signer():
    """Signer ed25519 trong bộ nhớ (``helpers.local_signer.LocalSigner``): seal-key và sth-key phiên bản 1."""
    from helpers.local_signer import LocalSigner

    return LocalSigner()


@pytest.fixture
def failing_signer():
    """Signer luôn ném ``KmsUnavailable`` (OpenBao bị khóa hoặc mất kết nối)."""
    from helpers.local_signer import FailingSigner

    return FailingSigner()


# ---------------------------------------------------------------- cầu nối quy trình (Plan 02 Task 6)
@pytest.fixture
async def flow(s3_settings, core_conn, core_dsn, test_jwks, flowable_client, local_signer, tmp_path):
    """``FlowHarness`` (helpers/flow.py): API thật (S3, fake clamd, Flowable thật, ``local_signer``) với
    ``test-flow`` 0.1.0 đã cài và ACTIVE; khi xong hủy mọi instance Flowable của DB test này."""
    from dxos_core.jobs.context import WorkerContext
    from dxos_core.objects.storage import ObjectStore
    from dxos_core.settings import read_secret
    from helpers.api import running_api
    from helpers.flow import FlowHarness

    password = tmp_path / "flowable-password"
    password.write_text(FLOWABLE_PASSWORD, encoding="utf-8")
    settings = s3_settings.model_copy(update={
        "flowable_url": FLOWABLE_URL, "flowable_user": FLOWABLE_USER, "flowable_password_file": password})
    pool = await create_pool(core_dsn)
    try:
        async with running_api(settings, signer=local_signer) as api:
            ctx = WorkerContext(pool=pool, store=ObjectStore(settings), settings=settings,
                                hmac_key=read_secret(settings.actor_hmac_key_file).encode("utf-8"))
            harness = FlowHarness(api, core_conn, flowable_client, ctx)
            try:
                await harness.install_version("0.1.0")
                yield harness
            finally:
                await harness.close()
    finally:
        await pool.close()


@pytest.fixture
async def other_app_task(flow, flowable_client):
    """Id một task đang mở của quy trình app khác (``other-flow``), có businessKey là một bản ghi test-app
    đang ``running`` đúng instance đó; hủy instance khi xong."""
    from dxos_core.registry.bpmn import parse_bpmn, render_bpmn
    from helpers.flow import BPMN_FILE

    xml = BPMN_FILE.read_bytes().replace(b"test-flow", b"other-flow")
    rendered = render_bpmn(parse_bpmn(xml, app_id="other-flow", seal_end=None))
    name = f"other-flow@it#{hashlib.sha256(rendered).hexdigest()[:16]}"
    definition = await flowable_client.definition_id(
        await flowable_client.deploy(name, "other-review.bpmn20.xml", rendered))
    rid = await _insert_record(flow.conn)
    iid = await flowable_client.start(definition, str(rid), {"dxos_record_id": str(rid)})
    await flow.conn.execute("UPDATE records SET wf_instance_id=$2, wf_state='running' WHERE id=$1", rid, iid)
    try:
        [task] = [t for t in await flowable_client.list_tasks(["app:other-flow:reviewer"], "other-flow.")
                  if t.process_instance_id == iid]
        yield task.id
    finally:
        await flowable_client.cancel(iid, "dxos:test-teardown")


@pytest.fixture
def break_finalize_once(monkeypatch):
    """Bước hoàn tất phía DB (``reconcile.finalize``) ném lỗi đúng một lần, sau khi Flowable đã chạy."""
    from dxos_core.workflow import reconcile

    real, left = reconcile.finalize, [1]

    async def broken(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise RuntimeError("DB lỗi giả lập sau khi Flowable đã hoàn thành task")
        return await real(*args, **kwargs)

    monkeypatch.setattr(reconcile, "finalize", broken)


@pytest.fixture
def flowable_down_once(flow, monkeypatch):
    """Lần gọi ``complete`` đầu tiên của API tới Flowable lỗi mạng (không tới được Flowable)."""
    from dxos_core.workflow.flowable import WorkflowUnavailable

    client = flow.api.app.state.flowable
    real, left = client.complete, [1]

    async def down(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise WorkflowUnavailable("Flowable ConnectError (giả lập)")
        return await real(*args, **kwargs)

    monkeypatch.setattr(client, "complete", down)


@pytest.fixture
def guard_flips_after_flowable(flow, monkeypatch):
    """Guard đổi kết quả giữa lúc gọi Flowable và lúc hoàn tất: lần ``evaluate`` đầu tiên sau mỗi lần
    ``complete`` thành công trả ``attachments_clean`` sai (409)."""
    from dxos_core.workflow import guards

    client = flow.api.app.state.flowable
    real_complete, real_evaluate, flipped = client.complete, guards.evaluate, [False]

    async def complete(*args, **kwargs):
        await real_complete(*args, **kwargs)
        flipped[0] = True

    def evaluate(gs, gi):
        if flipped[0]:
            flipped[0] = False
            return guards.GuardFailure("attachments_clean", "attachments_not_clean", 409)
        return real_evaluate(gs, gi)

    monkeypatch.setattr(client, "complete", complete)
    monkeypatch.setattr(guards, "evaluate", evaluate)
