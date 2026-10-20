# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Smoke test Flowable REST (spike Plan 01 Task 6). Chỉ dùng thư viện chuẩn.

Chạy TRONG mạng net-wf (Flowable không có cổng ra ngoài), xem flowable-smoke.sh.
Các bước: chờ engine -> deploy BPMN 1 user task -> start theo key -> liệt kê task
theo candidateGroup -> complete kèm biến -> kiểm process đã kết thúc -> xóa deployment.
Dòng cuối là `SMOKE OK` nếu mọi bước đạt.
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("FLOWABLE_URL", "http://flowable:8080/flowable-rest/service")
USER = os.environ.get("FLOWABLE_REST_USER", "rest-admin")
PASSWORD = os.environ["FLOWABLE_REST_PASSWORD"]
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
KEY = "dxosSmoke"

BPMN = f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:flowable="http://flowable.org/bpmn"
             targetNamespace="http://dxos.local/spike">
  <process id="{KEY}" name="DX-OS smoke" isExecutable="true">
    <startEvent id="start"/>
    <sequenceFlow id="f1" sourceRef="start" targetRef="review"/>
    <userTask id="review" name="Duyet" flowable:candidateGroups="smoke-group"/>
    <sequenceFlow id="f2" sourceRef="review" targetRef="end"/>
    <endEvent id="end"/>
  </process>
</definitions>
"""


def call(method, path, body=None, headers=None, ok=(200, 201, 204)):
    hdrs = {"Authorization": AUTH, **(headers or {})}
    data = body
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - URL nội bộ cố định
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    if status not in ok:
        raise SystemExit(f"FAIL {method} {path}: HTTP {status} {raw[:300]!r}")
    return status, (json.loads(raw) if raw else None)


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    t0 = time.time()
    for _ in range(60):
        try:
            _, eng = call("GET", "/management/engine")
            break
        except (SystemExit, OSError):
            time.sleep(3)
    else:
        raise SystemExit("FAIL engine không sẵn sàng sau 180 s")
    step(f"engine {eng.get('name')} version {eng.get('version')} (chờ {time.time() - t0:.1f}s)")

    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.bpmn20.xml\"\r\n"
        f"Content-Type: text/xml\r\n\r\n{BPMN}\r\n--{boundary}--\r\n"
    ).encode()
    _, dep = call("POST", "/repository/deployments", body,
                  {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    step(f"deploy OK id={dep['id']}  [POST /repository/deployments]")

    _, pi = call("POST", "/runtime/process-instances", {
        "processDefinitionKey": KEY,
        "businessKey": "smoke-1",
        "variables": [{"name": "recordId", "value": "rec-123", "type": "string"}],
    })
    step(f"start OK instance={pi['id']}  [POST /runtime/process-instances]")

    _, tasks = call("GET", f"/runtime/tasks?candidateGroup=smoke-group&processInstanceId={pi['id']}")
    assert tasks["total"] == 1, tasks
    task = tasks["data"][0]
    step(f"list OK task={task['id']} name={task['name']}  [GET /runtime/tasks?candidateGroup=]")

    _, by_assignee = call("GET", "/runtime/tasks?assignee=nobody")
    step(f"list theo assignee OK total={by_assignee['total']}  [GET /runtime/tasks?assignee=]")

    call("POST", f"/runtime/tasks/{task['id']}", {
        "action": "complete",
        "variables": [{"name": "approved", "value": True, "type": "boolean"}],
    })
    step("complete OK  [POST /runtime/tasks/{id} action=complete]")

    st, _ = call("GET", f"/runtime/process-instances/{pi['id']}", ok=(404,))
    _, hist = call("GET", f"/history/historic-process-instances/{pi['id']}")
    assert hist["endTime"], hist
    _, hvars = call("GET", f"/history/historic-variable-instances?processInstanceId={pi['id']}")
    names = sorted(v["variable"]["name"] for v in hvars["data"])
    assert names == ["approved", "recordId"], names
    step(f"ended OK endTime={hist['endTime']} vars={names}  "
         "[GET /runtime/process-instances/{id} -> 404; /history/historic-process-instances/{id}]")

    call("DELETE", f"/repository/deployments/{dep['id']}?cascade=true")
    step(f"cleanup OK; tổng {time.time() - t0:.1f}s")
    print("SMOKE OK")


if __name__ == "__main__":
    sys.exit(main())
