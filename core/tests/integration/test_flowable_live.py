# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client Flowable trên Flowable 7.1.0 thật (compose.test, H2). Plan 02 Task 4.

Flowable dùng chung và còn dữ liệu của các lần chạy trước: mỗi test dùng business key riêng,
chọn task theo process instance và hủy instance của mình khi xong.
"""

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from dxos_core.registry.bpmn import parse_bpmn, render_bpmn
from dxos_core.workflow.flowable import (
    FlowableClient,
    Outcome,
    TaskGone,
    WorkflowUnavailable,
)

pytestmark = pytest.mark.integration

FIX = Path(__file__).resolve().parents[1] / "fixtures"
NAME, FILENAME = "test-flow@it", "test-review.bpmn20.xml"
REVIEWER, APPROVER = "app:test-flow:reviewer", "app:test-flow:approver"


def model_xml() -> bytes:
    """test-review.bpmn đi qua bộ kiểm danh sách cho phép và bản dựng lại chuẩn, đúng như lúc cài app thật."""
    raw = (FIX / "bpmn/test-review.bpmn").read_bytes()
    return render_bpmn(parse_bpmn(raw, app_id="test-flow", seal_end="approved"))


@pytest.fixture
async def definition_id(flowable_client: FlowableClient) -> str:
    return await flowable_client.definition_id(await flowable_client.deploy(NAME, FILENAME, model_xml()))


async def start(c: FlowableClient, definition_id: str) -> tuple[str, str, str]:
    """Bắt đầu một instance mới; trả (business key, instance id, id task xem xét của chính nó)."""
    key = f"rec-{uuid4()}"
    iid = await c.start(definition_id, key, {"dxos_record_id": key})
    [task] = [t for t in await c.list_tasks([REVIEWER], "test-flow.") if t.process_instance_id == iid]
    return key, iid, task.id


async def test_round_trip_on_real_flowable(flowable_client):
    c = flowable_client
    dep = await c.deploy(NAME, FILENAME, model_xml())
    assert dep == await c.deploy(NAME, FILENAME, model_xml())   # idempotent theo tên deployment
    key = f"rec-{uuid4()}"
    iid = await c.start(await c.definition_id(dep), key, {"dxos_record_id": key})
    [t] = [x for x in await c.list_tasks([REVIEWER], "test-flow.") if x.process_instance_id == iid]
    assert t.task_key == "review" and t.process_definition_key == "test-flow.review" and t.assignee is None
    assert await c.business_key(t.process_instance_id) == key
    assert (await c.get_task(t.id)) == t
    assert not await c.historic_task_done(t.id)
    await c.complete(t.id, {"decision": "reject"})
    assert await c.outcome(iid) == Outcome(ended=True, end_event="rejected")
    assert await c.historic_task_done(t.id)
    assert await c.business_key(iid) == key              # instance đã kết thúc: đọc từ lịch sử


async def test_intent_id_is_task_local_and_readable_from_history(definition_id, flowable_client):
    c = flowable_client
    _, iid, tid = await start(c, definition_id)
    assert await c.historic_intent_id(tid) is None
    intent = f"intent-{uuid4()}"
    await c.complete(tid, {"decision": "approve"}, local_variables={"dxos_intent_id": intent})
    assert await c.historic_intent_id(tid) == intent
    assert await c.outcome(iid) == Outcome(ended=False, end_event=None)       # còn bước phê duyệt
    [approve] = [t for t in await c.list_tasks([APPROVER], "test-flow.") if t.process_instance_id == iid]
    assert approve.task_key == "approve"
    assert await c.historic_intent_id(approve.id) is None                     # không rò sang task khác
    await c.complete(approve.id, {"decision": "approve"})
    assert await c.outcome(iid) == Outcome(ended=True, end_event="approved")


async def test_candidate_group_filter_really_filters(definition_id, flowable_client):
    """Bẫy đã gặp: `candidateGroupIn` bị Flowable bỏ qua và trả MỌI task; nhóm khác không được thấy task."""
    c = flowable_client
    _, iid, tid = await start(c, definition_id)
    try:
        assert tid in {t.id for t in await c.list_tasks([REVIEWER], "test-flow.")}
        assert tid in {t.id for t in await c.list_tasks(["x", REVIEWER], "test-flow.")}
        assert tid not in {t.id for t in await c.list_tasks([APPROVER], "test-flow.")}
        assert tid not in {t.id for t in await c.list_tasks([REVIEWER], "other-app.")}
        assert tid not in {t.id for t in await c.list_tasks(["app:other:reviewer"], "test-flow.")}
    finally:
        await c.cancel(iid, "dxos:test")


async def test_list_tasks_pages_beyond_flowable_default_of_ten(definition_id, flowable_client):
    c = flowable_client
    iids = [(await start(c, definition_id))[1] for _ in range(12)]
    try:
        got = {t.process_instance_id for t in await c.list_tasks([REVIEWER], "test-flow.")}
        assert set(iids) <= got
    finally:
        await asyncio.gather(*(c.cancel(i, "dxos:test") for i in iids))


async def test_complete_twice_is_task_gone(definition_id, flowable_client):
    c = flowable_client
    _, iid, tid = await start(c, definition_id)
    await c.complete(tid, {"decision": "reject"})
    with pytest.raises(TaskGone):
        await c.complete(tid, {"decision": "reject"})
    assert await c.get_task(tid) is None
    assert await c.get_task(f"no-such-{uuid4()}") is None


async def test_concurrent_completes_one_winner_everyone_else_task_gone(definition_id, flowable_client):
    c = flowable_client
    for _ in range(3):
        _, iid, tid = await start(c, definition_id)
        results = await asyncio.gather(*(c.complete(tid, {"decision": "reject"}) for _ in range(6)),
                                       return_exceptions=True)
        assert sum(r is None for r in results) == 1, results
        assert all(r is None or isinstance(r, TaskGone) for r in results), results
        assert await c.outcome(iid) == Outcome(ended=True, end_event="rejected")


async def test_cancel_running_unknown_and_twice(definition_id, flowable_client):
    c = flowable_client
    key, iid, tid = await start(c, definition_id)
    assert await c.running_instance(definition_id, key) == iid
    await c.cancel(iid, "dxos:hủy-thử")
    assert await c.outcome(iid) == Outcome(ended=True, end_event=None)
    assert await c.running_instance(definition_id, key) is None
    assert await c.historic_task_done(tid)
    await c.cancel(iid, "dxos:hủy-thử")                                       # 404 không phải lỗi
    await c.cancel(f"no-such-{uuid4()}", "dxos:hủy-thử")


async def test_start_by_definition_id_pins_the_version(flowable_client):
    c = flowable_client
    d1 = await c.definition_id(await c.deploy(NAME, FILENAME, model_xml()))
    d2 = await c.definition_id(await c.deploy(f"{NAME}-v2-{uuid4()}", FILENAME, model_xml()))
    assert d1 != d2 and d1.split(":")[0] == d2.split(":")[0] == "test-flow.review"   # cùng key, bản khác nhau
    key = f"rec-{uuid4()}"
    iid = await c.start(d1, key, {})
    try:
        assert await c.running_instance(d1, key) == iid
        assert await c.running_instance(d2, key) is None
    finally:
        await c.cancel(iid, "dxos:test")


async def test_wrong_password_is_unavailable(flowable_client):
    bad = FlowableClient(flowable_client.base_url, "rest-admin", "wrong-password")
    with pytest.raises(WorkflowUnavailable):
        await bad.get_task("t1")


async def test_unreachable_flowable_is_unavailable():
    down = FlowableClient("http://127.0.0.1:1/flowable-rest/service", "u", "p", timeout_s=2.0)
    with pytest.raises(WorkflowUnavailable):
        await down.get_task("t1")
