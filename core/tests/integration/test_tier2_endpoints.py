# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test ba endpoint chung cho client Tầng 2 (Plan 03 Task 1): xem manifest, liệt kê tệp đính kèm,
đọc ledger (admin). Chỉ dùng manifest tổng hợp ``test-app`` và ``test-flow`` (D6)."""

import json
import uuid

import pytest
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from helpers.api import activate, last_event_type, tok
from helpers.files import fixture
from helpers.manifests import raw

pytestmark = pytest.mark.integration

APP_URL = "/api/v1/apps/test-app/manifest"
FLOW_URL = "/api/v1/apps/test-flow/manifest"
REC_T = "/api/v1/apps/test-app/collections/item/records"
REC_F = "/api/v1/apps/test-flow/collections/doc/records"
ENTRIES = "/admin/v1/ledger/entries"
ITEM_KEYS = {"upload_id", "status", "sha256", "reason", "created_at"}


@pytest.fixture
async def env(flow, core_conn):
    """``flow`` (test-flow đã triển khai trên Flowable thật) cộng ``test-app`` (không có quy trình)."""
    await activate(core_conn, ("test-app",))
    return flow


@pytest.fixture
def api(env):
    return env.api


@pytest.fixture
def owner_a():
    return tok("owner_a1", "app:test-app:member")


@pytest.fixture
def owner_b():
    return tok("owner_b1", "app:test-app:member")


@pytest.fixture
def reviewer():
    return tok("reviewer1", "app:test-app:reviewer")


@pytest.fixture
def outsider():
    return tok("outsider1", "app:other-app:member")          # có vai trò, nhưng của app khác


@pytest.fixture
def admin(env):
    return env.admin()


async def denied_count(conn) -> int:
    return await conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='policy.denied'")


async def revealed_count(conn) -> int:
    return await conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='field.revealed'")


async def make_record(api, headers, url=REC_T, body=None) -> str:
    r = await api.post(url, json=body or {"title": "t", "secret_code": "012345678901"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def insert_upload(conn, rid: str, status: str, *, created_at: str, sha256=None, reason=None) -> str:
    return str(await conn.fetchval(
        "INSERT INTO uploads(record_id, staging_key, original_name_hash, size, status, sha256, reason,"
        " created_at) VALUES ($1, 'k', $2, 1, $3, $4, $5, $6::text::timestamptz) RETURNING id",
        uuid.UUID(rid), "b" * 64, status, sha256, reason, created_at))


# ---------------------------------------------------------------- GET manifest
async def test_manifest_view_for_app_member(api, owner_a):
    r = await api.get(APP_URL, headers=owner_a)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "private, max-age=60"
    v = r.json()
    assert v["app"] == {"id": "test-app", "version": "0.1.0", "name": "Test app"}
    assert v["roles"] == ["member", "reviewer"]
    assert v["workflow"] is None
    assert v["collections"]["item"]["access"] == {"read": ["owner", "role:reviewer"],
                                                  "create": ["role:member"], "update": ["owner"]}
    assert v["collections"]["item"]["fields"]["secret_code"]["pii"] == "CCCD"


async def test_manifest_view_with_workflow_decisions_from_deployed_bpmn(api):
    r = await api.get(FLOW_URL, headers=tok("a1", "app:test-flow:author"))
    assert r.status_code == 200, r.text
    wf = r.json()["workflow"]
    assert wf["decisions"] == {"review": ["approve", "reject"], "approve": ["approve", "reject"]}
    assert wf["tasks"]["approve"]["role"] == "approver"
    assert "bpmn" not in json.dumps(r.json())


async def test_manifest_view_hidden_from_non_member(env, api, outsider, core_conn):
    before = await denied_count(core_conn)
    r = await api.get(APP_URL, headers=outsider)
    assert r.status_code == 404 and r.json()["type"].endswith("/not-found")
    assert "cache-control" not in r.headers
    assert await denied_count(core_conn) == before + 1
    assert await last_event_type(core_conn) == "policy.denied"
    assert await env.last_denied_reason() == "no_app_role"


async def test_manifest_view_not_given_to_admin_without_app_role(env, api, admin):
    assert (await api.get(APP_URL, headers=admin)).status_code == 404
    assert await env.last_denied_reason() == "no_app_role"


async def test_manifest_view_unknown_or_disabled_app_is_404_app_not_active(api, owner_a, core_conn):
    for app in ("no-such-app", "Bad_Slug"):
        r = await api.get(f"/api/v1/apps/{app}/manifest", headers=owner_a)
        assert r.status_code == 404 and r.json()["type"].endswith("/app-not-active")
    await core_conn.execute("UPDATE apps SET status='DISABLED' WHERE id='test-app'")
    r = await api.get(APP_URL, headers=owner_a)
    assert r.status_code == 404 and r.json()["type"].endswith("/app-not-active")


async def test_manifest_view_needs_token(api):
    assert (await api.get(APP_URL)).status_code == 401


async def test_manifest_view_fails_closed_when_workflow_is_not_deployed(api, env):
    newer = raw("test-flow")
    newer["app"]["version"] = "0.2.0"                  # ACTIVE nhưng chưa có BPMN / deployment đi kèm
    await save_manifest(env.conn, validate_manifest(newer), newer, "ACTIVE", "seed")
    r = await api.get(FLOW_URL, headers=tok("a1", "app:test-flow:author"))
    assert r.status_code == 409 and r.json()["type"].endswith("/app-not-deployed")


# ---------------------------------------------------------------- GET attachments
async def test_attachments_list_survives_reload(api, owner_a):
    rid = await make_record(api, owner_a)
    r = await api.post(f"{REC_T}/{rid}/attachments", headers=owner_a,
                       files={"file": ("a.pdf", fixture("clean-text.pdf"), "application/pdf")})
    assert r.status_code == 202, r.text
    up = r.json()["upload_id"]
    r = await api.get(f"{REC_T}/{rid}/attachments", headers=owner_a)
    assert r.status_code == 200, r.text
    assert [i["upload_id"] for i in r.json()["items"]] == [up]
    item = r.json()["items"][0]
    assert set(item) == ITEM_KEYS
    assert item["status"] == "STAGING" and item["sha256"] is None and item["reason"] is None
    assert item["created_at"].endswith("Z")


async def test_attachments_list_after_scan_shows_clean_sha(env, api):
    rid = await env.ready_record("a1")
    r = await api.get(f"{REC_F}/{rid}/attachments", headers=tok("r1", "app:test-flow:reviewer"))
    [item] = r.json()["items"]
    assert item["status"] == "CLEAN" and len(item["sha256"]) == 64 and item["reason"] is None
    status = await api.get(f"/api/v1/uploads/{item['upload_id']}", headers=tok("a1", "app:test-flow:author"))
    assert status.json() == {"status": "CLEAN", "sha256": item["sha256"]}


async def test_attachments_list_order_and_status_fields(api, owner_a, core_conn):
    rid = await make_record(api, owner_a)
    third = await insert_upload(core_conn, rid, "REJECTED", created_at="2026-10-22T10:00:03Z",
                                reason="NO_TEXT_LAYER")
    first = await insert_upload(core_conn, rid, "CLEAN", created_at="2026-10-22T10:00:01Z", sha256="c" * 64)
    second = await insert_upload(core_conn, rid, "INFECTED", created_at="2026-10-22T10:00:02Z",
                                 reason="Eicar")
    fourth = await insert_upload(core_conn, rid, "STAGING", created_at="2026-10-22T10:00:04Z")
    r = await api.get(f"{REC_T}/{rid}/attachments", headers=owner_a)
    items = r.json()["items"]
    assert [i["upload_id"] for i in items] == [first, second, third, fourth]
    assert [(i["status"], i["sha256"], i["reason"]) for i in items] == [
        ("CLEAN", "c" * 64, None), ("INFECTED", None, "Eicar"), ("REJECTED", None, "NO_TEXT_LAYER"),
        ("STAGING", None, None)]
    assert items[0]["created_at"] == "2026-10-22T10:00:01Z"


async def test_attachments_list_empty(api, owner_a):
    rid = await make_record(api, owner_a)
    r = await api.get(f"{REC_T}/{rid}/attachments", headers=owner_a)
    assert r.status_code == 200 and r.json() == {"items": []}


async def test_attachments_list_allowed_for_manifest_read_role(api, owner_a, reviewer, core_conn):
    rid = await make_record(api, owner_a)
    up = await insert_upload(core_conn, rid, "STAGING", created_at="2026-10-22T10:00:00Z")
    r = await api.get(f"{REC_T}/{rid}/attachments", headers=reviewer)
    assert r.status_code == 200 and [i["upload_id"] for i in r.json()["items"]] == [up]


async def test_attachments_list_is_404_for_other_user(api, owner_a, owner_b, outsider, core_conn):
    rid = await make_record(api, owner_a)
    await insert_upload(core_conn, rid, "STAGING", created_at="2026-10-22T10:00:00Z")
    for who in (owner_b, outsider):          # có vai trò nhưng không được đọc / không có vai trò của app
        before = await denied_count(core_conn)
        r = await api.get(f"{REC_T}/{rid}/attachments", headers=who)
        assert r.status_code == 404 and r.json()["type"].endswith("/not-found")
        assert await denied_count(core_conn) == before + 1
        assert set(r.json()) == {"type", "title", "status"}


async def test_attachments_list_same_404_as_missing_record(api, owner_a):
    for rid in (str(uuid.uuid4()), "not-a-uuid"):
        r = await api.get(f"{REC_T}/{rid}/attachments", headers=owner_a)
        assert r.status_code == 404 and r.json()["type"].endswith("/not-found")
    r = await api.get(f"/api/v1/apps/test-app/collections/nope/records/{uuid.uuid4()}/attachments",
                      headers=owner_a)
    assert r.status_code == 404
    r = await api.get(f"/api/v1/apps/no-such-app/collections/item/records/{uuid.uuid4()}/attachments",
                      headers=owner_a)
    assert r.status_code == 404 and r.json()["type"].endswith("/app-not-active")


async def test_attachments_list_does_not_reveal_pii(env, api, core_conn):
    """Người được xem PII rõ gọi liệt kê tệp: không ghi ``field.revealed`` (khác ``GET`` bản ghi)."""
    rid = await env.new_record("a1", {"title": "Hồ sơ", "cccd": "012345678901"})
    approver = tok("p1", "app:test-flow:approver")
    before = await revealed_count(core_conn)
    assert (await api.get(f"{REC_F}/{rid}/attachments", headers=approver)).status_code == 200
    assert await revealed_count(core_conn) == before
    assert (await api.get(f"{REC_F}/{rid}", headers=approver)).status_code == 200
    assert await revealed_count(core_conn) == before + 1       # đối chứng: GET bản ghi thì có ghi


async def test_attachments_list_needs_token(api, owner_a):
    rid = await make_record(api, owner_a)
    assert (await api.get(f"{REC_T}/{rid}/attachments")).status_code == 401


# ---------------------------------------------------------------- GET /admin/v1/ledger/entries
async def test_ledger_entries_filters_and_orders(api, outsider, admin):
    for _ in range(3):
        await api.get(APP_URL, headers=outsider)                       # 3 lá policy.denied
    r = await api.get(f"{ENTRIES}?type=policy.denied&limit=2", headers=admin)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    assert all(set(i) == {"idx", "ts", "type", "app_id", "subject", "actor_ref"} for i in items)
    assert all(i["type"] == "policy.denied" and i["app_id"] == "test-app" for i in items)
    assert items == sorted(items, key=lambda i: -i["idx"])
    assert items[0]["subject"] == "test-app" and len(items[0]["actor_ref"]) == 64


async def test_ledger_entries_newest_first_across_types_and_default_limit(env, api, owner_a, admin):
    rid = await make_record(api, owner_a)                              # record.created
    await api.get(APP_URL, headers=tok("x", "app:other-app:m"))        # policy.denied
    items = (await api.get(ENTRIES, headers=admin)).json()["items"]
    assert [i["type"] for i in items[:2]] == ["policy.denied", "record.created"]
    assert items[1]["subject"] == rid
    only = (await api.get(f"{ENTRIES}?type=record.created", headers=admin)).json()["items"]
    assert [i["type"] for i in only] == ["record.created"]


async def test_ledger_entries_default_limit_is_20_and_max_100(env, api, outsider, admin, core_conn):
    for _ in range(25):
        await api.get(APP_URL, headers=outsider)
    assert len((await api.get(ENTRIES, headers=admin)).json()["items"]) == 20
    assert len((await api.get(f"{ENTRIES}?limit=100", headers=admin)).json()["items"]) == 25
    for bad in ("0", "101", "-1", "abc"):
        r = await api.get(f"{ENTRIES}?limit={bad}", headers=admin)
        assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request"), bad


async def test_ledger_entries_rejects_unknown_type(api, admin):
    r = await api.get(f"{ENTRIES}?type=nope", headers=admin)
    assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request")


async def test_ledger_entries_admin_only(api, owner_a):
    assert (await api.get(ENTRIES)).status_code == 401
    assert (await api.get(ENTRIES, headers=owner_a)).status_code == 403
