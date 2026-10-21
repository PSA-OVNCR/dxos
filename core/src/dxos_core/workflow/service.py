# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cầu nối quy trình (Plan 02 Task 6; spec 12.1, 13.2; P2-D4, P2-D5, P2-D19, P2-D20, P2-D24, P2-D25).

- ``start``: ghim phiên bản app và ``process_definition_id`` lên bản ghi (P2-D19). Gọi Flowable **trong**
  transaction đang giữ ``FOR UPDATE`` trên bản ghi: trigger ``upload_record_open`` (``FOR SHARE``) nhờ vậy chờ
  tới khi bản ghi đã ``running`` rồi mới quyết định, nên không tệp nào lọt vào khoảng giữa (P2-D4). Commit lỗi
  sau khi Flowable đã tạo instance thì lần sau dùng lại instance đó (``_instance_for``).
- ``inbox``: task Flowable theo nhóm ứng viên, chỉ giữ task của bản ghi đang chạy đúng instance đó.
- ``complete``: kiểm quyền → (khóa theo bản ghi) đối soát → version → decision → guard → R-1 → ghi ý định
  và commit → Flowable → ``finalize``. Không mở transaction khi gọi Flowable hay ``deny``.
  ``comment`` chỉ được kiểm độ dài, **không lưu** ở đâu (P2-D24).
