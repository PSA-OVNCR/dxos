# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route vòng đời app của API quản trị (spec 9.5, 12.3; Plan 02 Task 12). Logic ở ``registry/installer.py``.

Mọi route nằm dưới ``/admin/v1`` (APISIX chỉ mở trên host admin) và cần ``dxos-admin``. Thân request đọc theo
luồng với trần cứng (413 ngay khi vượt), chỉ nhận ``application/json`` (415).
"""

from typing import Any

from fastapi import APIRouter, Depends, Request

from dxos_core.errors import ProblemError
from dxos_core.http_body import read_capped_body
from dxos_core.identity.deps import require_admin
from dxos_core.identity.jwt import Principal
from dxos_core.jsonbody import JsonBodyError, parse_json
from dxos_core.registry import installer

router = APIRouter(tags=["admin"])            # gắn dưới /admin/v1 trong admin/router.py

MAX_SUBMIT_BYTES = 1024 * 1024      # POST /apps: manifest + BPMN
MAX_SMALL_BYTES = 4096              # :approve


async def read_json(request: Request, limit: int) -> Any:
    """``read_capped_body`` (415/413/400) rồi JSON hợp lệ, mã hóa UTF-8 được, lồng không quá sâu (422
    ``invalid-request``; ``dxos_core.jsonbody``)."""
    raw = await read_capped_body(request, limit)
    try:
        return parse_json(raw)
    except JsonBodyError as exc:
        detail = "body is not valid JSON" if exc.malformed else exc.detail
        raise ProblemError(422, "invalid-request", "Request validation failed", detail) from None


@router.post("/apps", status_code=202)
async def submit_app(request: Request, p: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    body = await read_json(request, MAX_SUBMIT_BYTES)
    return await installer.submit(request.app.state.pool, body, actor=p, hmac_key=request.app.state.hmac_key)


@router.get("/apps")
async def list_apps(request: Request, _: Principal = Depends(require_admin)) -> list[dict]:  # noqa: B008
    return await installer.list_apps(request.app.state.pool, hmac_key=request.app.state.hmac_key)


@router.get("/apps/{app_id}/versions/{version}/diff")
async def app_diff(app_id: str, version: str, request: Request,
                   _: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    return await installer.version_diff(request.app.state.pool, app_id, version)


@router.post("/apps/{app_id}:approve")
async def approve_app(app_id: str, request: Request, p: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    body = await read_json(request, MAX_SMALL_BYTES)
    if not isinstance(body, dict) or set(body) != {"version"} or not isinstance(body["version"], str):
        raise ProblemError(422, "invalid-request", "Request validation failed",
                           'body must be {"version": "x.y.z"}')
    return await installer.approve(request.app.state, app_id, body["version"], approver=p)


@router.post("/apps/{app_id}:disable")
async def disable_app(app_id: str, request: Request, p: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    state = request.app.state
    return await installer.disable(state.pool, app_id, actor=p, hmac_key=state.hmac_key)
