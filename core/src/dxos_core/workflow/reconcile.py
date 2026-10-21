# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ý định hoàn thành task và đối soát với Flowable (P2-D20; Plan 02 Task 6).

Luồng ``:complete`` ghi ``task_intents`` và commit **trước** khi gọi Flowable. Sau khi Flowable chạy,
``finalize`` hoàn tất phía DB trong một transaction. Nếu DB lỗi sau Flowable, ý định còn treo (chưa có dòng
``task_intent_outcomes``) và ``reconcile_record`` giải quyết nó ở lần gọi sau hoặc khi admin đối soát:

- task đã xong trên Flowable **và** biến lịch sử ``dxos_intent_id`` (task-local, C18) bằng id ý định
  → ``finalize`` với đúng ``actor_sub``/``actor_roles``/``decision`` của ý định;
- task đã xong nhưng ``dxos_intent_id`` khác → ``abandoned`` (không thể xảy ra khi có khóa; ghi log ERROR);
- task chưa xong → ``abandoned``: lần trước chưa tới được Flowable, người dùng gửi lại được ngay.

Mọi thao tác trên các ý định của một bản ghi chạy dưới khóa advisory phiên ``record_lock`` (``LOCK_WF``),
trên một kết nối riêng và luôn nhả trong ``finally``. Không gọi Flowable khi đang mở transaction.

