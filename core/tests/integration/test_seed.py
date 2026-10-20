# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Nạp manifest tạm thời (Plan 01 Task 17, ops/seed_manifests.py)."""

import pytest
from dxos_core.registry.seed import seed
from dxos_core.registry.store import get_active
from helpers.manifests import PATHS

pytestmark = pytest.mark.integration


async def test_seed_activates_and_is_idempotent(core_dsn, core_conn):
    paths = [PATHS["test-app"], PATHS["phong-ho-so"], PATHS["chung-nhan"]]
    first = await seed(core_dsn, paths, "seed", b"k")
    second = await seed(core_dsn, paths, "seed", b"k")
    assert first == ["test-app@0.1.0", "phong-ho-so@1.0.0", "chung-nhan@1.0.0"]
    assert all(s.endswith("(đã ACTIVE)") for s in second)
    assert (await get_active(core_conn, "phong-ho-so")).app.name == "Phòng hồ sơ số"
    types = [r["type"] for r in await core_conn.fetch("SELECT type FROM ledger_entries ORDER BY idx")]
    assert types == ["app.submitted", "app.installed"] * 3
