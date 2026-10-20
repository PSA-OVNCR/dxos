# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm manifest trước khi cài (spec 9.1–9.3, 9.5; AT-11, AT-12).

Thứ tự kiểm (lỗi đầu tiên thắng):
1. ``FLOOR_WEAKENED``: có khóa ``quarantine`` ở bất kỳ đâu với giá trị khác ``"required"``.
2. ``NAMESPACE_VIOLATION``: tên role/collection (hoặc ``app.id``) chứa ``:``, hoặc role/collection
   bắt đầu bằng ``app``.
3. ``SCHEMA_INVALID``: sai JSON Schema ``manifest.schema.json``.
4. ``UNKNOWN_GUARD``: guard ngoài danh mục chung.
5. ``SCHEMA_INVALID``: tham chiếu sai (role chưa khai báo, ``public_fields`` không có cờ ``public``...).
"""

import json
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

ErrorCode = Literal["SCHEMA_INVALID", "NAMESPACE_VIOLATION", "FLOOR_WEAKENED", "UNKNOWN_GUARD"]


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
    return isinstance(name, str) and (":" in name or name.startswith("app"))


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


def _check_guards(m: Manifest) -> None:
    if m.workflow is None:
        return
    for task, spec in m.workflow.tasks.items():
        for i, g in enumerate(spec.guards):
            if g.split(":", 1)[0] not in GUARD_CATALOG:
                raise ManifestError("UNKNOWN_GUARD", f"/workflow/tasks/{task}/guards/{i}",
                                    f"guard {g!r} không thuộc danh mục chung")


def _check_references(m: Manifest) -> None:
    roles = set(m.roles)
    for cname, col in m.collections.items():
        for fname, f in col.fields.items():
            if f.pii and f.type != "string":       # lõi chỉ che được chuỗi (masking.py)
                raise ManifestError("SCHEMA_INVALID", f"/collections/{cname}/fields/{fname}/pii",
                                    "pii chỉ dùng cho trường type: string")
        for action in ("read", "create", "update"):
            for i, entry in enumerate(getattr(col.access, action)):
                if entry.startswith("role:") and entry[5:] not in roles:
                    raise ManifestError("SCHEMA_INVALID", f"/collections/{cname}/access/{action}/{i}",
                                        f"role chưa khai báo: {entry[5:]!r}")
    for i, r in enumerate(m.policies.pii.reveal_roles):
        if r not in roles:
            raise ManifestError("SCHEMA_INVALID", f"/policies/pii/reveal_roles/{i}",
                                f"role chưa khai báo: {r!r}")
    if m.workflow is not None:
        for task, spec in m.workflow.tasks.items():
            if spec.role not in roles:
                raise ManifestError("SCHEMA_INVALID", f"/workflow/tasks/{task}/role",
                                    f"role chưa khai báo: {spec.role!r}")
    if m.policies.seal is not None:
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
