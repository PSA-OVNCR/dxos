# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cầu nối quy trình trên Flowable thật (Plan 02 Task 6; AT-07, AT-08, AT-20a; P2-D4, P2-D19, P2-D20).

Fixture ``flow`` (conftest): API thật + ``test-flow`` 0.1.0 đã cài. Flowable dùng chung giữa các lần chạy, nên
mọi task được chọn theo instance của bản ghi trong DB riêng của test; hộp việc lọc theo bản ghi của DB đó.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from dxos_core.kms.base import KmsUnavailable
from dxos_core.policy.pdp import deny
from dxos_core.settings import ORG_NAME_DEFAULT
from dxos_core.workflow.reconcile import SealHooks
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.files import fixture
from helpers.manifests import manifest

pytestmark = pytest.mark.integration


# ---------- Các test do Plan 02 Task 6 quy định ----------

async def test_creator_self_approval_denied_and_logged(flow):                 # AT-07
    rid = await flow.ready_record(author="a1")                                  # có 1 PDF CLEAN
    await flow.start(rid, as_="a1")
    r = await flow.complete_task("review", rid, "approve", as_=flow.token("a1", "author", "reviewer"))
    assert r.status_code == 403 and r.json()["guard"] == "not_same_actor:creator"
    assert r.json()["type"].endswith("/guard-failed") and r.json()["reason"] == "same_actor"
    assert await flow.last_denied_reason() == "guard:not_same_actor:creator:same_actor"
    assert await flow.task_exists("review", rid) and await flow.count("task_intents", rid) == 0


async def test_start_needs_clean_attachments(flow):                            # AT-08 (cổng vào)
    rid = await flow.record_with_staging_upload(author="a1")
    r = await flow.start(rid, as_="a1")
    assert r.status_code == 409 and r.json()["type"].endswith("/attachments-pending")
    no_file = await flow.new_record("a1")
    r = await flow.start(no_file, as_="a1")
    assert r.status_code == 409 and r.json()["type"].endswith("/attachments-not-clean")


