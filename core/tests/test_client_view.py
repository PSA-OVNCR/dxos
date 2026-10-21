# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Phần thuần của ``GET /api/v1/apps/{app}/manifest`` (Plan 03 Task 1): chỉ khóa an toàn đi ra client."""

import json

from dxos_core.registry.client_view import client_view
from helpers.manifests import manifest

FIELD_KEYS = {"type", "required", "public", "pii", "format", "label"}


def test_client_view_exposes_only_safe_keys():
    v = client_view(manifest("test-flow"), {"review": ["approve", "reject"]})
    assert set(v) == {"app", "roles", "collections", "workflow", "policies"}
    text = json.dumps(v)
    hidden = ("bpmn", "document_detect", "on_event", "target", "apiVersion", "spaces", "reset", "quarantine")
    assert not [k for k in hidden if k in text]
    col = v["collections"]["doc"]
    assert set(col) == {"fields", "attachments", "access"}
    assert set(next(iter(col["fields"].values()))) == FIELD_KEYS
    assert v["workflow"]["decisions"] == {"review": ["approve", "reject"]}


def test_client_view_values_follow_the_manifest():
    v = client_view(manifest("test-flow"), {"review": ["approve", "reject"]})
    assert v["app"] == {"id": "test-flow", "version": "0.1.0", "name": "Test flow"}
    assert v["roles"] == ["author", "reviewer", "approver"]
    title = v["collections"]["doc"]["fields"]["title"]
    assert title == {"type": "string", "required": True, "public": True, "pii": None, "format": None,
                     "label": "Tiêu đề"}
    assert v["collections"]["doc"]["fields"]["cccd"]["pii"] == "CCCD"
    assert v["collections"]["doc"]["fields"]["ref"]["format"] == "{n:02}/TF"
    assert v["collections"]["doc"]["attachments"] == {"kinds": ["pdf"], "max_mb": 1, "min": 1}
    assert v["collections"]["doc"]["access"] == {
        "read": ["owner", "role:reviewer", "role:approver"], "create": ["role:author"], "update": ["owner"]}
    assert v["workflow"]["tasks"]["review"] == {"role": "reviewer",
                                                "guards": ["attachments_clean", "not_same_actor:creator"]}
    assert v["policies"] == {
        "pii": {"reveal_roles": ["approver"], "erase_roles": ["approver"]},
        "seal": {"public_fields": ["ref", "title"], "revoke_roles": ["approver"]},
        "verify": {"public": True, "require_file": True}}


def test_client_view_without_workflow():
    v = client_view(manifest("test-app"), None)
    assert v["workflow"] is None
    assert v["policies"]["seal"] is None and v["policies"]["verify"] is None
    assert v["collections"]["item"]["fields"]["secret_code"]["pii"] == "CCCD"


def test_client_view_returns_plain_copies():
    decisions = {"review": ["approve"]}
    v = client_view(manifest("test-flow"), decisions)
    decisions["review"].append("x")
    assert v["workflow"]["decisions"] == {"review": ["approve"]}
