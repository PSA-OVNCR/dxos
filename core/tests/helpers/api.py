# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: chạy app FastAPI thật (DB thật, JWKS giả) qua httpx.ASGITransport."""

from contextlib import asynccontextmanager

import asyncpg
import httpx
from dxos_core.app import create_app
from dxos_core.registry.store import save_manifest

from helpers.manifests import manifest, raw
from helpers.tokens import bearer, make_token

APPS = ("test-app", "test-flow")


@asynccontextmanager
async def running_api(settings, *, signer=None):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        if signer is not None:
            app.state.signer = signer
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.app = app
            yield client


async def activate(conn: asyncpg.Connection, names=APPS) -> None:
    for n in names:
        await save_manifest(conn, manifest(n), raw(n), "ACTIVE", "seed")


async def last_event_type(conn: asyncpg.Connection) -> str | None:
    return await conn.fetchval("SELECT type FROM ledger_entries ORDER BY idx DESC LIMIT 1")


def tok(sub: str, *roles: str) -> dict[str, str]:
    return bearer(make_token(sub, list(roles)))
