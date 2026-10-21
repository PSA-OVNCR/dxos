# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route vận hành của API quản trị: ``/admin/v1/health`` và ``/admin/v1/quarantine`` (spec 12.3; Plan 02
Task 12).

``health`` luôn trả HTTP 200 (để CLI đọc được); mỗi thành phần là ``"ok"`` hoặc ``"down: <lý do ngắn>"``,
mỗi lần thăm dò có hạn chờ ngắn. Trạng thái niêm phong (``seal_pending``, ``seal_key``, ``org``; Task 7)
chuyển từ ``/admin/v1/ledger/status`` về đây. ``seal_key``: ``ok``, ``none``, ``expired``, ``invalid``,
``unknown`` (xem ``seal_key_status``) hoặc ``down: db unavailable``.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from dxos_core.identity.deps import require_admin
from dxos_core.identity.jwt import Principal
from dxos_core.kms.base import KmsUnavailable
from dxos_core.objects.clamd import ScannerUnavailable, clamd_version
from dxos_core.registry.keycloak_admin import IdpAdminUnavailable
from dxos_core.seal.keys import KeyStatementInvalid, checked_statement_for, org_configured, within_validity
from dxos_core.workflow.flowable import WorkflowUnavailable
from dxos_core.workflow.service import KMS_PROBE

log = logging.getLogger("dxos_core.admin.ops")

router = APIRouter(tags=["admin"])            # gắn dưới /admin/v1 trong admin/router.py

CHECK_TIMEOUT_S = 3.0
# Ý định hoàn thành task chưa có kết quả quá lâu (P2-D20): cần chạy workflow:reconcile.
STUCK_INTENT_AFTER = timedelta(minutes=2)
_DB_ERRORS = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)


class _Down(Exception):  # noqa: N818
    """Thành phần trả lời nhưng không đạt; thông điệp là lý do ngắn."""


async def _probe(check: Callable[[], Awaitable[None]], *, what: str) -> str:
    """Chạy ``check`` với hạn chờ; ``"ok"`` hoặc ``"down: <lý do ngắn>"`` (không lộ địa chỉ hay bí mật)."""
    try:
        await asyncio.wait_for(check(), CHECK_TIMEOUT_S)
    except TimeoutError:
        return "down: timeout"
    except _Down as exc:
        return f"down: {exc}"
    except (KmsUnavailable, ScannerUnavailable, WorkflowUnavailable, IdpAdminUnavailable, OSError) as exc:
        log.warning("health %s: %s", what, exc)
        return "down: unavailable"
    except Exception:
        log.exception("health %s: lỗi không lường trước", what)
        return "down: error"
    return "ok"


# ---------------------------------------------------------------- từng thành phần
async def seal_key_status(conn: asyncpg.Connection, signer: Any) -> str:
    """``seal_key`` theo phiên bản seal-key lớn nhất KMS biết (phiên bản lần niêm phong sau sẽ dùng):

    - ``"ok"`` / ``"expired"``: tuyên bố đã kiểm của phiên bản đó, theo thời hạn;
    - ``"none"``: chưa có tuyên bố (lần niêm phong đầu bằng nó sẽ tạo);
    - ``"invalid"``: có hàng tuyên bố nhưng không qua kiểm hash/phiên bản (bị sửa; niêm phong bị chặn);
    - ``"unknown"``: KMS không trả lời nên không biết phiên bản nào sẽ dùng (không báo "ok" cũ).
    """
    try:
        versions = (await asyncio.wait_for(signer.public_keys(), CHECK_TIMEOUT_S))["seal-key"]
    except (KmsUnavailable, TimeoutError):
        return "unknown"
    try:
        statement = await checked_statement_for(conn, max(versions)) if versions else None
    except KeyStatementInvalid:
        return "invalid"
    if statement is None:
        return "none"
    return "ok" if within_validity(statement, datetime.now(UTC)) else "expired"


async def _clamav(settings) -> None:
    reply = await clamd_version(settings.clamd_host, settings.clamd_port, timeout_s=CHECK_TIMEOUT_S)
    if not reply.startswith("ClamAV"):
        raise _Down("unexpected VERSION reply")


async def _openbao(signer) -> None:
    health = getattr(signer, "health", None)        # OpenBaoTransit: sys/health; signer test không có
    if health is not None:
        await health()
    await signer.sign("seal-key", KMS_PROBE)        # một lần ký thăm dò, như R-1


