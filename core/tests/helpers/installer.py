# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper cho installer (Plan 02 Task 12): tệp BPMN của ``test-flow`` và các truy vấn kiểm kết quả."""

import asyncpg
import httpx
from dxos_core.workflow.flowable import FlowableClient

from helpers.flow import BPMN_FILE, BPMN_PATH
from helpers.manifests import load

# Nội dung BPMN hợp lệ của test-flow (fixtures/bpmn/test-review.bpmn) và ``files`` tương ứng của POST /apps.
GOOD_XML = BPMN_FILE.read_text(encoding="utf-8")
FLOW_FILES = {BPMN_PATH: GOOD_XML}


async def submit(client: httpx.AsyncClient, app_id: str, *, doc: dict | None = None,
                 files: dict | None = None) -> dict:
    """``POST /admin/v1/apps`` với manifest ``app_id`` (hoặc ``doc``) và ``FLOW_FILES``; phải 202, trả
    body."""
    doc = doc if doc is not None else load(app_id)
    if files is None:
        files = FLOW_FILES if doc.get("workflow") else {}
    r = await client.post("/admin/v1/apps", json={"manifest": doc, "files": files})
    assert r.status_code == 202, r.text
    return r.json()


async def status_of(conn: asyncpg.Connection, app_id: str, version: str) -> str | None:
    """``apps.status`` của một phiên bản (None nếu chưa có)."""
    return await conn.fetchval("SELECT status FROM apps WHERE id=$1 AND version=$2", app_id, version)


async def deployment_of(conn: asyncpg.Connection, app_id: str, version: str) -> asyncpg.Record | None:
    """Hàng ``app_deployments`` (deployment_id, process_definition_id, rendered_sha256) của phiên bản."""
    return await conn.fetchrow("SELECT * FROM app_deployments WHERE app_id=$1 AND version=$2",
                               app_id, version)


async def ledger_types(conn: asyncpg.Connection, app_id: str) -> set[str]:
    """Tập loại lá ledger có ``app_id`` này."""
    return {r["type"] for r in await conn.fetch("SELECT type FROM ledger_entries WHERE app_id=$1", app_id)}


async def ledger_rows(conn: asyncpg.Connection, app_id: str, type_: str) -> list[asyncpg.Record]:
    """Các lá ``type_`` của ``app_id`` theo thứ tự ``idx``."""
    return await conn.fetch("SELECT * FROM ledger_entries WHERE app_id=$1 AND type=$2 ORDER BY idx",
                            app_id, type_)


async def deployment_resource(client: FlowableClient, deployment_id: str) -> bytes:
    """Bytes của tài nguyên BPMN duy nhất trong deployment, đọc thẳng từ Flowable
    (``GET /repository/deployments/{id}/resources`` rồi ``resourcedata``)."""
    resources = (await client._send("GET", f"/repository/deployments/{deployment_id}/resources",
                                    ok=(200,))).json()
    [res] = [r for r in resources if r.get("type") == "processDefinition"]
    resp = await client._send("GET", f"/repository/deployments/{deployment_id}/resourcedata/{res['id']}",
                              ok=(200,))
    return resp.content
