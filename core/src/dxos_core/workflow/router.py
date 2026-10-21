# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route cầu nối quy trình và ``:pii-review`` (spec 12.1; Plan 02 Task 6). Logic ở ``service.py``.

Flowable chưa cấu hình (``app.state.flowable is None``) hoặc không tới được → 503 ``workflow-unavailable``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from dxos_core.records import service as records
from dxos_core.records.router import _json_body, _with_etag, ctx_dep
from dxos_core.workflow import service
from dxos_core.workflow.flowable import WorkflowUnavailable
from dxos_core.workflow.reconcile import deps_from_state, workflow_unavailable

router = APIRouter(prefix="/api/v1/apps/{app}", tags=["workflow"])


@asynccontextmanager
async def _flowable_errors() -> AsyncIterator[None]:
    try:
        yield
    except WorkflowUnavailable as exc:
        raise workflow_unavailable() from exc


@router.post("/collections/{col}/records/{rid}/workflow:start")
async def start_workflow(app: str, col: str, rid: str, request: Request,
                         if_match: str | None = Header(default=None),  # noqa: B008
                         ctx: records.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    deps = deps_from_state(request.app.state)
    async with _flowable_errors():
        return _with_etag(await service.start(ctx, deps, app, col, rid, if_match))


@router.get("/tasks")
async def inbox(app: str, request: Request, assigned: str = "me",
                ctx: records.Ctx = Depends(ctx_dep)) -> dict:  # noqa: B008
    deps = deps_from_state(request.app.state)
    async with _flowable_errors():
        return await service.inbox(ctx, deps, app, assigned)


@router.post("/tasks/{task_id}:complete")
async def complete_task(app: str, task_id: str, request: Request,
                        if_match: str | None = Header(default=None),  # noqa: B008
                        ctx: records.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    deps = deps_from_state(request.app.state)
    body = await _json_body(request)
    async with _flowable_errors():
        out = await service.complete(ctx, deps, app, task_id, body, if_match)
    return JSONResponse(out, headers={"ETag": f'"{out["record"]["version"]}"'})


@router.post("/collections/{col}/records/{rid}:pii-review")
async def pii_review(app: str, col: str, rid: str, if_match: str | None = Header(default=None),  # noqa: B008
                     ctx: records.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    return _with_etag(await service.pii_review(ctx, app, col, rid, if_match))
