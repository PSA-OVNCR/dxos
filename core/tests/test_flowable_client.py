# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test client Flowable REST với HTTP giả lập (respx). Plan 02 Task 4.

Tên endpoint/tham số trong test này đã được đối chiếu với Flowable 7.1.0 thật, xem
``docs/spikes/flowable.md`` (mục "Kiểm lại Plan 02 Task 4") và test integration ``test_flowable_live``.
"""

import json
from urllib.parse import parse_qs

import httpx
import pytest
from dxos_core.settings import Settings
from dxos_core.workflow.flowable import (
    FlowableClient,
    FlowTask,
    Outcome,
    TaskGone,
    WorkflowUnavailable,
    flowable_from_settings,
)

BASE = "http://flowable.test:8080/flowable-rest/service"
PASSWORD = "changeme-flowable-secret"


@pytest.fixture
def client() -> FlowableClient:
    return FlowableClient(BASE, "rest-admin", PASSWORD)


def task_json(**over) -> dict:
    base = {"id": "t1", "taskDefinitionKey": "review", "name": None, "processInstanceId": "i1",
            "processDefinitionId": "test-flow.review:3:abc-def", "assignee": None,
            "createTime": "2026-10-21T13:14:30.393+07:00"}
    return base | over


def query(route) -> dict[str, list[str]]:
    return parse_qs(route.calls.last.request.url.query.decode())


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


# ---------------------------------------------------------------- ánh xạ lỗi
async def test_5xx_and_network_errors_are_unavailable(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/process-instances").mock(return_value=httpx.Response(503))
    with pytest.raises(WorkflowUnavailable):
        await client.start("test-flow.review:1:1", "rid", {})
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(WorkflowUnavailable):
        await client.get_task("t1")


async def test_timeout_is_unavailable(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(WorkflowUnavailable):
        await client.get_task("t1")


@pytest.mark.parametrize("status", [401, 403, 500, 502, 503])
async def test_auth_and_server_errors_are_unavailable_never_none(client, respx_mock, status):
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(status))
    with pytest.raises(WorkflowUnavailable):
        await client.get_task("t1")


async def test_unexpected_4xx_is_unavailable_with_status_but_without_body(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/process-instances").mock(
        return_value=httpx.Response(400, json={"exception": f"leak {PASSWORD}"}))
    with pytest.raises(WorkflowUnavailable) as e:
        await client.start("nope:1:1", "rid", {})
    assert "400" in str(e.value)
    assert PASSWORD not in str(e.value) and "leak" not in str(e.value)


async def test_garbage_json_is_unavailable(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/process-instances").mock(return_value=httpx.Response(201, text="<html>"))
    with pytest.raises(WorkflowUnavailable):
        await client.start("d:1:1", "rid", {})


async def test_password_never_appears_in_error_messages(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(side_effect=httpx.ConnectError(f"boom {PASSWORD}"))
    with pytest.raises(WorkflowUnavailable) as e:
        await client.get_task("t1")
    assert PASSWORD not in str(e.value) and PASSWORD not in repr(client)


@pytest.mark.parametrize("status", [404, 409])
async def test_complete_on_gone_or_conflicting_task_is_task_gone(client, respx_mock, status):
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(status))
    with pytest.raises(TaskGone):
        await client.complete("t1", {"decision": "approve"})


@pytest.mark.parametrize("exception", [
    "Execution[ id 'e5' ] - definition 'test-flow.review:3:x' - activity 'approve' - parent 'e4'"
    " was updated by another transaction concurrently",
    'Cannot invoke "ExecutionEntity.getId()" because "processInstanceExecution" is null'])
async def test_complete_lost_race_reported_as_500_is_task_gone(client, respx_mock, exception):
    """Flowable 7.1.0 trả 500 (không phải 409) cho bên thua cuộc đua, thông điệp khác nhau; task đã xong."""
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(
        return_value=httpx.Response(500, json={"message": "Internal server error", "exception": exception}))
    hist = respx_mock.get(f"{BASE}/history/historic-task-instances/t1").mock(
        return_value=httpx.Response(200, json={"id": "t1", "endTime": "2026-10-21T13:15:15.403+07:00"}))
    with pytest.raises(TaskGone):
        await client.complete("t1", {"decision": "approve"})
    assert hist.called


async def test_complete_500_on_open_task_stays_unavailable(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(
        return_value=httpx.Response(500, json={"exception": "No outgoing sequence flow of the gateway"}))
    respx_mock.get(f"{BASE}/history/historic-task-instances/t1").mock(
        return_value=httpx.Response(200, json={"id": "t1", "endTime": None}))
    with pytest.raises(WorkflowUnavailable):
        await client.complete("t1", {"decision": "approve"})


async def test_complete_500_with_unreadable_history_stays_unavailable(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(500))
    respx_mock.get(f"{BASE}/history/historic-task-instances/t1").mock(return_value=httpx.Response(503))
    with pytest.raises(WorkflowUnavailable):
        await client.complete("t1", {"decision": "approve"})


async def test_get_task_404_is_none(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(404))
    assert await client.get_task("t1") is None


async def test_cancel_404_is_not_an_error_and_sends_reason(client, respx_mock):
    route = respx_mock.delete(f"{BASE}/runtime/process-instances/i1").mock(return_value=httpx.Response(204))
    await client.cancel("i1", "dxos:huy")
    assert query(route) == {"deleteReason": ["dxos:huy"]}
    route.mock(return_value=httpx.Response(404))
    await client.cancel("i1", "dxos:huy")
    route.mock(return_value=httpx.Response(500))
    with pytest.raises(WorkflowUnavailable):
        await client.cancel("i1", "dxos:huy")


# ---------------------------------------------------------------- xác thực và biến
async def test_basic_auth_sent_and_only_string_variables(client, respx_mock):
    route = respx_mock.post(f"{BASE}/runtime/process-instances").mock(
        return_value=httpx.Response(201, json={"id": "i1"}))
    assert await client.start("test-flow.review:1:1", "rid", {"dxos_record_id": "rid"}) == "i1"
    req = route.calls.last.request
    assert req.headers["authorization"].startswith("Basic ")
    assert body(route) == {"processDefinitionId": "test-flow.review:1:1", "businessKey": "rid",
                           "variables": [{"name": "dxos_record_id", "value": "rid", "type": "string"}]}


async def test_start_without_variables_sends_empty_list(client, respx_mock):
    route = respx_mock.post(f"{BASE}/runtime/process-instances").mock(
        return_value=httpx.Response(201, json={"id": "i1"}))
    await client.start("d:1:1", "rid", {})
    assert body(route)["variables"] == []


@pytest.mark.parametrize("bad", [True, 1, None, b"x", ["a"]])
async def test_non_string_variable_values_are_rejected_before_any_request(client, respx_mock, bad):
    route = respx_mock.post(f"{BASE}/runtime/process-instances").mock(
        return_value=httpx.Response(201, json={"id": "i"}))
    with pytest.raises(TypeError):
        await client.start("d:1:1", "rid", {"a": bad})
    with pytest.raises(TypeError):
        await client.complete("t1", {"a": bad})
    with pytest.raises(TypeError):
        await client.complete("t1", {}, local_variables={"a": bad})
    assert not route.called


async def test_complete_sends_global_and_task_local_variables(client, respx_mock):
    route = respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(200))
    await client.complete("t1", {"decision": "approve"}, local_variables={"dxos_intent_id": "intent-1"})
    assert body(route) == {"action": "complete", "variables": [
        {"name": "decision", "value": "approve", "type": "string"},
        {"name": "dxos_intent_id", "value": "intent-1", "type": "string", "scope": "local"}]}


async def test_complete_positional_signature_without_local_variables(client, respx_mock):
    route = respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(200))
    await client.complete("t1", {"decision": "reject"})
    assert body(route) == {"action": "complete",
                           "variables": [{"name": "decision", "value": "reject", "type": "string"}]}


async def test_same_name_in_global_and_local_is_rejected(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(200))
    with pytest.raises(ValueError, match="decision"):
        await client.complete("t1", {"decision": "a"}, local_variables={"decision": "b"})


# ---------------------------------------------------------------- outcome
async def test_outcome_reads_history_end_activity(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/process-instances/i1").mock(return_value=httpx.Response(404))
    respx_mock.get(f"{BASE}/history/historic-process-instances/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1", "endTime": "2026-11-01T00:00:00Z",
                                               "endActivityId": "approved"}))
    assert await client.outcome("i1") == Outcome(ended=True, end_event="approved")


async def test_outcome_running_does_not_touch_history(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/process-instances/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1", "ended": False}))
    assert await client.outcome("i1") == Outcome(ended=False, end_event=None)


async def test_outcome_cancelled_instance_has_no_end_event(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/process-instances/i1").mock(return_value=httpx.Response(404))
    respx_mock.get(f"{BASE}/history/historic-process-instances/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1", "endTime": "2026-11-01T00:00:00Z",
                                               "endActivityId": None, "deleteReason": "dxos:huy"}))
    assert await client.outcome("i1") == Outcome(ended=True, end_event=None)


async def test_outcome_of_unknown_instance_is_unavailable(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/process-instances/i1").mock(return_value=httpx.Response(404))
    respx_mock.get(f"{BASE}/history/historic-process-instances/i1").mock(return_value=httpx.Response(404))
    with pytest.raises(WorkflowUnavailable):
        await client.outcome("i1")


# ---------------------------------------------------------------- deploy / definition
async def test_deploy_reuses_deployment_with_same_name(client, respx_mock):
    lookup = respx_mock.get(f"{BASE}/repository/deployments").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "dep-old"}], "total": 1}))
    post = respx_mock.post(f"{BASE}/repository/deployments").mock(
        return_value=httpx.Response(201, json={"id": "new"}))
    assert await client.deploy("test-flow@it", "test-review.bpmn20.xml", b"<definitions/>") == "dep-old"
    assert query(lookup)["name"] == ["test-flow@it"]
    assert not post.called


async def test_deploy_posts_multipart_with_deployment_name_when_absent(client, respx_mock):
    respx_mock.get(f"{BASE}/repository/deployments").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0}))
    post = respx_mock.post(f"{BASE}/repository/deployments").mock(
        return_value=httpx.Response(201, json={"id": "dep-new", "name": "test-flow@it"}))
    assert await client.deploy("test-flow@it", "test-review.bpmn20.xml", b"<definitions/>") == "dep-new"
    req = post.calls.last.request
    assert query(post) == {"deploymentName": ["test-flow@it"]}
    assert req.headers["content-type"].startswith("multipart/form-data")
    assert b'name="file"; filename="test-review.bpmn20.xml"' in req.content
    assert b"<definitions/>" in req.content


@pytest.mark.parametrize("filename", ["x.bpmn", "x.xml", "../x.bpmn20.xml", "a/b.bpmn20.xml", ""])
async def test_deploy_rejects_bad_filename(client, respx_mock, filename):
    with pytest.raises(ValueError):
        await client.deploy("n", filename, b"<definitions/>")


async def test_definition_id_of_deployment(client, respx_mock):
    route = respx_mock.get(f"{BASE}/repository/process-definitions").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "test-flow.review:3:abc"}], "total": 1}))
    assert await client.definition_id("dep1") == "test-flow.review:3:abc"
    assert query(route) == {"deploymentId": ["dep1"]}


@pytest.mark.parametrize("data", [[], [{"id": "a:1:1"}, {"id": "b:1:1"}]])
async def test_definition_id_requires_exactly_one_definition(client, respx_mock, data):
    respx_mock.get(f"{BASE}/repository/process-definitions").mock(
        return_value=httpx.Response(200, json={"data": data, "total": len(data)}))
    with pytest.raises(WorkflowUnavailable):
        await client.definition_id("dep1")


# ---------------------------------------------------------------- instance / task
async def test_running_instance_by_definition_and_business_key(client, respx_mock):
    route = respx_mock.get(f"{BASE}/runtime/process-instances").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "i9"}], "total": 1}))
    assert await client.running_instance("d:1:1", "rec-1") == "i9"
    assert query(route) == {"processDefinitionId": ["d:1:1"], "businessKey": ["rec-1"]}
    route.mock(return_value=httpx.Response(200, json={"data": [], "total": 0}))
    assert await client.running_instance("d:1:1", "rec-1") is None


async def test_business_key_running_then_history_then_none(client, respx_mock):
    run = respx_mock.get(f"{BASE}/runtime/process-instances/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1", "businessKey": "rec-1"}))
    assert await client.business_key("i1") == "rec-1"
    run.mock(return_value=httpx.Response(404))
    hist = respx_mock.get(f"{BASE}/history/historic-process-instances/i1").mock(
        return_value=httpx.Response(200, json={"id": "i1", "businessKey": "rec-1"}))
    assert await client.business_key("i1") == "rec-1"
    hist.mock(return_value=httpx.Response(404))
    assert await client.business_key("i1") is None
    run.mock(return_value=httpx.Response(200, json={"id": "i1", "businessKey": None}))
    assert await client.business_key("i1") is None


async def test_get_task_maps_fields(client, respx_mock):
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(200, json=task_json()))
    assert await client.get_task("t1") == FlowTask(
        id="t1", task_key="review", name="", process_instance_id="i1",
        process_definition_key="test-flow.review", assignee=None, created="2026-10-21T13:14:30.393+07:00")


async def test_historic_task_done(client, respx_mock):
    route = respx_mock.get(f"{BASE}/history/historic-task-instances/t1").mock(
        return_value=httpx.Response(200, json={"id": "t1", "endTime": "2026-10-21T13:15:15.403+07:00"}))
    assert await client.historic_task_done("t1") is True
    route.mock(return_value=httpx.Response(200, json={"id": "t1", "endTime": None}))
    assert await client.historic_task_done("t1") is False
    route.mock(return_value=httpx.Response(404))
    assert await client.historic_task_done("t1") is False
    route.mock(return_value=httpx.Response(503))
    with pytest.raises(WorkflowUnavailable):
        await client.historic_task_done("t1")


async def test_historic_intent_id_reads_task_scoped_variable(client, respx_mock):
    route = respx_mock.get(f"{BASE}/history/historic-variable-instances").mock(
        return_value=httpx.Response(200, json={"data": [{"taskId": "t1", "variable": {
            "name": "dxos_intent_id", "type": "string", "value": "intent-1",
            "scope": "local"}}], "total": 1}))
    assert await client.historic_intent_id("t1") == "intent-1"
    assert query(route) == {"taskId": ["t1"], "variableName": ["dxos_intent_id"]}
    route.mock(return_value=httpx.Response(200, json={"data": [], "total": 0}))
    assert await client.historic_intent_id("t1") is None


# ---------------------------------------------------------------- list_tasks
async def test_list_tasks_filters_by_candidate_groups_and_key_prefix(client, respx_mock):
    route = respx_mock.get(f"{BASE}/runtime/tasks").mock(
        return_value=httpx.Response(200, json={"data": [task_json()], "total": 1, "start": 0, "size": 1}))
    tasks = await client.list_tasks(["app:test-flow:reviewer", "app:test-flow:approver"], "test-flow.")
    assert [t.id for t in tasks] == ["t1"]
    q = query(route)
    # Flowable 7.1.0 bỏ qua IM LẶNG `candidateGroupIn`; tên đúng là `candidateGroups` (phân cách dấu phẩy).
    assert "candidateGroupIn" not in q
    assert q["candidateGroups"] == ["app:test-flow:reviewer,app:test-flow:approver"]
    assert q["processDefinitionKeyLike"] == ["test-flow.%"]


async def test_list_tasks_follows_pages(client, respx_mock):
    pages = {"0": [task_json(id=f"a{i}", createTime=f"2026-10-21T10:00:{i:02d}Z") for i in range(3)],
             "3": [task_json(id=f"b{i}", createTime=f"2026-10-21T11:00:{i:02d}Z") for i in range(2)]}

    def reply(request: httpx.Request) -> httpx.Response:
        start = request.url.params["start"]
        assert request.url.params["size"] == "3"
        return httpx.Response(200, json={"data": pages[start], "total": 5, "start": int(start)})

    respx_mock.get(f"{BASE}/runtime/tasks").mock(side_effect=reply)
    client._page_size = 3
    tasks = await client.list_tasks(["g"], "test-flow.")
    assert [t.id for t in tasks] == ["a0", "a1", "a2", "b0", "b1"]


async def test_list_tasks_empty_groups_make_no_request(client, respx_mock):
    route = respx_mock.get(f"{BASE}/runtime/tasks").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0}))
    assert await client.list_tasks([], "test-flow.") == []
    assert not route.called


@pytest.mark.parametrize("groups", [["a,b"], [""], ["ok", " "]])
async def test_list_tasks_rejects_groups_that_could_widen_the_filter(client, respx_mock, groups):
    route = respx_mock.get(f"{BASE}/runtime/tasks").mock(
        return_value=httpx.Response(200, json={"data": [], "total": 0}))
    with pytest.raises(ValueError):
        await client.list_tasks(groups, "test-flow.")
    assert not route.called


async def test_list_tasks_rejects_empty_prefix(client, respx_mock):
    with pytest.raises(ValueError):
        await client.list_tasks(["g"], "")


async def test_list_tasks_also_filters_prefix_exactly_on_the_client(client, respx_mock):
    """LIKE của Flowable coi `_` và `%` là ký tự đại diện; lọc lại `startswith` để không rò sang app khác."""
    respx_mock.get(f"{BASE}/runtime/tasks").mock(return_value=httpx.Response(200, json={"total": 2, "data": [
        task_json(id="t1", processDefinitionId="test_flow.review:1:x"),
        task_json(id="t2", processDefinitionId="testXflow.review:1:x")]}))
    assert [t.id for t in await client.list_tasks(["g"], "test_flow.")] == ["t1"]


# ---------------------------------------------------------------- Settings và factory
def test_settings_defaults_leave_flowable_unconfigured(make_settings):
    s = make_settings()
    assert s.flowable_url == "http://flowable:8080/flowable-rest/service"
    assert s.flowable_user == "rest-admin"
    assert s.flowable_password_file is None
    assert flowable_from_settings(s) is None


async def test_factory_reads_password_file_at_use_time(make_settings, tmp_path, respx_mock):
    pw = tmp_path / "flowable-rest-password"
    route = respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(404))
    s: Settings = make_settings(flowable_url=BASE, flowable_password_file=pw)
    seen = []
    for secret in ("first\n", "rotated\n"):
        pw.write_text(secret, encoding="utf-8")
        c = flowable_from_settings(s)
        assert isinstance(c, FlowableClient) and c.base_url == BASE
        await c.get_task("t1")
        seen.append(route.calls.last.request.headers["authorization"])
    assert seen[0] != seen[1]


def test_factory_fails_closed_when_secret_unreadable(make_settings, tmp_path):
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")
    for path in (tmp_path / "missing", empty):
        with pytest.raises(WorkflowUnavailable):
            flowable_from_settings(make_settings(flowable_password_file=path))


# ---------------------------------------------------------------- id đặt vào đường dẫn URL (fix round 1)
BAD_IDS = ["../../repository/deployments/x", "a?b=c", "a#b", "..", ".", "", "a/b", "a b", "a\\b", "x" * 256,
           "a%2Fb", "é"]


@pytest.mark.parametrize("bad", BAD_IDS)
async def test_ids_in_url_paths_are_validated_before_any_request(client, respx_mock, bad):
    respx_mock.route().mock(return_value=httpx.Response(200, json={}))
    calls = [
        client.cancel(bad, "r"), client.outcome(bad), client.get_task(bad), client.complete(bad, {"d": "x"}),
        client.business_key(bad), client.historic_task_done(bad), client.historic_intent_id(bad),
    ]
    for coro in calls:
        with pytest.raises(ValueError):
            await coro
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize("bad", [None, 7, b"x"])
async def test_non_string_ids_are_rejected(client, respx_mock, bad):
    respx_mock.route().mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        await client.get_task(bad)
    assert respx_mock.calls.call_count == 0


@pytest.mark.parametrize("good", ["test-flow.review:1:42", "ad32d484-cd16-11f1-b9f8-02fc00000001", "a@b_c",
                                  "x" * 255])
async def test_real_shaped_ids_are_accepted(client, respx_mock, good):
    respx_mock.get(f"{BASE}/runtime/tasks/{good}").mock(return_value=httpx.Response(404))
    assert await client.get_task(good) is None


# ---------------------------------------------------------------- các điểm nhỏ của fix round 1
@pytest.mark.parametrize("body", [{"data": []}, {"data": [], "total": "5"}, {"data": [], "total": None}])
async def test_list_tasks_unknown_total_is_unavailable(client, respx_mock, body):
    respx_mock.get(f"{BASE}/runtime/tasks").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(WorkflowUnavailable):
        await client.list_tasks(["g"], "test-flow.")


async def test_list_tasks_beyond_page_cap_is_unavailable(client, respx_mock, monkeypatch):
    monkeypatch.setattr("dxos_core.workflow.flowable._MAX_TASKS", 6)
    client._page_size = 2
    respx_mock.get(f"{BASE}/runtime/tasks").mock(side_effect=lambda r: httpx.Response(200, json={
        "total": 10**9, "data": [task_json(id=f"t{r.url.params['start']}-{i}") for i in range(2)]}))
    with pytest.raises(WorkflowUnavailable):
        await client.list_tasks(["g"], "test-flow.")


@pytest.mark.parametrize("url", ["http://u:p@flowable.test/x", "http://u@flowable.test/x"])
def test_base_url_with_userinfo_is_rejected(url):
    with pytest.raises(ValueError) as e:
        FlowableClient(url, "rest-admin", PASSWORD)
    assert "u:p" not in str(e.value) and PASSWORD not in str(e.value)


async def test_proxy_environment_is_ignored(client, respx_mock, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    created = []
    real = httpx.AsyncClient

    def spy(*args, **kwargs):
        created.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr("dxos_core.workflow.flowable.httpx.AsyncClient", spy)
    respx_mock.get(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(404))
    await client.get_task("t1")
    assert created and all(kw.get("trust_env") is False for kw in created)


async def test_ping_ok_and_failures(client, respx_mock):
    route = respx_mock.get(f"{BASE}/management/engine").mock(
        return_value=httpx.Response(200, json={"version": "7.1.0"}))
    assert await client.ping() is None
    for resp in (httpx.Response(404), httpx.Response(401), httpx.Response(503)):
        route.mock(return_value=resp)
        with pytest.raises(WorkflowUnavailable):
            await client.ping()
    route.mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(WorkflowUnavailable):
        await client.ping()


# ---------------------------------------------------------------- request có tới Flowable không (fix vòng 1)
@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ConnectTimeout("syn"),
                                 httpx.PoolTimeout("pool")])
async def test_never_sent_errors_are_marked_not_sent(client, respx_mock, exc):
    """Lỗi trước khi request rời client: chắc chắn Flowable chưa nhận gì (bên gọi bỏ ý định ngay)."""
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(side_effect=exc)
    with pytest.raises(WorkflowUnavailable) as e:
        await client.complete("t1", {"decision": "approve"})
    assert e.value.sent is False


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.WriteTimeout("slow"),
                                 httpx.RemoteProtocolError("eof"), httpx.ReadError("reset")])
async def test_errors_after_sending_are_outcome_unknown(client, respx_mock, exc):
    """Request có thể đã tới Flowable và được commit sau đó: kết quả không rõ (sent=True)."""
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(side_effect=exc)
    with pytest.raises(WorkflowUnavailable) as e:
        await client.complete("t1", {"decision": "approve"})
    assert e.value.sent is True


async def test_status_errors_and_default_are_sent(client, respx_mock):
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(503))
    with pytest.raises(WorkflowUnavailable) as e:
        await client.complete("t1", {"decision": "approve"})
    assert e.value.sent is True
    assert WorkflowUnavailable("x").sent is True                       # mặc định thận trọng


async def test_complete_500_then_history_unreachable_is_still_sent(client, respx_mock):
    """POST đã tới Flowable (trả 500); lần đọc lịch sử sau đó không kết nối được vẫn là 'không rõ kết quả'."""
    respx_mock.post(f"{BASE}/runtime/tasks/t1").mock(return_value=httpx.Response(500))
    respx_mock.get(f"{BASE}/history/historic-task-instances/t1").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(WorkflowUnavailable) as e:
        await client.complete("t1", {"decision": "approve"})
    assert e.value.sent is True


def test_client_exposes_timeout(client):
    assert client.timeout_s == 10.0
    assert FlowableClient(BASE, "u", "p", timeout_s=3.5).timeout_s == 3.5
