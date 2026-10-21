# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Khởi tạo ứng dụng FastAPI của trust-core-api.

Chạy: ``uvicorn --factory dxos_core.app:create_app`` (cấu hình lấy từ biến ``DXOS_*``).
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dxos_core import __version__, health
from dxos_core.admin import router as admin
from dxos_core.db.pool import create_pool
from dxos_core.errors import install_error_handlers
from dxos_core.identity import deps as identity
from dxos_core.identity.jwt import JwksVerifier
from dxos_core.kms.openbao import OpenBaoTransit
from dxos_core.ledger import router as verify
from dxos_core.objects import router as objects
from dxos_core.objects.storage import ObjectStore
from dxos_core.records import router as records
from dxos_core.settings import Settings, read_secret
from dxos_core.workflow import router as workflow
from dxos_core.workflow.flowable import FlowableClient, WorkflowUnavailable, flowable_from_settings

log = logging.getLogger("dxos_core.app")


async def _flowable(settings: Settings) -> FlowableClient | None:
    """Client Flowable hoặc None (mọi route quy trình trả 503). Không làm hỏng khởi động khi Flowable lỗi.

    ``ping()`` một lần: base URL sai làm mọi đường dẫn trả 404, dễ bị đọc nhầm là "task không còn".
    """
    try:
        client = flowable_from_settings(settings)
    except WorkflowUnavailable:
        log.error("không đọc được bí mật Flowable; các route quy trình sẽ trả 503")
        return None
    if client is not None:
        try:
            await client.ping()
        except WorkflowUnavailable as exc:
            log.error("Flowable không trả lời ở %s lúc khởi động: %s", client.base_url, exc)
    return client


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.hmac_key = read_secret(settings.actor_hmac_key_file).encode("utf-8")
        app.state.pool = await create_pool(settings.database_url, min_size=0)
        app.state.store = ObjectStore(settings)
        app.state.signer = OpenBaoTransit(settings.openbao_addr, read_secret(settings.openbao_token_file))
        app.state.flowable = await _flowable(settings)
        app.state.process_models = {}
        # Task 7 đặt SealHooks(request_seal, seal_record); chưa có thì tới end event niêm phong: fail-closed.
        app.state.seal_hooks = None
        try:
            yield
        finally:
            await app.state.pool.close()

    app = FastAPI(title="DX-OS Trust Core", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.verifier = JwksVerifier(
        settings.keycloak_jwks_url, settings.keycloak_issuer, settings.jwt_audience)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(identity.router)
    app.include_router(records.router)
    app.include_router(objects.router)
    app.include_router(workflow.router)
    app.include_router(verify.router)
    app.include_router(admin.router)
    return app
