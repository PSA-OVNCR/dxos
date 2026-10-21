# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``GET /api/v1/apps/{app}/manifest``: phần manifest dành cho client Tầng 2 (Plan 03 Task 1).

Chung cho mọi app (I3): lõi chỉ đọc manifest đang ACTIVE, không biết app nào. Nội dung do
``client_view`` quyết định; ``decisions`` lấy từ BPMN đã triển khai của đúng phiên bản đó.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import app_roles
from dxos_core.policy import pdp
from dxos_core.records import service
from dxos_core.records.router import ctx_dep
from dxos_core.registry.client_view import client_view
from dxos_core.registry.store import get_active
from dxos_core.workflow.reconcile import deps_from_state, process_model

router = APIRouter(prefix="/api/v1/apps/{app}", tags=["apps"])

CACHE_CONTROL = "private, max-age=60"


@router.get("/manifest")
async def get_manifest_view(app: str, request: Request,
                            ctx: service.Ctx = Depends(ctx_dep)) -> JSONResponse:  # noqa: B008
    """Người gọi cần ít nhất một vai trò ``app:<app>:*``. Không có thì ghi ``policy.denied`` rồi trả 404
    ``not-found`` (không lộ app có tồn tại hay không đối với người ngoài); app không ACTIVE trả 404
    ``app-not-active`` như các route khác của app."""
    m = await get_active(ctx.conn, app) if service._valid_slug(app) else None
    if m is None:
        raise ProblemError(404, "app-not-active", "Application not active", f"no active app {app!r}")
    if not app_roles(ctx.principal, app):
        await pdp.deny(ctx.conn, ctx.principal, m, action="read_manifest", reason="no_app_role",
                       subject=app, hmac_key=ctx.hmac_key)
        raise ProblemError(404, "not-found", "Not Found")
    decisions = None
    if m.workflow is not None:
        model = await process_model(ctx.conn, deps_from_state(request.app.state), m)
        decisions = {task: sorted(vals) for task, vals in model.decisions_by_task.items()}
    return JSONResponse(client_view(m, decisions), headers={"Cache-Control": CACHE_CONTROL})
