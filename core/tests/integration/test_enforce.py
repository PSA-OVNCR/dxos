# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test enforce(): từ chối thì ghi ledger policy.denied (Plan 01 Task 12, F3)."""

import json

import pytest
from dxos_core.ledger.log import verify_log
from dxos_core.policy.pdp import Decision, Forbidden, NotFound, enforce
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.manifests import P, manifest

pytestmark = pytest.mark.integration


@pytest.fixture
def m_test():
    return manifest("test-app")


@pytest.fixture
def key() -> bytes:
    return b"changeme-test-hmac-key"


async def test_enforce_logs_policy_denied(core_conn, m_test, key):
    with pytest.raises(NotFound):
        await enforce(core_conn, P("owner_b1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1",
                      "rec-1", key)
    row = await core_conn.fetchrow("SELECT type, app_id FROM ledger_entries ORDER BY idx DESC LIMIT 1")
    assert tuple(row) == ("policy.denied", "test-app")


@pytest.mark.parametrize("action,exc", [("list", Forbidden), ("create", Forbidden),
                                        ("read", NotFound), ("update", NotFound), ("reveal_pii", NotFound)])
async def test_enforce_exception_per_action(core_conn, m_test, key, action, exc):
    with pytest.raises(exc):
        await enforce(core_conn, P("x", ["app:other:member"]), action, m_test, "item", "owner_a1", "s", key)


async def test_denied_body_and_subject(core_conn, m_test, key):
    with pytest.raises(NotFound):
        await enforce(core_conn, P("owner_b1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1",
                      "rec-9", key)
    row = await core_conn.fetchrow("SELECT subject, body_sha256, actor_ref FROM ledger_entries")
    assert row["subject"] == "rec-9" and row["actor_ref"] is not None and "owner_b1" not in row["actor_ref"]
    expected = {"action": "read", "reason": "not_in_access_list", "collection": "item"}
    assert row["body_sha256"] == sha256_hex(canonical_bytes(expected))
    assert json.dumps(expected)  # body chỉ để tính hash, không lưu
    assert (await verify_log(core_conn)).ok


async def test_allowed_writes_nothing_and_returns_decision(core_conn, m_test, key):
    d = await enforce(core_conn, P("owner_a1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1",
                      "rec-1", key)
    assert d == Decision(True, "owner")
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries") == 0


async def test_denial_must_not_run_inside_caller_transaction(core_conn, m_test, key):
    # Nếu chạy trong transaction của bên gọi, rollback sẽ xóa luôn bằng chứng bị từ chối (vi phạm F3).
    with pytest.raises(RuntimeError):
        async with core_conn.transaction():
            await enforce(core_conn, P("owner_b1", ["app:test-app:member"]), "read", m_test, "item",
                          "owner_a1", "rec-1", key)
