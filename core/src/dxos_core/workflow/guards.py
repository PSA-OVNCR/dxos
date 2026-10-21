# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Danh mục guard chung (spec 9.3, bản 1.0.3 phần B; Plan 02 Task 5).

Guard là kiểm tra khai báo mà manifest gắn vào task của quy trình. Tách làm hai nửa:

* ``load_guard_input``: nửa DUY NHẤT có I/O, gom mọi dữ kiện từ DB vào một ``GuardInput`` bất biến.
* ``evaluate``: hàm thuần, không I/O, đánh giá danh sách guard theo thứ tự khai báo; lỗi đầu tiên thắng.

Cú pháp guard dùng lại ``split_guard``/``parse_role_list`` của validator (một bộ phân tích duy nhất).
Manifest đã được kiểm lúc cài, nên guard ngoài danh mục hoặc sai tham số ở đây là lỗi lập trình:
``evaluate`` ném ``ValueError`` chứ không trả ``GuardFailure``.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import asyncpg
from dxos_proof.canonical import canonical_bytes, sha256_hex

from dxos_core.identity.jwt import Principal, app_roles
from dxos_core.records.digest import data_digest, ensure_salt
from dxos_core.registry.model import CollectionSpec, Manifest
from dxos_core.registry.validator import GUARD_CATALOG, parse_role_list, split_guard


@dataclass(frozen=True)
class GuardInput:
    caller_sub: str
    caller_roles: frozenset[str]            # role của app, đã bỏ tiền tố ``app:<id>:``
    owner_sub: str
    seal_state: str
    data: dict                              # nguyên giá trị: ``field_required`` cần đọc
    task_assignee: str | None
    uploads_pending: int                    # số upload STAGING của bản ghi
    clean_attachments: tuple[str, ...]      # sha256 các tệp CLEAN (object_refs ``original``), đã sắp xếp
    attachments_min: int                    # 0 nếu collection không có attachments
    completions: tuple[tuple[str, str], ...]  # (task_key, actor_sub) của instance hiện tại
    pii_required: bool                      # collection có trường pii hoặc policies.pii.document_detect
    finding_ids: tuple[int, ...]            # id pii_findings của các tệp CLEAN hiện tại, đã sắp xếp
    last_review_digest: str | None          # review_digest của pii_reviews mới nhất của bản ghi
    data_digest: str                        # data_digest(data, salt của bản ghi), có salt (P2-D22)


@dataclass(frozen=True)
class GuardFailure:
    guard: str                              # nguyên văn chuỗi guard trong manifest
    reason: str
    status: int                             # 403 hoặc 409


def review_digest(data_digest: str, clean_attachments: Sequence[str], finding_ids: Sequence[int]) -> str:
    """Cam kết của lần rà PII: dữ liệu + tệp CLEAN + phát hiện, không phụ thuộc thứ tự đầu vào.

    ``data_digest`` là bản có salt (P2-D22): ``pii_reviews`` là bảng chỉ thêm, không được giữ cam kết
    không salt.
    """
    return sha256_hex(canonical_bytes({
        "data_digest": data_digest,
        "attachments": sorted(clean_attachments),
        "findings": sorted(finding_ids),
    }))


def _fail(guard: str, reason: str, status: int) -> GuardFailure:
    return GuardFailure(guard, reason, status)


def _check(guard: str, gi: GuardInput) -> GuardFailure | None:
    name, arg = split_guard(guard)
    if name not in GUARD_CATALOG:
        raise ValueError(f"guard ngoài danh mục: {guard!r}")
    if name == "not_same_actor":
        if not arg:
            raise ValueError(f"guard thiếu tham số: {guard!r}")
        if arg == "creator":
            same = gi.caller_sub == gi.owner_sub
        else:
            same = any(task == arg and actor == gi.caller_sub for task, actor in gi.completions)
        return _fail(guard, "same_actor", 403) if same else None
    if name == "role_in":
        roles = parse_role_list(arg) if arg is not None else None
        # ngoặc lệch (``[a,b``) thì parse_role_list không bắt được, nên kiểm thêm ở đây
        if roles is None or any("[" in r or "]" in r for r in roles):
            raise ValueError(f"guard sai danh sách role: {guard!r}")
        return None if gi.caller_roles & set(roles) else _fail(guard, "role_not_allowed", 403)
    if name == "field_required":
        if not arg:
            raise ValueError(f"guard thiếu tham số: {guard!r}")
        v = gi.data.get(arg)
        return _fail(guard, "field_missing", 409) if v is None or v == "" else None
    if arg is not None:
        raise ValueError(f"guard này không có tham số: {guard!r}")
    if name == "attachments_clean":
        ok = gi.uploads_pending == 0 and len(gi.clean_attachments) >= gi.attachments_min
        return None if ok else _fail(guard, "attachments_not_clean", 409)
    if name == "pii_reviewed":
        if not gi.pii_required:
            return None
        want = review_digest(gi.data_digest, gi.clean_attachments, gi.finding_ids)
        return None if gi.last_review_digest == want else _fail(guard, "pii_not_reviewed", 409)
    if name == "record_not_sealed":
        return None if gi.seal_state == "NONE" else _fail(guard, "record_sealed", 409)
    # assignee_is_caller: task không có assignee thì trượt (Plan 02 chưa có API nhận việc, nên hiện luôn
    # trượt).
    ok = gi.task_assignee is not None and gi.task_assignee == gi.caller_sub
    return None if ok else _fail(guard, "not_assignee", 403)


