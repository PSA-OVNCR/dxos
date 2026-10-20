# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration: app và worker nói chuyện với PostgreSQL thật qua role dxos_core."""

import pytest
from dxos_core import worker
from dxos_core.app import create_app
from dxos_core.db.pool import create_pool
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_readyz_ok_after_migrations(make_settings, core_dsn):
    with TestClient(create_app(make_settings(database_url=core_dsn))) as c:
        r = c.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "schema": "001_core.sql"}


async def test_pool_uses_core_search_path(core_dsn):
    pool = await create_pool(core_dsn)
    try:
        async with pool.acquire() as conn:
            assert await conn.fetchval("SHOW search_path") == "core"
            assert await conn.fetchval("SELECT count(*) FROM ledger_entries") == 0
    finally:
        await pool.close()


async def test_worker_run_once_touches_heartbeat(make_settings, core_dsn, tmp_path):
    hb = tmp_path / "hb"
    await worker.run(make_settings(database_url=core_dsn), heartbeat=hb, once=True)
    assert worker.heartbeat_fresh(hb, max_age=60)
