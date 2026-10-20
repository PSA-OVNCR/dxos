# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test hàng đợi việc trên PostgreSQL (FOR UPDATE SKIP LOCKED)."""

import asyncio

import pytest
from dxos_core.jobs.queue import claim, complete, enqueue, fail, retry_later

pytestmark = pytest.mark.integration


async def test_enqueue_claim_complete(core_conn):
    jid = await enqueue(core_conn, "scan", {"upload_id": "u1"})
    job = await claim(core_conn, ["scan"])
    assert (job.id, job.kind, job.payload, job.attempts) == (jid, "scan", {"upload_id": "u1"}, 1)
    assert await claim(core_conn, ["scan"]) is None          # đang RUNNING
    await complete(core_conn, jid)
    assert await core_conn.fetchval("SELECT state FROM jobs WHERE id=$1", jid) == "DONE"


async def test_kind_filter_and_order(core_conn):
    a = await enqueue(core_conn, "anchor_sth", {})
    b = await enqueue(core_conn, "scan", {})
    c = await enqueue(core_conn, "scan", {})
    assert (await claim(core_conn, ["scan"])).id == b
    assert (await claim(core_conn, ["scan"])).id == c
    assert (await claim(core_conn, ["anchor_sth", "scan"])).id == a


async def test_retry_later_delays(core_conn):
    jid = await enqueue(core_conn, "scan", {})
    await claim(core_conn, ["scan"])
    await retry_later(core_conn, jid, 3600)
    assert await claim(core_conn, ["scan"]) is None
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE id=$1", jid)
    assert (await claim(core_conn, ["scan"])).attempts == 2


async def test_fail_is_terminal(core_conn):
    jid = await enqueue(core_conn, "scan", {})
    await claim(core_conn, ["scan"])
    await fail(core_conn, jid, "payload hỏng")
    row = await core_conn.fetchrow("SELECT state, last_error FROM jobs WHERE id=$1", jid)
    assert tuple(row) == ("FAILED", "payload hỏng")
    assert await claim(core_conn, ["scan"]) is None


async def test_stale_running_job_is_reclaimed(core_conn):
    jid = await enqueue(core_conn, "scan", {})
    await claim(core_conn, ["scan"])
    await core_conn.execute("UPDATE jobs SET updated_at=now() - interval '10 minutes' WHERE id=$1", jid)
    assert (await claim(core_conn, ["scan"])).id == jid


async def test_concurrent_claims_never_share_a_job(core_pool):
    async with core_pool.acquire() as c:
        for _ in range(20):
            await enqueue(c, "scan", {})

    async def worker():
        got = []
        async with core_pool.acquire() as c:
            while (j := await claim(c, ["scan"])) is not None:
                got.append(j.id)
        return got

    results = await asyncio.gather(*(worker() for _ in range(5)))
    ids = [i for r in results for i in r]
    assert len(ids) == 20 and len(set(ids)) == 20