async def test_record_locked_while_running(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    r = await flow.patch(rid, {"title": "đổi"}, as_="a1")
    assert r.status_code == 409 and r.json()["type"].endswith("/record-in-workflow")
    r = await flow.upload(rid, fixture("clean-text.pdf"), as_="a1")
    assert r.status_code == 409 and r.json()["type"].endswith("/record-not-open")


async def test_upload_racing_with_start_is_refused(flow):          # P2-D4: tệp không lọt vào sau khi duyệt
    rid = await flow.ready_record(author="a1")
    upload = asyncio.create_task(flow.slow_upload(rid, fixture("clean-text.pdf"), as_="a1"))
    assert (await flow.start(rid, as_="a1")).status_code == 200
    r = await upload
    assert flow.slow_uploads_past_checks == 1           # đã qua bước kiểm: trigger chặn lúc ghi uploads
    assert r.status_code == 409 and r.json()["type"].endswith("/record-not-open")
    assert await flow.conn.fetchval("SELECT count(*) FROM uploads WHERE record_id=$1", uuid.UUID(rid)) == 1


async def test_reject_reopens_record(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    await flow.complete_task("review", rid, "reject", as_="r1")
    rec = await flow.get(rid, as_="a1")
    assert rec["wf_state"] == "ended:rejected" and rec["seal_state"] == "NONE"
    assert (await flow.patch(rid, {"title": "sửa lại"}, as_="a1")).status_code == 200


async def test_two_approvers_race_only_one_wins(flow):                         # Review Focus 2
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    r1, r2 = await asyncio.gather(flow.complete_task("review", rid, "approve", as_="r1"),
                                  flow.complete_task("review", rid, "approve", as_="r2"))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    assert await flow.count("task_completions", rid) == 1
    assert await flow.count_ledger("task.completed", subject=rid) == 1


async def test_db_failure_after_flowable_is_reconciled(flow, break_finalize_once):   # P2-D20
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    assert (await flow.complete_task("review", rid, "approve", as_="r1")).status_code == 500
    assert not await flow.task_exists("review", rid)                           # Flowable đã đi tiếp
    r = await flow.admin_post("/admin/v1/workflow:reconcile")
    assert r.json()["completed"] == 1 and r.json()["errors"] == 0
    assert await flow.completion_actor(rid, "review") == "r1"                  # đúng người, đúng quyết định
    assert await flow.task_exists("approve", rid)
    assert (await flow.admin_post("/admin/v1/workflow:reconcile")).json()["records"] == 0   # idempotent


async def test_unreached_flowable_call_does_not_block_retry(flow, flowable_down_once):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    assert (await flow.complete_task("review", rid, "approve", as_="r1")).status_code == 503
    r = await flow.complete_task("review", rid, "approve", as_="r1")
    assert r.status_code == 200, r.text                                         # không phải chờ
    outcomes = await flow.conn.fetch(
        "SELECT o.outcome FROM task_intent_outcomes o JOIN task_intents i ON i.id = o.intent_id"
        " WHERE i.record_id=$1 ORDER BY i.id", uuid.UUID(rid))
    assert [o["outcome"] for o in outcomes] == ["abandoned", "completed"]


async def test_guard_failure_after_flowable_cancels_instance(flow, guard_flips_after_flowable):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    old = await flow.instance_of(rid)
    r = await flow.complete_task("review", rid, "approve", as_="r1")
    assert r.status_code == 409 and r.json()["guard"] == "attachments_clean"
    assert not await flow.instance_running(old)
    assert (await flow.get(rid))["wf_state"] == "ended:guard_failed"
    assert await flow.last_denied_reason() == "guard:attachments_clean:attachments_not_clean"
    await flow.start(rid, as_="a1")
    assert await flow.instance_of(rid) != old
    assert await flow.task_exists("review", rid)                                # không bỏ qua bước review


async def test_kms_down_before_last_task_is_503_and_flowable_untouched(flow, failing_signer):   # AT-20a
    rid = await flow.reviewed_record(author="a1", reviewer="r1")               # đã qua review + pii-review
    r = await flow.complete_task("approve", rid, "approve", as_="p1", signer=failing_signer)
    assert r.status_code == 503 and await flow.task_exists("approve", rid)
    assert r.json()["type"].endswith("/kms-unavailable")
    assert await flow.last_denied_reason() == "kms_unavailable"


async def test_guards_follow_pinned_version_after_upgrade(flow):              # P2-D19
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    await flow.install_version("0.2.0", add_guard={"review": "field_required:cccd"})   # siết chặt: được phép
    r = await flow.complete_task("review", rid, "approve", as_="r1")           # bản ghi không có cccd
    assert r.status_code == 200                                                 # instance cũ theo 0.1.0
    rid2 = await flow.ready_record(author="a1")
    await flow.start(rid2, as_="a1")
    r = await flow.complete_task("review", rid2, "approve", as_="r1")
    assert r.status_code == 409 and r.json()["guard"] == "field_required:cccd"  # instance mới theo 0.2.0


async def test_task_of_other_app_is_404(flow, other_app_task):
    assert (await flow.complete_raw(other_app_task, "approve", as_="r1")).status_code == 404


async def test_inbox_lists_only_my_role_tasks(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    items = await flow.inbox(as_="r1")
    assert [t["task_key"] for t in items] == ["review"]
    assert items[0]["record_id"] == rid and items[0]["collection"] == "doc"
    assert await flow.inbox(as_="p1") == []


async def test_pii_review_requires_read_access(flow):
    rid = await flow.ready_record(author="a1")
    # reviewer đọc được nhưng không thuộc reveal_roles; approver: đọc được và thuộc reveal_roles
    assert (await flow.pii_review(rid, as_="r1")).status_code == 404
    assert await flow.last_denied_reason() == "not_pii_reviewer"
    assert (await flow.pii_review(rid, as_="p1")).status_code == 200
    assert await flow.count("pii_reviews", rid) == 1
    assert await flow.count_ledger("pii.reviewed", subject=rid) == 1


# ---------- Bổ sung ----------

async def test_reaching_seal_end_without_seal_hooks_fails_closed(flow):
    """Chưa có Task 7: tới end event niêm phong thì rollback, 500; không SEAL_PENDING thiếu seal_requests."""
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    assert flow.api.app.state.seal_hooks is None
    r = await flow.complete_task("approve", rid, "approve", as_="p1")
    assert r.status_code == 500
    row = await flow.conn.fetchrow("SELECT seal_state, wf_state FROM records WHERE id=$1", uuid.UUID(rid))
    assert (row["seal_state"], row["wf_state"]) == ("NONE", "running")
    assert await flow.count("seal_requests", rid) == 0
    assert await flow.completion_actor(rid, "approve") is None
    pending = await flow.conn.fetchval(
        "SELECT count(*) FROM task_intents i WHERE i.record_id=$1 AND NOT EXISTS"
        " (SELECT 1 FROM task_intent_outcomes o WHERE o.intent_id = i.id)", uuid.UUID(rid))
    assert pending == 1                                         # đối soát được sau khi Task 7 nối hook


async def test_seal_end_requests_seal_in_transaction_and_tries_once_after_commit(flow):
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    calls: list[str] = []
    seal_id = "A" * 26

    async def request_seal(conn, *, record, m):
        assert conn.is_in_transaction() and record["seal_state"] == "SEAL_PENDING"
        assert m.app.version == record["wf_app_version"] == "0.1.0"
        await conn.execute(
            "INSERT INTO seal_requests(seal_id, record_id, app_id, app_version, record_digest, attachments,"
            " public_fields) VALUES ($1, $2, $3, $4, $5, '[]', '{}')",
            seal_id, record["id"], record["app_id"], record["wf_app_version"], "a" * 64)
        calls.append("request")
        return seal_id

    async def seal_record(conn, *, signer, hmac_key, settings, record_id):
        assert not conn.is_in_transaction() and str(record_id) == rid
        calls.append("seal")
        raise KmsUnavailable("giả lập")

    flow.api.app.state.seal_hooks = SealHooks(request_seal=request_seal, seal_record=seal_record)
    r = await flow.complete_task("approve", rid, "approve", as_="p1")
    assert r.status_code == 200, r.text
    assert calls == ["request", "seal"]
    body = r.json()
    assert body["seal_state"] == "SEAL_PENDING" and body["seal_id"] == seal_id
    assert body["record"]["wf_state"] == "ended:approved"
    assert await flow.count_ledger("workflow.completed", subject=rid) == 1


async def test_decision_and_comment_are_validated_before_flowable(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    assert (await flow.complete_task("review", rid, "maybe", as_="r1")).status_code == 422   # ngoài cổng
    assert (await flow.complete_task("review", rid, "Approve!", as_="r1")).status_code == 422
    r = await flow.complete_task("review", rid, "approve", as_="r1", comment="x" * 1001)
    assert r.status_code == 422
    assert await flow.task_exists("review", rid) and await flow.count("task_intents", rid) == 0
    secret = "ghi-chú-không-được-lưu-" + uuid.uuid4().hex
    assert (await flow.complete_task("review", rid, "approve", as_="r1", comment=secret)).status_code == 200
    dump = json.dumps([dict(r) for r in await flow.conn.fetch("SELECT * FROM task_intents")], default=str)
    assert secret not in dump                                                   # P2-D24


async def test_wrong_task_role_is_404_and_logged(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    assert (await flow.complete_task("review", rid, "approve", as_="p1")).status_code == 404
    assert await flow.last_denied_reason() == "not_task_role"


async def test_completed_task_is_409_and_stale_version_is_409(flow):
    rid = await flow.ready_record(author="a1")
    await flow.start(rid, as_="a1")
    tid = await flow.task_id("review", rid)
    stale = await flow.version(rid) - 1
    r = await flow.complete_raw(tid, "approve", as_="r1", version=stale)
    assert r.status_code == 409 and r.json()["type"].endswith("/version-conflict")
    assert (await flow.complete_task("review", rid, "approve", as_="r1")).status_code == 200
    r = await flow.complete_raw(tid, "approve", as_="r1", version=await flow.version(rid))
    assert r.status_code == 409 and r.json()["type"].endswith("/task-gone")
    assert (await flow.complete_raw(f"no-such-{uuid.uuid4()}", "approve", as_="r1")).status_code == 404
    assert (await flow.complete_raw("..%2F..%2Fx", "approve", as_="r1")).status_code == 404


async def test_org_not_configured_and_expired_key_statement_block_last_task(flow):    # P2-D25, spec 25.3
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    state = flow.api.app.state
    good = state.settings
    state.settings = good.model_copy(update={"org_name": ORG_NAME_DEFAULT})
    try:
        r = await flow.complete_task("approve", rid, "approve", as_="p1")
    finally:
        state.settings = good
    assert r.status_code == 503 and r.json()["type"].endswith("/org-not-configured")
    assert await flow.last_denied_reason() == "org_not_configured"
    past = datetime.now(UTC) - timedelta(days=2)
    statement = {"format": "dxos-key-statement/1", "key": "seal-key", "version": 1,
                 "valid_from": (past - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "valid_until": past.strftime("%Y-%m-%dT%H:%M:%SZ")}
    await flow.conn.execute(
        "INSERT INTO key_statements(key, version, statement, statement_sha256)"
        " VALUES ('seal-key', 1, $1, $2)",
        json.dumps(statement), sha256_hex(canonical_bytes(statement)))
    r = await flow.complete_task("approve", rid, "approve", as_="p1")
    assert r.status_code == 503 and r.json()["type"].endswith("/seal-key-expired")
    assert await flow.last_denied_reason() == "seal_key_expired"
    assert await flow.task_exists("approve", rid)
    assert await flow.count("task_intents", rid) == 1                           # chỉ ý định của review


async def test_inbox_needs_an_app_role(flow):
    r = await flow.api.get("/api/v1/apps/test-flow/tasks?assigned=me", headers=flow.admin())
    assert r.status_code == 403
    assert await flow.last_denied_reason() == "admin_no_data_access"


async def test_deny_refuses_to_run_inside_a_transaction(core_conn):
    from helpers.manifests import P

    async with core_conn.transaction():
        with pytest.raises(RuntimeError):
            await deny(core_conn, P("u1", []), manifest("test-flow"), action="complete",
                       reason="not_task_role", subject="s", hmac_key=b"k")
