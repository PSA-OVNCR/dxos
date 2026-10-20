# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test kho manifest (Plan 01 Task 11)."""

import copy
from pathlib import Path

import pytest
import yaml
from dxos_core.registry.store import get_active, save_manifest
from dxos_core.registry.validator import validate_manifest

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "manifest-test-app.yaml"


def load(name: str = "test-app") -> dict:
    assert name == "test-app"
    return copy.deepcopy(yaml.safe_load(FIXTURE.read_text(encoding="utf-8")))


async def test_store_roundtrip(core_conn):
    m = validate_manifest(load("test-app"))
    await save_manifest(core_conn, m, load("test-app"), "ACTIVE", "admin")
    assert (await get_active(core_conn, "test-app")).app.id == "test-app"


async def test_pending_is_not_active(core_conn):
    await save_manifest(core_conn, validate_manifest(load()), load(), "PENDING", "dev")
    assert await get_active(core_conn, "test-app") is None
    assert await get_active(core_conn, "khong-co") is None


async def test_new_active_version_disables_previous(core_conn):
    await save_manifest(core_conn, validate_manifest(load()), load(), "ACTIVE", "admin")
    v2 = load()
    v2["app"]["version"] = "0.2.0"
    v2["collections"]["item"]["fields"]["note"] = {"type": "string"}
    await save_manifest(core_conn, validate_manifest(v2), v2, "ACTIVE", "admin")
    active = await get_active(core_conn, "test-app")
    assert active.app.version == "0.2.0" and "note" in active.collections["item"].fields
    rows = await core_conn.fetch("SELECT version, status FROM apps WHERE id='test-app' ORDER BY version")
    assert [tuple(r) for r in rows] == [("0.1.0", "DISABLED"), ("0.2.0", "ACTIVE")]


async def test_same_version_different_content_rejected(core_conn):
    await save_manifest(core_conn, validate_manifest(load()), load(), "PENDING", "dev")
    changed = load()
    changed["roles"].append("extra")
    with pytest.raises(ValueError, match="0.1.0"):
        await save_manifest(core_conn, validate_manifest(changed), changed, "PENDING", "dev")


async def test_status_change_same_content_and_ledger_events(core_conn):
    key = b"k"
    await save_manifest(core_conn, validate_manifest(load()), load(), "PENDING", "dev", hmac_key=key)
    await save_manifest(core_conn, validate_manifest(load()), load(), "ACTIVE", "admin", hmac_key=key)
    await save_manifest(core_conn, validate_manifest(load()), load(), "DISABLED", "admin", hmac_key=key)
    types = [r["type"] for r in await core_conn.fetch("SELECT type FROM ledger_entries ORDER BY idx")]
    assert types == ["app.submitted", "app.installed", "app.disabled"]
    row = await core_conn.fetchrow("SELECT status, submitted_by, approved_by, manifest_sha256 FROM apps")
    assert (row["status"], row["submitted_by"], row["approved_by"]) == ("DISABLED", "dev", "admin")
    assert len(row["manifest_sha256"]) == 64
