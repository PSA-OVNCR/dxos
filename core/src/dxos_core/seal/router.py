# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route thu hồi và thông tin niêm phong của một bản ghi (spec 12.1; Plan 02 Task 7).

Logic ở ``service.py``.
"""

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from dxos_core.records import service as records
from dxos_core.records.router import _json_body, _with_etag, ctx_dep
from dxos_core.seal import service

router = APIRouter(prefix="/api/v1/apps/{app}/collections/{col}", tags=["seal"])


@router.post("/records/{rid}:revoke")
async def revoke(app: str, col: str, rid: str, request: Request,
                 if_match: str | None = Header(default=None),  # noqa: B008
                 ctx: records.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    return _with_etag(await service.revoke(ctx, app, col, rid, await _json_body(request), if_match))


@router.get("/records/{rid}/seal")
async def seal_info(app: str, col: str, rid: str, request: Request,
                    ctx: records.Ctx = Depends(ctx_dep)) -> dict:  # noqa: B008
    return await service.seal_info(ctx, app, col, rid, request.app.state.settings.public_base_url)