def evaluate(guards: Sequence[str], gi: GuardInput) -> GuardFailure | None:
    """Lỗi đầu tiên theo thứ tự khai báo, hoặc ``None`` nếu mọi guard đạt. Thuần, không I/O."""
    for g in guards:
        failure = _check(g, gi)
        if failure is not None:
            return failure
    return None


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def load_guard_input(conn: asyncpg.Connection, *, record: asyncpg.Record, spec: CollectionSpec,
                           m: Manifest, p: Principal, task_assignee: str | None) -> GuardInput:
    """Gom dữ kiện cho ``evaluate``. Mọi truy vấn DB của guard nằm ở đây.

    HỢP ĐỒNG KHÓA (C7, spec 25.2): hàm này KHÔNG tự khóa. Người gọi phải đang ở trong một transaction đã giữ
    ``SELECT … FROM core.records WHERE id = $1 FOR SHARE`` (hoặc ``FOR UPDATE``) trên hàng của bản ghi và
    đã đọc ``record`` SAU khi giữ khóa. Lý do: salt của bản ghi chỉ được đọc/tạo dưới khóa hàng
    (``ensure_salt`` có thể INSERT), và khóa này chặn các bên giữ ``FOR UPDATE`` (``:erase-pii``,
    ``workflow:start``, sửa bản ghi) chen giữa lúc đọc.
    Người gọi: bridge hoàn thành task (Task 6) và ``:pii-review``.
    """
    record_id: uuid.UUID = record["id"]
    data = _loads(record["data"])
    uploads_pending = await conn.fetchval(
        "SELECT count(*) FROM core.uploads WHERE record_id=$1 AND status='STAGING'", record_id)
    clean = tuple(r["sha256"] for r in await conn.fetch(
        "SELECT r.sha256 FROM core.object_refs r JOIN core.objects o ON o.sha256 = r.sha256"
        " WHERE r.record_id=$1 AND r.role='original' AND o.status='CLEAN' ORDER BY r.sha256", record_id))
    findings = tuple(r["id"] for r in await conn.fetch(
        "SELECT id FROM core.pii_findings WHERE sha256::text = ANY($1::text[]) ORDER BY id", list(clean)))
    last_review = await conn.fetchval(
        "SELECT review_digest FROM core.pii_reviews WHERE record_id=$1 ORDER BY id DESC LIMIT 1", record_id)
    instance = record["wf_instance_id"]
    completions: tuple[tuple[str, str], ...] = ()
    if instance is not None:
        completions = tuple((r["task_key"], r["actor_sub"]) for r in await conn.fetch(
            "SELECT task_key, actor_sub FROM core.task_completions WHERE record_id=$1 AND wf_instance_id=$2"
            " ORDER BY completed_at, task_id", record_id, instance))
    pii_required = any(f.pii for f in spec.fields.values()) or bool(m.policies.pii.document_detect)
    salt = await ensure_salt(conn, record_id)
    return GuardInput(
        caller_sub=p.sub,
        caller_roles=app_roles(p, m.app.id),
        owner_sub=record["owner_sub"],
        seal_state=record["seal_state"],
        data=data,
        task_assignee=task_assignee,
        uploads_pending=uploads_pending,
        clean_attachments=clean,
        attachments_min=spec.attachments.min if spec.attachments else 0,
        completions=completions,
        pii_required=pii_required,
        finding_ids=findings,
        last_review_digest=last_review,
        data_digest=data_digest(data, salt),
    )
