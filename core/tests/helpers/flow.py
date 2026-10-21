# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: app ``test-flow`` chạy trên Flowable thật, với API thật (Plan 02 Task 6; Task 7 dùng tiếp).

``FlowHarness`` cài ``test-flow`` như installer sẽ làm (Task 12): lưu manifest + ``app_files``, deploy
``render_bpmn(check_against_manifest(...))`` lên Flowable, ghi ``app_deployments``, kích hoạt bằng
``save_manifest``. Người dùng mặc định: ``a1`` author, ``r1``/``r2`` reviewer, ``p1`` approver.

Flowable dùng chung và giữ trạng thái giữa các lần chạy: task luôn được chọn theo process instance của bản ghi
trong DB riêng của test; ``close()`` hủy mọi instance mà DB này biết.
"""

import asyncio
import copy
import hashlib
import uuid
from collections.abc import Coroutine
from typing import Any

import asyncpg
import httpx
from dxos_core import worker
from dxos_core.jobs.context import WorkerContext
from dxos_core.registry.bpmn import check_against_manifest, render_bpmn
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_core.workflow.flowable import FlowableClient
from dxos_proof.canonical import canonical_bytes, sha256_hex

from helpers.files import FILES
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
_DENY_ACTIONS = ("complete", "pii_review", "list_tasks", "read", "update", "list", "create", "reveal_pii")
_GUARD_REASONS = ("same_actor", "role_not_allowed", "field_missing", "attachments_not_clean",
                  "pii_not_reviewed", "record_sealed", "not_assignee")
_PLAIN_REASONS = ("not_task_role", "kms_unavailable", "seal_key_expired", "org_not_configured",
                  "not_pii_reviewer", "no_app_role", "admin_no_data_access", "not_in_access_list")


def headers_for(as_: str | dict) -> dict[str, str]:
    if isinstance(as_, dict):
        return as_
    return bearer(make_token(as_, [f"app:{APP}:{r}" for r in ROLES[as_]]))


class FlowHarness:
    def __init__(self, api: httpx.AsyncClient, conn: asyncpg.Connection, flowable: FlowableClient,
                 worker_ctx: WorkerContext) -> None:
        self.api, self.conn, self.flowable, self.worker_ctx = api, conn, flowable, worker_ctx
        self.db = worker_ctx.pool              # đọc từ pool: các lời gọi của harness có thể chạy đồng thời
        self._slow: list[tuple[asyncio.Event, asyncio.Event]] = []
        self.slow_uploads_past_checks = 0      # số upload chậm đã qua bước kiểm quyền, đang gửi thân
        self._guards: set[str] = set()

    # ------------------------------------------------------------ cài app
    async def install_version(self, version: str = "0.1.0", *, add_guard: dict[str, str] | None = None,
                              activate: bool = True) -> None:
        """Cài một phiên bản ``test-flow`` (tùy chọn thêm guard vào task) và kích hoạt nó."""
        r = raw(APP)
        r["app"]["version"] = version
        for task, guard in (add_guard or {}).items():
            r["workflow"]["tasks"][task]["guards"] = [*r["workflow"]["tasks"][task]["guards"], guard]
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
        r = await self.api.post(URL, json=data or {"title": "Hồ sơ thử"}, headers=headers_for(author))
        assert r.status_code == 201, r.text
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

    async def instance_running(self, iid: str) -> bool:
        return not (await self.flowable.outcome(iid)).ended

    async def admin_post(self, path: str) -> httpx.Response:
        r = await self.api.post(path, headers=self.admin())
        assert r.status_code == 200, r.text
        return r

    # ------------------------------------------------------------ đọc DB / ledger
    async def count(self, table: str, rid: str) -> int:
        assert table.isidentifier()
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
