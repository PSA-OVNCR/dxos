# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ý định hoàn thành task và đối soát với Flowable (P2-D20; Plan 02 Task 6).

Luồng ``:complete`` ghi ``task_intents`` và commit **trước** khi gọi Flowable. Sau khi Flowable chạy,
``finalize`` hoàn tất phía DB trong một transaction. Nếu DB lỗi sau Flowable, ý định còn treo (chưa có dòng
``task_intent_outcomes``) và ``reconcile_record`` giải quyết nó ở lần gọi sau hoặc khi admin đối soát:

- task đã xong trên Flowable **và** biến lịch sử ``dxos_intent_id`` (task-local, C18) bằng id ý định
  → ``finalize`` với đúng ``actor_sub``/``actor_roles``/``decision`` của ý định;
- task đã xong với ``dxos_intent_id`` của **một ý định khác của cùng bản ghi và cùng task**: đó là lần gửi
  Flowable thật sự áp dụng. Chưa có kết quả → ``finalize`` ý định đó; đã ``abandoned`` → không bao giờ bỏ qua
  im lặng: ``WorkflowInconsistent`` (409, admin thấy bản ghi), ý định hiện tại để mở;
- task đã xong với id lạ (hoặc không có, ví dụ instance bị hủy) → ``abandoned``;
- task chưa xong → ``abandoned`` chỉ khi ý định đã quá ``late_commit_margin_s`` (3 × thời hạn client
  Flowable). Trước đó kết quả còn chưa rõ: Flowable có thể commit muộn sau khi client đã bỏ cuộc, nên ý định
  để mở (``pending``) và ``:complete`` trả 503 ``workflow-pending``. Lời gọi chắc chắn chưa tới Flowable
  (``WorkflowUnavailable.sent is False``) thì ``:complete`` bỏ ý định ngay, không phải chờ.

Mọi thao tác trên các ý định của một bản ghi chạy dưới khóa advisory phiên ``record_lock`` (``LOCK_WF``),
trên một kết nối riêng và luôn nhả trong ``finally``. Không gọi Flowable khi đang mở transaction.
Thứ tự lấy tài nguyên toàn cục (chống cạn pool rồi chờ vòng): **kết nối làm việc trước, rồi tới
``record_lock``** (kết nối của khóa) — ``:complete`` (kết nối của request) và ``reconcile_all`` đều theo.

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
# Ý định chưa rõ kết quả chỉ được bỏ sau LATE_COMMIT_FACTOR × thời hạn client Flowable (mặc định 30 s).
LATE_COMMIT_FACTOR = 3


def late_commit_margin_s(flowable: FlowableClient) -> float:
    return LATE_COMMIT_FACTOR * flowable.timeout_s


class WorkflowInconsistent(Exception):  # noqa: N818
    """Flowable và DB lệch nhau mà lõi không tự sửa được (admin phải xử lý): Flowable đã áp dụng một ý định đã
    ghi ``abandoned``, hoặc một task đã xong không có ``task_completions`` (xem ``check_completions``)."""

    def __init__(self, record_id: uuid.UUID, detail: str) -> None:
        super().__init__(f"bản ghi {record_id}: {detail}")
        self.record_id, self.detail = record_id, detail


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


