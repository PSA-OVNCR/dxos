# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Luật nâng phiên bản app (P2-D14, spec 9.5, 25.4; Plan 02 Task 12)."""

import pytest
from dxos_core.registry.upgrade import check_upgrade
from dxos_core.registry.validator import ManifestError, validate_manifest
from helpers.manifests import load, mutate


@pytest.mark.parametrize(
    "change",
    [
        "drop_field",
        "change_type",
        "drop_role",
        "drop_collection",
        "new_required_field",
        "drop_task_guard",
        "widen_reveal_roles",
        "widen_revoke_roles",
        "change_seal",
        "change_verify",
    ],
)
def test_upgrade_must_be_additive(change):  # Review Focus 5
    old = validate_manifest(load("test-flow"))
    new = mutate(load("test-flow"), change, version="0.2.0")
    with pytest.raises(ManifestError) as e:
        check_upgrade(old, validate_manifest(new), sealed_before=True)
    assert e.value.code == "UPGRADE_NOT_ADDITIVE"


def test_upgrade_adding_optional_field_and_role_ok():
    check_upgrade(
        validate_manifest(load("test-flow")),
        validate_manifest(mutate(load("test-flow"), "add_optional", version="0.2.0")),
        sealed_before=True,
    )


@pytest.mark.parametrize("change", ["change_seal", "change_verify", "widen_revoke_roles"])  # P2-D14 ngoại lệ
def test_seal_policy_may_change_before_any_seal(change):
    old = validate_manifest(load("test-flow"))
    new = validate_manifest(mutate(load("test-flow"), change, version="0.2.0"))
    check_upgrade(old, new, sealed_before=False)


def test_erase_roles_may_change_after_seals():
    old = validate_manifest(load("test-flow"))
    new = validate_manifest(mutate(load("test-flow"), "widen_erase_roles", version="0.2.0"))
    check_upgrade(old, new, sealed_before=True)


def test_label_change_is_allowed():
    old = validate_manifest(load("test-flow"))
    new = validate_manifest(mutate(load("test-flow"), "change_label", version="0.2.0"))
    check_upgrade(old, new, sealed_before=True)


def test_sequence_format_and_reset_change_freely():  # spec 25.4
    old = validate_manifest(load("test-flow"))
    new = validate_manifest(mutate(load("test-flow"), "change_sequence", version="0.2.0"))
    check_upgrade(old, new, sealed_before=True)


@pytest.mark.parametrize(
    "change",
    [
        "drop_field",
        "change_type",
        "drop_role",
        "drop_collection",
        "new_required_field",
        "drop_task_guard",
        "widen_reveal_roles",
    ],
)
def test_non_seal_rules_hold_even_before_any_seal(change):
    old = validate_manifest(load("test-flow"))
    with pytest.raises(ManifestError) as e:
        check_upgrade(
            old, validate_manifest(mutate(load("test-flow"), change, version="0.2.0")), sealed_before=False
        )
    assert e.value.code == "UPGRADE_NOT_ADDITIVE"


def test_error_path_points_at_the_change():
    old = validate_manifest(load("test-flow"))
    with pytest.raises(ManifestError) as e:
        check_upgrade(
            old,
            validate_manifest(mutate(load("test-flow"), "change_type", version="0.2.0")),
            sealed_before=True,
        )
    assert e.value.path == "/collections/doc/fields/title/type"


def test_task_role_change_and_task_drop_rejected():
    old = validate_manifest(load("test-flow"))
    doc = mutate(load("test-flow"), "none", version="0.2.0")
    doc["workflow"]["tasks"]["review"]["role"] = "approver"
    with pytest.raises(ManifestError) as e:
        check_upgrade(old, validate_manifest(doc), sealed_before=True)
    assert e.value.path == "/workflow/tasks/review/role"


def test_optional_field_becoming_required_rejected():
    old = validate_manifest(load("test-flow"))
    doc = mutate(load("test-flow"), "none", version="0.2.0")
    doc["collections"]["doc"]["fields"]["cccd"]["required"] = True
    with pytest.raises(ManifestError) as e:
        check_upgrade(old, validate_manifest(doc), sealed_before=True)
    assert e.value.code == "UPGRADE_NOT_ADDITIVE"


def test_pii_flag_cannot_be_removed_but_may_be_added():
    old = validate_manifest(load("test-flow"))
    doc = mutate(load("test-flow"), "none", version="0.2.0")
    del doc["collections"]["doc"]["fields"]["cccd"]["pii"]
    with pytest.raises(ManifestError):
        check_upgrade(old, validate_manifest(doc), sealed_before=False)
    doc = mutate(load("test-flow"), "add_optional", version="0.2.0")
    doc["collections"]["doc"]["fields"]["note"]["pii"] = "PHONE"
    check_upgrade(old, validate_manifest(doc), sealed_before=True)


def test_new_collection_may_have_required_fields():
    old = validate_manifest(load("test-flow"))
    doc = mutate(load("test-flow"), "none", version="0.2.0")
    doc["collections"]["extra"] = {
        "fields": {"x": {"type": "string", "required": True}},
        "access": {"read": ["owner"], "create": ["role:author"]},
    }
    check_upgrade(old, validate_manifest(doc), sealed_before=True)
