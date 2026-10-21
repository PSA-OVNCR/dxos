# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test PDP (Plan 01 Task 12): vai trò theo app (RF3), admin không mặc nhiên đọc dữ liệu (D4)."""

import pytest
from dxos_core.policy.pdp import Decision, decide
from helpers.manifests import P, manifest


@pytest.fixture(scope="module")
def m_test():
    return manifest("test-app")


@pytest.fixture(scope="module")
def m_flow():
    return manifest("test-flow")


# ---------- Các test do Plan 01 Task 12 quy định ----------

def test_owner_can_read(m_test):
    assert decide(P("owner_a1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1").allow


def test_non_owner_member_denied(m_test):
    assert decide(P("owner_b1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1") == \
        Decision(False, "not_in_access_list")


def test_role_from_other_app_denied(m_flow):                                        # RF3
    assert decide(P("u", ["app:test-app:reviewer"]), "read", m_flow, "doc", "x") == \
        Decision(False, "no_app_role")


def test_admin_has_no_implicit_data_access(m_test):                              # D4
    assert decide(P("admin1", ["dxos-admin"], admin=True), "read", m_test, "item", "x") == \
        Decision(False, "admin_no_data_access")


def test_reveal_only_reveal_roles(m_test):
    assert decide(P("r", ["app:test-app:reviewer"]), "reveal_pii", m_test, "item", "x").allow
    assert not decide(P("owner_a1", ["app:test-app:member"]), "reveal_pii", m_test, "item", "owner_a1").allow


# ---------- Bổ sung ----------

def test_role_grant_reason(m_test):
    assert decide(P("r", ["app:test-app:reviewer"]), "read", m_test, "item", "someone") == \
        Decision(True, "role:reviewer")


def test_role_wins_over_owner_for_list(m_test):
    # reviewer xem được mọi bản ghi; reason "owner" nghĩa là chỉ thấy bản ghi của mình
    assert decide(P("r", ["app:test-app:reviewer", "app:test-app:member"]), "list", m_test, "item", None) == \
        Decision(True, "role:reviewer")
    assert decide(P("m", ["app:test-app:member"]), "list", m_test, "item", None) == Decision(True, "owner")


def test_create_and_update_lists(m_test):
    member, reviewer = P("m", ["app:test-app:member"]), P("r", ["app:test-app:reviewer"])
    assert decide(member, "create", m_test, "item", None) == Decision(True, "role:member")
    assert decide(reviewer, "create", m_test, "item", None) == Decision(False, "not_in_access_list")
    assert decide(member, "update", m_test, "item", "m") == Decision(True, "owner")
    assert decide(reviewer, "update", m_test, "item", "m") == Decision(False, "not_in_access_list")


def test_owner_entry_never_matches_unknown_owner(m_test):
    assert not decide(P("m", ["app:test-app:member"]), "read", m_test, "item", None).allow


def test_admin_with_app_role_is_treated_like_that_role(m_test):
    p = P("a", ["dxos-admin", "app:test-app:reviewer"], admin=True)
    assert decide(p, "read", m_test, "item", "x") == Decision(True, "role:reviewer")


def test_unknown_collection_denied(m_test):
    assert decide(P("m", ["app:test-app:member"]), "read", m_test, "khong_co", "m") == \
        Decision(False, "unknown_collection")


def test_role_prefix_of_another_app_id_not_confused(m_test):
    # app id "test-app-2" không được tính là "test-app"
    p = P("m", ["app:test-app-2:reviewer"])
    assert decide(p, "read", m_test, "item", "x") == Decision(False, "no_app_role")


def test_decide_is_pure(m_test):
    p = P("m", ["app:test-app:member"])
    assert decide(p, "read", m_test, "item", "m") == decide(p, "read", m_test, "item", "m")
