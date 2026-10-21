# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test validator manifest: schema, namespace, chính sách sàn, guard (Plan 01 Task 11, AT-11, AT-12)."""

import copy
import re
from pathlib import Path
from typing import get_args

import pytest
import yaml
from dxos_core.registry.validator import GUARD_CATALOG, ErrorCode, ManifestError, validate_manifest

ROOT = Path(__file__).resolve().parents[2]
PATHS = {
    "test-app": ROOT / "core/tests/fixtures/manifest-test-app.yaml",
    "test-flow": ROOT / "core/tests/fixtures/manifest-test-flow.yaml",
}


def load_yaml(path) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def load(name: str) -> dict:
    return copy.deepcopy(yaml.safe_load(PATHS[name].read_text(encoding="utf-8")))


def raises_code(doc: dict) -> str:
    with pytest.raises(ManifestError) as e:
        validate_manifest(doc)
    return e.value.code


# ---------- Các test do Plan 01 Task 11 quy định ----------

@pytest.mark.parametrize("path", ["core/tests/fixtures/manifest-test-app.yaml",
                                  "core/tests/fixtures/manifest-test-flow.yaml"])
def test_fixture_manifests_valid(path):          # manifest App A/B: xem tests/apps/test_app_manifests.py
    assert validate_manifest(load_yaml(path)).app.id


def test_floor_weakened():                                                       # AT-11
    doc = load("test-flow")
    doc["collections"]["doc"]["attachments"]["quarantine"] = "optional"
    assert raises_code(doc) == "FLOOR_WEAKENED"


def test_unknown_guard():                                                        # AT-11
    doc = load("test-flow")
    doc["workflow"]["tasks"]["approve"]["guards"].append("skip_scan")
    assert raises_code(doc) == "UNKNOWN_GUARD"


@pytest.mark.parametrize("mutate", [
    lambda d: d["roles"].append("app:test-app:reviewer"),
    lambda d: d["collections"].__setitem__("x:y", {"fields": {}, "access": {"read": [], "create": []}}),
])
def test_namespace_violation(mutate):                                            # AT-12
    doc = load("test-flow")
    mutate(doc)
    assert raises_code(doc) == "NAMESPACE_VIOLATION"


def test_reveal_role_must_be_declared():
    doc = load("test-flow")
    doc["policies"]["pii"]["reveal_roles"] = ["ghost"]
    assert raises_code(doc) == "SCHEMA_INVALID"


# ---------- Bổ sung ----------

def test_parsed_model_fields():
    m = validate_manifest(load("test-flow"))
    vb = m.collections["doc"]
    assert m.app.version == "0.1.0"
    assert m.roles == ["author", "reviewer", "approver"]
    assert vb.fields["ref"].type == "sequence" and vb.fields["ref"].format == "{n:02}/TF"
    assert vb.fields["cccd"].pii == "CCCD"
    assert vb.attachments.max_mb == 1 and vb.attachments.min == 1 and vb.access.update == ["owner"]
    assert m.policies.pii.reveal_roles == ["approver"]
    guards = m.workflow.tasks["approve"].guards
    assert guards == ["attachments_clean", "pii_reviewed", "not_same_actor:creator", "not_same_actor:review"]
    assert validate_manifest(load("test-app")).workflow is None


def test_quarantine_required_is_allowed():
    doc = load("test-flow")
    doc["collections"]["doc"]["attachments"]["quarantine"] = "required"
    validate_manifest(doc)


def test_floor_weakened_anywhere_and_reports_path():
    doc = load("test-app")
    doc["policies"]["quarantine"] = False
    with pytest.raises(ManifestError) as e:
        validate_manifest(doc)
    assert e.value.code == "FLOOR_WEAKENED" and e.value.path == "/policies/quarantine"


@pytest.mark.parametrize("bad_id", ["A", "a", "1abc", "abc_def", "a" * 32, "x:y"])
def test_app_id_format(bad_id):
    doc = load("test-app")
    doc["app"]["id"] = bad_id
    assert raises_code(doc) in ("SCHEMA_INVALID", "NAMESPACE_VIOLATION")


@pytest.mark.parametrize("role", ["app", "app_admin", "a:b", "Admin", "1x"])
def test_role_namespace_or_format(role):
    doc = load("test-app")
    doc["roles"].append(role)
    reserved = ":" in role or role == "app" or role.startswith("app_")
    expected = "NAMESPACE_VIOLATION" if reserved else "SCHEMA_INVALID"
    assert raises_code(doc) == expected


@pytest.mark.parametrize("name", ["approver", "application", "apps"])
def test_names_merely_starting_with_app_are_allowed(name):        # "approver" là role của manifest test-flow
    doc = load("test-app")
    doc["roles"].append(name)
    doc["collections"][name] = {"fields": {}, "access": {"read": ["owner"], "create": [f"role:{name}"]}}
    assert validate_manifest(doc).roles[-1] == name


