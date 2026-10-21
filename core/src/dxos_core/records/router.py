# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route Records API (spec 12.1). Logic nằm ở ``service.py``; ở đây chỉ nhận request và trả response."""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from dxos_core.errors import ProblemError
from dxos_core.identity.deps import require_principal
from dxos_core.identity.jwt import Principal
from dxos_core.records import service

router = APIRouter(prefix="/api/v1/apps/{app}/collections/{col}", tags=["records"])


async def ctx_dep(request: Request, p: Principal = Depends(require_principal)) -> AsyncIterator[service.Ctx]:  # noqa: B008
    async with request.app.state.pool.acquire() as conn:
        yield service.Ctx(conn=conn, principal=p, hmac_key=request.app.state.hmac_key,
                          timezone=request.app.state.settings.timezone)


async def _json_body(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProblemError(400, "bad-request", "Bad Request", "body must be JSON") from exc


def _with_etag(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"ETag": f'"{body["version"]}"'})


@router.get("/records")
async def list_records(app: str, col: str, cursor: str | None = None, limit: int = 50,
                       ctx: service.Ctx = Depends(ctx_dep)) -> dict:  # noqa: B008
    return await service.list_records(ctx, app, col, cursor, limit)


@router.post("/records", status_code=201)
async def create_record(app: str, col: str, request: Request,
                        ctx: service.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    return _with_etag(await service.create(ctx, app, col, await _json_body(request)), 201)


@router.post("/records:bulk")
async def bulk_create(app: str, col: str, request: Request, ctx: service.Ctx = Depends(ctx_dep)) -> dict:  # noqa: B008
    return await service.bulk_create(ctx, app, col, await _json_body(request))


@router.get("/records/{rid}")
async def get_record(app: str, col: str, rid: str, ctx: service.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    return _with_etag(await service.get(ctx, app, col, rid))


@router.patch("/records/{rid}")
async def patch_record(app: str, col: str, rid: str, request: Request,
                       if_match: str | None = Header(default=None),  # noqa: B008
                       ctx: service.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    return _with_etag(await service.patch(ctx, app, col, rid, await _json_body(request), if_match))
