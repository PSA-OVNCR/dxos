# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""PDP: quyết định quyền theo manifest (spec 9.4 điểm 3; Plan 01 Task 12).

Thứ tự trong ``decide``:
1. Người gọi không có vai trò nào của app → ``admin_no_data_access`` (nếu là dxos-admin, D4)
   hoặc ``no_app_role``.
2. Collection không có trong manifest → ``unknown_collection``.
3. ``reveal_pii`` → ``policies.pii.reveal_roles``.
4. ``list``/``read`` → ``access.read``; ``create`` → ``access.create``; ``update`` → ``access.update``.
   Vai trò được xét trước ``owner``: với ``list``, lý do ``owner`` nghĩa là chỉ được thấy bản ghi của mình.

``deny`` ghi một lần từ chối không do ``decide`` quyết định (guard, role của task, KMS...), Plan 02 Task 6.
"""

from dataclasses import dataclass
from typing import Literal

import asyncpg

from dxos_core.identity.jwt import Principal, app_roles
from dxos_core.ledger.log import append
from dxos_core.registry.model import Manifest

Action = Literal["list", "read", "create", "update", "reveal_pii"]
_ACCESS_LIST = {"list": "read", "read": "read", "create": "create", "update": "update"}


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


class NotFound(Exception):
    """Từ chối đọc/sửa bản ghi: trả 404 để không lộ bản ghi có tồn tại (chống IDOR, AT-06)."""


class Forbidden(Exception):
    """Từ chối ở mức collection (list/create): trả 403."""


def decide(p: Principal, action: Action, m: Manifest, collection: str, record_owner: str | None) -> Decision:
    roles = app_roles(p, m.app.id)
    if not roles:
        return Decision(False, "admin_no_data_access" if p.is_admin else "no_app_role")
    col = m.collections.get(collection)
    if col is None:
        return Decision(False, "unknown_collection")
    if action == "reveal_pii":
        for r in m.policies.pii.reveal_roles:
            if r in roles:
                return Decision(True, f"role:{r}")
        return Decision(False, "not_in_access_list")
    entries = getattr(col.access, _ACCESS_LIST[action])
    for entry in entries:
        if entry.startswith("role:") and entry[5:] in roles:
            return Decision(True, entry)
    if "owner" in entries and action != "create":
        if action == "list" or (record_owner is not None and record_owner == p.sub):
            return Decision(True, "owner")
    return Decision(False, "not_in_access_list")


async def enforce(conn: asyncpg.Connection, p: Principal, action: Action, m: Manifest, collection: str,
                  record_owner: str | None, subject: str, hmac_key: bytes) -> Decision:
    """Như ``decide`` nhưng khi từ chối thì ghi ledger ``policy.denied`` rồi raise (F3).

    Phải gọi **ngoài** transaction của bên gọi: nếu không, rollback sẽ xóa luôn bằng chứng bị từ chối.
    """
    d = decide(p, action, m, collection, record_owner)
    if d.allow:
        return d
    if conn.is_in_transaction():
        raise RuntimeError("enforce() bị từ chối trong một transaction: lá policy.denied có thể bị rollback")
    await append(conn, type="policy.denied", subject=subject,
                 body={"action": action, "reason": d.reason, "collection": collection},
                 hmac_key=hmac_key, app_id=m if isinstance(m, str) else m.app.id, actor_sub=p.sub)
    if action in ("list", "create"):
        raise Forbidden(d.reason)
    raise NotFound(d.reason)


async def deny(conn: asyncpg.Connection, p: Principal, m: Manifest | str, *, action: str, reason: str,
               subject: str, hmac_key: bytes) -> None:
    """Ghi ledger ``policy.denied {action, reason}`` cho một lần từ chối ngoài ``decide`` (Plan 02 Task 6).

    ``reason`` theo định dạng thống nhất: ``guard:<guard>:<lý do>``, ``not_task_role``, ``kms_unavailable``,
    ``seal_key_expired``, ``org_not_configured``, ``not_pii_reviewer`` (Task 7/12 thêm ``not_revoker``,
    ``not_eraser``, ``self_approval``; Plan 04 Task 5 thêm ``pii_original``: tải bản gốc tệp bị khóa).
    Bên gọi tự trả mã HTTP.
    ``m`` là manifest hoặc chỉ ``app_id`` (installer từ chối duyệt trước khi kiểm manifest, Task 12).
    Như ``enforce``: phải gọi **ngoài** transaction, nếu không lá có thể bị rollback cùng transaction (F3).
    """
    if conn.is_in_transaction():
        raise RuntimeError("deny() trong một transaction: lá policy.denied có thể bị rollback")
    await append(conn, type="policy.denied", subject=subject, body={"action": action, "reason": reason},
                 hmac_key=hmac_key, app_id=m if isinstance(m, str) else m.app.id, actor_sub=p.sub)
