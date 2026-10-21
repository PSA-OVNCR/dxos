# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Phần thuần của installer (Plan 02 Task 12): luật tệp đi kèm và diff quyền."""

import pytest
from dxos_core.registry.installer import check_files, permission_diff
from dxos_core.registry.validator import ManifestError, validate_manifest
from helpers.flow import BPMN_FILE
from helpers.manifests import load, mutate

XML = BPMN_FILE.read_text(encoding="utf-8")


def test_files_must_be_exactly_the_referenced_ones():
    m = validate_manifest(load("test-flow"))
    assert check_files(m, {"bpmn/test-review.bpmn": XML}) == {"bpmn/test-review.bpmn": XML.encode("utf-8")}


@pytest.mark.parametrize(
    "files",
    [
        {},  # thiếu
        {"bpmn/test-review.bpmn": XML, "bpmn/extra.bpmn": "<x/>"},  # thừa
        {"../bpmn/test-review.bpmn": XML},
        {"/bpmn/test-review.bpmn": XML},
        {"\\bpmn\\test-review.bpmn": XML},
        {"C:bpmn/test-review.bpmn": XML},
        {"bpmn/./test-review.bpmn": XML},
        {"bpmn/test-review.bpmn": 1},  # nội dung không phải chuỗi
        {"bpmn/test-review.bpmn": "x" * (256 * 1024 + 1)},  # quá MAX_BPMN_BYTES
        [],  # không phải object
    ],
)
def test_bad_files_rejected(files):
    m = validate_manifest(load("test-flow"))
    with pytest.raises(ManifestError) as e:
        check_files(m, files)
    assert e.value.code == "SCHEMA_INVALID" and e.value.path.startswith("/files")


def test_app_without_workflow_takes_no_files():
    m = validate_manifest(load("test-app"))
    assert check_files(m, {}) == {}
    with pytest.raises(ManifestError):
        check_files(m, {"bpmn/x.bpmn": "<x/>"})


def test_diff_against_nothing_lists_everything():
    m = validate_manifest(load("test-flow"))
    d = permission_diff(None, m, bpmn_sha256="a" * 64)
    assert d["against"] is None and d["roles_added"] == ["approver", "author", "reviewer"]
    assert d["collections_added"] == ["doc"] and d["fields_added"] == {"doc": ["cccd", "ref", "title"]}
    assert d["access"]["doc"] == {
        "read": ["owner", "role:reviewer", "role:approver"],
        "create": ["role:author"],
        "update": ["owner"],
    }
    assert d["pii_reveal_roles"] == {"old": None, "new": ["approver"]}
    assert d["tasks"]["review"] == {
        "role": "reviewer",
        "guards": ["attachments_clean", "not_same_actor:creator"],
    }
    assert d["seal"]["old"] is None and d["seal"]["new"]["public_fields"] == ["ref", "title"]
    assert d["sequences"] == {
        "doc": {"ref": {"old": None, "new": {"format": "{n:02}/TF", "reset": "yearly"}}}
    }
    assert d["labels"] == {"doc": {"title": {"old": None, "new": "Tiêu đề"}}}
    assert d["bpmn_sha256"] == "a" * 64


def test_diff_against_active_shows_only_changes():
    old = validate_manifest(load("test-flow"))
    new = validate_manifest(mutate(load("test-flow"), "add_optional", version="0.2.0"))
    d = permission_diff(old, new, bpmn_sha256=None)
    assert d["against"] == "0.1.0" and d["roles_added"] == ["observer"] and d["collections_added"] == []
    assert d["fields_added"] == {"doc": ["note"]} and d["access"] == {} and d["tasks"] == {}
    assert d["labels"] == {} and d["sequences"] == {}
    assert d["pii_erase_roles"] == {"old": ["approver"], "new": ["approver"]}
    assert set(d) == {
        "app_id",
        "version",
        "against",
        "roles_added",
        "collections_added",
        "fields_added",
        "access",
        "pii_reveal_roles",
        "pii_erase_roles",
        "seal",
        "verify",
        "tasks",
        "labels",
        "sequences",
        "bpmn_sha256",
    }


def test_diff_shows_changed_guard_label_and_sequence():
    old = validate_manifest(load("test-flow"))
    doc = mutate(load("test-flow"), "change_label", version="0.2.0")
    doc["workflow"]["tasks"]["review"]["guards"].append("pii_reviewed")
    doc["collections"]["doc"]["fields"]["ref"]["reset"] = "never"
    d = permission_diff(old, validate_manifest(doc), bpmn_sha256=None)
    assert d["tasks"] == {
        "review": {
            "role": "reviewer",
            "guards": ["attachments_clean", "not_same_actor:creator", "pii_reviewed"],
        }
    }
    assert d["labels"] == {"doc": {"title": {"old": "Tiêu đề", "new": "Tên hồ sơ"}}}
    assert d["sequences"]["doc"]["ref"] == {
        "old": {"format": "{n:02}/TF", "reset": "yearly"},
        "new": {"format": "{n:02}/TF", "reset": "never"},
    }