# ---------------------------------------------------------------- bất biến hoàn thành
async def check_completions(deps: WorkflowDeps, conn: asyncpg.Connection, record_id: uuid.UUID, instance: str,
                            *, exclude: frozenset[str] = frozenset()) -> None:
    """Bất biến: mọi task Flowable báo ĐÃ XONG của ``instance`` có hàng ``task_completions`` của bản ghi, hoặc
    còn một ý định chưa có kết quả trỏ tới nó (``reconcile_record`` xử lý ý định đó, theo thứ tự id).

    Không thỏa → log ERROR + ``WorkflowInconsistent`` (fail-closed: không đánh giá guard, không gọi Flowable).
    Thiếu hàng hoàn thành nghĩa là guard ``not_same_actor:<task>`` sẽ đọc thiếu người đã làm task đó, ví dụ
    khi Flowable commit muộn hơn biên ``late_commit_margin_s`` và không ai gửi lại. Cách khôi phục hiện có
    (``reconcile_record``) phải chạy TRƯỚC hàm này; ``exclude``: task của chính ý định đang hoàn tất.
    Người gọi giữ ``record_lock``; ``conn`` không đang trong transaction.
    """
    done = await deps.flowable.historic_done_tasks(instance)
    if not done:
        return
    recorded = {r["task_id"] for r in await conn.fetch(
        "SELECT task_id FROM core.task_completions WHERE record_id=$1 AND wf_instance_id=$2",
        record_id, instance)}
    open_intents = {r["task_id"] for r in await conn.fetch(
        "SELECT i.task_id FROM core.task_intents i WHERE i.record_id=$1 AND NOT EXISTS"
        " (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id)", record_id)}
    missing = [(tid, key) for tid, key in done if tid not in recorded | open_intents | exclude]
    if missing:
        log.error("bản ghi %s: task đã xong trên Flowable nhưng không có bản ghi hoàn thành: %s",
                  record_id, missing)
        raise WorkflowInconsistent(record_id, "task đã xong trên Flowable không có bản ghi hoàn thành: "
                                   + ", ".join(f"{key} ({tid})" for tid, key in missing))


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
    # Không ghi hoàn thành chồng lên một hoàn thành bị thiếu (bất biến, fix vòng 2).
    await check_completions(deps, conn, rid, instance, exclude=frozenset({intent["task_id"]}))
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
@dataclass
class Reconciled:
    outcomes: list[str] = field(default_factory=list)   # kết quả đã ghi, theo thứ tự
    retry_after_s: float | None = None                  # còn ý định chưa rõ kết quả: chờ bấy nhiêu giây


async def _outcome_of(conn: asyncpg.Connection, intent_id: int) -> str | None:
    return await conn.fetchval("SELECT outcome FROM core.task_intent_outcomes WHERE intent_id=$1", intent_id)


async def _applied_intent(conn: asyncpg.Connection, seen: str | None,
                          intent: asyncpg.Record) -> asyncpg.Record | None:
    """Ý định có id ``seen`` nếu nó thuộc CÙNG bản ghi và CÙNG task với ``intent``; ngược lại None."""
    if seen is None or not seen.isdigit() or str(intent["id"]) == seen:
        return None
    return await conn.fetchrow("SELECT * FROM core.task_intents WHERE id=$1 AND record_id=$2 AND task_id=$3",
                               int(seen), intent["record_id"], intent["task_id"])


