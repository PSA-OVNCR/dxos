# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Luật nâng phiên bản app: chỉ cộng thêm hoặc siết chặt (P2-D14, spec 9.5, 25.4; Plan 02 Task 12).

Kiểm lúc nộp và **kiểm lại** lúc duyệt, so với bản ACTIVE tại thời điểm đó. Mọi vi phạm là
``ManifestError("UPGRADE_NOT_ADDITIVE", <JSON pointer vào manifest mới>, <thông điệp>)``.

Luật:
- Collection cũ còn nguyên; trường cũ còn nguyên và giữ ``type``; trường cũ không chuyển sang ``required``;
  trường mới của collection cũ không ``required`` (collection mới thì tự do: chưa có bản ghi nào).
- Trường cũ có ``pii`` thì giữ đúng loại ``pii`` (bỏ cờ là nới che dữ liệu); thêm ``pii`` vào trường cũ là
  siết.
- Tập role mới ⊇ tập role cũ.
- Bản cũ có workflow thì bản mới cũng có; task cũ còn, giữ ``role``, tập guard mới ⊇ tập guard cũ.
- ``pii.reveal_roles`` mới ⊆ cũ.
- Khi ``sealed_before``: ``policies.seal`` (kể cả ``public_fields``, ``revoke_roles``) và ``policies.verify``
  không đổi, ``revoke_roles`` mới ⊆ cũ. Khi chưa từng niêm phong (``sealed_before=False``) thì bỏ qua cả ba.
- Đổi tự do: ``pii.erase_roles``, ``label`` của trường, ``format`` và ``reset`` của trường ``sequence``
  (``format`` không phải kiểu), ``access``, ``app.name``. ``access`` hiện ra trong diff quyền để người duyệt
  xem.
"""

import asyncpg

from dxos_core.registry.model import Manifest
from dxos_core.registry.validator import ManifestError


def _fail(path: str, message: str) -> ManifestError:
    return ManifestError("UPGRADE_NOT_ADDITIVE", path, message)


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _check_collections(old: Manifest, new: Manifest) -> None:
    for cname, ocol in old.collections.items():
        base = f"/collections/{_esc(cname)}"
        ncol = new.collections.get(cname)
        if ncol is None:
            raise _fail(base, f"collection {cname!r} của bản cũ bị bỏ")
        for fname, of in ocol.fields.items():
            fpath = f"{base}/fields/{_esc(fname)}"
            nf = ncol.fields.get(fname)
            if nf is None:
                raise _fail(fpath, f"trường {cname}.{fname} của bản cũ bị bỏ")
            if nf.type != of.type:
                raise _fail(f"{fpath}/type", f"trường {cname}.{fname} đổi kiểu {of.type} → {nf.type}")
            if nf.required and not of.required:
                raise _fail(f"{fpath}/required",
                            f"trường {cname}.{fname} chuyển sang bắt buộc: bản ghi cũ có thể thiếu nó")
            if of.pii is not None and nf.pii != of.pii:
                raise _fail(f"{fpath}/pii", f"trường {cname}.{fname} bỏ hoặc đổi loại pii ({of.pii})")
        for fname, nf in ncol.fields.items():
            if fname not in ocol.fields and nf.required:
                raise _fail(f"{base}/fields/{_esc(fname)}/required",
                            f"trường mới {cname}.{fname} không được bắt buộc khi nâng phiên bản")


def _check_workflow(old: Manifest, new: Manifest) -> None:
    if old.workflow is None:
        return
    if new.workflow is None:
        raise _fail("/workflow", "bản cũ có workflow, bản mới bỏ workflow")
    for task, ot in old.workflow.tasks.items():
        tpath = f"/workflow/tasks/{_esc(task)}"
        nt = new.workflow.tasks.get(task)
        if nt is None:
            raise _fail(tpath, f"task {task!r} của bản cũ bị bỏ")
        if nt.role != ot.role:
            raise _fail(f"{tpath}/role", f"task {task!r} đổi role {ot.role} → {nt.role}")
        missing = sorted(set(ot.guards) - set(nt.guards))
        if missing:
            raise _fail(f"{tpath}/guards", f"task {task!r} bỏ guard {missing}")


def check_upgrade(old: Manifest, new: Manifest, *, sealed_before: bool) -> None:
    """Ném ``ManifestError("UPGRADE_NOT_ADDITIVE")`` nếu ``new`` không phải bản nâng cộng thêm của ``old``."""
    if old.app.id != new.app.id:
        raise _fail("/app/id", "khác app")
    dropped = sorted(set(old.roles) - set(new.roles))
    if dropped:
        raise _fail("/roles", f"bỏ role {dropped}")
    _check_collections(old, new)
    _check_workflow(old, new)
    widened = sorted(set(new.policies.pii.reveal_roles) - set(old.policies.pii.reveal_roles))
    if widened:
        raise _fail("/policies/pii/reveal_roles", f"mở rộng quyền xem PII cho {widened}")
    if not sealed_before:
        return                    # P2-D14 ngoại lệ: chưa từng niêm phong thì chính sách niêm phong đổi được
    oseal, nseal = old.policies.seal, new.policies.seal
    if oseal is not None and nseal is not None:
        widened = sorted(set(nseal.revoke_roles) - set(oseal.revoke_roles))
        if widened:
            raise _fail("/policies/seal/revoke_roles", f"mở rộng quyền thu hồi cho {widened}")
    if oseal != nseal:
        raise _fail("/policies/seal", "app đã có niêm phong: không được đổi policies.seal")
    if old.policies.verify != new.policies.verify:
        raise _fail("/policies/verify", "app đã có niêm phong: không được đổi policies.verify")


async def sealed_before(conn: asyncpg.Connection, app_id: str) -> bool:
    """App đã từng có yêu cầu niêm phong, hoặc đang có bản ghi trong quy trình (P2-D14 ngoại lệ)."""
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM core.seal_requests WHERE app_id = $1)"
        " OR EXISTS (SELECT 1 FROM core.records WHERE app_id = $1 AND wf_state = 'running')", app_id)
