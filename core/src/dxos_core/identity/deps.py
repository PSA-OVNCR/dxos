# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""FastAPI dependency lấy ``Principal`` từ header ``Authorization: Bearer``.

APISIX đã kiểm token ở lớp ngoài; lõi kiểm lại (phòng thủ nhiều lớp, không tin mạng nội bộ).
"""

from fastapi import APIRouter, Depends, Request

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import AuthError, IdpUnavailable, JwksVerifier, Principal

_WWW_AUTH = {"WWW-Authenticate": 'Bearer realm="dxos"'}
_WWW_AUTH_INVALID = {"WWW-Authenticate": 'Bearer realm="dxos", error="invalid_token"'}


async def require_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ProblemError(401, "unauthenticated", "Unauthenticated", "missing bearer token",
                           headers=_WWW_AUTH)
    verifier: JwksVerifier = request.app.state.verifier
    try:
        return await verifier.verify(token.strip())
    except IdpUnavailable as exc:
        raise ProblemError(503, "idp-unavailable", "Identity provider unavailable") from exc
    except AuthError as exc:
        raise ProblemError(401, "unauthenticated", "Unauthenticated", "invalid token",
                           headers=_WWW_AUTH_INVALID) from exc


async def require_admin(p: Principal = Depends(require_principal)) -> Principal:  # noqa: B008
    """Chỉ ``dxos-admin`` (API quản trị /admin/v1, spec 12.3)."""
    if not p.is_admin:
        raise ProblemError(403, "forbidden", "Forbidden", "dxos-admin role required")
    return p


router = APIRouter(tags=["identity"])


@router.get("/api/v1/whoami")
async def whoami(p: Principal = Depends(require_principal)) -> dict:  # noqa: B008
    return {"sub": p.sub, "roles": sorted(p.roles), "is_admin": p.is_admin}