Mô-đun này cũng giữ phần dùng chung của bridge (``WorkflowDeps``, ``SealHooks``, ``process_model``) để
``service.py`` import một chiều, không vòng.
"""

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import Principal
from dxos_core.kms.base import Signer
from dxos_core.ledger.log import append
from dxos_core.policy import pdp
from dxos_core.registry.bpmn import ProcessModel, check_against_manifest, render_bpmn
from dxos_core.registry.model import Manifest
from dxos_core.registry.store import get_deployment, get_version
from dxos_core.settings import Settings
from dxos_core.workflow import guards
from dxos_core.workflow.flowable import FlowableClient, WorkflowUnavailable

log = logging.getLogger("dxos_core.workflow")

# Khóa advisory hai số nguyên: (LOCK_WF, hashtext(record_id)). Khác 724000 (migrate), 724001 (ledger),
# 724101 (LOCK_KEYSTMT, Task 7).
LOCK_WF = 724100


@dataclass(frozen=True)
class SealHooks:
    """Hai hàm niêm phong do Task 7 cung cấp (ở ``app.state.seal_hooks``), truyền vào để tránh vòng import.

    - ``request_seal(conn, *, record, m) -> seal_id``: chạy **trong** transaction hoàn tất task cuối, chụp nội
      dung lúc đó vào ``seal_requests`` (P2-D18) và xếp job niêm phong.
    - ``seal_record(conn, *, signer, hmac_key, settings, record_id) -> SealOutcome``: thử ký ngay sau commit.
    """

    request_seal: Callable[..., Awaitable[str]]
    seal_record: Callable[..., Awaitable[Any]]


class SealHooksMissing(RuntimeError):
    """Quy trình tới end event niêm phong nhưng chưa có ``SealHooks``: fail-closed, rollback (không bao giờ
    đặt ``SEAL_PENDING`` mà không có hàng ``seal_requests``)."""


@dataclass
class WorkflowDeps:
    pool: asyncpg.Pool
    flowable: FlowableClient
    hmac_key: bytes
    signer: Signer
    settings: Settings
    seal_hooks: SealHooks | None
    # ProcessModel theo (app_id, phiên bản): phiên bản app bất biến nên cache an toàn; không băm model.
    models: dict[tuple[str, str], ProcessModel] = field(default_factory=dict)


def deps_from_state(state: Any) -> WorkflowDeps:
    """Gom phụ thuộc từ ``app.state``; chưa cấu hình Flowable → 503 ``workflow-unavailable``."""
    flowable = getattr(state, "flowable", None)
    if flowable is None:
        raise ProblemError(503, "workflow-unavailable", "Workflow engine unavailable",
                           "Flowable is not configured")
    models = getattr(state, "process_models", None)
    if models is None:
        models = state.process_models = {}
    return WorkflowDeps(pool=state.pool, flowable=flowable, hmac_key=state.hmac_key, signer=state.signer,
                        settings=state.settings, seal_hooks=getattr(state, "seal_hooks", None), models=models)


def workflow_unavailable() -> ProblemError:
    return ProblemError(503, "workflow-unavailable", "Workflow engine unavailable")


@asynccontextmanager
async def record_lock(pool: asyncpg.Pool, record_id: uuid.UUID) -> AsyncIterator[None]:
    """Khóa advisory **phiên** theo bản ghi trên một kết nối riêng của pool; nhả trong ``finally``.

    Hai lần ``:complete`` (và đối soát) của cùng một bản ghi vì vậy xếp hàng nối tiếp nhau.
    Nhả lỗi thì hủy kết nối: khóa phiên mất theo phiên, không bao giờ treo lại trong pool.
    """
    conn = await pool.acquire()
    try:
        await conn.execute("SELECT pg_advisory_lock($1, hashtext($2))", LOCK_WF, str(record_id))
        try:
            yield
        finally:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1, hashtext($2))", LOCK_WF, str(record_id))
            except BaseException as exc:
                # Hủy kết nối thì phiên mất, khóa phiên mất theo. Việc đã commit không bị biến thành lỗi 500;
                # chỉ hủy bỏ (CancelledError...) được ném tiếp.
                log.exception("không nhả được khóa quy trình của bản ghi %s; hủy kết nối", record_id)
                conn.terminate()
                if not isinstance(exc, Exception):
                    raise
    finally:
        await pool.release(conn)


async def process_model(conn: asyncpg.Connection, deps: WorkflowDeps, m: Manifest) -> ProcessModel:
    """``ProcessModel`` của đúng phiên bản ``m`` (đã ghim), từ BPMN trong ``app_files``; cache theo khóa.

    Chỉ tin ``seal_tasks``/``decisions_by_task`` từ ``check_against_manifest`` của chính phiên bản đó, và
    chỉ khi bản dựng lại khớp ``rendered_sha256`` đã deploy: thứ Flowable chạy đúng là thứ lõi đã kiểm.
    """
    key = (m.app.id, m.app.version)
    cached = deps.models.get(key)
    if cached is not None:
        return cached
    if m.workflow is None:
        raise ProblemError(409, "no-workflow", "Application has no workflow")
    xml = await conn.fetchval("SELECT content FROM core.app_files WHERE app_id=$1 AND version=$2 AND path=$3",
                              m.app.id, m.app.version, m.workflow.bpmn)
    dep = await get_deployment(conn, m.app.id, m.app.version)
    if xml is None or dep is None:
        raise ProblemError(409, "app-not-deployed", "Application workflow is not deployed")
    model = check_against_manifest(xml.encode("utf-8"), m)
    if hashlib.sha256(render_bpmn(model)).hexdigest() != dep["rendered_sha256"]:
        log.error("BPMN của %s@%s không khớp bản đã deploy", m.app.id, m.app.version)
        raise ProblemError(500, "workflow-model-mismatch", "Deployed workflow does not match the manifest")
    deps.models[key] = model
    return model


# ---------------------------------------------------------------- hoàn tất một ý định
@dataclass(frozen=True)
class Finalized:
    record: asyncpg.Record
    outcome: str                                  # completed | guard_failed | abandoned
    seal_id: str | None = None
    guard_failure: guards.GuardFailure | None = None


class _GuardFailed(Exception):  # noqa: N818 (chỉ để thoát transaction)
    pass


def _intent_principal(intent: asyncpg.Record, app_id: str) -> Principal:
    """Principal dựng lại từ ý định: guard được đánh giá lại theo ``actor_roles`` lúc gửi."""
    roles = frozenset(f"app:{app_id}:{r}" for r in intent["actor_roles"])
    return Principal(intent["actor_sub"], roles, False)


async def _record_outcome(conn: asyncpg.Connection, intent_id: int, outcome: str) -> None:
    await conn.execute("INSERT INTO core.task_intent_outcomes(intent_id, outcome) VALUES ($1, $2)"
                       " ON CONFLICT (intent_id) DO NOTHING", intent_id, outcome)


async def finalize(deps: WorkflowDeps, conn: asyncpg.Connection, intent: asyncpg.Record, *,
                   task_assignee: str | None = None) -> Finalized:
    """Hoàn tất phía DB một ý định mà Flowable đã thực hiện. Người gọi giữ ``record_lock`` của bản ghi.

    Guard được **đánh giá lại** dưới ``FOR UPDATE`` theo ``actor_roles`` của ý định. Sai (P2-D20):
    rollback, ghi ``deny`` ngoài transaction, hủy instance trên Flowable, rồi trong transaction riêng
    đưa bản ghi sang ``ended:guard_failed``. Đúng: ``task_completions``, kết quả ``completed``, ledger
    ``task.completed``, ``version+1``; instance đã kết thúc thì ``ended:<end_event>`` và nếu đó là end event
    niêm phong thì ``SEAL_PENDING`` + ``request_seal`` trong chính transaction này (P2-D18).
    ``task_assignee``: assignee của task lúc gửi (luồng trực tiếp); đối soát không còn task nên truyền None.
    """
    rid: uuid.UUID = intent["record_id"]
    instance: str = intent["wf_instance_id"]
    # Đọc kết quả instance TRƯỚC khi mở transaction: không gọi Flowable khi đang giữ khóa hàng. Dưới
    # record_lock không ai khác đẩy instance này đi tiếp, nên kết quả không đổi tới lúc commit.
    flow_outcome = await deps.flowable.outcome(instance)
    failure: guards.GuardFailure | None = None
    p: Principal | None = None
    m: Manifest | None = None
    try:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", rid)
            if row["wf_state"] != "running" or row["wf_instance_id"] != instance:
                # Instance không còn là instance hiện tại của bản ghi: không thể xảy ra dưới khóa.
                log.error("ý định #%s trỏ tới instance %s không còn chạy trên bản ghi %s",
                          intent["id"], instance, rid)
                await _record_outcome(conn, intent["id"], "abandoned")
                return Finalized(row, "abandoned")
            m = await get_version(conn, row["app_id"], row["wf_app_version"])
            if m is None or m.workflow is None or intent["task_key"] not in m.workflow.tasks:
                raise RuntimeError(f"bản đã ghim của bản ghi {rid} không có task {intent['task_key']!r}")
            spec = m.collections[row["collection"]]
            p = _intent_principal(intent, row["app_id"])
            gi = await guards.load_guard_input(conn, record=row, spec=spec, m=m, p=p,
                                               task_assignee=task_assignee)
            failure = guards.evaluate(m.workflow.tasks[intent["task_key"]].guards, gi)
            if failure is not None:
                raise _GuardFailed
            seal_end = (m.policies.seal is not None and flow_outcome.ended
                        and f"process.completed:{flow_outcome.end_event}" == m.policies.seal.on_event)
            wf_state = row["wf_state"]
            if flow_outcome.ended:
                wf_state = f"ended:{flow_outcome.end_event or 'cancelled'}"
            new = await conn.fetchrow(
                "UPDATE core.records SET version=version+1, wf_state=$2, seal_state=$3, updated_at=now()"
                " WHERE id=$1 RETURNING *",
                rid, wf_state, "SEAL_PENDING" if seal_end else row["seal_state"])
            await conn.execute(
                "INSERT INTO core.task_completions(task_id, intent_id, record_id, wf_instance_id, task_key,"
                " actor_sub, decision) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                intent["task_id"], intent["id"], rid, instance, intent["task_key"], intent["actor_sub"],
                intent["decision"])
            await _record_outcome(conn, intent["id"], "completed")
            await append(conn, type="task.completed", subject=str(rid),
                         body={"task_key": intent["task_key"], "decision": intent["decision"],
                               "version": new["version"]},
                         hmac_key=deps.hmac_key, app_id=row["app_id"], actor_sub=intent["actor_sub"])
            if flow_outcome.ended:
                await append(conn, type="workflow.completed", subject=str(rid),
                             body={"outcome": flow_outcome.end_event or "cancelled"},
                             hmac_key=deps.hmac_key, app_id=row["app_id"], actor_sub=intent["actor_sub"])
            seal_id = None
            if seal_end:
                if deps.seal_hooks is None:
                    raise SealHooksMissing(f"bản ghi {rid} tới end event niêm phong nhưng chưa có seal hooks")
                seal_id = await deps.seal_hooks.request_seal(conn, record=new, m=m)
            return Finalized(new, "completed", seal_id=seal_id)
    except _GuardFailed:
        pass
    # Guard mới sai sau khi Flowable đã chạy: transaction trên đã rollback.
    if failure is None or p is None or m is None:      # chỉ tới đây qua _GuardFailed
        raise RuntimeError("finalize: trạng thái guard không nhất quán")
    await pdp.deny(conn, p, m, action="complete", reason=f"guard:{failure.guard}:{failure.reason}",
                   subject=str(rid), hmac_key=deps.hmac_key)
    try:
        await deps.flowable.cancel(instance, "dxos:guard_failed")
    except WorkflowUnavailable:
        # Instance mồ côi vô hại: bản ghi không còn trỏ tới nó; workflow:start sau sẽ hủy hoặc bỏ qua nó.
        log.error("không hủy được instance %s sau khi guard sai (bản ghi %s)", instance, rid)
    async with conn.transaction():
        row = await conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", rid)
        if row["wf_state"] == "running" and row["wf_instance_id"] == instance:
            row = await conn.fetchrow(
                "UPDATE core.records SET wf_state='ended:guard_failed', version=version+1, updated_at=now()"
                " WHERE id=$1 RETURNING *", rid)
        await _record_outcome(conn, intent["id"], "guard_failed")
        await append(conn, type="workflow.completed", subject=str(rid), body={"outcome": "guard_failed"},
                     hmac_key=deps.hmac_key, app_id=row["app_id"], actor_sub=intent["actor_sub"])
    return Finalized(row, "guard_failed", guard_failure=failure)


# ---------------------------------------------------------------- đối soát
async def reconcile_record(deps: WorkflowDeps, conn: asyncpg.Connection, record_id: uuid.UUID) -> list[str]:
    """Giải quyết mọi ý định chưa có kết quả của bản ghi; idempotent. Người gọi giữ ``record_lock``.

    Trả danh sách kết quả đã ghi (theo thứ tự ý định). ``conn`` không được đang trong transaction.
    """
    pending = await conn.fetch(
        "SELECT i.* FROM core.task_intents i WHERE i.record_id=$1 AND NOT EXISTS"
        " (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id) ORDER BY i.id", record_id)
    results: list[str] = []
    for intent in pending:
        if await deps.flowable.historic_task_done(intent["task_id"]):
            seen = await deps.flowable.historic_intent_id(intent["task_id"])
            if seen == str(intent["id"]):
                results.append((await finalize(deps, conn, intent)).outcome)
                continue
            log.error("task %s đã xong với dxos_intent_id=%r, khác ý định #%s (bản ghi %s)",
                      intent["task_id"], seen, intent["id"], record_id)
        await _record_outcome(conn, intent["id"], "abandoned")
        results.append("abandoned")
    return results


async def reconcile_all(deps: WorkflowDeps) -> dict[str, int]:
    """``POST /admin/v1/workflow:reconcile``: đối soát mọi bản ghi có ý định chưa có kết quả."""
    async with deps.pool.acquire() as conn:
        rids = [r["record_id"] for r in await conn.fetch(
            "SELECT DISTINCT i.record_id FROM core.task_intents i WHERE NOT EXISTS"
            " (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id) ORDER BY i.record_id")]
    counts = {"records": len(rids), "completed": 0, "abandoned": 0, "guard_failed": 0, "errors": 0}
    for rid in rids:
        try:
            async with record_lock(deps.pool, rid), deps.pool.acquire() as conn:
                for outcome in await reconcile_record(deps, conn, rid):
                    counts[outcome] += 1
        except Exception:  # noqa: BLE001 (một bản ghi lỗi không chặn các bản ghi khác)
            log.exception("đối soát bản ghi %s lỗi", rid)
            counts["errors"] += 1
    return counts