@pytest.mark.parametrize("entry", ["role:ghost", "everyone", "role:", "owner:x"])
def test_access_entries(entry):
    doc = load("test-app")
    doc["collections"]["item"]["access"]["read"].append(entry)
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_task_role_must_be_declared():
    doc = load("test-flow")
    doc["workflow"]["tasks"]["approve"]["role"] = "ghost"
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_guard_with_argument_known_name_ok_and_catalog_is_exact():
    assert GUARD_CATALOG == frozenset({"attachments_clean", "pii_reviewed", "not_same_actor", "role_in",
                                       "field_required", "record_not_sealed", "assignee_is_caller"})
    doc = load("test-flow")
    doc["workflow"]["tasks"]["approve"]["guards"].append("field_required:title")
    validate_manifest(doc)


def test_public_fields_must_be_public():
    doc = load("test-flow")
    doc["policies"]["seal"]["public_fields"].append("cccd")
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("mutate", [
    lambda d: d.__setitem__("unexpected", 1),
    lambda d: d["collections"]["item"]["fields"]["title"].__setitem__("type", "float"),
    lambda d: d["collections"]["item"]["fields"]["title"].__setitem__("pii", "PASSPORT"),
    lambda d: d.__setitem__("apiVersion", "dxos/v2"),
    lambda d: d["collections"]["item"]["attachments"].__setitem__("kinds", ["exe"]),
    lambda d: d.pop("roles"),
])
def test_schema_invalid(mutate):
    doc = load("test-app")
    mutate(doc)
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_error_is_value_error_with_path():
    doc = load("test-app")
    doc["roles"].append("app:x:y")
    with pytest.raises(ValueError) as e:
        validate_manifest(doc)
    assert e.value.path == "/roles/2"