async def reconcile_record(deps: WorkflowDeps, conn: asyncpg.Connection, record_id: uuid.UUID) -> Reconciled:
    """Giải quyết các ý định chưa có kết quả của bản ghi; idempotent. Người gọi giữ ``record_lock``.

    ``conn`` không được đang trong transaction. Ý định chưa rõ kết quả (task chưa xong, chưa quá biên commit
    muộn) được để mở và báo qua ``retry_after_s``. ``WorkflowInconsistent`` khi Flowable đã áp dụng một ý
    định đã bị bỏ.
    """
    pending = await conn.fetch(
        "SELECT i.*, extract(epoch FROM now() - i.created_at)::float8 AS age_s FROM core.task_intents i"
        " WHERE i.record_id=$1 AND NOT EXISTS"
        " (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id) ORDER BY i.id", record_id)
    res = Reconciled()
    margin = late_commit_margin_s(deps.flowable)
    for intent in pending:
        if await _outcome_of(conn, intent["id"]) is not None:      # đã được hoàn tất ở vòng trước
            continue
        if not await deps.flowable.historic_task_done(intent["task_id"]):
            if intent["age_s"] <= margin:
                wait = margin - intent["age_s"]
                res.retry_after_s = wait if res.retry_after_s is None else max(res.retry_after_s, wait)
                continue
            await _record_outcome(conn, intent["id"], "abandoned")
            res.outcomes.append("abandoned")
            continue
        seen = await deps.flowable.historic_intent_id(intent["task_id"])
        if seen == str(intent["id"]):
            res.outcomes.append((await finalize(deps, conn, intent)).outcome)
            continue
        applied = await _applied_intent(conn, seen, intent)
        if applied is not None:
            status = await _outcome_of(conn, applied["id"])
            if status is None:
                res.outcomes.append((await finalize(deps, conn, applied)).outcome)
            elif status == "abandoned":
                log.error("Flowable đã áp dụng ý định #%s (đã bị bỏ) cho task %s của bản ghi %s",
                          applied["id"], intent["task_id"], record_id)
                raise WorkflowInconsistent(record_id, f"Flowable đã áp dụng ý định #{applied['id']} đã bị bỏ")
            # completed/guard_failed: lần gửi đó đã được xử lý; ý định này không được áp dụng
        elif seen is not None:
            log.error("task %s đã xong với dxos_intent_id=%r lạ, khác ý định #%s (bản ghi %s)",
                      intent["task_id"], seen, intent["id"], record_id)
        await _record_outcome(conn, intent["id"], "abandoned")
        res.outcomes.append("abandoned")
    return res


async def reconcile_all(deps: WorkflowDeps) -> dict[str, Any]:
    """``POST /admin/v1/workflow:reconcile``: đối soát mọi bản ghi có ý định chưa có kết quả.

    ``unavailable`` > 0 khi có bản ghi không đối soát được vì Flowable lỗi (route trả 503 kèm số đếm);
    ``inconsistent`` liệt kê bản ghi cần admin xử lý tay.
    """
    async with deps.pool.acquire() as conn:
        rids = [r["record_id"] for r in await conn.fetch(
            "SELECT DISTINCT i.record_id FROM core.task_intents i WHERE NOT EXISTS"
            " (SELECT 1 FROM core.task_intent_outcomes o WHERE o.intent_id = i.id) ORDER BY i.record_id")]
        running = [r["id"] for r in await conn.fetch(
            "SELECT id FROM core.records WHERE wf_state='running' AND wf_instance_id IS NOT NULL"
            " ORDER BY id")]
    # records: bản ghi có ý định chưa có kết quả; checked: bản ghi đang chạy đã kiểm bất biến hoàn thành.
    counts: dict[str, Any] = {"records": len(rids), "checked": 0, "completed": 0, "abandoned": 0,
                              "guard_failed": 0, "pending": 0, "unavailable": 0, "errors": 0,
                              "inconsistent": []}
    for rid in [*rids, *(r for r in running if r not in set(rids))]:
        try:
            # Thứ tự toàn cục: kết nối làm việc trước, khóa bản ghi sau (như :complete).
            async with deps.pool.acquire() as conn, record_lock(deps.pool, rid):
                res = await reconcile_record(deps, conn, rid)
                row = await conn.fetchrow(
                    "SELECT wf_state, wf_instance_id FROM core.records WHERE id=$1", rid)
                if row["wf_state"] == "running" and row["wf_instance_id"] is not None:
                    counts["checked"] += 1
                    await check_completions(deps, conn, rid, row["wf_instance_id"])
            for outcome in res.outcomes:
                counts[outcome] += 1
            if res.retry_after_s is not None:
                counts["pending"] += 1
        except WorkflowInconsistent:
            counts["inconsistent"].append(str(rid))
        except WorkflowUnavailable:
            log.warning("đối soát bản ghi %s: Flowable không sẵn sàng", rid)
            counts["unavailable"] += 1
        except Exception:  # noqa: BLE001 (một bản ghi lỗi không chặn các bản ghi khác)
            log.exception("đối soát bản ghi %s lỗi", rid)
            counts["errors"] += 1
    return counts
