# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Installer qua API quản trị (spec 9.5, 12.3; Plan 02 Task 12): nộp, diff quyền, duyệt bốn mắt (role
Keycloak + deploy BPMN đã dựng lại), vô hiệu hóa, health, quarantine."""

import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from dxos_core.ledger.log import actor_ref
from dxos_core.registry.bpmn import check_against_manifest, render_bpmn
from dxos_core.registry.store import get_active
from dxos_core.registry.validator import validate_manifest
from dxos_core.workflow.flowable import WorkflowUnavailable
from dxos_proof.canonical import canonical_bytes
from dxos_proof.canonical import sha256_hex as _sha
from helpers.installer import (
    FLOW_FILES,
    GOOD_XML,
    deployment_of,
    deployment_resource,
    ledger_rows,
    ledger_types,
    status_of,
    submit,
)
from helpers.manifests import load, mutate

pytestmark = pytest.mark.integration

HMAC = b"changeme-test-secret"  # nội dung secret_file (khóa HMAC của make_settings)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- brief Step 1
async def test_submit_bad_manifest_422_with_code(admin):  # AT-11 qua API
    doc = load("test-flow")
    doc["collections"]["doc"]["attachments"]["quarantine"] = "optional"
    r = await admin.post("/admin/v1/apps", json={"manifest": doc, "files": FLOW_FILES})
    assert r.status_code == 422 and r.json()["code"] == "FLOOR_WEAKENED"
    assert (
        r.json()["type"].endswith("/manifest-invalid")
        and r.json()["path"] == "/collections/doc/attachments/quarantine"
    )


async def test_submit_rejects_unreferenced_or_traversal_files(admin):
    for files in ({**FLOW_FILES, "bpmn/extra.bpmn": "<x/>"}, {"../bpmn/test-review.bpmn": GOOD_XML}):
        assert (
            await admin.post("/admin/v1/apps", json={"manifest": load("test-flow"), "files": files})
        ).status_code == 422


async def test_submit_then_approve_installs(admin, kc_fake, flowable_client, core_conn):
    assert (
        await admin.post("/admin/v1/apps", json={"manifest": load("test-flow"), "files": FLOW_FILES})
    ).status_code == 202
    assert await get_active(core_conn, "test-flow") is None  # chưa duyệt thì chưa dùng được
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 200 and kc_fake.roles >= {"app:test-flow:reviewer", "app:test-flow:approver"}
    assert (await get_active(core_conn, "test-flow")).app.version == "0.1.0"
    assert await ledger_types(core_conn, "test-flow") >= {"app.submitted", "app.installed"}


async def test_submitter_cannot_approve_own_app(admin_strict, core_conn):  # P2-D21
    await submit(admin_strict, "test-flow")
    r = await admin_strict.post(
        "/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"}
    )  # cùng admin đã nộp
    assert r.status_code == 403 and await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"
    assert r.json()["reason"] == "self_approval"
    [leaf] = await ledger_rows(core_conn, "test-flow", "policy.denied")
    assert leaf["body_sha256"] == _sha(canonical_bytes({"action": "approve", "reason": "self_approval"}))
    assert leaf["actor_ref"] == actor_ref("admin1", HMAC)


async def test_deployed_bpmn_is_the_rendered_one(admin2, flowable_client, core_conn):
    await submit(admin2.submitter, "test-flow")
    r = await admin2.approver.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 200, r.text
    dep = await deployment_of(core_conn, "test-flow", "0.1.0")
    assert sha256(await deployment_resource(flowable_client, dep["deployment_id"])) == dep["rendered_sha256"]
    expected = render_bpmn(check_against_manifest(GOOD_XML.encode(), validate_manifest(load("test-flow"))))
    assert dep["rendered_sha256"] == sha256(expected)
    assert dep["process_definition_id"] == await flowable_client.definition_id(dep["deployment_id"])


async def test_approve_is_retryable_after_idp_failure(admin, kc_fake, core_conn):
    await submit(admin, "test-flow")
    kc_fake.down = True
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 503 and r.json()["type"].endswith("/idp-admin-unavailable")
    assert await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"
    assert "app.installed" not in await ledger_types(core_conn, "test-flow")
    kc_fake.down = False
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200


async def test_non_admin_and_public_host_cannot_install(api_as_member):
    assert (await api_as_member.post("/admin/v1/apps", json={})).status_code == 403


async def test_quarantine_lists_infected_without_names(admin, infected_upload):
    item = (await admin.get("/admin/v1/quarantine")).json()[0]
    assert item["status"] == "INFECTED" and "name" not in json.dumps(item)
    assert set(item) == {"upload_id", "sha256", "status", "reason", "app_id", "created_at"}
    assert item["upload_id"] == str(infected_upload) and item["app_id"] == "test-app"


# ---------------------------------------------------------------- nộp
async def test_submit_202_body_and_ledger_leaf_carries_file_hashes(admin, core_conn):
    body = await submit(admin, "test-flow")
    digest = _sha(canonical_bytes(load("test-flow")))
    files = {"bpmn/test-review.bpmn": sha256(GOOD_XML.encode())}
    assert body == {
        "app_id": "test-flow",
        "version": "0.1.0",
        "status": "PENDING",
        "manifest_sha256": digest,
        "files": files,
    }
    [leaf] = await ledger_rows(core_conn, "test-flow", "app.submitted")
    assert leaf["body_sha256"] == _sha(
        canonical_bytes({"manifest_sha256": digest, "status": "PENDING", "files": files})
    )
    assert leaf["actor_ref"] == actor_ref("admin1", HMAC) and leaf["subject"] == "test-flow@0.1.0"
    assert await core_conn.fetchval("SELECT content FROM app_files WHERE app_id='test-flow'") == GOOD_XML


async def test_identical_resubmission_is_idempotent_and_changed_content_409(admin, core_conn):
    first = await submit(admin, "test-flow")
    assert await submit(admin, "test-flow") == first
    assert len(await ledger_rows(core_conn, "test-flow", "app.submitted")) == 1
    doc = load("test-flow")
    doc["app"]["name"] = "Khác"
    r = await admin.post("/admin/v1/apps", json={"manifest": doc, "files": FLOW_FILES})
    assert r.status_code == 409
    other_xml = GOOD_XML.replace("<process ", "<!-- khác -->\n  <process ", 1)
    r = await admin.post(
        "/admin/v1/apps", json={"manifest": load("test-flow"), "files": {"bpmn/test-review.bpmn": other_xml}}
    )
    assert r.status_code == 409


async def test_submit_bad_bpmn_422(admin):
    bad = GOOD_XML.replace(
        'flowable:candidateGroups="app:test-flow:reviewer"',
        'flowable:candidateGroups="app:test-flow:approver"',
    )
    assert bad != GOOD_XML
    r = await admin.post(
        "/admin/v1/apps", json={"manifest": load("test-flow"), "files": {"bpmn/test-review.bpmn": bad}}
    )
    assert r.status_code == 422 and r.json()["code"] == "BPMN_INVALID"


async def test_submit_body_cap_and_shape(admin):
    big = {"manifest": load("test-flow"), "files": FLOW_FILES, "pad": "x" * (1024 * 1024)}
    assert (await admin.post("/admin/v1/apps", json=big)).status_code == 413
    assert (
        await admin.post("/admin/v1/apps", content=b"{not json", headers={"content-type": "application/json"})
    ).status_code == 422
    assert (await admin.post("/admin/v1/apps", json={"manifest": load("test-flow")})).status_code == 422
    assert (
        await admin.post("/admin/v1/apps", content=b"x", headers={"content-type": "text/plain"})
    ).status_code == 415


async def test_upgrade_must_be_additive_via_api(admin, core_conn):
    await submit(admin, "test-flow")
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200
    r = await admin.post(
        "/admin/v1/apps",
        json={"manifest": mutate(load("test-flow"), "drop_field", version="0.2.0"), "files": FLOW_FILES},
    )
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    # Chưa từng niêm phong, không bản ghi nào running: được đổi chính sách niêm phong (P2-D14 ngoại lệ).
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "change_seal", version="0.2.0"))
    await core_conn.execute(
        "INSERT INTO records(app_id, collection, data, owner_sub, wf_state)"
        " VALUES ('test-flow', 'doc', '{}', 'u1', 'running')"
    )
    r = await admin.post(
        "/admin/v1/apps",
        json={"manifest": mutate(load("test-flow"), "change_verify", version="0.3.0"), "files": FLOW_FILES},
    )
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    # Duyệt kiểm lại theo trạng thái lúc này: đã có bản ghi running nên 0.2.0 (đổi seal) không còn hợp lệ.
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    assert await status_of(core_conn, "test-flow", "0.2.0") == "PENDING"


# ---------------------------------------------------------------- duyệt
async def test_approve_rechecks_against_the_active_version_now(admin, core_conn):
    await submit(admin, "test-flow")
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "none", version="0.3.0"))
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    ).status_code == 200
    # 0.3.0 hợp lệ lúc nộp (so với 0.1.0) nhưng thiếu trường note và role observer của bản ACTIVE (0.2.0).
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.3.0"})
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    assert await status_of(core_conn, "test-flow", "0.3.0") == "PENDING"
    assert await deployment_of(core_conn, "test-flow", "0.3.0") is None


async def test_approve_twice_is_idempotent_and_upgrade_disables_old(admin, kc_fake, core_conn):
    await submit(admin, "test-flow")
    first = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    again = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    assert len(await ledger_rows(core_conn, "test-flow", "app.installed")) == 1 and kc_fake.calls == 1
    body = first.json()
    assert body["status"] == "ACTIVE" and body["self_approved"] is True
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    ).status_code == 200
    assert await status_of(core_conn, "test-flow", "0.1.0") == "DISABLED"
    assert (await get_active(core_conn, "test-flow")).app.version == "0.2.0"
    assert "app:test-flow:observer" in kc_fake.roles


async def test_installed_leaf_body_and_actor(admin2, core_conn):
    await submit(admin2.submitter, "test-flow")
    r = await admin2.approver.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 200 and r.json()["self_approved"] is False
    dep = await deployment_of(core_conn, "test-flow", "0.1.0")
    [leaf] = await ledger_rows(core_conn, "test-flow", "app.installed")
    assert leaf["body_sha256"] == _sha(
        canonical_bytes(
            {
                "manifest_sha256": _sha(canonical_bytes(load("test-flow"))),
                "status": "ACTIVE",
                "bpmn_sha256": sha256(GOOD_XML.encode()),
                "rendered_sha256": dep["rendered_sha256"],
                "deployment_id": dep["deployment_id"],
                "self_approved": False,
            }
        )
    )
    assert leaf["actor_ref"] == actor_ref("admin-app", HMAC)
    row = await core_conn.fetchrow("SELECT submitted_by, approved_by FROM apps WHERE id='test-flow'")
    assert (row["submitted_by"], row["approved_by"]) == ("admin-sub", "admin-app")


async def test_approve_retryable_after_flowable_failure(admin, core_conn, monkeypatch):
    await submit(admin, "test-flow")
    client = admin.app.state.flowable
    real, left = client.deploy, [1]

    async def down(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise WorkflowUnavailable("Flowable ConnectError (giả lập)", sent=False)
        return await real(*args, **kwargs)

    monkeypatch.setattr(client, "deploy", down)
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 503 and r.json()["type"].endswith("/workflow-unavailable")
    assert await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"
    assert await deployment_of(core_conn, "test-flow", "0.1.0") is None
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200


async def test_approve_reuses_recorded_deployment_after_late_failure(admin, core_conn, monkeypatch):
    from dxos_core.registry import installer

    await submit(admin, "test-flow")
    real, left = installer.save_manifest, [1]

    async def broken(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise RuntimeError("DB lỗi giả lập ở bước kích hoạt")
        return await real(*args, **kwargs)

    monkeypatch.setattr(installer, "save_manifest", broken)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=admin.app, raise_app_exceptions=False),
        base_url="http://test",
        headers=admin.headers,
    ) as c:
        r = await c.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 500 and await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"
    dep = await deployment_of(core_conn, "test-flow", "0.1.0")
    assert dep is not None
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200
    assert await deployment_of(core_conn, "test-flow", "0.1.0") == dep
    # Hàng deploy đã có nhưng hash khác (bảng chỉ-thêm) → 409, không deploy đè.
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    await core_conn.execute(
        "INSERT INTO app_deployments(app_id, version, deployment_id, process_definition_id, rendered_sha256)"
        " VALUES ('test-flow', '0.2.0', 'd', 'p', $1)",
        "0" * 64,
    )
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    assert r.status_code == 409 and await status_of(core_conn, "test-flow", "0.2.0") == "PENDING"


async def test_approve_without_installer_client_is_503(admin, core_conn):
    from dxos_core.registry.keycloak_admin import KeycloakAdminSource

    admin.app.state.kc_admin = KeycloakAdminSource()  # chưa đặt installer_client_secret_file
    await submit(admin, "test-flow")
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 503 and r.json()["type"].endswith("/idp-admin-unavailable")
    assert await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"


async def test_approve_unknown_or_bad_version(admin):
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "9.9.9"})
    ).status_code == 404
    assert (await admin.post("/admin/v1/apps/test-flow:approve", json={})).status_code == 422
    assert (
        await admin.post("/admin/v1/apps/NOT_AN_ID:approve", json={"version": "0.1.0"})
    ).status_code == 404


async def test_activated_app_starts_workflow(admin, core_conn):
    """Bản đã duyệt chạy được qua bridge thật của Task 6 (process_model khớp rendered_sha256)."""
    from dxos_core.workflow.reconcile import deps_from_state, process_model

    await submit(admin, "test-flow")
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200
    m = await get_active(core_conn, "test-flow")
    model = await process_model(core_conn, deps_from_state(admin.app.state), m)
    assert set(model.user_tasks) == {"review", "approve"}


# ---------------------------------------------------------------- danh sách, diff, vô hiệu hóa
async def test_list_shows_refs_not_subs(admin2):
    await submit(admin2.submitter, "test-flow")
    await admin2.approver.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    [row] = (await admin2.approver.get("/admin/v1/apps")).json()
    assert set(row) == {
        "app_id",
        "version",
        "status",
        "manifest_sha256",
        "submitted_by_ref",
        "approved_by_ref",
        "created_at",
    }
    assert row["submitted_by_ref"] == actor_ref("admin-sub", HMAC)
    assert row["approved_by_ref"] == actor_ref("admin-app", HMAC)
    assert "admin-sub" not in json.dumps(row) and row["status"] == "ACTIVE"


async def test_diff_against_active(admin):
    await submit(admin, "test-flow")
    d = (await admin.get("/admin/v1/apps/test-flow/versions/0.1.0/diff")).json()
    assert d["against"] is None and d["roles_added"] == ["approver", "author", "reviewer"]
    assert d["bpmn_sha256"] == sha256(GOOD_XML.encode())
    await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    d = (await admin.get("/admin/v1/apps/test-flow/versions/0.2.0/diff")).json()
    assert (
        d["against"] == "0.1.0"
        and d["roles_added"] == ["observer"]
        and d["fields_added"] == {"doc": ["note"]}
    )
    assert (await admin.get("/admin/v1/apps/test-flow/versions/9.9.9/diff")).status_code == 404


async def test_diff_after_disable_compares_with_last_active(admin, kc_fake):
    """Sau ``:disable`` không còn bản ACTIVE: diff quyền so với cùng mốc mà luật nâng cấp dùng (bản từng
    ACTIVE), để người duyệt bốn mắt vẫn thấy đúng phần thay đổi (rà soát cuối, residual 1)."""
    await submit(admin, "test-flow")
    await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    await admin.post("/admin/v1/apps/test-flow:disable")
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    d = (await admin.get("/admin/v1/apps/test-flow/versions/0.2.0/diff")).json()
    assert d["against"] == "0.1.0" and d["roles_added"] == ["observer"]
    assert d["fields_added"] == {"doc": ["note"]}


async def test_disable_keeps_data_and_ledger(admin, core_conn, kc_fake):
    await submit(admin, "test-flow")
    await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    before = await core_conn.fetchval("SELECT count(*) FROM ledger_entries")
    r = await admin.post("/admin/v1/apps/test-flow:disable")
    assert r.status_code == 200 and r.json() == {
        "app_id": "test-flow",
        "version": "0.1.0",
        "status": "DISABLED",
    }
    assert await status_of(core_conn, "test-flow", "0.1.0") == "DISABLED"
    assert await get_active(core_conn, "test-flow") is None
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries") == before + 1
    assert "app.disabled" in await ledger_types(core_conn, "test-flow")
    assert await deployment_of(core_conn, "test-flow", "0.1.0") is not None and kc_fake.roles
    assert (await admin.post("/admin/v1/apps/test-flow:disable")).status_code == 404
    from helpers.tokens import bearer, make_token

    r = await admin.post(
        "/api/v1/apps/test-flow/collections/doc/records",
        json={"title": "x"},
        headers=bearer(make_token("a1", ["app:test-flow:author"])),
    )
    assert r.status_code == 404 and r.json()["type"].endswith("/app-not-active")


async def test_all_installer_routes_need_admin(api_as_member):
    for method, path in (
        ("GET", "/admin/v1/apps"),
        ("GET", "/admin/v1/apps/test-flow/versions/0.1.0/diff"),
        ("POST", "/admin/v1/apps/test-flow:approve"),
        ("POST", "/admin/v1/apps/test-flow:disable"),
        ("GET", "/admin/v1/health"),
        ("GET", "/admin/v1/quarantine"),
    ):
        assert (await api_as_member.request(method, path, json={})).status_code == 403, path


# ---------------------------------------------------------------- health, quarantine
HEALTH_KEYS = {
    "db",
    "clamav",
    "openbao",
    "flowable",
    "keycloak_default_roles",
    "anchor",
    "seal_pending",
    "task_intents_stuck",
    "seal_key",
    "org",
}


async def test_health_reports_every_component(admin, kc_fake):
    r = await admin.get("/admin/v1/health")
    assert r.status_code == 200
    h = r.json()
    assert set(h) == HEALTH_KEYS
    assert (h["db"], h["clamav"], h["openbao"], h["flowable"], h["keycloak_default_roles"]) == ("ok",) * 5
    assert h["anchor"] == {"last_tree_size": None, "last_anchor_age_s": None}
    assert (h["seal_pending"], h["task_intents_stuck"], h["seal_key"], h["org"]) == (0, 0, "none", "ok")


async def test_health_down_items_still_200(admin, kc_fake, local_signer, monkeypatch):
    from dxos_core.kms.base import KmsUnavailable

    kc_fake.default_composites.append("dxos-admin")

    async def sealed(*_a, **_k):
        raise KmsUnavailable("OpenBao sealed (giả lập)")

    monkeypatch.setattr(local_signer, "sign", sealed)
    admin.app.state.flowable = None
    h = (await admin.get("/admin/v1/health")).json()
    assert h["keycloak_default_roles"].startswith("down:") and h["openbao"].startswith("down:")
    assert h["flowable"] == "down: not configured"
    kc_fake.default_composites[-1] = "app:test-flow:reviewer"
    assert (await admin.get("/admin/v1/health")).json()["keycloak_default_roles"].startswith("down:")
    kc_fake.down = True
    assert (await admin.get("/admin/v1/health")).json()["keycloak_default_roles"].startswith("down:")


async def test_health_counts_stuck_intents_and_anchor(admin, core_conn, owner_conn):
    rid = await core_conn.fetchval(
        "INSERT INTO records(app_id, collection, data, owner_sub)"
        " VALUES ('test-app', 'item', '{}', 'u1') RETURNING id"
    )
    for age in (timedelta(minutes=1), timedelta(minutes=5)):
        await core_conn.execute(
            "INSERT INTO task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub, actor_roles,"
            " decision, created_at) VALUES ('t', $1, 'i', 'review', 'u1', '{reviewer}', 'approve',"
            " now() - $2::interval)",
            rid,
            age,
        )
    await owner_conn.execute(
        "INSERT INTO tree_heads(tree_size, root_hash, ts, key_version, signature)"
        " VALUES (3, $1, '2026-10-21T00:00:00Z', 1, 'sig')",
        "c" * 64,
    )
    await owner_conn.execute(
        "INSERT INTO anchors(tree_size, repo, commit_sha, anchored_at)"
        " VALUES (3, 'r', $1, now() - interval '90 seconds')",
        "a" * 40,
    )
    h = (await admin.get("/admin/v1/health")).json()
    assert h["task_intents_stuck"] == 1
    assert h["anchor"]["last_tree_size"] == 3 and 85 <= h["anchor"]["last_anchor_age_s"] <= 150


async def test_quarantine_limit(admin, infected_upload):
    assert (await admin.get("/admin/v1/quarantine?limit=0")).status_code == 422
    assert (await admin.get("/admin/v1/quarantine?limit=1")).json()[0]["upload_id"] == str(infected_upload)


async def test_concurrent_approves_never_wait_and_install_once(admin, kc_fake, core_conn, monkeypatch):
    """LOCK_INSTALL không chờ (fix 1, m5): lần duyệt đang chạy giữ khóa, lần khác trả 409 install-in-progress
    ngay hoặc 200 nếu tới lúc bản đã ACTIVE; thử lại sau đó được 200."""
    import asyncio

    await submit(admin, "test-flow")
    real = kc_fake.ensure_app_roles

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.5)
        return await real(*args, **kwargs)

    monkeypatch.setattr(kc_fake, "ensure_app_roles", slow)
    rs = await asyncio.gather(
        *(admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"}) for _ in range(3))
    )
    codes = sorted(r.status_code for r in rs)
    assert codes.count(200) >= 1 and set(codes) <= {200, 409}, codes
    assert all(r.json()["type"].endswith("/install-in-progress") for r in rs if r.status_code == 409)
    assert 409 in codes  # có lần không chờ khóa
    assert kc_fake.calls == 1
    assert len(await ledger_rows(core_conn, "test-flow", "app.installed")) == 1
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200
    assert (
        await core_conn.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=724102")
        == 0
    )


async def test_submit_and_disable_do_not_wait_for_a_running_approve(admin, core_conn, owner_conn):
    await submit(admin, "test-flow")
    await owner_conn.execute(
        "SELECT pg_advisory_lock(724102, hashtext('test-flow'))"
    )  # một lần duyệt đang chạy
    try:
        r = await admin.post(
            "/admin/v1/apps",
            json={"manifest": mutate(load("test-flow"), "none", version="0.2.0"), "files": FLOW_FILES},
        )
        assert r.status_code == 409 and r.json()["type"].endswith("/install-in-progress")
        r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
        assert r.status_code == 409 and r.json()["type"].endswith("/install-in-progress")
        assert (await admin.post("/admin/v1/apps/test-flow:disable")).status_code == 409
    finally:
        await owner_conn.execute("SELECT pg_advisory_unlock(724102, hashtext('test-flow'))")
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    ).status_code == 200


# ---------------------------------------------------------------- fix round 1
async def test_self_approval_denied_before_content_checks(admin_strict, owner_conn, core_conn):  # m1
    await submit(admin_strict, "test-flow")
    # Manifest đã lưu không còn qua bộ kiểm (vd. bộ kiểm siết hơn sau nâng cấp lõi): bốn mắt vẫn thắng.
    await owner_conn.execute(
        "UPDATE apps SET manifest = jsonb_set(manifest, '{roles}', '[\"app_bad\"]')"
        " WHERE id='test-flow' AND version='0.1.0'"
    )
    r = await admin_strict.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 403 and r.json()["reason"] == "self_approval"
    [leaf] = await ledger_rows(core_conn, "test-flow", "policy.denied")
    assert leaf["body_sha256"] == _sha(canonical_bytes({"action": "approve", "reason": "self_approval"}))
    assert await status_of(core_conn, "test-flow", "0.1.0") == "PENDING"


async def test_unencodable_manifest_is_422_not_500(admin):  # m2
    body = json.dumps(
        {
            "manifest": {**load("test-flow"), "app": {**load("test-flow")["app"], "name": "x\ud800y"}},
            "files": FLOW_FILES,
        },
        ensure_ascii=True,
    )
    assert "\\ud800" in body
    r = await admin.post(
        "/admin/v1/apps", content=body.encode(), headers={"content-type": "application/json"}
    )
    # Bộ đọc thân JSON dùng chung chặn trước cả bộ kiểm manifest (rà soát cuối Plan 02, m2).
    assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request"), r.text
    assert "surrogate" in r.json()["detail"]


async def test_deeply_nested_submit_is_422_not_500(admin):  # rà soát cuối Plan 02, m2
    body = b'{"manifest": ' + b"[" * 200_000 + b"]" * 200_000 + b', "files": {}}'
    r = await admin.post("/admin/v1/apps", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request"), r.text
    deep = b'{"manifest": ' + b"[" * 100 + b"]" * 100 + b', "files": {}}'
    r = await admin.post("/admin/v1/apps", content=deep, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request")
    assert "deep" in r.json()["detail"]


async def test_chunked_body_over_cap_is_413(admin):  # m4
    sent = []

    async def chunks():
        for _ in range(20):  # 20 × 64 KiB = 1,25 MiB, không có Content-Length
            sent.append(1)
            yield b"x" * 65536

    r = await admin.post("/admin/v1/apps", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["type"].endswith("/payload-too-large")
    assert len(sent) < 20  # dừng đọc ngay khi vượt trần


async def test_downgrade_or_same_version_rejected(admin, core_conn):  # m6
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "none", version="0.2.0"))
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "none", version="0.10.0"))
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    ).status_code == 200
    r = await admin.post("/admin/v1/apps", json={"manifest": load("test-flow"), "files": FLOW_FILES})  # 0.1.0
    assert r.status_code == 409 and r.json()["type"].endswith("/version-not-newer")
    # 0.10.0 > 0.2.0 theo semver (không so chuỗi).
    assert (
        await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.10.0"})
    ).status_code == 200
    # Nộp khi 0.2.0 còn ACTIVE, duyệt khi 0.10.0 đã ACTIVE → kiểm lại lúc duyệt.
    await core_conn.execute("UPDATE apps SET status='DISABLED' WHERE id='test-flow' AND version='0.10.0'")
    await core_conn.execute("UPDATE apps SET status='ACTIVE' WHERE id='test-flow' AND version='0.2.0'")
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "none", version="0.3.0"))
    await core_conn.execute("UPDATE apps SET status='DISABLED' WHERE id='test-flow' AND version='0.2.0'")
    await core_conn.execute("UPDATE apps SET status='ACTIVE' WHERE id='test-flow' AND version='0.10.0'")
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.3.0"})
    assert r.status_code == 409 and r.json()["type"].endswith("/version-not-newer")
    assert await status_of(core_conn, "test-flow", "0.3.0") == "PENDING"


# ---------------------------------------------------------------- rà soát cuối Plan 02, I2
async def test_upgrade_after_disable_still_checked_against_last_active(admin, core_conn):
    """Sau ``:disable`` không còn bản ACTIVE: mốc so sánh là bản từng ACTIVE có semver cao nhất (DISABLED).
    Vô hiệu hóa không được là đường vòng qua P2-D14 hay luật không hạ cấp."""
    await submit(admin, "test-flow")
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 200
    assert (await admin.post("/admin/v1/apps/test-flow:disable")).status_code == 200
    r = await admin.post(
        "/admin/v1/apps",
        json={"manifest": mutate(load("test-flow"), "drop_field", version="0.2.0"), "files": FLOW_FILES},
    )
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    r = await admin.post(
        "/admin/v1/apps",
        json={"manifest": mutate(load("test-flow"), "none", version="0.0.9"), "files": FLOW_FILES},
    )
    assert r.status_code == 409 and r.json()["type"].endswith("/version-not-newer")
    # Nộp lại một phiên bản mới hơn, chỉ thêm: duyệt được, app hoạt động lại.
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    assert r.status_code == 200
    assert await status_of(core_conn, "test-flow", "0.2.0") == "ACTIVE"


async def test_approve_after_disable_rechecks_against_last_active(admin, core_conn):
    await submit(admin, "test-flow")
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.0"})
    assert r.status_code == 200
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "none", version="0.3.0"))
    await submit(admin, "test-flow", doc=mutate(load("test-flow"), "add_optional", version="0.2.0"))
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.2.0"})
    assert r.status_code == 200
    assert (await admin.post("/admin/v1/apps/test-flow:disable")).status_code == 200
    # 0.3.0 thiếu trường note và role observer của 0.2.0 (bản từng ACTIVE cao nhất, nay DISABLED).
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.3.0"})
    assert r.status_code == 422 and r.json()["code"] == "UPGRADE_NOT_ADDITIVE"
    assert await status_of(core_conn, "test-flow", "0.3.0") == "PENDING"
    # Bản nộp khi 0.1.0 còn ACTIVE nhưng không mới hơn 0.2.0 → 409 lúc duyệt.
    await core_conn.execute(
        "INSERT INTO apps(id, version, manifest, manifest_sha256, status, submitted_by)"
        " SELECT id, '0.1.5', jsonb_set(manifest, '{app,version}', '\"0.1.5\"'), repeat('0', 64), 'PENDING',"
        " submitted_by FROM apps WHERE id='test-flow' AND version='0.2.0'")
    await core_conn.execute(
        "INSERT INTO app_files(app_id, version, path, sha256, content)"
        " SELECT app_id, '0.1.5', path, sha256, content FROM app_files WHERE app_id='test-flow'"
        " AND version='0.2.0'")
    r = await admin.post("/admin/v1/apps/test-flow:approve", json={"version": "0.1.5"})
    assert r.status_code == 409 and r.json()["type"].endswith("/version-not-newer")