def test_core_never_names_tier2_apps():                                          # I3 (AT-14, phần tĩnh)
    """Mã phát hành của lõi không chứa định danh nào của mọi ``apps/*/manifest.yaml``: app id (gạch nối và
    gạch dưới), tên collection, tên role. ``core/tests`` không nằm trong image nên không quét."""
    idents: set[str] = set()
    manifests = list((ROOT / "apps").glob("*/manifest.yaml"))
    for f in manifests:
        m = yaml.safe_load(f.read_text(encoding="utf-8"))
        idents |= {m["app"]["id"], m["app"]["id"].replace("-", "_"), *m["collections"], *m["roles"]}
    files = [p for d in ("src", "migrations", "docker") for p in (ROOT / "core" / d).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    files += [ROOT / "core/Dockerfile", ROOT / "core/pyproject.toml"]
    assert len(manifests) >= 2 and len(files) > 20           # chống test rỗng
    offenders = sorted({(p.relative_to(ROOT).as_posix(), i) for p in files for i in idents
                        if re.search(rf"\b{re.escape(i)}\b", p.read_text(encoding="utf-8", errors="ignore"))})
    assert offenders == []


@pytest.mark.parametrize("ftype", ["integer", "date", "boolean", "sequence"])
def test_pii_only_on_string_fields(ftype):                                         # rà soát #4
    doc = load("test-app")
    doc["collections"]["item"]["fields"]["so"] = {"type": ftype, "pii": "CCCD"}
    assert raises_code(doc) == "SCHEMA_INVALID"


# ---------- Plan 02 Task 1: manifest 1.0.3 (cộng thêm) ----------

def test_test_flow_fixture_is_valid_and_parsed():
    m = validate_manifest(load("test-flow"))
    doc = m.collections["doc"]
    assert m.app.id == "test-flow" and m.roles == ["author", "reviewer", "approver"]
    assert doc.fields["ref"].type == "sequence" and doc.fields["ref"].reset == "yearly"
    assert doc.fields["title"].label == "Tiêu đề" and doc.fields["cccd"].pii == "CCCD"
    assert doc.attachments.min == 1 and doc.attachments.max_mb == 1
    assert m.policies.seal.revoke_roles == ["approver"] and m.policies.pii.erase_roles == ["approver"]
    assert m.workflow.bpmn == "bpmn/test-review.bpmn"
    assert m.workflow.tasks["approve"].guards == [
        "attachments_clean", "pii_reviewed", "not_same_actor:creator", "not_same_actor:review"]


def test_pii_field_cannot_be_public():
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["cccd"]["public"] = True
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("ev", ["approved", "process.completed:", "process.completed:a b", "x:approved",
                                "process.completed:1abc", "process.completed:" + "a" * 65,
                                "process.completed:approved\n"])
def test_seal_on_event_format(ev):
    doc = load("test-flow")
    doc["policies"]["seal"]["on_event"] = ev
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("ev", ["process.completed:approved", "process.completed:Approved-1",
                                "process.completed:_end", "process.completed:" + "a" * 64])
def test_seal_on_event_accepts_valid_end_event_ids(ev):
    doc = load("test-flow")
    doc["policies"]["seal"]["on_event"] = ev
    assert validate_manifest(doc).policies.seal.on_event == ev


def test_seal_requires_workflow():
    doc = load("test-flow")
    del doc["workflow"]
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_revoke_roles_must_be_declared():
    doc = load("test-flow")
    doc["policies"]["seal"]["revoke_roles"] = ["ghost"]
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("bad", [["approver", "approver"], ["Bad-Role"], "approver"])
def test_revoke_roles_shape_checked_by_schema(bad):
    doc = load("test-flow")
    doc["policies"]["seal"]["revoke_roles"] = bad
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("name", ["creator", "Bad-Name", "1x", "a" * 32])
def test_task_name_checked(name):
    doc = load("test-flow")
    doc["workflow"]["tasks"][name] = {"role": "reviewer"}
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("guard", ["not_same_actor:nope", "not_same_actor", "field_required:missing",
                                   "role_in:ghost", "role_in:", "role_in", "field_required",
                                   "attachments_clean:x", "record_not_sealed:1", "pii_reviewed:x",
                                   "assignee_is_caller:me"])
def test_guard_arguments_checked(guard):
    doc = load("test-flow")
    doc["workflow"]["tasks"]["review"]["guards"].append(guard)
    assert raises_code(doc) == "UNKNOWN_GUARD"


@pytest.mark.parametrize("guard", ["not_same_actor:review", "not_same_actor:creator",
                                   "role_in:reviewer,approver", "role_in:[reviewer]",
                                   "role_in:[reviewer,approver]", "field_required:title",
                                   "record_not_sealed", "assignee_is_caller"])
def test_guard_arguments_accepted(guard):
    doc = load("test-flow")
    doc["workflow"]["tasks"]["approve"]["guards"].append(guard)
    validate_manifest(doc)


def test_revoke_roles_default_empty():
    doc = load("test-app")
    assert validate_manifest(doc).policies.seal is None
    doc = load("test-flow")
    del doc["policies"]["seal"]["revoke_roles"]
    assert validate_manifest(doc).policies.seal.revoke_roles == []


def test_erase_roles_must_be_declared():
    doc = load("test-flow")
    doc["policies"]["pii"]["erase_roles"] = ["ghost"]
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_erase_roles_default_empty():
    doc = load("test-flow")
    del doc["policies"]["pii"]["erase_roles"]
    assert validate_manifest(doc).policies.pii.erase_roles == []


@pytest.mark.parametrize("label", ["", "x" * 65, "a\nb", "ab\n", "a\tb", "a\x00b"])
def test_bad_label_rejected(label):
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["title"]["label"] = label
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_label_max_length_accepted():
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["title"]["label"] = "x" * 64
    assert validate_manifest(doc).collections["doc"].fields["title"].label == "x" * 64


@pytest.mark.parametrize("fmt", ["no-token", "{n}/{n}", "{n:01}", "{n:010}", "{n:2}", "{n}/{n:02}", "{N}",
                                 "{n}}", "{n}/{x}", ""])
def test_bad_sequence_format_rejected(fmt):
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["ref"]["format"] = fmt
    assert raises_code(doc) == "SCHEMA_INVALID"


@pytest.mark.parametrize("fmt", ["{n}/QĐ-SM", "{n:02}/TF", "{n:09}", "TF-{n:05}-X"])
def test_good_sequence_format_accepted(fmt):
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["ref"]["format"] = fmt
    validate_manifest(doc)


def test_sequence_without_format_rejected():
    doc = load("test-flow")
    del doc["collections"]["doc"]["fields"]["ref"]["format"]
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_reset_only_on_sequence():
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["title"]["reset"] = "yearly"
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_reset_value_checked_and_defaults_never():
    doc = load("test-flow")
    doc["collections"]["doc"]["fields"]["ref"]["reset"] = "monthly"
    assert raises_code(doc) == "SCHEMA_INVALID"
    doc = load("test-flow")
    del doc["collections"]["doc"]["fields"]["ref"]["reset"]
    assert validate_manifest(doc).collections["doc"].fields["ref"].reset == "never"


def test_error_codes_include_plan02_codes():          # BPMN_INVALID: Task 3; UPGRADE_NOT_ADDITIVE: Task 12
    assert {"BPMN_INVALID", "UPGRADE_NOT_ADDITIVE"} <= set(get_args(ErrorCode))
