# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Việc ``ots_stamp``: biên nhận OpenTimestamps cho STH đã neo, calendar giả qua ``httpx.MockTransport``
(Plan 03 Task 14, P3-D10). Không gọi calendar thật (V32)."""

import base64
import dataclasses
import hashlib
import subprocess

import asyncpg
import httpx
import pytest
from dxos_core import worker
from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import enqueue
from dxos_core.ledger.anchor import sth_path
from dxos_core.ledger.ots import OTS_ATTEMPTS, OTS_JOB, detached_timestamp, ots_path, ots_request_digest
from dxos_core.ledger.sth import get_sth, make_sth
from helpers.local_signer import LocalSigner

pytestmark = pytest.mark.integration
GIT_SSH = "ssh -o BatchMode=yes"
KEY = b"changeme-test-hmac-key"
CAL_A, CAL_B = "https://a.calendar.test", "https://b.calendar.test"
PENDING = bytes.fromhex("83dfe30d2ef90c8e")


def git(cwd, *args) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def git_bytes(cwd, *args) -> bytes:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True).stdout


def reply_for(cal: str) -> bytes:
    uri = cal.encode()
    tag = hashlib.sha256(uri).digest()[:4]
    return b"\xf1\x04" + tag + b"\x08\x00" + PENDING + bytes([len(uri) + 1, len(uri)]) + uri


class FakeCalendars:
    """Calendar giả: ``down`` = tập calendar trả 503; ``calls`` = mọi request đã nhận."""

    def __init__(self) -> None:
        self.down: set[str] = set()
        self.calls: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        cal = f"{req.url.scheme}://{req.url.host}"
        if cal in self.down:
            return httpx.Response(503, text="calendar bận")
        assert req.url.path == "/digest" and len(req.content) == 32
        return httpx.Response(200, content=reply_for(cal))


@pytest.fixture
def bare_remote(tmp_path):
    remote = tmp_path / "anchor-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


@pytest.fixture
def calendars():
    return FakeCalendars()


@pytest.fixture
async def make_ctx(make_settings, core_dsn, bare_remote, tmp_path, calendars):
    pool = await create_pool(core_dsn)
    signer = LocalSigner()                     # một khóa cho mọi ctx: tệp keys/ trong repo neo không đổi

    def make(ots_calendars: str) -> WorkerContext:
        s = make_settings(database_url=core_dsn, anchor_repo_dir=tmp_path / "worker-clone",
                          anchor_remote=f"file://{bare_remote}", anchor_git_ssh_command=GIT_SSH,
                          ots_calendars=ots_calendars)
        return WorkerContext(pool=pool, store=None, settings=s, hmac_key=KEY, signer=signer,
                             http_transport=httpx.MockTransport(calendars))
    try:
        yield make
    finally:
        await pool.close()


async def run_all(ctx, conn) -> None:
    """Chạy mọi việc tới hạn; việc hẹn giờ sau được kéo về ngay một lần (như lịch của job tới hạn)."""
    while await worker.run_once(ctx):
        pass


async def anchored_size(conn) -> int:
    return await conn.fetchval("SELECT tree_size FROM anchors")


# ---------- Step 2 của brief ----------

async def test_anchor_then_receipts_and_ots_file_in_bare_repo(make_ctx, core_conn, bare_remote, calendars):
    ctx = make_ctx(f"{CAL_A},{CAL_B}")
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    size = await anchored_size(core_conn)
    rows = await core_conn.fetch("SELECT tree_size, calendar, reply FROM ots_receipts ORDER BY calendar")
    assert [(r["tree_size"], r["calendar"]) for r in rows] == [(size, CAL_A), (size, CAL_B)]
    assert [bytes(r["reply"]) for r in rows] == [reply_for(CAL_A), reply_for(CAL_B)]
    th = await get_sth(core_conn, size)
    digest = ots_request_digest(dataclasses.asdict(th))
    ots = git_bytes(bare_remote, "show", f"main:{ots_path(size)}")
    assert ots == detached_timestamp(digest, [reply_for(CAL_A), reply_for(CAL_B)])
    # digest là SHA-256 của đúng tệp sth/<n>.json đã neo: `ots verify -f sth/<n>.json` kiểm trực tiếp
    assert hashlib.sha256(git_bytes(bare_remote, "show", f"main:{sth_path(size)}")).digest() == digest
    assert git(bare_remote, "log", "-1", "--format=%s", "main") == f"ots {size}"
    assert {r["state"] for r in await core_conn.fetch("SELECT state FROM jobs")} == {"DONE"}
    assert all(c.method == "POST" for c in calendars.calls) and len(calendars.calls) == 2


async def test_calendar_down_anchoring_still_done_and_job_retries(make_ctx, core_conn, bare_remote,
                                                                  calendars):
    ctx = make_ctx(f"{CAL_A},{CAL_B}")
    calendars.down = {CAL_A, CAL_B}
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    size = await anchored_size(core_conn)                            # neo vẫn xong
    assert git(bare_remote, "log", "-1", "--format=%s", "main") == f"sth {size}"
    job = await core_conn.fetchrow("SELECT state, run_after > now() AS later, last_error FROM jobs"
                                   " WHERE kind=$1", OTS_JOB)
    assert job["state"] == "QUEUED" and job["later"] and CAL_A in job["last_error"]
    assert await core_conn.fetchval("SELECT count(*) FROM ots_receipts") == 0

    calendars.down = {CAL_B}                                         # A hồi phục, B vẫn lỗi
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", OTS_JOB)
    await run_all(ctx, core_conn)
    assert await core_conn.fetchval("SELECT calendar FROM ots_receipts") == CAL_A
    assert await core_conn.fetchval("SELECT state FROM jobs WHERE kind=$1", OTS_JOB) == "QUEUED"
    assert ots_path(size) not in git(bare_remote, "ls-tree", "-r", "--name-only", "main")

    calendars.down = set()                                           # cả hai: commit một tệp đủ hai nhánh
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", OTS_JOB)
    n_calls = len(calendars.calls)
    await run_all(ctx, core_conn)
    assert len(calendars.calls) == n_calls + 1                       # chỉ hỏi lại calendar còn thiếu
    assert await core_conn.fetchval("SELECT state FROM jobs WHERE kind=$1", OTS_JOB) == "DONE"
    th = await get_sth(core_conn, size)
    assert git_bytes(bare_remote, "show", f"main:{ots_path(size)}") == detached_timestamp(
        ots_request_digest(dataclasses.asdict(th)), [reply_for(CAL_A), reply_for(CAL_B)])


async def test_partial_receipts_committed_after_last_attempt(make_ctx, core_conn, bare_remote, calendars):
    ctx = make_ctx(f"{CAL_A},{CAL_B}")
    calendars.down = {CAL_B}
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    for _ in range(OTS_ATTEMPTS):
        await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", OTS_JOB)
        await run_all(ctx, core_conn)
    size = await anchored_size(core_conn)
    assert await core_conn.fetchval("SELECT state FROM jobs WHERE kind=$1", OTS_JOB) == "DONE"
    th = await get_sth(core_conn, size)
    assert git_bytes(bare_remote, "show", f"main:{ots_path(size)}") == detached_timestamp(
        ots_request_digest(dataclasses.asdict(th)), [reply_for(CAL_A)])


async def test_all_calendars_down_job_fails_after_attempts_anchor_untouched(make_ctx, core_conn, calendars):
    ctx = make_ctx(CAL_A)
    calendars.down = {CAL_A}
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    for _ in range(OTS_ATTEMPTS):
        await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", OTS_JOB)
        await run_all(ctx, core_conn)
    states = dict(await core_conn.fetch("SELECT kind, state FROM jobs"))
    assert states == {"anchor_sth": "DONE", OTS_JOB: "FAILED"}
    assert await core_conn.fetchval("SELECT count(*) FROM anchors") == 1
    assert len(calendars.calls) == OTS_ATTEMPTS                      # một lần mỗi lượt, không vòng lặp nóng


async def test_no_calendars_means_no_request_and_no_job(make_ctx, core_conn, bare_remote, calendars):
    ctx = make_ctx("")
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    assert await core_conn.fetchval("SELECT count(*) FROM anchors") == 1
    assert calendars.calls == []
    assert await core_conn.fetchval("SELECT count(*) FROM jobs WHERE kind=$1", OTS_JOB) == 0
    assert "ots/" not in git(bare_remote, "ls-tree", "-r", "--name-only", "main")


async def test_calendars_removed_after_enqueue_no_request(make_ctx, core_conn, calendars):
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(make_ctx(CAL_A), core_conn)
    calendars.calls.clear()
    size = await anchored_size(core_conn)
    await enqueue(core_conn, OTS_JOB, {"tree_size": size})
    await run_all(make_ctx(""), core_conn)
    assert calendars.calls == []


async def test_reanchoring_same_sth_does_not_enqueue_twice(make_ctx, core_conn):
    ctx = make_ctx(CAL_A)
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    size = await anchored_size(core_conn)
    await enqueue(core_conn, "anchor_sth", {"tree_size": size})
    await run_all(ctx, core_conn)
    assert await core_conn.fetchval("SELECT count(*) FROM jobs WHERE kind=$1", OTS_JOB) == 1


async def test_garbage_reply_not_stored(make_ctx, core_conn):
    ctx = make_ctx(CAL_A)
    ctx.http_transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>ok</html>"))
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    assert await core_conn.fetchval("SELECT count(*) FROM ots_receipts") == 0
    assert "OtsFormatError" in await core_conn.fetchval("SELECT last_error FROM jobs WHERE kind=$1", OTS_JOB)


# ---------- bảng chỉ-thêm (như anchors) ----------

async def test_ots_receipts_append_only(core_conn, owner_conn):
    th = await make_sth(core_conn, LocalSigner())
    await core_conn.execute("INSERT INTO ots_receipts(tree_size, calendar, reply) VALUES ($1, $2, $3)",
                            th.tree_size, CAL_A, reply_for(CAL_A))
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("UPDATE ots_receipts SET reply=$1", b"x")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("DELETE FROM ots_receipts")
    for sql in ("UPDATE ots_receipts SET reply='\\x00'", "DELETE FROM ots_receipts", "TRUNCATE ots_receipts"):
        with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
            await owner_conn.execute(sql)
    assert await core_conn.fetchval("SELECT count(*) FROM ots_receipts") == 1


# ---------- gói bằng chứng: "timestamps" cho STH đã neo ----------

async def test_bundle_carries_timestamps_and_witness_notes_it(flow, verify, local_signer):
    from dxos_witness.bundle import verify_bundle

    await flow.install_verify_policy("0.2.0", require_file=False)
    sid, _ = await flow.sealed_ids()
    async with flow.db.acquire() as c:
        th = await make_sth(c, local_signer)
    await flow.db.execute("INSERT INTO anchors(tree_size, repo, commit_sha) VALUES ($1, 'file:///r.git', $2)",
                          th.tree_size, "a" * 40)
    b = (await verify.get(f"/verify/v1/seals/{sid}/bundle")).json()
    assert "timestamps" not in b                                     # chưa có biên nhận: không có khóa
    await flow.db.execute("INSERT INTO ots_receipts(tree_size, calendar, reply) VALUES ($1, $2, $3)",
                          th.tree_size, CAL_A, reply_for(CAL_A))
    b = (await verify.get(f"/verify/v1/seals/{sid}/bundle")).json()
    expected = detached_timestamp(ots_request_digest(dataclasses.asdict(th)), [reply_for(CAL_A)])
    assert b["timestamps"] == [{"type": "opentimestamps", "tree_size": th.tree_size,
                                "ots": base64.b64encode(expected).decode()}]
    r = verify_bundle(b, anchor_dir=None)
    assert r.ok and "OTS:" in r.detail and "ots verify" in r.detail, r.detail


# ---------- fix vòng 1: calendar chậm/hỏng không giữ worker; hàng cũ không làm hỏng gói ----------

async def test_trickling_calendar_cut_by_total_deadline(make_ctx, core_conn, calendars, monkeypatch):
    import asyncio
    import time

    from dxos_core.ledger import ots

    monkeypatch.setattr(ots, "CALENDAR_TIMEOUT_S", 0.5)

    async def trickle():
        for b in reply_for(CAL_A):
            await asyncio.sleep(0.2)
            yield bytes([b])

    def handler(req):
        if req.url.host == "a.calendar.test":
            return httpx.Response(200, content=trickle())
        return calendars(req)

    ctx = make_ctx(f"{CAL_A},{CAL_B}")
    ctx.http_transport = httpx.MockTransport(handler)
    await enqueue(core_conn, "anchor_sth", {})
    t0 = time.monotonic()
    await run_all(ctx, core_conn)
    assert time.monotonic() - t0 < 5
    assert await core_conn.fetchval("SELECT count(*) FROM anchors") == 1
    assert await core_conn.fetchval("SELECT calendar FROM ots_receipts") == CAL_B
    job = await core_conn.fetchrow("SELECT state, last_error FROM jobs WHERE kind=$1", OTS_JOB)
    assert job["state"] == "QUEUED" and f"{CAL_A}: TimeoutError" in job["last_error"]


async def test_db_error_on_one_calendar_does_not_cut_the_loop(make_ctx, core_conn, owner_conn):
    await owner_conn.execute(f"""
        CREATE FUNCTION core.test_reject_a() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.calendar = '{CAL_A}' THEN RAISE EXCEPTION 'tu_choi_thu'; END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER test_reject_a BEFORE INSERT ON core.ots_receipts
            FOR EACH ROW EXECUTE FUNCTION core.test_reject_a();
    """)
    ctx = make_ctx(f"{CAL_A},{CAL_B}")
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(ctx, core_conn)
    assert await core_conn.fetchval("SELECT calendar FROM ots_receipts") == CAL_B
    job = await core_conn.fetchrow("SELECT state, last_error FROM jobs WHERE kind=$1", OTS_JOB)
    assert job["state"] == "QUEUED" and "tu_choi_thu" in job["last_error"]


async def test_committed_but_unpushed_file_is_pushed_not_requeried(make_ctx, core_conn, bare_remote,
                                                                  calendars):
    hook = bare_remote / "hooks" / "pre-receive"
    await enqueue(core_conn, "anchor_sth", {})
    await run_all(make_ctx(CAL_A), core_conn)        # lượt đầu bình thường: clone của worker đã có
    size = await anchored_size(core_conn)
    assert ots_path(size) in git(bare_remote, "ls-tree", "-r", "--name-only", "main")
    # STH mới; lần đẩy tệp ots bị remote từ chối SAU khi đã commit ở clone.
    from dxos_core.ledger.log import append
    await append(core_conn, type="object.read", subject="s", body={}, hmac_key=KEY)
    await enqueue(core_conn, "anchor_sth", {})
    ctx_a = make_ctx(CAL_A)
    async with ctx_a.pool.acquire() as c:            # chạy riêng job neo, để hook chỉ chặn lần đẩy tệp ots
        from dxos_core.jobs.queue import claim
        from dxos_core.ledger.anchor_job import process_anchor_job
        await process_anchor_job(ctx_a, await claim(c, ["anchor_sth"]))
    size2 = await core_conn.fetchval("SELECT max(tree_size) FROM anchors")
    assert size2 > size
    hook.write_text("#!/bin/sh\necho 'tam tu choi' >&2\nexit 1\n")
    hook.chmod(0o755)
    await run_all(ctx_a, core_conn)
    job = await core_conn.fetchrow(
        "SELECT state, last_error FROM jobs WHERE kind=$1 AND payload->>'tree_size'=$2", OTS_JOB, str(size2))
    assert job["state"] == "QUEUED" and "PUSH_FAILED" in job["last_error"]
    assert (ctx_a.settings.anchor_repo_dir / ots_path(size2)).is_file()           # đã commit ở clone
    hook.unlink()
    calendars.calls.clear()
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", OTS_JOB)
    await run_all(make_ctx(f"{CAL_A},{CAL_B}"), core_conn)    # thêm calendar B: không được hỏi nữa
    assert calendars.calls == []
    job = await core_conn.fetchrow("SELECT state FROM jobs WHERE kind=$1 AND payload->>'tree_size'=$2",
                                   OTS_JOB, str(size2))
    assert job["state"] == "DONE"
    th = await get_sth(core_conn, size2)
    assert git_bytes(bare_remote, "show", f"main:{ots_path(size2)}") == detached_timestamp(
        ots_request_digest(dataclasses.asdict(th)), [reply_for(CAL_A)])


async def test_unparseable_stored_rows_are_skipped_for_bundle(core_conn):
    from dxos_core.ledger.ots import receipts_ots

    th = await make_sth(core_conn, LocalSigner())
    sth = dataclasses.asdict(th)
    # Hàng mà bộ phân tích cũ (trước fix vòng 1) nhận, trình đọc chính thức từ chối: thông điệp 8032 byte.
    bad = (b"\xf0\xa0\x1f" + b"a" * 4000 + b"\xf0\xa0\x1f" + b"b" * 4000
           + b"\x00" + PENDING + b"\x0a\x09https://x")
    await core_conn.execute("INSERT INTO ots_receipts(tree_size, calendar, reply) VALUES ($1, $2, $3)",
                            th.tree_size, "https://cu.calendar.test", bad)
    assert await receipts_ots(core_conn, th.tree_size, sth) is None                # chỉ có hàng hỏng
    await core_conn.execute("INSERT INTO ots_receipts(tree_size, calendar, reply) VALUES ($1, $2, $3)",
                            th.tree_size, CAL_A, reply_for(CAL_A))
    assert await receipts_ots(core_conn, th.tree_size, sth) == detached_timestamp(
        ots_request_digest(sth), [reply_for(CAL_A)])
