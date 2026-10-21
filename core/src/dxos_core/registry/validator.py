# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm manifest trước khi cài (spec 9.1–9.3, 9.5; AT-11, AT-12).

Thứ tự kiểm (lỗi đầu tiên thắng):
1. ``FLOOR_WEAKENED``: có khóa ``quarantine`` ở bất kỳ đâu với giá trị khác ``"required"``.
2. ``NAMESPACE_VIOLATION``: tên role/collection (hoặc ``app.id``) chứa ``:``, hoặc role/collection
   là ``app`` hay bắt đầu bằng ``app_``.
3. ``SCHEMA_INVALID``: sai JSON Schema ``manifest.schema.json``.
4. ``UNKNOWN_GUARD``: guard ngoài danh mục chung, hoặc tham số guard sai (mục 9.3, bản 1.0.3).
5. ``SCHEMA_INVALID``: tham chiếu và ràng buộc chéo (role chưa khai báo, ``public_fields`` không có cờ
   ``public``, trường vừa ``pii`` vừa ``public``, ``seal`` thiếu ``workflow``, định dạng ``sequence``...).
"""

import json
import re
from functools import cache
from importlib import resources
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from dxos_core.registry.model import Manifest

GUARD_CATALOG = frozenset({
    "attachments_clean", "pii_reviewed", "not_same_actor", "role_in",
    "field_required", "record_not_sealed", "assignee_is_caller",
})

# Guard không có tham số: thêm ``:x`` vào là sai.
_NO_ARG_GUARDS = frozenset({"attachments_clean", "pii_reviewed", "record_not_sealed", "assignee_is_caller"})

# ``$`` của Python khớp cả trước ``\n`` cuối chuỗi, nên các mẫu quan trọng được kiểm lại bằng ``fullmatch``.
_ON_EVENT = re.compile(r"process\.completed:[A-Za-z_][A-Za-z0-9_-]{0,63}")
# Token số thứ tự hợp lệ: ``{n}`` hoặc ``{n:0W}`` với W từ 2 đến 9 (spec 25.4).
_SEQ_TOKEN = re.compile(r"\{n(?::0[2-9])?\}")

ErrorCode = Literal["SCHEMA_INVALID", "NAMESPACE_VIOLATION", "FLOOR_WEAKENED", "UNKNOWN_GUARD",
                    "BPMN_INVALID", "UPGRADE_NOT_ADDITIVE"]


class ManifestError(ValueError):
    def __init__(self, code: ErrorCode, path: str, message: str) -> None:
        super().__init__(f"{code} at {path}: {message}")
        self.code, self.path, self.message = code, path, message


@cache
def _schema_validator() -> Draft202012Validator:
    text = resources.files("dxos_core.registry").joinpath("manifest.schema.json").read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer(parts) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts) if parts else ""


def _check_floor(node: Any, path: list) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "quarantine" and v != "required":
                raise ManifestError("FLOOR_WEAKENED", _pointer([*path, k]),
                                    "kiểm dịch là chính sách sàn, chỉ được để 'required'")
            _check_floor(v, [*path, k])
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_floor(v, [*path, i])


def _bad_namespace(name: Any) -> bool:
    # Lõi tự thêm tiền tố ``app:<id>:`` cho role. Giữ riêng ``app`` và ``app_*``; KHÔNG chặn mọi tên bắt đầu
    # bằng "app" (bản 1.0.3 phần B), vì như vậy "approver" (role của manifest test-flow) bị từ chối oan.
    return isinstance(name, str) and (":" in name or name == "app" or name.startswith("app_"))


def _check_namespace(doc: dict) -> None:
    app_id = (doc.get("app") or {}).get("id") if isinstance(doc.get("app"), dict) else None
    if isinstance(app_id, str) and ":" in app_id:
        raise ManifestError("NAMESPACE_VIOLATION", "/app/id", "app.id không được chứa ':'")
    roles = doc.get("roles")
    if isinstance(roles, list):
        for i, r in enumerate(roles):
            if _bad_namespace(r):
                raise ManifestError("NAMESPACE_VIOLATION", f"/roles/{i}",
                                    f"role {r!r}: lõi tự thêm tiền tố app:<id>:, manifest không được tự đặt")
    cols = doc.get("collections")
    if isinstance(cols, dict):
        for name in cols:
            if _bad_namespace(name):
                raise ManifestError("NAMESPACE_VIOLATION", _pointer(["collections", name]),
                                    f"collection {name!r} vi phạm namespace")


def _check_schema(doc: dict) -> None:
    errors = sorted(_schema_validator().iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        e = errors[0]
        raise ManifestError("SCHEMA_INVALID", _pointer(list(e.absolute_path)), e.message)


def split_guard(guard: str) -> tuple[str, str | None]:
    """``"role_in:a,b"`` -> ``("role_in", "a,b")``; guard không tham số -> ``(tên, None)``."""
    name, sep, arg = guard.partition(":")
    return name, (arg if sep else None)


def parse_role_list(arg: str) -> list[str] | None:
    """Tham số của ``role_in``: ``r1,r2`` hoặc ``[r1,r2]``. Rỗng, thiếu phần tử hay ngoặc lệch -> ``None``."""
    if arg.startswith("[") and arg.endswith("]"):
        arg = arg[1:-1]
    parts = [p.strip() for p in arg.split(",")]
    return parts if parts and all(parts) else None


def _guard_arg_error(name: str, arg: str | None, m: Manifest) -> str | None:
    """Trả lý do nếu tham số của guard sai (mục 9.3); ``None`` nếu hợp lệ."""
    if name in _NO_ARG_GUARDS:
        return None if arg is None else "guard này không có tham số"
    if name == "not_same_actor":
        if arg is None:
            return "thiếu tham số: creator hoặc tên task"
        if arg != "creator" and arg not in m.workflow.tasks:
            return f"tham số phải là 'creator' hoặc một task của workflow, không phải {arg!r}"
    elif name == "field_required":
        if arg is None:
            return "thiếu tham số: tên trường"
        if not any(arg in col.fields for col in m.collections.values()):
            return f"trường {arg!r} không thuộc collection nào"
    elif name == "role_in":
        roles = parse_role_list(arg) if arg is not None else None
        if roles is None:
            return "thiếu hoặc sai danh sách role: role_in:r1,r2"
        for r in roles:
            if r not in m.roles:
                return f"role chưa khai báo: {r!r}"
    return None


def _check_guards(m: Manifest) -> None:
    if m.workflow is None:
        return
    for task, spec in m.workflow.tasks.items():
        for i, g in enumerate(spec.guards):
            path = f"/workflow/tasks/{task}/guards/{i}"
            name, arg = split_guard(g)
            if name not in GUARD_CATALOG:
                raise ManifestError("UNKNOWN_GUARD", path, f"guard {g!r} không thuộc danh mục chung")
            why = _guard_arg_error(name, arg, m)
            if why:
                raise ManifestError("UNKNOWN_GUARD", path, f"guard {g!r}: {why}")


def _check_sequence(cname: str, fname: str, f) -> None:
    base = f"/collections/{cname}/fields/{fname}"
    if f.reset != "never" and f.type != "sequence":
        raise ManifestError("SCHEMA_INVALID", f"{base}/reset", "reset chỉ dùng cho trường type: sequence")
    if f.type != "sequence":
        return
    fmt = f.format or ""
    rest = _SEQ_TOKEN.sub("", fmt)
    if len(_SEQ_TOKEN.findall(fmt)) != 1 or "{" in rest or "}" in rest:
        raise ManifestError("SCHEMA_INVALID", f"{base}/format",
                            "format của sequence phải chứa đúng một token {n} hoặc {n:0W} (W từ 2 đến 9)")


def _check_references(m: Manifest) -> None:
    roles = set(m.roles)
    for cname, col in m.collections.items():
        for fname, f in col.fields.items():
            if f.pii and f.type != "string":       # lõi chỉ che được chuỗi (masking.py)
                raise ManifestError("SCHEMA_INVALID", f"/collections/{cname}/fields/{fname}/pii",
                                    "pii chỉ dùng cho trường type: string")
            if f.pii and f.public:                 # trường công khai thì không thể vừa là PII
                raise ManifestError("SCHEMA_INVALID", f"/collections/{cname}/fields/{fname}/public",
                                    "trường pii không được đặt public: true")
            _check_sequence(cname, fname, f)
        for action in ("read", "create", "update"):
            for i, entry in enumerate(getattr(col.access, action)):
                if entry.startswith("role:") and entry[5:] not in roles:
                    raise ManifestError("SCHEMA_INVALID", f"/collections/{cname}/access/{action}/{i}",
                                        f"role chưa khai báo: {entry[5:]!r}")
    for i, r in enumerate(m.policies.pii.reveal_roles):
        if r not in roles:
            raise ManifestError("SCHEMA_INVALID", f"/policies/pii/reveal_roles/{i}",
                                f"role chưa khai báo: {r!r}")
    for i, r in enumerate(m.policies.pii.erase_roles):
        if r not in roles:
            raise ManifestError("SCHEMA_INVALID", f"/policies/pii/erase_roles/{i}",
                                f"role chưa khai báo: {r!r}")
    if m.workflow is not None:
        for task, spec in m.workflow.tasks.items():
            if task == "creator":              # "creator" là tham số đặc biệt của not_same_actor
                raise ManifestError("SCHEMA_INVALID", f"/workflow/tasks/{task}",
                                    "tên task không được là 'creator' (trùng tham số của not_same_actor)")
            if spec.role not in roles:
                raise ManifestError("SCHEMA_INVALID", f"/workflow/tasks/{task}/role",
                                    f"role chưa khai báo: {spec.role!r}")
    if m.policies.seal is not None:
        if m.workflow is None:
            raise ManifestError("SCHEMA_INVALID", "/policies/seal",
                                "khai policies.seal thì bắt buộc khai workflow")
        if not _ON_EVENT.fullmatch(m.policies.seal.on_event):
            raise ManifestError("SCHEMA_INVALID", "/policies/seal/on_event",
                                "on_event phải có dạng process.completed:<id end event>")
        for i, r in enumerate(m.policies.seal.revoke_roles):
            if r not in roles:
                raise ManifestError("SCHEMA_INVALID", f"/policies/seal/revoke_roles/{i}",
                                    f"role chưa khai báo: {r!r}")
        public = {f for col in m.collections.values() for f, spec in col.fields.items() if spec.public}
        for i, f in enumerate(m.policies.seal.public_fields):
            if f not in public:
                raise ManifestError("SCHEMA_INVALID", f"/policies/seal/public_fields/{i}",
                                    f"trường {f!r} không có cờ public: true")


def validate_manifest(doc: dict) -> Manifest:
    if not isinstance(doc, dict):
        raise ManifestError("SCHEMA_INVALID", "", "manifest phải là một object")
    _check_floor(doc, [])
    _check_namespace(doc)
    _check_schema(doc)
    try:
        m = Manifest.model_validate(doc)
    except ValidationError as exc:  # schema đã chặn trước; phòng hờ hai bên lệch nhau
        raise ManifestError("SCHEMA_INVALID", "", str(exc)) from exc
    _check_guards(m)
    _check_references(m)
    return m