- ``pii_review``: xác nhận đã rà PII cho đúng tập hiện tại (P2-D10).
"""

import logging
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import app_roles
from dxos_core.kms.base import KmsUnavailable
from dxos_core.ledger.log import append
from dxos_core.policy import pdp
from dxos_core.records.service import (
    Ctx,
    _valid_slug,
    enforce_or_problem,
    fetch_record,
    load_target,
    parse_if_match,
    record_out,
)
from dxos_core.registry.model import CollectionSpec, Manifest
from dxos_core.registry.store import get_active, get_deployment, get_version
from dxos_core.seal.keys import (
    OrgNotConfigured,
    SealKeyExpired,
    org_configured,
    statement_for,
    within_validity,
)
from dxos_core.workflow import guards, reconcile
from dxos_core.workflow.flowable import TaskGone, WorkflowUnavailable
from dxos_core.workflow.reconcile import WorkflowDeps, process_model, record_lock

log = logging.getLogger("dxos_core.workflow")

DECISION = re.compile(r"[a-z][a-z0-9_]{0,31}")
MAX_COMMENT = 1000
KMS_PROBE = b"dxos-kms-probe"


def _not_found() -> ProblemError:
    return ProblemError(404, "not-found", "Not Found")


def _conflict(type_: str, title: str, detail: str | None = None) -> ProblemError:
    return ProblemError(409, type_, title, detail)


def _version_conflict(expected: int, current: int) -> ProblemError:
    return _conflict("version-conflict", "Version conflict",
                     f"If-Match {expected} but current version is {current}")


def _task_gone() -> ProblemError:
    return _conflict("task-gone", "Task is no longer open")


def _guard_problem(f: guards.GuardFailure, status: int | None = None) -> ProblemError:
    return ProblemError(status or f.status, "guard-failed", "Guard failed", guard=f.guard, reason=f.reason)


# ---------------------------------------------------------------- workflow:start
async def _check_startable(conn: asyncpg.Connection, row: asyncpg.Record, spec: CollectionSpec) -> None:
    if row["seal_state"] != "NONE":
        raise _conflict("record-sealed", "Record is sealed", f"seal_state={row['seal_state']}")
    if row["wf_state"] == "running":
        raise _conflict("already-running", "Workflow already running")
    pending = await conn.fetchval(
        "SELECT count(*) FROM core.uploads WHERE record_id=$1 AND status='STAGING'", row["id"])
    if pending:
        raise _conflict("attachments-pending", "Attachments are still being scanned", f"{pending} pending")
    if spec.attachments is not None:
        clean = await conn.fetchval(
            "SELECT count(*) FROM core.object_refs r JOIN core.objects o ON o.sha256 = r.sha256"
            " WHERE r.record_id=$1 AND r.role='original' AND o.status='CLEAN'", row["id"])
        if clean < spec.attachments.min:
            raise _conflict("attachments-not-clean", "Not enough clean attachments",
                            f"{clean} clean, at least {spec.attachments.min} required")


async def _instance_for(deps: WorkflowDeps, conn: asyncpg.Connection, row: asyncpg.Record,
                        definition_id: str, app_id: str) -> str:
    """Instance cho lần bắt đầu này.

    Dùng lại instance đang chạy cùng businessKey chỉ khi nó chưa từng được ghi lên bản ghi (commit lần trước
    lỗi sau khi Flowable đã tạo instance); ngược lại hủy nó và tạo instance mới.
    """
    rid = str(row["id"])
    existing = await deps.flowable.running_instance(definition_id, rid)
    if existing is not None:
        used = existing == row["wf_instance_id"] or await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM core.task_intents WHERE record_id=$1 AND wf_instance_id=$2)"
            " OR EXISTS (SELECT 1 FROM core.task_completions WHERE record_id=$1 AND wf_instance_id=$2)",
            row["id"], existing)
        if not used:
            return existing
        await deps.flowable.cancel(existing, "dxos:superseded")
    return await deps.flowable.start(definition_id, rid, {"dxos_record_id": rid, "dxos_app": app_id})


async def start(ctx: Ctx, deps: WorkflowDeps, app: str, col: str, rid: str, if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    m, spec = await load_target(ctx, app, col)                # không có bản ACTIVE → 404 app-not-active
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "update", m, col, row["owner_sub"], str(row["id"]))
    if m.workflow is None:
        raise _conflict("no-workflow", "Application has no workflow")
    await _check_startable(ctx.conn, row, spec)
    if row["version"] != expected:
        raise _version_conflict(expected, row["version"])
    dep = await get_deployment(ctx.conn, m.app.id, m.app.version)
    if dep is None:
        raise _conflict("app-not-deployed", "Application workflow is not deployed")
    await process_model(ctx.conn, deps, m)                    # BPMN đã ghim phải khớp bản đã deploy
    async with ctx.conn.transaction():
        row = await ctx.conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", row["id"])
        await _check_startable(ctx.conn, row, spec)
        if row["version"] != expected:
            raise _version_conflict(expected, row["version"])
        iid = await _instance_for(deps, ctx.conn, row, dep["process_definition_id"], m.app.id)
        new = await ctx.conn.fetchrow(
            "UPDATE core.records SET wf_instance_id=$2, wf_state='running', wf_app_version=$3,"
            " wf_definition_id=$4, version=version+1, updated_at=now() WHERE id=$1 RETURNING *",
            row["id"], iid, m.app.version, dep["process_definition_id"])
        await append(ctx.conn, type="workflow.started", subject=str(row["id"]),
                     body={"collection": col, "version": new["version"], "app_version": m.app.version},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return record_out(new, ctx.principal, spec, can_reveal=False)


# ---------------------------------------------------------------- hộp việc
async def _active_or_404(conn: asyncpg.Connection, app: str) -> Manifest:
    m = await get_active(conn, app) if _valid_slug(app) else None
    if m is None:
        raise ProblemError(404, "app-not-active", "Application not active", f"no active app {app!r}")
    return m


async def inbox(ctx: Ctx, deps: WorkflowDeps, app: str, assigned: str) -> dict:
    if assigned != "me":
        raise ProblemError(400, "bad-request", "Bad Request", "only assigned=me is supported")
    m = await _active_or_404(ctx.conn, app)
    roles = app_roles(ctx.principal, app)
    if not roles:
        await pdp.deny(ctx.conn, ctx.principal, m, action="list_tasks",
                       reason="admin_no_data_access" if ctx.principal.is_admin else "no_app_role",
                       subject=app, hmac_key=ctx.hmac_key)
        raise ProblemError(403, "forbidden", "Forbidden")
    tasks = await deps.flowable.list_tasks(sorted(f"app:{app}:{r}" for r in roles), f"{app}.")
    if not tasks:
        return {"items": []}
    rows = await ctx.conn.fetch(
        "SELECT id, collection, owner_sub, wf_instance_id FROM core.records"
        " WHERE app_id=$1 AND wf_state='running' AND wf_instance_id = ANY($2::text[])",
        app, sorted({t.process_instance_id for t in tasks}))
    # Chỉ giữ task của bản ghi người gọi được đọc theo chính sách hiện hành. Lọc thầm (decide, không enforce):
    # không ghi policy.denied cho mỗi task bị lọc.
    by_instance = {r["wf_instance_id"]: r for r in rows
                   if pdp.decide(ctx.principal, "read", m, r["collection"], r["owner_sub"]).allow}
    items = [{"task_id": t.id, "task_key": t.task_key, "name": t.name,
              "record_id": str(by_instance[t.process_instance_id]["id"]),
              "collection": by_instance[t.process_instance_id]["collection"], "created": t.created}
             for t in tasks if t.process_instance_id in by_instance]
    return {"items": items}


# ---------------------------------------------------------------- :complete
def _body_fields(body: Any) -> tuple[Any, Any]:
    if not isinstance(body, dict):
        raise ProblemError(422, "invalid-request", "Request body must be an object")
    return body.get("decision"), body.get("comment")


def _check_decision(decision: Any, comment: Any, allowed: frozenset[str]) -> str:
    """``decision`` theo mẫu và thuộc ``decisions_by_task`` (nếu khác rỗng); ``comment`` ≤ 1000 ký tự.

    Phải kiểm TRƯỚC khi gọi Flowable: decision không khớp cổng nào làm Flowable trả 500 và task vẫn mở.
    """
    if not isinstance(decision, str) or not DECISION.fullmatch(decision):
        raise ProblemError(422, "invalid-decision", "Invalid decision",
                           "decision must match [a-z][a-z0-9_]{0,31}")
    if allowed and decision not in allowed:
        raise ProblemError(422, "invalid-decision", "Invalid decision",
                           f"decision must be one of {sorted(allowed)}")
    if comment is not None and (not isinstance(comment, str) or len(comment) > MAX_COMMENT):
        raise ProblemError(422, "invalid-comment", "Invalid comment",
                           f"comment must be a string of at most {MAX_COMMENT} characters")
    return decision


async def _task_known(conn: asyncpg.Connection, app: str, task_id: str) -> bool:
    """Task không còn trên Flowable nhưng đã thuộc một bản ghi của app này (đã có ý định hoặc hoàn thành)."""
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM core.task_intents i JOIN core.records r ON r.id = i.record_id"
        " WHERE i.task_id=$1 AND r.app_id=$2)", task_id, app)


async def _r1_precheck(ctx: Ctx, deps: WorkflowDeps, m: Manifest, subject: str) -> None:
    """R-1 trước task niêm phong: KMS ký được, tuyên bố khóa còn hạn, tên tổ chức đã cấu hình (spec 25.3).

    Sai thì ``deny`` + 503 và Flowable chưa bị gọi (AT-20a).
    """
    async def refuse(reason: str, type_: str, title: str) -> ProblemError:
        await pdp.deny(ctx.conn, ctx.principal, m, action="complete", reason=reason, subject=subject,
                       hmac_key=ctx.hmac_key)
        return ProblemError(503, type_, title)

    try:
        probe = await deps.signer.sign("seal-key", KMS_PROBE)
    except KmsUnavailable as exc:
        raise await refuse("kms_unavailable", "kms-unavailable", "Key service unavailable") from exc
    statement = await statement_for(ctx.conn, probe.key_version)
    if statement is not None and not within_validity(statement, datetime.now(UTC)):
        raise await refuse("seal_key_expired", "seal-key-expired", "Seal key statement expired")
    if not org_configured(deps.settings):
        raise await refuse("org_not_configured", "org-not-configured", "Organisation name not configured")


def _inconsistent() -> ProblemError:
    return ProblemError(409, "workflow-inconsistent", "Workflow state is inconsistent",
                        "the workflow engine and the completion records disagree;"
                        " an administrator must reconcile this record")


async def _reconcile_or_problem(deps: WorkflowDeps, conn: asyncpg.Connection, rid: uuid.UUID, *,
                                raise_pending: bool = True) -> None:
    """Đối soát dưới khóa; còn ý định chưa rõ kết quả → 503 ``workflow-pending`` kèm ``Retry-After``;
    Flowable và bản ghi hoàn thành lệch nhau → 409 ``workflow-inconsistent`` (admin xử lý)."""
    try:
        res = await reconcile.reconcile_record(deps, conn, rid)
    except reconcile.WorkflowInconsistent as exc:
        raise _inconsistent() from exc
    if raise_pending and res.retry_after_s is not None:
        raise ProblemError(503, "workflow-pending", "Previous completion outcome not yet known",
                           headers={"Retry-After": str(max(1, math.ceil(res.retry_after_s)))})


async def _try_seal(ctx: Ctx, deps: WorkflowDeps, row: asyncpg.Record) -> asyncpg.Record:
    """Sau commit: thử niêm phong **một lần**. Không được thì giữ ``SEAL_PENDING``; job ở worker thử lại."""
    hooks = deps.seal_hooks
    if hooks is None:          # không tới được đây: finalize đã fail-closed
        return row
    try:
        await hooks.seal_record(ctx.conn, signer=deps.signer, hmac_key=deps.hmac_key, settings=deps.settings,
                                record_id=row["id"])
    except (KmsUnavailable, SealKeyExpired, OrgNotConfigured) as exc:
        log.warning("chưa niêm phong được bản ghi %s ngay (%s); job sẽ thử lại", row["id"],
                    type(exc).__name__)
    except Exception:  # noqa: BLE001 (đã commit SEAL_PENDING + seal_requests: job thử lại, không trả 500)
        log.exception("niêm phong ngay bản ghi %s lỗi; job sẽ thử lại", row["id"])
    return await ctx.conn.fetchrow("SELECT * FROM core.records WHERE id=$1", row["id"])


async def complete(ctx: Ctx, deps: WorkflowDeps, app: str, task_id: str, body: Any,
                   if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    decision_in, comment = _body_fields(body)
    conn, p = ctx.conn, ctx.principal
    # 1. Task còn mở?
    try:
        task = await deps.flowable.get_task(task_id)
    except ValueError as exc:                                 # id sai dạng trong URL
        raise _not_found() from exc
    if task is None:
        if _valid_slug(app) and await _task_known(conn, app, task_id):
            raise _task_gone()
        raise _not_found()
    # 2. Bản ghi qua businessKey; phải là bản ghi của app này, đang chạy đúng instance của task.
    if not task.process_definition_key.startswith(f"{app}."):
        raise _not_found()
    try:
        rid = uuid.UUID(await deps.flowable.business_key(task.process_instance_id) or "")
    except ValueError as exc:
        raise _not_found() from exc
    row = await conn.fetchrow("SELECT * FROM core.records WHERE id=$1", rid)
    if row is None or row["app_id"] != app or row["wf_state"] != "running" \
            or row["wf_instance_id"] != task.process_instance_id:
        raise _not_found()
    # 3. App không còn bản ACTIVE → đóng băng quy trình (C4).
    active = await _active_or_404(conn, app)
    # 4. Manifest theo phiên bản đã ghim (P2-D19); task lạ → 409 (fail-closed).
    m = await get_version(conn, app, row["wf_app_version"])
    if m is None or m.workflow is None or task.task_key not in m.workflow.tasks:
        raise _conflict("task-unknown", "Task is not declared by the pinned application version")
    task_spec = m.workflow.tasks[task.task_key]
    # 5. Quyền đọc bản ghi (chính sách hiện hành), rồi role của task (bản đã ghim).
    await enforce_or_problem(ctx, "read", active, row["collection"], row["owner_sub"], str(rid))
    if task_spec.role not in app_roles(p, app):
        await pdp.deny(conn, p, m, action="complete", reason="not_task_role", subject=str(rid),
                       hmac_key=ctx.hmac_key)
        raise _not_found()
    model = await process_model(conn, deps, m)
    spec = m.collections[row["collection"]]
    out_spec = active.collections.get(row["collection"], spec)

    async with record_lock(conn, rid):         # khóa trên kết nối request: không xin kết nối thứ hai
        # 6. Bước 0: đối soát ý định còn treo của bản ghi này.
        await _reconcile_or_problem(deps, conn, rid)
        task = await deps.flowable.get_task(task_id)
        row = await conn.fetchrow("SELECT * FROM core.records WHERE id=$1", rid)
        if task is None or row["wf_state"] != "running" or row["wf_instance_id"] != task.process_instance_id:
            raise _task_gone()
        # Bất biến (fix vòng 2): mọi task đã xong của instance có bản ghi hoàn thành; không thì fail-closed
        # trước khi đánh giá guard (not_same_actor sẽ đọc thiếu) và trước mọi lời gọi Flowable có ghi.
        try:
            await reconcile.check_completions(deps, conn, rid, task.process_instance_id)
        except reconcile.WorkflowInconsistent as exc:
            raise _inconsistent() from exc
        # 7–8. Version, decision, comment.
        if row["version"] != expected:
            raise _version_conflict(expected, row["version"])
        allowed = model.decisions_by_task.get(task.task_key, frozenset())
        decision = _check_decision(decision_in, comment, allowed)
        # 9. Guard, dưới FOR SHARE trên hàng bản ghi (C7); deny ngoài transaction.
        async with conn.transaction():
            locked = await conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR SHARE", rid)
            gi = await guards.load_guard_input(conn, record=locked, spec=spec, m=m, p=p,
                                               task_assignee=task.assignee)
        failure = guards.evaluate(task_spec.guards, gi)
        if failure is not None:
            await pdp.deny(conn, p, m, action="complete", reason=f"guard:{failure.guard}:{failure.reason}",
                           subject=str(rid), hmac_key=ctx.hmac_key)
            raise _guard_problem(failure)
        # 10. R-1 trước task niêm phong.
        if task.task_key in model.seal_tasks:
            await _r1_precheck(ctx, deps, m, str(rid))
        # Ý định: INSERT tự commit (không có transaction đang mở) TRƯỚC khi gọi Flowable (P2-D20).
        intent = await conn.fetchrow(
            "INSERT INTO core.task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub,"
            " actor_roles, decision) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            task.id, rid, task.process_instance_id, task.task_key, p.sub, sorted(app_roles(p, app)), decision)
        try:
            await deps.flowable.complete(task.id, {"decision": decision},
                                         local_variables={"dxos_intent_id": str(intent["id"])})
        except TaskGone as exc:
            await _reconcile_or_problem(deps, conn, rid, raise_pending=False)
            raise _task_gone() from exc
        except WorkflowUnavailable as exc:
            if not exc.sent:
                # Chắc chắn chưa tới Flowable: bỏ ý định ngay để lần gửi lại không phải chờ.
                await conn.execute("INSERT INTO core.task_intent_outcomes(intent_id, outcome)"
                                   " VALUES ($1, 'abandoned') ON CONFLICT (intent_id) DO NOTHING",
                                   intent["id"])
            # sent=True: Flowable có thể commit muộn; ý định để mở, đối soát quyết định sau.
            raise
        # Flowable đã chạy. Mọi lỗi từ đây để lại ý định treo; lần gọi sau hoặc admin đối soát giải quyết nó.
        try:
            done = await reconcile.finalize(deps, conn, intent, task_assignee=task.assignee)
        except (ProblemError, WorkflowUnavailable):
            raise
        except reconcile.WorkflowInconsistent as exc:
            raise _inconsistent() from exc
        except Exception as exc:
            log.exception("hoàn tất phía DB của ý định #%s lỗi sau khi Flowable đã chạy", intent["id"])
            raise ProblemError(500, "workflow-finalize-failed", "Task completed but not yet recorded",
                               "the completion will be reconciled") from exc
        if done.guard_failure is not None:
            raise _guard_problem(done.guard_failure, 409)
        row = done.record
        if row["seal_state"] == "SEAL_PENDING":
            row = await _try_seal(ctx, deps, row)
    seal_id = done.seal_id
    if seal_id is None and row["seal_state"] != "NONE":
        seal_id = await conn.fetchval("SELECT seal_id FROM core.seal_requests WHERE record_id=$1", rid)
    return {"record": record_out(row, p, out_spec, can_reveal=False), "seal_state": row["seal_state"],
            "seal_id": seal_id}


# ---------------------------------------------------------------- :pii-review
async def pii_review(ctx: Ctx, app: str, col: str, rid: str, if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    m, spec = await load_target(ctx, app, col)
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "read", m, col, row["owner_sub"], str(row["id"]))
    if not pdp.decide(ctx.principal, "reveal_pii", m, col, None).allow:
        await pdp.deny(ctx.conn, ctx.principal, m, action="pii_review", reason="not_pii_reviewer",
                       subject=str(row["id"]), hmac_key=ctx.hmac_key)
        raise _not_found()

    def check(r: asyncpg.Record) -> None:
        if r["seal_state"] != "NONE":
            raise _conflict("record-sealed", "Record is sealed", f"seal_state={r['seal_state']}")
        if r["version"] != expected:
            raise _version_conflict(expected, r["version"])

    check(row)
    async with ctx.conn.transaction():
        row = await ctx.conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", row["id"])
        check(row)
        gi = await guards.load_guard_input(ctx.conn, record=row, spec=spec, m=m, p=ctx.principal,
                                           task_assignee=None)
        digest = guards.review_digest(gi.data_digest, gi.clean_attachments, gi.finding_ids)
        await ctx.conn.execute(
            "INSERT INTO core.pii_reviews(record_id, review_digest, reviewed_by) VALUES ($1, $2, $3)",
            row["id"], digest, ctx.principal.sub)
        # Chỉ đổi version, không đổi data: trigger record_workflow_guard cho qua cả khi đang chạy quy trình.
        new = await ctx.conn.fetchrow(
            "UPDATE core.records SET version=version+1, updated_at=now() WHERE id=$1 RETURNING *", row["id"])
        await append(ctx.conn, type="pii.reviewed", subject=str(row["id"]), body={"review_digest": digest},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return record_out(new, ctx.principal, spec, can_reveal=False)
