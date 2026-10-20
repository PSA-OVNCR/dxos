# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Endpoint sức khỏe: ``/healthz`` (tiến trình sống) và ``/readyz`` (DB + migration sẵn sàng)."""

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dxos_core.errors import problem

router = APIRouter(tags=["health"])

_DB_ERRORS = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readyz(request: Request) -> dict[str, str] | JSONResponse:
    pool: asyncpg.Pool = request.app.state.pool
    try:
        async with pool.acquire(timeout=3) as conn:
            schema = await conn.fetchval("SELECT max(filename) FROM schema_migrations")
    except _DB_ERRORS:
        # Không trả chi tiết lỗi kết nối ra ngoài (địa chỉ, tên role).
        return problem(503, "not-ready", "Service not ready", "database unavailable")
    if schema is None:
        return problem(503, "not-ready", "Service not ready", "no migration applied")
    return {"status": "ready", "schema": schema}
