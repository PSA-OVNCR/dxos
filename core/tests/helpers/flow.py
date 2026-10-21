# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: app ``test-flow`` chạy trên Flowable thật, với API thật (Plan 02 Task 6; Task 7 thêm niêm
phong, thu hồi, xóa PII).

``FlowHarness`` cài ``test-flow`` như installer sẽ làm (Task 12): lưu manifest + ``app_files``, deploy
``render_bpmn(check_against_manifest(...))`` lên Flowable, ghi ``app_deployments``, kích hoạt bằng
``save_manifest``. Người dùng mặc định: ``a1`` author, ``r1``/``r2`` reviewer, ``p1`` approver.

Flowable dùng chung và giữ trạng thái giữa các lần chạy: task luôn được chọn theo process instance của bản ghi
trong DB riêng của test; ``close()`` hủy mọi instance mà DB này biết.
"""

import asyncio
import copy
import functools
import hashlib
import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import asyncpg
import httpx
from dxos_core import worker
from dxos_core.jobs.context import WorkerContext
from dxos_core.ledger.log import LedgerEntry, VerifyResult, verify_log
from dxos_core.registry.bpmn import check_against_manifest, render_bpmn
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_core.workflow.flowable import FlowableClient
from dxos_core.workflow.reconcile import SealHooks
from dxos_proof.canonical import canonical_bytes, sha256_hex

from helpers.files import FILES
from helpers.local_signer import FlakySigner
from helpers.manifests import raw
from helpers.tokens import bearer, make_token

APP = "test-flow"
COL = "doc"
URL = f"/api/v1/apps/{APP}/collections/{COL}/records"
BPMN_PATH = "bpmn/test-review.bpmn"
BPMN_FILE = FILES.parent / "bpmn/test-review.bpmn"
ROLES = {"a1": ("author",), "a2": ("author",), "r1": ("reviewer",), "r2": ("reviewer",), "p1": ("approver",)}
ROLE_NAMES = ("author", "reviewer", "approver")
# Từ vựng lý do của policy.denied (Task 6 + lý do guard của Task 5), để đọc ngược lá ledger qua body_sha256.
_DENY_ACTIONS = ("complete", "pii_review", "list_tasks", "read", "update", "list", "create", "reveal_pii",
                 "revoke", "erase_pii")
_GUARD_REASONS = ("same_actor", "role_not_allowed", "field_missing", "attachments_not_clean",
                  "pii_not_reviewed", "record_sealed", "not_assignee")
_PLAIN_REASONS = ("not_task_role", "kms_unavailable", "seal_key_expired", "org_not_configured",
                  "not_pii_reviewer", "no_app_role", "admin_no_data_access", "not_in_access_list",
                  "not_revoker", "not_eraser")
# Bảng không có cột record_id: đếm qua seals.
_VIA_SEAL = frozenset({"seal_revocations", "seal_revocation_notes"})


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def headers_for(as_: str | dict) -> dict[str, str]:
    if isinstance(as_, dict):
        return as_
    return bearer(make_token(as_, [f"app:{APP}:{r}" for r in ROLES[as_]]))


class FlowHarness:
    def __init__(self, api: httpx.AsyncClient, conn: asyncpg.Connection, flowable: FlowableClient,
                 worker_ctx: WorkerContext, *, owner: asyncpg.Connection | None = None) -> None:
        self.api, self.conn, self.flowable, self.worker_ctx = api, conn, flowable, worker_ctx
        self.owner = owner                     # dxos_owner: đọc không che, bỏ qua quyền của dxos_core
        self._sent: dict[str, list[dict]] = {}  # các dict data đã gửi cho từng bản ghi
        self.db = worker_ctx.pool              # đọc từ pool: các lời gọi của harness có thể chạy đồng thời
        self._slow: list[tuple[asyncio.Event, asyncio.Event]] = []
        self.slow_uploads_past_checks = 0      # số upload chậm đã qua bước kiểm quyền, đang gửi thân
        self._guards: set[str] = set()

    # ------------------------------------------------------------ cài app
    async def install_version(self, version: str = "0.1.0", *, add_guard: dict[str, str] | None = None,
                              mutate: Callable[[dict], None] | None = None, activate: bool = True) -> None:
        """Cài một phiên bản ``test-flow`` (tùy chọn thêm guard vào task, hoặc sửa manifest thô bằng
        ``mutate``) và kích hoạt nó. Không qua installer: không kiểm luật nâng cấp (Task 12)."""
        r = raw(APP)
        r["app"]["version"] = version
        for task, guard in (add_guard or {}).items():
            r["workflow"]["tasks"][task]["guards"] = [*r["workflow"]["tasks"][task]["guards"], guard]
        if mutate is not None:
            mutate(r)
        m = validate_manifest(copy.deepcopy(r))
        for t in m.workflow.tasks.values():
            self._guards.update(t.guards)
        xml = BPMN_FILE.read_bytes()
        rendered = render_bpmn(check_against_manifest(xml, m))
        rsha = hashlib.sha256(rendered).hexdigest()
        await save_manifest(self.conn, m, r, "PENDING", "installer")
        await self.conn.execute(
            "INSERT INTO app_files(app_id, version, path, sha256, content) VALUES ($1, $2, $3, $4, $5)",
            APP, version, BPMN_PATH, hashlib.sha256(xml).hexdigest(), xml.decode("utf-8"))
        dep = await self.flowable.deploy(f"{APP}@{version}#{rsha[:16]}", "test-review.bpmn20.xml", rendered)
        definition = await self.flowable.definition_id(dep)
        await self.conn.execute(
            "INSERT INTO app_deployments(app_id, version, deployment_id, process_definition_id,"
            " rendered_sha256) VALUES ($1, $2, $3, $4, $5)", APP, version, dep, definition, rsha)
        if activate:
            await save_manifest(self.conn, m, r, "ACTIVE", "installer")

    # ------------------------------------------------------------ người dùng
    def token(self, sub: str, *roles: str) -> dict[str, str]:
        return bearer(make_token(sub, [f"app:{APP}:{r}" for r in roles]))

    def admin(self) -> dict[str, str]:
        return bearer(make_token("admin1", ["dxos-admin"]))

    # ------------------------------------------------------------ bản ghi và tệp
    async def new_record(self, author: str = "a1", data: dict | None = None) -> str:
        body = data or {"title": "Hồ sơ thử"}
        r = await self.api.post(URL, json=body, headers=headers_for(author))
        assert r.status_code == 201, r.text
        self._sent.setdefault(r.json()["id"], []).append(dict(body))
        return r.json()["id"]

    async def upload(self, rid: str, data: bytes, as_: str | dict = "a1") -> httpx.Response:
        files = {"file": ("a.pdf", data, "application/pdf")}
        return await self.api.post(f"{URL}/{rid}/attachments", files=files, headers=headers_for(as_))

    def slow_upload(self, rid: str, data: bytes,
                    as_: str | dict = "a1") -> Coroutine[Any, Any, httpx.Response]:
        """Upload đi qua bước kiểm quyền, rồi dừng giữa thân request cho tới khi ``start`` kế tiếp xong.

        Nhờ vậy upload chỉ có thể bị chặn bởi trigger ``upload_record_open`` lúc ghi ``uploads`` (P2-D4).
        Hàm thường (không ``async``): cặp sự kiện được đăng ký ngay lúc gọi, trước khi ``start`` chạy.
        """
        reading, release = asyncio.Event(), asyncio.Event()
        self._slow.append((reading, release))
        return self._slow_upload(rid, data, as_, reading, release)

    async def _slow_upload(self, rid: str, data: bytes, as_: str | dict, reading: asyncio.Event,
                           release: asyncio.Event) -> httpx.Response:
        req = httpx.Request("POST", "http://x", files={"file": ("a.pdf", data, "application/pdf")})
        body, ctype = req.read(), req.headers["content-type"]
        half = len(body) // 2

        async def stream():
            yield body[:half]
            self.slow_uploads_past_checks += 1
            reading.set()
            await release.wait()
            yield body[half:]

        headers = {**headers_for(as_), "content-type": ctype, "content-length": str(len(body))}
        return await self.api.post(f"{URL}/{rid}/attachments", content=stream(), headers=headers)

    async def scan_all(self) -> None:
        """Chạy worker (fake clamd) cho tới khi hết việc."""
        while await worker.run_once(self.worker_ctx):
            pass

    async def ready_record(self, author: str = "a1", data: dict | None = None) -> str:
        """Bản ghi có một PDF đã CLEAN, sẵn sàng bắt đầu quy trình."""
        rid = await self.new_record(author, data)
        r = await self.upload(rid, (FILES / "clean-text.pdf").read_bytes(), as_=author)
        assert r.status_code == 202, r.text
        await self.scan_all()
        return rid

    async def record_with_staging_upload(self, author: str = "a1") -> str:
        rid = await self.new_record(author)
        r = await self.upload(rid, (FILES / "clean-text.pdf").read_bytes(), as_=author)
        assert r.status_code == 202, r.text
        return rid

    async def version(self, rid: str) -> int:
        return await self.db.fetchval("SELECT version FROM records WHERE id=$1", uuid.UUID(rid))

    async def get(self, rid: str, as_: str | dict = "a1") -> dict:
        r = await self.api.get(f"{URL}/{rid}", headers=headers_for(as_))
        assert r.status_code == 200, r.text
        return r.json()

    async def patch(self, rid: str, data: dict, as_: str | dict = "a1") -> httpx.Response:
        headers = {**headers_for(as_), "If-Match": f'"{await self.version(rid)}"'}
        self._sent.setdefault(rid, []).append(dict(data))
        return await self.api.patch(f"{URL}/{rid}", json=data, headers=headers)

    # ------------------------------------------------------------ quy trình
    async def start(self, rid: str, as_: str | dict = "a1") -> httpx.Response:
        slow = self._slow.pop(0) if self._slow else None
        if slow is not None:
            await slow[0].wait()               # upload chậm đã qua bước kiểm quyền
        try:
            headers = {**headers_for(as_), "If-Match": f'"{await self.version(rid)}"'}
            return await self.api.post(f"{URL}/{rid}/workflow:start", headers=headers)
        finally:
            if slow is not None:
                slow[1].set()

    async def instance_of(self, rid: str) -> str | None:
        return await self.db.fetchval("SELECT wf_instance_id FROM records WHERE id=$1", uuid.UUID(rid))

    async def open_task(self, task_key: str, rid: str):
        iid = await self.instance_of(rid)
        if iid is None:
            return None
        tasks = await self.flowable.list_tasks([f"app:{APP}:{r}" for r in ROLE_NAMES], f"{APP}.")
        return next((t for t in tasks if t.process_instance_id == iid and t.task_key == task_key), None)

    async def task_exists(self, task_key: str, rid: str) -> bool:
        return await self.open_task(task_key, rid) is not None

    async def task_id(self, task_key: str, rid: str) -> str:
        """Id task mở của bản ghi; đã có người hoàn thành thì lấy id đó (để request vẫn đi và nhận 409)."""
        t = await self.open_task(task_key, rid)
        if t is not None:
            return t.id
        tid = await self.db.fetchval(
            "SELECT task_id FROM task_intents WHERE record_id=$1 AND task_key=$2 ORDER BY id DESC LIMIT 1",
            uuid.UUID(rid), task_key)
        assert tid is not None, f"không có task {task_key} cho bản ghi {rid}"
        return tid

    async def complete_raw(self, task_id: str, decision: str, as_: str | dict, *, version: int = 1,
                           comment: str | None = None) -> httpx.Response:
        body: dict[str, Any] = {"decision": decision}
        if comment is not None:
            body["comment"] = comment
        headers = {**headers_for(as_), "If-Match": f'"{version}"'}
        return await self.api.post(f"/api/v1/apps/{APP}/tasks/{task_id}:complete", json=body, headers=headers)

    async def complete_task(self, task_key: str, rid: str, decision: str, as_: str | dict, *, signer=None,
                            comment: str | None = None) -> httpx.Response:
        tid = await self.task_id(task_key, rid)
        version = await self.version(rid)
        old = self.api.app.state.signer
        if signer is not None:
            self.api.app.state.signer = signer
        try:
            return await self.complete_raw(tid, decision, as_, version=version, comment=comment)
        finally:
            self.api.app.state.signer = old

    async def inbox(self, as_: str | dict) -> list[dict]:
        r = await self.api.get(f"/api/v1/apps/{APP}/tasks?assigned=me", headers=headers_for(as_))
        assert r.status_code == 200, r.text
        return r.json()["items"]

    async def pii_review(self, rid: str, as_: str | dict) -> httpx.Response:
        headers = {**headers_for(as_), "If-Match": f'"{await self.version(rid)}"'}
        return await self.api.post(f"{URL}/{rid}:pii-review", headers=headers)

    async def reviewed_record(self, author: str = "a1", reviewer: str = "r1",
                              data: dict | None = None) -> str:
        """Bản ghi đã qua bước review (approve) và đã được ``p1`` xác nhận rà PII; đang chờ task approve."""
        rid = await self.ready_record(author, data)
        assert (r := await self.start(rid, as_=author)).status_code == 200, r.text
        r = await self.complete_task("review", rid, "approve", as_=reviewer)
        assert r.status_code == 200, r.text
        assert (r := await self.pii_review(rid, as_="p1")).status_code == 200, r.text
        return rid

    async def late_commit(self, task_key: str, rid: str, intent_id: int, decision: str = "approve") -> None:
        """Flowable commit muộn đúng lần gửi của ý định ``intent_id`` (như lời gọi đã quá hạn phía client)."""
        tid = await self.task_id(task_key, rid)
        await self.flowable.complete(tid, {"decision": decision},
                                     local_variables={"dxos_intent_id": str(intent_id)})

    async def intents(self, rid: str) -> list[asyncpg.Record]:
        """Ý định của bản ghi theo thứ tự id, kèm ``outcome`` (None nếu chưa có kết quả)."""
        return await self.db.fetch(
            "SELECT i.*, o.outcome FROM task_intents i LEFT JOIN task_intent_outcomes o ON o.intent_id = i.id"
            " WHERE i.record_id=$1 ORDER BY i.id", uuid.UUID(rid))

    async def add_intent(self, rid: str, task_key: str, actor: str, *, outcome: str | None = None) -> int:
        """Chèn một ý định cho task đang mở của bản ghi (giả lập lần gửi khác của cùng task)."""
        tid = await self.task_id(task_key, rid)
        iid = await self.instance_of(rid)
        intent = await self.db.fetchval(
            "INSERT INTO task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub, actor_roles,"
            " decision) VALUES ($1, $2, $3, $4, $5, $6, 'approve') RETURNING id",
            tid, uuid.UUID(rid), iid, task_key, actor, list(ROLES[actor]))
        if outcome is not None:
            await self.db.execute("INSERT INTO task_intent_outcomes(intent_id, outcome) VALUES ($1, $2)",
                                  intent, outcome)
        return intent

    async def instance_running(self, iid: str) -> bool:
        return not (await self.flowable.outcome(iid)).ended

    async def admin_post(self, path: str, *, expect: int = 200) -> httpx.Response:
        r = await self.api.post(path, headers=self.admin())
        assert r.status_code == expect, r.text
        return r


    # ------------------------------------------------------------ niêm phong (Plan 02 Task 7)
    @property
    def settings(self):
        return self.api.app.state.settings

    async def approved_record(self, *, signer=None, kms_ok_for_probe: bool = True, seal_now=None,
                              data: dict | None = None) -> str:
        """Bản ghi đã qua cả hai task; ``p1`` vừa duyệt cuối (200), nên đã ``SEAL_PENDING`` rồi thử ký ngay.

        ``signer``: signer của API cho riêng lần ``:complete`` này (ký thăm dò R-1 và ký thật sau commit).
        ``kms_ok_for_probe``: với ``FlakySigner``, lần ký thăm dò có đạt hay không. ``seal_now``: ``now``
        truyền vào ``seal_record`` của lần ký ngay (thời điểm niêm phong giả lập).
        """
        rid = await self.reviewed_record(data=data)
        if isinstance(signer, FlakySigner):
            signer.probe_ok = kms_ok_for_probe
        state = self.api.app.state
        hooks = state.seal_hooks
        if seal_now is not None:
            state.seal_hooks = SealHooks(request_seal=hooks.request_seal,
                                         seal_record=functools.partial(hooks.seal_record, now=seal_now))
        try:
            r = await self.complete_task("approve", rid, "approve", as_="p1", signer=signer)
        finally:
            state.seal_hooks = hooks
        assert r.status_code == 200, r.text
        return rid

    async def sealed_record(self, data: dict | None = None) -> str:
        """Bản ghi đã ``SEALED`` (ký ngay sau lần duyệt cuối, bằng signer của API)."""
        rid = await self.approved_record(data=data)
        assert await self.seal_state_db(rid) == "SEALED"
        return rid

    async def pending_record(self) -> str:
        """Bản ghi ``SEAL_PENDING`` có job niêm phong đang chờ: lần ký ngay lỗi KMS (cùng khóa với signer của
        API)."""
        flaky = FlakySigner(self.api.app.state.signer)
        flaky.fail = True
        rid = await self.approved_record(signer=flaky)
        assert await self.seal_state_db(rid) == "SEAL_PENDING"
        return rid

    async def approved_record_before_seal(self) -> str:
        """Bản ghi vừa kết thúc lần duyệt cuối nhưng lần commit ``SEAL_PENDING`` chưa tới: dựng bằng owner từ
        một bản ghi sẵn sàng (``wf_state='ended:approved'``, ``seal_state='NONE'``), có trường ``cccd``."""
        rid = await self.ready_record(data={"title": "QĐ", "cccd": "001099012345"})
        await self.owner.execute("UPDATE records SET wf_state='ended:approved' WHERE id=$1", uuid.UUID(rid))
        return rid

    async def seal_inline(self, rid: str, *, signer=None, settings=None, now=None):
        """Gọi thẳng ``seal_record`` (như lần thử ngay của API); mặc định signer và Settings của API."""
        from dxos_core.seal.service import seal_record

        state = self.api.app.state
        async with self.db.acquire() as c:
            return await seal_record(c, signer=signer or state.signer, hmac_key=state.hmac_key,
                                     settings=settings or state.settings, record_id=uuid.UUID(rid), now=now)

    async def run_worker_once(self) -> bool:
        return await worker.run_once(self.worker_ctx)

    async def run_worker_until_idle(self, signer=None, *, settings=None) -> None:
        """Chạy worker tới khi hết việc tới hạn; ``signer``/``settings`` thay của worker trong lúc chạy."""
        old = self.worker_ctx.signer, self.worker_ctx.settings
        if signer is not None:
            self.worker_ctx.signer = signer
        if settings is not None:
            self.worker_ctx.settings = settings
        try:
            for _ in range(100):
                if not await worker.run_once(self.worker_ctx):
                    return
            raise AssertionError("worker không hết việc sau 100 lần")
        finally:
            self.worker_ctx.signer, self.worker_ctx.settings = old

    def settings_with(self, **update):
        """Bản sao Settings của API với ``update`` (``model_copy``: không qua validator, giữ nguyên chuỗi)."""
        return self.settings.model_copy(update=update)

    async def seal_state_db(self, rid: str) -> str:
        return await self.db.fetchval("SELECT seal_state FROM records WHERE id=$1", uuid.UUID(rid))

    async def seal_row(self, rid: str) -> dict:
        row = await self.db.fetchrow("SELECT * FROM seals WHERE record_id=$1", uuid.UUID(rid))
        assert row is not None, f"bản ghi {rid} chưa có niêm phong"
        return {**dict(row), "payload": _loads(row["payload"])}

    async def seal_request(self, rid: str) -> dict:
        row = await self.db.fetchrow("SELECT * FROM seal_requests WHERE record_id=$1", uuid.UUID(rid))
        assert row is not None
        return {**dict(row), "attachments": _loads(row["attachments"]),
                "public_fields": _loads(row["public_fields"])}

    async def seal_id_of(self, rid: str) -> str | None:
        return await self.db.fetchval("SELECT seal_id FROM seal_requests WHERE record_id=$1", uuid.UUID(rid))

    async def seal_status(self, rid: str) -> str | None:
        return await self.db.fetchval("SELECT status FROM seals WHERE record_id=$1", uuid.UUID(rid))

    async def seal_job(self, rid: str) -> asyncpg.Record:
        return await self.db.fetchrow("SELECT * FROM jobs WHERE kind='seal' AND payload->>'record_id' = $1"
                                      " ORDER BY id DESC LIMIT 1", rid)

    async def queued_jobs(self, kind: str) -> int:
        return await self.db.fetchval("SELECT count(*) FROM jobs WHERE kind=$1 AND state='QUEUED'", kind)

    async def force_extra_clean_ref(self, rid: str) -> str:
        """Thêm một tệp CLEAN + object_ref ``original`` cho bản ghi bằng owner (bỏ qua mọi kiểm của lõi)."""
        sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        await self.owner.execute("INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
                                 " VALUES ($1, 1, 'application/pdf', 'CLEAN', $2)", sha, f"late-{sha}")
        await self.owner.execute(
            "INSERT INTO object_refs(record_id, sha256, role) VALUES ($1, $2, 'original')",
            uuid.UUID(rid), sha)
        return sha

    async def disable_app(self) -> None:
        await self.conn.execute("UPDATE apps SET status='DISABLED', updated_at=now() WHERE id=$1", APP)

    async def revoke(self, rid: str, as_: str | dict, *, reason_code: str = "superseded",
                     note: str | None = None) -> httpx.Response:
        body: dict[str, Any] = {"reason_code": reason_code}
        if note is not None:
            body["note"] = note
        headers = {**headers_for(as_), "If-Match": f'"{await self.version(rid)}"'}
        return await self.api.post(f"{URL}/{rid}:revoke", json=body, headers=headers)

    async def erase_pii(self, rid: str, fields: Any, reason_code: str, as_: str | dict, *,
                        version: int | None = None) -> httpx.Response:
        """``:erase-pii`` kèm ``If-Match`` hiện tại (hoặc ``version``)."""
        v = version if version is not None else await self.version(rid)
        headers = {**headers_for(as_), "If-Match": f'"{v}"'}
        return await self.api.post(f"{URL}/{rid}:erase-pii",
                                   json={"fields": fields, "reason_code": reason_code}, headers=headers)

    async def admin_status(self) -> dict:
        """``GET /admin/v1/health`` (seal_pending, seal_key, org chuyển từ ledger/status về đây, Task 12)."""
        r = await self.api.get("/admin/v1/health", headers=self.admin())
        assert r.status_code == 200, r.text
        return r.json()

    # ------------------------------------------------------------ đối soát công khai (Plan 02 Task 8)
    async def sealed_ids(self, data: dict | None = None) -> tuple[str, str]:
        """``(seal_id, record_id)`` của một bản ghi vừa ``SEALED``."""
        rid = await self.sealed_record(data=data)
        return await self.seal_id_of(rid), rid

    async def install_verify_policy(self, version: str, **verify: bool) -> None:
        """Cài và kích hoạt phiên bản ``version`` với ``policies.verify`` sửa theo ``verify``; bản ghi bắt đầu
        quy trình sau đó ghim phiên bản này."""
        def mutate(r: dict) -> None:
            r["policies"]["verify"] = {**r["policies"]["verify"], **verify}

        await self.install_version(version, mutate=mutate)

    async def pending_seal_id(self, *, verify_public: bool = True) -> str:
        """``seal_id`` của một bản ghi ``SEAL_PENDING``; ``verify_public=False``: phiên bản đã ghim có
        ``verify.public: false`` (cài 0.2.0 trước)."""
        if not verify_public:
            await self.install_verify_policy("0.2.0", public=False)
        return await self.seal_id_of(await self.pending_record())

    async def sealed_with_file(self) -> tuple[str, bytes]:
        """``(seal_id, bytes tệp gốc)`` của bản ghi đã niêm phong kèm đúng một tệp (``clean-text.pdf``)."""
        sid, _ = await self.sealed_ids()
        original = (FILES / "clean-text.pdf").read_bytes()
        assert await self.attachment_hashes(sid) == [hashlib.sha256(original).hexdigest()]
        return sid, original

    async def revoked_seal_id(self) -> str:
        """``seal_id`` của một niêm phong đã bị ``p1`` thu hồi."""
        sid, rid = await self.sealed_ids()
        r = await self.revoke(rid, as_="p1")
        assert r.status_code == 200, r.text
        return sid

    async def attachment_hashes(self, sid: str) -> list[str]:
        """Hash tệp trong payload đã ký của niêm phong ``sid``."""
        payload = await self.db.fetchval("SELECT payload FROM seals WHERE seal_id=$1", sid)
        return _loads(payload)["attachments"]

    async def record_data_of(self, sid: str) -> dict:
        """``data`` đang lưu (owner, không che) của bản ghi thuộc niêm phong ``sid``."""
        rid = await self.db.fetchval("SELECT record_id FROM seal_requests WHERE seal_id=$1", sid)
        return await self.raw_data(str(rid))

    async def owner_bypass(self, sql: str, *args: Any) -> None:
        """Chạy ``sql`` bằng owner (superuser) với trigger tắt (``session_replication_role = replica``): giả
        lập kẻ có quyền SQL sửa bảng chỉ-thêm."""
        async with self.owner.transaction():
            await self.owner.execute("SET LOCAL session_replication_role = replica")
            await self.owner.execute(sql, *args)

    # ------------------------------------------------------------ đọc thô (owner)
    async def salt_of(self, rid: str) -> str | None:
        return await self.owner.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", uuid.UUID(rid))

    async def raw_data(self, rid: str) -> dict:
        return _loads(await self.owner.fetchval("SELECT data FROM records WHERE id=$1", uuid.UUID(rid)))

    async def data_versions_sent(self, rid: str) -> list[dict]:
        """Các dict ``data`` fixture đã gửi cho bản ghi, cộng ``data`` đang lưu (có trường do lõi cấp)."""
        out = [*self._sent.get(rid, []), await self.raw_data(rid)]
        return [d for i, d in enumerate(out) if d not in out[:i]]

    async def dump_core_tables(self) -> str:
        """``row_to_json(t)::text`` của mọi hàng trong mọi bảng schema ``core`` (cả bảng chỉ-thêm), nối
        lại."""
        names = [r["table_name"] for r in await self.owner.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='core'"
            " AND table_type='BASE TABLE' ORDER BY table_name")]
        parts = []
        for t in names:
            rows = await self.owner.fetch(f'SELECT row_to_json(t)::text AS j FROM core."{t}" t')  # noqa: S608
            parts += [r["j"] for r in rows]
        return "\n".join(parts)

    async def ledger_has_body_sha256(self, h: str) -> bool:
        return await self.db.fetchval("SELECT EXISTS (SELECT 1 FROM ledger_entries WHERE body_sha256=$1)", h)

    async def ledger_entries(self, type_: str) -> list[LedgerEntry]:
        rows = await self.db.fetch("SELECT * FROM ledger_entries WHERE type=$1 ORDER BY idx", type_)
        return [self._entry(r) for r in rows]

    async def ledger_entry(self, idx: int) -> LedgerEntry:
        return self._entry(await self.db.fetchrow("SELECT * FROM ledger_entries WHERE idx=$1", idx))

    @staticmethod
    def _entry(r: asyncpg.Record) -> LedgerEntry:
        return LedgerEntry(idx=r["idx"], ts=r["ts"], type=r["type"], app_id=r["app_id"], subject=r["subject"],
                           actor_ref=r["actor_ref"], body_sha256=r["body_sha256"],
                           leaf_hash=bytes(r["leaf_hash"]))

    async def ledger_verify(self) -> VerifyResult:
        async with self.db.acquire() as c:
            return await verify_log(c)

    async def key_statements(self) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM key_statements ORDER BY key, version")
        return [{**dict(r), "statement": _loads(r["statement"])} for r in rows]

    async def first_seal_payload(self) -> dict:
        return _loads(await self.db.fetchval("SELECT payload FROM seals ORDER BY leaf_index LIMIT 1"))

    # ------------------------------------------------------------ đọc DB / ledger
    async def count(self, table: str, rid: str | None = None) -> int:
        """Số hàng của ``table`` thuộc bản ghi ``rid`` (bảng không có record_id thì đếm qua seals); không có
        ``rid`` thì đếm cả bảng."""
        assert table.isidentifier()
        if rid is None:
            return await self.db.fetchval(f"SELECT count(*) FROM {table}")  # noqa: S608
        if table in _VIA_SEAL:
            return await self.db.fetchval(
                f"SELECT count(*) FROM {table} x JOIN seals s ON s.seal_id = x.seal_id"  # noqa: S608
                " WHERE s.record_id=$1", uuid.UUID(rid))
        return await self.db.fetchval(f"SELECT count(*) FROM {table} WHERE record_id=$1",  # noqa: S608
                                        uuid.UUID(rid))

    async def count_ledger(self, type_: str, *, subject: str) -> int:
        return await self.db.fetchval("SELECT count(*) FROM ledger_entries WHERE type=$1 AND subject=$2",
                                        type_, subject)

    async def completion_actor(self, rid: str, task_key: str) -> str | None:
        return await self.db.fetchval(
            "SELECT actor_sub FROM task_completions WHERE record_id=$1 AND task_key=$2",
            uuid.UUID(rid), task_key)

    async def last_denied_reason(self) -> str | None:
        """``reason`` của lá ``policy.denied`` mới nhất, tìm ngược qua ``body_sha256``."""
        digest = await self.db.fetchval(
            "SELECT body_sha256 FROM ledger_entries WHERE type='policy.denied' ORDER BY idx DESC LIMIT 1")
        if digest is None:
            return None
        reasons = [*_PLAIN_REASONS, *(f"guard:{g}:{r}" for g in self._guards for r in _GUARD_REASONS)]
        for action in _DENY_ACTIONS:
            for reason in reasons:
                if sha256_hex(canonical_bytes({"action": action, "reason": reason})) == digest:
                    return reason
        return "<không nhận ra>"

    async def close(self) -> None:
        """Hủy mọi instance Flowable mà DB của test này biết (Flowable dùng chung)."""
        iids = {r["wf_instance_id"] for r in await self.conn.fetch(
            "SELECT wf_instance_id FROM records WHERE wf_instance_id IS NOT NULL")}
        iids |= {r["wf_instance_id"] for r in await self.conn.fetch(
            "SELECT wf_instance_id FROM task_intents")}
        await asyncio.gather(*(self.flowable.cancel(i, "dxos:test-teardown") for i in iids),
                             return_exceptions=True)
