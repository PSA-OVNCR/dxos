# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Phần manifest được phép đưa cho client Tầng 2 (``GET /api/v1/apps/{app}/manifest``).

Dựng từng khóa một, KHÔNG ``model_dump()`` cả manifest: khóa mới thêm vào model sau này mặc định không ra
khỏi lõi cho tới khi có người quyết định đưa vào đây. Cố ý không có: đường dẫn BPMN, ``spaces``,
``policies.pii.document_detect``, ``policies.seal.on_event``/``target``, ``attachments.quarantine``,
``fields.<f>.reset``.
"""

from collections.abc import Mapping

from dxos_core.registry.model import AttachmentSpec, CollectionSpec, FieldSpec, Manifest


def _field(f: FieldSpec) -> dict:
    return {"type": f.type, "required": f.required, "public": f.public, "pii": f.pii, "format": f.format,
            "label": f.label}


def _attachments(a: AttachmentSpec | None) -> dict | None:
    return None if a is None else {"kinds": list(a.kinds), "max_mb": a.max_mb, "min": a.min}


def _collection(c: CollectionSpec) -> dict:
    return {
        "fields": {name: _field(f) for name, f in c.fields.items()},
        "attachments": _attachments(c.attachments),
        "access": {"read": list(c.access.read), "create": list(c.access.create),
                   "update": list(c.access.update)},
    }


def client_view(m: Manifest, decisions: Mapping[str, list[str]] | None) -> dict:
    """``decisions``: task → giá trị ``decision`` mà cổng sau task chấp nhận (từ BPMN đã triển khai của đúng
    phiên bản ``m``); ``None`` khi bên gọi không có quy trình để hỏi."""
    wf = m.workflow
    seal, verify = m.policies.seal, m.policies.verify
    return {
        "app": {"id": m.app.id, "version": m.app.version, "name": m.app.name},
        "roles": list(m.roles),
        "collections": {name: _collection(c) for name, c in m.collections.items()},
        "workflow": None if wf is None else {
            "tasks": {key: {"role": t.role, "guards": list(t.guards)} for key, t in wf.tasks.items()},
            "decisions": {key: list(vals) for key, vals in (decisions or {}).items()},
        },
        "policies": {
            "pii": {"reveal_roles": list(m.policies.pii.reveal_roles),
                    "erase_roles": list(m.policies.pii.erase_roles)},
            "seal": None if seal is None else {"public_fields": list(seal.public_fields),
                                                "revoke_roles": list(seal.revoke_roles)},
            "verify": None if verify is None else {"public": verify.public,
                                                    "require_file": verify.require_file},
        },
    }
