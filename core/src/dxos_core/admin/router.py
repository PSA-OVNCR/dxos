# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route quản trị ledger: neo thủ công và trạng thái (spec 12.3; Plan 01 Task 16).

``/admin/v1/health`` chưa có (Plan 02 Task 12): trạng thái niêm phong (``seal_pending``, ``seal_key``,
``org``; Plan 02 Task 7) tạm nằm ở ``GET /admin/v1/ledger/status``.

Admin không có API nào sửa hay xóa ledger (F7).
"""

import dataclasses
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from dxos_core.errors import ProblemError
from dxos_core.identity.deps import require_admin
from dxos_core.identity.jwt import Principal
from dxos_core.jobs.queue import enqueue
from dxos_core.kms.base import KmsUnavailable
from dxos_core.ledger.anchor_job import ANCHOR_JOB
from dxos_core.ledger.log import verify_log
from dxos_core.ledger.sth import latest_sth, make_sth
from dxos_core.seal.keys import latest_statement, org_configured, statement_for, within_validity
from dxos_core.workflow.flowable import WorkflowUnavailable
from dxos_core.workflow.reconcile import deps_from_state, reconcile_all, workflow_unavailable

router = APIRouter(prefix="/admin/v1", tags=["admin"])


@router.post("/anchor:run")
async def anchor_run(request: Request, _: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    """Lập STH ngay (ký qua OpenBao) và xếp việc đẩy STH đó lên repo neo (worker có mạng ra ngoài)."""
    async with request.app.state.pool.acquire() as conn:
        try:
            th = await make_sth(conn, request.app.state.signer)
        except KmsUnavailable as exc:
            raise ProblemError(503, "kms-unavailable", "Key service unavailable",
                               "OpenBao sealed or unreachable") from exc
        job_id = await enqueue(conn, ANCHOR_JOB, {"tree_size": th.tree_size})
    return {**dataclasses.asdict(th), "anchor_job_id": job_id}


@router.get("/ledger/status")
async def ledger_status(request: Request, _: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    async with request.app.state.pool.acquire() as conn:
        size = await conn.fetchval("SELECT count(*) FROM ledger_entries")
        th = await latest_sth(conn)
        anchor = await conn.fetchrow(
            "SELECT tree_size, repo, commit_sha, anchored_at FROM anchors ORDER BY tree_size DESC LIMIT 1")
        pending = await conn.fetchval(
            "SELECT count(*) FROM jobs WHERE kind=$1 AND state IN ('QUEUED', 'RUNNING')", ANCHOR_JOB)
        v = await verify_log(conn)
        seal_pending = await conn.fetchval("SELECT count(*) FROM records WHERE seal_state='SEAL_PENDING'")
        # seal_key theo phiên bản seal-key lớn nhất KMS biết (phiên bản lần niêm phong sau sẽ dùng): chưa có
        # tuyên bố → "none" (lần niêm phong đầu bằng nó sẽ tạo). KMS không trả lời → tuyên bố mới nhất đã có.
        try:
            versions = (await request.app.state.signer.public_keys())["seal-key"]
            statement = await statement_for(conn, max(versions)) if versions else None
        except KmsUnavailable:
            statement = await latest_statement(conn)
    if statement is None:
        seal_key = "none"
    else:
        seal_key = "ok" if within_validity(statement, datetime.now(UTC)) else "expired"
    org = "ok" if org_configured(request.app.state.settings) else "down: not configured"
    return {
        "tree_size": size,
        "latest_sth": dataclasses.asdict(th) if th else None,
        "last_anchor": None if anchor is None else {
            "tree_size": anchor["tree_size"], "repo": anchor["repo"], "commit_sha": anchor["commit_sha"],
            "anchored_at": anchor["anchored_at"].isoformat()},
        "pending_anchor_jobs": pending,
        "verify": {"ok": v.ok, "first_bad_idx": v.first_bad_idx},
        # Niêm phong (spec 25.3).
        "seal_pending": seal_pending,
        "seal_key": seal_key,
        "org": org,
    }


@router.post("/workflow:reconcile")
async def workflow_reconcile(request: Request, _: Principal = Depends(require_admin)) -> dict:  # noqa: B008
    """Đối soát mọi ý định hoàn thành task chưa có kết quả với lịch sử Flowable (P2-D20, spec 15 T6)."""
    deps = deps_from_state(request.app.state)
    try:
        counts = await reconcile_all(deps)
    except WorkflowUnavailable as exc:
        raise workflow_unavailable() from exc
    if counts["unavailable"]:
        # Đã xử lý các bản ghi khác; báo 503 để admin/CLI biết còn bản ghi chưa đối soát được.
        raise ProblemError(503, "workflow-unavailable", "Workflow engine unavailable",
                           "some records could not be reconciled", counts=counts)
    return counts
