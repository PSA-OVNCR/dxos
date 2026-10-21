# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client Flowable REST (7.1.0). Chỉ ``trust-core-api`` được gọi (net-wf); worker không bao giờ cần Flowable.

Tên endpoint và tham số đã đối chiếu với Flowable thật, xem ``docs/spikes/flowable.md``
(mục "Kiểm lại Plan 02 Task 4"). Quy ước lỗi (F8, fail-closed):

- mạng lỗi, quá hạn, 5xx, 401, 403, 4xx bất ngờ, phản hồi sai dạng -> ``WorkflowUnavailable`` (API trả 503);
- ``complete`` gặp 404/409, hoặc 500 mà task đã xong trong lịch sử (thua cuộc đua) -> ``TaskGone``;
- ``get_task`` 404 -> ``None``; ``cancel`` 404 không phải lỗi.

Ngữ nghĩa 404 -> ``None``/``TaskGone`` giả định ``base_url`` đúng: nơi khởi động (app, bridge) phải gọi
``ping()`` trước, vì base URL sai thì mọi đường dẫn đều 404 và bị đọc nhầm là "task không còn".
Mọi id đặt vào đường dẫn URL phải qua ``_seg`` (``ValueError`` nếu không khớp ``[A-Za-z0-9._:@-]{1,255}`` hoặc
toàn dấu chấm), để id thô không thể đổi đích request (``..``, ``?``, ``#``). Bên gọi map ValueError thành 404.

Thông báo lỗi không bao giờ chứa mật khẩu hay nội dung phản hồi của Flowable.
Mọi biến gửi lên Flowable đều có ``type: "string"``; client không tự thêm biến nào.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from dxos_core.settings import read_secret

if TYPE_CHECKING:
    from dxos_core.settings import Settings

INTENT_VARIABLE = "dxos_intent_id"
_BPMN_SUFFIX = ".bpmn20.xml"
_MAX_TASKS = 10_000
# Lỗi xảy ra trước khi request rời client: Flowable chắc chắn chưa nhận request (client mới cho mỗi request,
# không dùng lại kết nối, nên ConnectError không thể xảy ra sau khi đã gửi).
_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
# Id Flowable đặt vào đường dẫn URL: uuid, `key:phiên-bản:uuid`, ... Không có `/ ? # % \` hay khoảng trắng.
_SEGMENT = re.compile(r"[A-Za-z0-9._:@-]{1,255}")


class WorkflowUnavailable(Exception):  # noqa: N818 (tên theo spec F8)
    """Mạng lỗi, 5xx, 401/403 hoặc phản hồi không dùng được -> API trả 503 (F8).

    ``sent``: request có thể đã tới Flowable hay không. ``False`` chỉ khi lỗi xảy ra trước khi request rời
    client (không kết nối được, hết hạn chờ kết nối hay chờ pool): chắc chắn Flowable chưa nhận gì.
    Mọi trường hợp khác (quá hạn đọc/ghi, lỗi giao thức, mã lỗi sau khi gửi) là ``True``: Flowable có thể đã
    commit, kể cả sau khi client bỏ cuộc. Mặc định ``True`` (thận trọng).
    """

    def __init__(self, *args: object, sent: bool = True) -> None:
        super().__init__(*args)
        self.sent = sent


class TaskGone(Exception):  # noqa: N818
    """Task đã xong/không còn (404) hoặc đang bị người khác hoàn thành cùng lúc (409)."""


@dataclass(frozen=True)
class FlowTask:
    id: str
    task_key: str
    name: str
    process_instance_id: str
    process_definition_key: str
    assignee: str | None
    created: str


@dataclass(frozen=True)
class Outcome:
    ended: bool
    end_event: str | None      # endActivityId khi đã kết thúc; None nếu bị hủy (không qua end event)


def _seg(value: object) -> str:
    """Id hợp lệ để đặt vào một đoạn đường dẫn URL, nếu không thì ``ValueError`` (lỗi của người gọi).

    httpx chuẩn hóa dấu chấm (``..``) và không mã hóa ``?``/``#``, nên id thô như
    ``../../repository/deployments/x`` sẽ đổi đích của request sang endpoint khác với quyền rest-admin.
    """
    if not isinstance(value, str) or not _SEGMENT.fullmatch(value) or not value.strip("."):
        raise ValueError("id không hợp lệ để đặt vào đường dẫn Flowable")
    return value


def _variables(variables: Mapping[str, str], *, local: bool = False) -> list[dict[str, str]]:
    """Dựng danh sách biến Flowable. Chỉ nhận ``str``; không bao giờ suy đoán kiểu khác."""
    out: list[dict[str, str]] = []
    for name, value in variables.items():
        if not isinstance(name, str) or not name:
            raise TypeError(f"tên biến phải là chuỗi không rỗng: {name!r}")
        if not isinstance(value, str):
            raise TypeError(f"biến {name!r} phải là str, nhận {type(value).__name__}")
        item = {"name": name, "value": value, "type": "string"}
        if local:
            item["scope"] = "local"
        out.append(item)
    return out


class FlowableClient:
    def __init__(self, base_url: str, user: str, password: str, *, timeout_s: float = 10.0) -> None:
        parts = urlsplit(base_url)
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise ValueError("base_url không được chứa thông tin đăng nhập (dùng user/password)")
        self.base_url = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(user, password)
        self._timeout = timeout_s
        self._page_size = 100

    @property
    def timeout_s(self) -> float:
        return self._timeout

    def __repr__(self) -> str:
        return f"FlowableClient({self.base_url!r})"

    # ------------------------------------------------------------ truyền tải
    async def _send(self, method: str, path: str, *, ok: tuple[int, ...], **kwargs: Any) -> httpx.Response:
        """Gửi một request; trả phản hồi nếu mã nằm trong ``ok``, ngược lại ``WorkflowUnavailable``."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth, trust_env=False) as client:
                resp = await client.request(method, f"{self.base_url}{path}", **kwargs)
        except _NEVER_SENT as exc:
            raise WorkflowUnavailable(f"Flowable {type(exc).__name__}", sent=False) from exc
        except httpx.HTTPError as exc:
            raise WorkflowUnavailable(f"Flowable {type(exc).__name__}", sent=True) from exc
        if resp.status_code not in ok:
            raise WorkflowUnavailable(f"Flowable trả HTTP {resp.status_code} cho {method} {path}")
        return resp

    @staticmethod
    def _json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as exc:
            raise WorkflowUnavailable("Flowable trả dữ liệu không phải JSON") from exc
        if not isinstance(data, dict):
            raise WorkflowUnavailable("Flowable trả dữ liệu sai dạng")
        return data

    @classmethod
    def _rows(cls, resp: httpx.Response) -> list[dict[str, Any]]:
        rows = cls._json(resp).get("data")
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise WorkflowUnavailable("Flowable trả danh sách sai dạng")
        return rows

    @staticmethod
    def _id(row: Mapping[str, Any]) -> str:
        value = row.get("id")
        if not isinstance(value, str) or not value:
            raise WorkflowUnavailable("Flowable trả bản ghi thiếu id")
        return value

    @staticmethod
    def _task(row: Mapping[str, Any]) -> FlowTask:
        try:
            definition_id = str(row["processDefinitionId"])
            return FlowTask(
                id=str(row["id"]), task_key=str(row["taskDefinitionKey"]), name=str(row.get("name") or ""),
                process_instance_id=str(row["processInstanceId"]),
                # processDefinitionId có dạng key:phiên-bản:uuid; key BPMN (NCName) không chứa dấu ':'.
                process_definition_key=definition_id.split(":", 1)[0],
                assignee=row.get("assignee") or None, created=str(row.get("createTime") or ""))
        except KeyError as exc:
            raise WorkflowUnavailable("Flowable trả task thiếu trường") from exc

    async def ping(self) -> None:
        """``GET /management/engine`` phải trả 200; mã khác hay lỗi mạng -> ``WorkflowUnavailable``.

        Dùng lúc khởi động để phân biệt base URL sai (404 ở mọi nơi) với "task đã mất".
        """
        await self._send("GET", "/management/engine", ok=(200,))

    # ------------------------------------------------------------ deploy
    async def deploy(self, name: str, filename: str, xml: bytes) -> str:
        """Triển khai BPMN; trả id deployment. Đã có deployment cùng ``name`` thì trả id cũ.

        Flowable đặt tên deployment từ tên tệp trừ khi có tham số ``deploymentName``; client luôn truyền nó.
        Trùng tên mà nội dung khác vẫn trả id cũ: người gọi phải đưa phiên bản/băm vào ``name``.
        """
        if not filename.endswith(_BPMN_SUFFIX) or len(filename) == len(_BPMN_SUFFIX) or "/" in filename \
                or "\\" in filename or ".." in filename:
            raise ValueError(f"tên tệp BPMN phải dạng <tên>{_BPMN_SUFFIX}: {filename!r}")
        found = await self._send("GET", "/repository/deployments", ok=(200,), params={
            "name": name, "sort": "deployTime", "order": "asc", "size": 1})
        rows = self._rows(found)
        if rows:
            return self._id(rows[0])
        resp = await self._send("POST", "/repository/deployments", ok=(200, 201),
                                params={"deploymentName": name},
                                files={"file": (filename, xml, "text/xml")})
        return self._id(self._json(resp))

    async def definition_id(self, deployment_id: str) -> str:
        """``processDefinitionId`` của deployment (lõi chỉ triển khai mô hình một quy trình)."""
        resp = await self._send("GET", "/repository/process-definitions", ok=(200,),
                                params={"deploymentId": deployment_id})
        rows = self._rows(resp)
        if len(rows) != 1:
            raise WorkflowUnavailable(f"deployment phải có đúng một process definition, thấy {len(rows)}")
        return self._id(rows[0])

    # ------------------------------------------------------------ instance
    async def start(self, definition_id: str, business_key: str, variables: Mapping[str, str]) -> str:
        """Bắt đầu quy trình theo ``processDefinitionId`` (ghim phiên bản, P2-D19); trả id instance."""
        payload = {"processDefinitionId": definition_id, "businessKey": business_key,
                   "variables": _variables(variables)}
        resp = await self._send("POST", "/runtime/process-instances", ok=(200, 201), json=payload)
        return self._id(self._json(resp))

    async def running_instance(self, definition_id: str, business_key: str) -> str | None:
        resp = await self._send("GET", "/runtime/process-instances", ok=(200,), params={
            "processDefinitionId": definition_id, "businessKey": business_key})
        rows = self._rows(resp)
        return self._id(rows[0]) if rows else None

    async def business_key(self, instance_id: str) -> str | None:
        """Business key của instance, đang chạy hoặc đã kết thúc (đọc lịch sử); không có instance -> None."""
        seg = _seg(instance_id)
        for path in (f"/runtime/process-instances/{seg}", f"/history/historic-process-instances/{seg}"):
            resp = await self._send("GET", path, ok=(200, 404))
            if resp.status_code == 200:
                value = self._json(resp).get("businessKey")
                return value if isinstance(value, str) and value else None
        return None

    async def cancel(self, instance_id: str, reason: str) -> None:
        """Hủy instance đang chạy; 404 (đã xong hoặc không có) không phải lỗi."""
        await self._send("DELETE", f"/runtime/process-instances/{_seg(instance_id)}", ok=(200, 204, 404),
                         params={"deleteReason": reason})

    async def outcome(self, instance_id: str) -> Outcome:
        """Đang chạy -> ``Outcome(False, None)``; đã kết thúc -> ``endActivityId`` lịch sử (None: bị hủy)."""
        seg = _seg(instance_id)
        running = await self._send("GET", f"/runtime/process-instances/{seg}", ok=(200, 404))
        if running.status_code == 200:
            return Outcome(ended=False, end_event=None)
        hist = await self._send("GET", f"/history/historic-process-instances/{seg}", ok=(200, 404))
        if hist.status_code == 404:
            raise WorkflowUnavailable("Flowable không còn instance này (cả runtime lẫn lịch sử)")
        data = self._json(hist)
        end = data.get("endActivityId")
        return Outcome(ended=data.get("endTime") is not None, end_event=end if isinstance(end, str) else None)

    # ------------------------------------------------------------ task
    async def get_task(self, task_id: str) -> FlowTask | None:
        resp = await self._send("GET", f"/runtime/tasks/{_seg(task_id)}", ok=(200, 404))
        return None if resp.status_code == 404 else self._task(self._json(resp))

    async def list_tasks(self, candidate_groups: list[str], process_key_prefix: str) -> list[FlowTask]:
        """Task đang mở có nhóm ứng viên thuộc ``candidate_groups``, của quy trình có key bắt đầu bằng prefix.

        Tham số thật là ``candidateGroups`` (phân cách dấu phẩy). ``candidateGroupIn`` bị Flowable 7.1.0
        bỏ qua im lặng và trả mọi task, nên tuyệt đối không dùng. Nhóm chứa dấu phẩy bị từ chối vì sẽ
        tách thành hai nhóm.
        """
        if not process_key_prefix:
            raise ValueError("tiền tố key quy trình không được rỗng")
        for g in candidate_groups:
            if not g.strip() or "," in g:
                raise ValueError(f"nhóm ứng viên không hợp lệ: {g!r}")
        if not candidate_groups:
            return []
        found: dict[str, FlowTask] = {}
        start = 0
        while True:
            resp = await self._send("GET", "/runtime/tasks", ok=(200,), params={
                "candidateGroups": ",".join(candidate_groups),
                "processDefinitionKeyLike": f"{process_key_prefix}%",
                "size": self._page_size, "start": start})
            page = self._json(resp)
            rows = self._rows(resp)
            total = page.get("total")
            if not isinstance(total, int) or isinstance(total, bool):
                raise WorkflowUnavailable("Flowable không trả tổng số task (total)")
            for row in rows:
                task = self._task(row)
                # LIKE coi `_` và `%` là ký tự đại diện: lọc lại chính xác để không rò sang app khác.
                if task.process_definition_key.startswith(process_key_prefix):
                    found[task.id] = task
            start += len(rows)
            if not rows or start >= total:
                break
            if start >= _MAX_TASKS:
                raise WorkflowUnavailable("quá nhiều task đang mở để liệt kê")
        return sorted(found.values(), key=lambda t: (t.created, t.id))

    async def complete(self, task_id: str, variables: Mapping[str, str], *,
                       local_variables: Mapping[str, str] | None = None) -> None:
        """Hoàn thành task. ``local_variables`` gắn vào chính task (``scope: local``), vd. dxos_intent_id."""
        seg = _seg(task_id)
        glob = _variables(variables)
        local = _variables(local_variables or {}, local=True)
        clash = {v["name"] for v in glob} & {v["name"] for v in local}
        if clash:
            raise ValueError(f"biến trùng tên giữa toàn cục và cục bộ: {sorted(clash)}")
        resp = await self._send("POST", f"/runtime/tasks/{seg}", ok=(200, 204, 404, 409, 500),
                                json={"action": "complete", "variables": glob + local})
        if resp.status_code in (404, 409):
            raise TaskGone(task_id)
        if resp.status_code == 500:
            # Flowable 7.1.0 KHÔNG trả 409 cho bên thua cuộc đua hoàn thành cùng lúc mà trả 500 với nhiều
            # thông điệp ("was updated by another transaction concurrently", cả NullPointerException).
            # Không so khớp thông điệp: bên thắng đã commit trước nên task đã xong trong lịch sử -> TaskGone.
            # Task chưa xong thì 500 là lỗi thật (vd. quyết định không khớp cổng) -> WorkflowUnavailable.
            try:
                done = await self.historic_task_done(task_id)
            except WorkflowUnavailable as exc:      # POST đã tới Flowable: kết quả vẫn không rõ
                raise WorkflowUnavailable(str(exc), sent=True) from exc
            if done:
                raise TaskGone(task_id)
            raise WorkflowUnavailable(f"Flowable trả HTTP 500 cho POST /runtime/tasks/{seg}")

    # ------------------------------------------------------------ đối soát ý định (P2-D20)
    async def historic_task_done(self, task_id: str) -> bool:
        resp = await self._send("GET", f"/history/historic-task-instances/{_seg(task_id)}", ok=(200, 404))
        return resp.status_code == 200 and self._json(resp).get("endTime") is not None

    async def historic_done_tasks(self, instance_id: str) -> list[tuple[str, str]]:
        """``(task_id, task_key)`` của mọi task ĐÃ XONG của instance (lịch sử, ``finished=true``), theo trang.

        Dùng cho bất biến của cầu nối: mọi task đã xong của instance hiện tại phải có ``task_completions``.
        Trang rỗng khi chưa đủ ``total`` → ``WorkflowUnavailable`` (không bao giờ trả danh sách thiếu).
        """
        seg = _seg(instance_id)
        out: list[tuple[str, str]] = []
        start = 0
        while True:
            resp = await self._send("GET", "/history/historic-task-instances", ok=(200,), params={
                "processInstanceId": seg, "finished": "true", "size": self._page_size, "start": start})
            total = self._json(resp).get("total")
            if not isinstance(total, int) or isinstance(total, bool):
                raise WorkflowUnavailable("Flowable không trả tổng số task (total)")
            rows = self._rows(resp)
            for row in rows:
                key = row.get("taskDefinitionKey")
                if not isinstance(key, str) or not key:
                    raise WorkflowUnavailable("Flowable trả task lịch sử thiếu taskDefinitionKey")
                out.append((self._id(row), key))
            start += len(rows)
            if start >= total:
                return out
            if not rows:
                # Trang rỗng mà chưa đủ ``total``: lịch sử lệch/đang dọn, không biết đã đủ chưa → fail-closed.
                raise WorkflowUnavailable("Flowable trả trang lịch sử rỗng trước khi đủ total")
            if start >= _MAX_TASKS:
                raise WorkflowUnavailable("quá nhiều task lịch sử để liệt kê")

    async def historic_intent_id(self, task_id: str) -> str | None:
        """Biến ``dxos_intent_id`` (task-local) lúc task hoàn thành; chưa có -> None."""
        resp = await self._send("GET", "/history/historic-variable-instances", ok=(200,), params={
            "taskId": _seg(task_id), "variableName": INTENT_VARIABLE})
        for row in self._rows(resp):
            variable = row.get("variable")
            if isinstance(variable, dict) and isinstance(variable.get("value"), str):
                return variable["value"]
        return None


def flowable_from_settings(settings: Settings) -> FlowableClient | None:
    """Client theo cấu hình; ``None`` khi chưa đặt ``flowable_password_file`` (API trả 503 cho workflow).

    Đọc tệp bí mật ở thời điểm dùng. Không đọc được hoặc rỗng -> ``WorkflowUnavailable`` (fail-closed,
    không lộ đường dẫn hay nội dung).
    """
    if settings.flowable_password_file is None:
        return None
    try:
        password = read_secret(settings.flowable_password_file)
    except (OSError, ValueError) as exc:
        raise WorkflowUnavailable("không đọc được bí mật Flowable") from exc
    return FlowableClient(settings.flowable_url, settings.flowable_user, password)
