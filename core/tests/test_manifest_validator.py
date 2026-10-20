# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test validator manifest: schema, namespace, chính sách sàn, guard (Plan 01 Task 11, AT-11, AT-12)."""

import copy
from pathlib import Path

import pytest
import yaml
from dxos_core.registry.validator import GUARD_CATALOG, ManifestError, validate_manifest

ROOT = Path(__file__).resolve().parents[2]
PATHS = {
    "phong-ho-so": ROOT / "apps/phong-ho-so/manifest.yaml",
    "chung-nhan": ROOT / "apps/chung-nhan/manifest.yaml",
    "test-app": ROOT / "core/tests/fixtures/manifest-test-app.yaml",
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

@pytest.mark.parametrize("path", ["apps/phong-ho-so/manifest.yaml", "apps/chung-nhan/manifest.yaml",
                                  "core/tests/fixtures/manifest-test-app.yaml"])
def test_shipped_manifests_valid(path):
    assert validate_manifest(load_yaml(path)).app.id


def test_floor_weakened():                                                       # AT-11
    doc = load("phong-ho-so")
    doc["collections"]["van_ban"]["attachments"]["quarantine"] = "optional"
    assert raises_code(doc) == "FLOOR_WEAKENED"


def test_unknown_guard():                                                        # AT-11
    doc = load("phong-ho-so")
    doc["workflow"]["tasks"]["ban_hanh"]["guards"].append("skip_scan")
    assert raises_code(doc) == "UNKNOWN_GUARD"


@pytest.mark.parametrize("mutate", [
    lambda d: d["roles"].append("app:chung-nhan:truong_clb"),
    lambda d: d["collections"].__setitem__("x:y", {"fields": {}, "access": {"read": [], "create": []}}),
])
def test_namespace_violation(mutate):                                            # AT-12
    doc = load("phong-ho-so")
    mutate(doc)
    assert raises_code(doc) == "NAMESPACE_VIOLATION"


def test_reveal_role_must_be_declared():
    doc = load("phong-ho-so")
    doc["policies"]["pii"]["reveal_roles"] = ["ghost"]
    assert raises_code(doc) == "SCHEMA_INVALID"


# ---------- Bổ sung ----------

def test_parsed_model_fields():
    m = validate_manifest(load("phong-ho-so"))
    vb = m.collections["van_ban"]
    assert m.app.version == "1.0.0"
    assert m.roles == ["chuyen_vien", "truong_phong", "giam_doc", "van_thu", "nhan_vien"]
    assert vb.fields["so_hieu"].type == "sequence" and vb.fields["so_hieu"].format == "{n}/QĐ-SM"
    assert vb.fields["nguoi_lien_he_cccd"].pii == "CCCD"
    assert vb.attachments.max_mb == 15 and vb.attachments.min == 1 and vb.access.update == ["owner"]
    assert m.policies.pii.reveal_roles == ["giam_doc", "van_thu"]
    guards = m.workflow.tasks["ban_hanh"].guards
    assert guards == ["attachments_clean", "pii_reviewed", "not_same_actor:creator"]
    assert validate_manifest(load("test-app")).workflow is None


def test_quarantine_required_is_allowed():
    doc = load("phong-ho-so")
    doc["collections"]["van_ban"]["attachments"]["quarantine"] = "required"
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


@pytest.mark.parametrize("role", ["application", "app_admin", "a:b", "Admin", "1x"])
def test_role_namespace_or_format(role):
    doc = load("test-app")
    doc["roles"].append(role)
    expected = "NAMESPACE_VIOLATION" if (":" in role or role.startswith("app")) else "SCHEMA_INVALID"
    assert raises_code(doc) == expected


@pytest.mark.parametrize("entry", ["role:ghost", "everyone", "role:", "owner:x"])
def test_access_entries(entry):
    doc = load("test-app")
    doc["collections"]["item"]["access"]["read"].append(entry)
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_task_role_must_be_declared():
    doc = load("phong-ho-so")
    doc["workflow"]["tasks"]["ban_hanh"]["role"] = "ghost"
    assert raises_code(doc) == "SCHEMA_INVALID"


def test_guard_with_argument_known_name_ok_and_catalog_is_exact():
    assert GUARD_CATALOG == frozenset({"attachments_clean", "pii_reviewed", "not_same_actor", "role_in",
                                       "field_required", "record_not_sealed", "assignee_is_caller"})
    doc = load("phong-ho-so")
    doc["workflow"]["tasks"]["ban_hanh"]["guards"].append("field_required:trich_yeu")
    validate_manifest(doc)


def test_public_fields_must_be_public():
    doc = load("phong-ho-so")
    doc["policies"]["seal"]["public_fields"].append("nguoi_lien_he_cccd")
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
    src = ROOT / "core/src"
    offenders = [p for p in src.rglob("*.py") if any(n in p.read_text(encoding="utf-8")
                                                     for n in ("phong-ho-so", "chung-nhan", "phong_ho_so"))]
    assert offenders == []
