# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration: cấp số văn bản, có đánh số lại theo năm (spec 25.4, P2-D26)."""

import pytest
from dxos_core.records.sequences import next_sequence

pytestmark = pytest.mark.integration


async def test_yearly_sequence_restarts_and_continues_on_switch(core_conn):
    assert [await next_sequence(core_conn, "test-app", "item.no") for _ in range(3)] == [1, 2, 3]
    assert await next_sequence(core_conn, "test-app", "item.no", year=2026) == 4  # chuyển chế độ: tiếp nối
    assert await next_sequence(core_conn, "test-app", "item.no", year=2026) == 5
    assert await next_sequence(core_conn, "test-app", "item.no", year=2027) == 1          # sang năm: từ 1


async def test_yearly_sequence_without_legacy_counter_starts_at_one(core_conn):
    assert await next_sequence(core_conn, "test-app", "doc.ref", year=2026) == 1
    assert await next_sequence(core_conn, "test-app", "doc.ref", year=2026) == 2


async def test_yearly_counters_are_per_app_and_name(core_conn):
    await next_sequence(core_conn, "test-app", "a.no", year=2026)
    assert await next_sequence(core_conn, "other-app", "a.no", year=2026) == 1
    assert await next_sequence(core_conn, "test-app", "b.no", year=2026) == 1


async def test_yearly_sequence_concurrent_first_use_has_no_duplicates(core_pool):
    import asyncio

    async def one():
        async with core_pool.acquire() as c, c.transaction():
            return await next_sequence(c, "test-app", "item.no", year=2026)

    got = await asyncio.gather(*(one() for _ in range(8)))
    assert sorted(got) == list(range(1, 9))