async def _flowable(client) -> None:
    if client is None:
        raise _Down("not configured")
    await client.ping()


async def _default_roles(state) -> None:
    """P2-D12: ``default-roles-dxos`` không được gộp ``dxos-admin`` hay role ``app:*``."""
    kc = state.kc_admin.get(state.settings)
    if kc is None:
        raise _Down("not configured")
    bad = [r for r in await kc.default_role_composites() if r == "dxos-admin" or r.startswith("app:")]
    if bad:
        more = f" (+{len(bad) - 3})" if len(bad) > 3 else ""
        raise _Down(f"default-roles-dxos includes {', '.join(bad[:3])}{more}")


async def _db_section(pool: asyncpg.Pool, signer: Any) -> dict[str, Any]:
    async with pool.acquire(timeout=CHECK_TIMEOUT_S) as conn:
        await conn.fetchval("SELECT 1")
        anchor = await conn.fetchrow(
            "SELECT tree_size, extract(epoch FROM now() - anchored_at)::bigint AS age FROM core.anchors"
            " ORDER BY tree_size DESC LIMIT 1")
        seal_pending = await conn.fetchval(
            "SELECT count(*) FROM core.records WHERE seal_state='SEAL_PENDING'")
        stuck = await conn.fetchval(
            "SELECT count(*) FROM core.task_intents i WHERE i.created_at < now() - $1::interval"
            " AND NOT EXISTS (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id)",
            STUCK_INTENT_AFTER)
        seal_key = await seal_key_status(conn, signer)
    return {
        "db": "ok",
        "anchor": {"last_tree_size": None if anchor is None else anchor["tree_size"],
                   "last_anchor_age_s": None if anchor is None else max(0, anchor["age"])},
        "seal_pending": seal_pending,
        "task_intents_stuck": stuck,
        "seal_key": seal_key,
    }


@router.get("/health")
async def health(request: Request, _: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    state = request.app.state
    settings = state.settings

    async def db() -> dict[str, Any]:
        try:
            return await asyncio.wait_for(_db_section(state.pool, state.signer), CHECK_TIMEOUT_S * 3)
        except (*_DB_ERRORS, TimeoutError) as exc:
            log.warning("health db: %s", type(exc).__name__)
            return {"db": "down: unavailable", "anchor": {"last_tree_size": None, "last_anchor_age_s": None},
                    "seal_pending": None, "task_intents_stuck": None, "seal_key": "down: db unavailable"}

    section, clamav, openbao, flowable, roles = await asyncio.gather(
        db(),
        _probe(lambda: _clamav(settings), what="clamav"),
        _probe(lambda: _openbao(state.signer), what="openbao"),
        _probe(lambda: _flowable(state.flowable), what="flowable"),
        _probe(lambda: _default_roles(state), what="keycloak"),
    )
    return {
        "db": section["db"],
        "clamav": clamav,
        "openbao": openbao,
        "flowable": flowable,
        "keycloak_default_roles": roles,
        "anchor": section["anchor"],
        "seal_pending": section["seal_pending"],
        "task_intents_stuck": section["task_intents_stuck"],
        "seal_key": section["seal_key"],
        "org": "ok" if org_configured(settings) else "down: not configured",
    }


@router.get("/quarantine")
async def quarantine(request: Request, limit: int = Query(100, ge=1, le=1000),
                     _: Principal = Depends(require_admin)) -> list[dict]:  # noqa: B008
    """Upload ``INFECTED``/``REJECTED`` mới nhất trước. Không có tên tệp (chỉ lưu dạng hash) và không trả cả
    hash của tên; ``app_id`` lấy từ bản ghi của upload."""
    async with request.app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT u.id, u.sha256, u.status, u.reason, r.app_id, u.created_at FROM core.uploads u"
            " JOIN core.records r ON r.id = u.record_id WHERE u.status IN ('INFECTED', 'REJECTED')"
            " ORDER BY u.created_at DESC, u.id LIMIT $1", limit)
    return [{"upload_id": str(r["id"]), "sha256": r["sha256"], "status": r["status"], "reason": r["reason"],
             "app_id": r["app_id"], "created_at": r["created_at"].isoformat()} for r in rows]
