# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Danh mục guard chung (spec 9.3; Plan 02 Task 5): ``evaluate`` là hàm thuần, không I/O."""

from dataclasses import replace

import pytest
from dxos_core.workflow.guards import GuardFailure, GuardInput, evaluate, review_digest

BASE = GuardInput(caller_sub="rev", caller_roles=frozenset({"reviewer"}), owner_sub="author",
                  seal_state="NONE", data={"title": "x"}, task_assignee=None, uploads_pending=0,
                  clean_attachments=("a" * 64,), attachments_min=1, completions=(), pii_required=False,
                  finding_ids=(), last_review_digest=None, data_digest="d" * 64)


def test_creator_cannot_approve_own_record():                                     # AT-07
    f = evaluate(["not_same_actor:creator"], replace(BASE, caller_sub="author"))
    assert (f.guard, f.reason, f.status) == ("not_same_actor:creator", "same_actor", 403)


def test_pending_upload_blocks_with_409():                                        # AT-08
    assert evaluate(["attachments_clean"], replace(BASE, uploads_pending=1)).status == 409
    no_files = replace(BASE, clean_attachments=())
    assert evaluate(["attachments_clean"], no_files).reason == "attachments_not_clean"


def test_previous_step_actor_cannot_do_next_step():
    gi = replace(BASE, completions=(("review", "rev"),))
    assert evaluate(["not_same_actor:review"], gi).reason == "same_actor"


def test_pii_review_must_match_current_data_and_files():
    d = review_digest(BASE.data_digest, BASE.clean_attachments, ())
    ok = replace(BASE, pii_required=True, last_review_digest=d)
    assert evaluate(["pii_reviewed"], ok) is None
    assert evaluate(["pii_reviewed"], replace(ok, clean_attachments=("b" * 64,))).reason == "pii_not_reviewed"
    # có phát hiện mới sau lần xác nhận
    assert evaluate(["pii_reviewed"], replace(ok, finding_ids=(7,))) is not None
    # dữ liệu đổi sau lần xác nhận
    assert evaluate(["pii_reviewed"], replace(ok, data_digest="e" * 64)) is not None


def test_first_failure_in_declared_order_wins():
    gi = replace(BASE, caller_sub="author", uploads_pending=1)
    assert evaluate(["attachments_clean", "not_same_actor:creator"], gi).guard == "attachments_clean"


def test_assignee_guard_fails_without_assignee():
    assert evaluate(["assignee_is_caller"], BASE).reason == "not_assignee"
    assert evaluate(["assignee_is_caller"], replace(BASE, task_assignee="rev")) is None


# ------------------------------------------------------------ từng guard: đạt / trượt đúng (guard, lý do, mã)
def test_no_guards_passes():
    assert evaluate([], BASE) is None


def test_attachments_clean_pass_and_fail_matrix():
    assert evaluate(["attachments_clean"], BASE) is None
    two = replace(BASE, clean_attachments=("a" * 64, "b" * 64), attachments_min=2)
    assert evaluate(["attachments_clean"], two) is None
    assert evaluate(["attachments_clean"], replace(BASE, attachments_min=2)) == GuardFailure(
        "attachments_clean", "attachments_not_clean", 409)
    # collection không có attachments: min = 0, không có tệp vẫn đạt
    assert evaluate(["attachments_clean"], replace(BASE, clean_attachments=(), attachments_min=0)) is None
    # còn upload STAGING thì trượt dù đã đủ tệp CLEAN
    assert evaluate(["attachments_clean"], replace(BASE, uploads_pending=2)) == GuardFailure(
        "attachments_clean", "attachments_not_clean", 409)


def test_pii_reviewed_not_required_passes_without_review():
    assert evaluate(["pii_reviewed"], BASE) is None


def test_pii_reviewed_required_without_review_fails_409():
    f = evaluate(["pii_reviewed"], replace(BASE, pii_required=True))
    assert f == GuardFailure("pii_reviewed", "pii_not_reviewed", 409)


def test_not_same_actor_creator_passes_for_other_caller():
    assert evaluate(["not_same_actor:creator"], BASE) is None


def test_not_same_actor_task_pass_and_fail():
    other = replace(BASE, completions=(("review", "someone-else"), ("approve", "rev")))
    # "rev" đã làm approve, không phải review
    assert evaluate(["not_same_actor:review"], other) is None
    gi = replace(BASE, completions=(("review", "rev"),))
    assert evaluate(["not_same_actor:review"], gi) == GuardFailure("not_same_actor:review", "same_actor", 403)
    assert evaluate(["not_same_actor:review"], replace(BASE, completions=())) is None


def test_role_in_with_several_roles():
    assert evaluate(["role_in:reviewer"], BASE) is None
    assert evaluate(["role_in:approver,reviewer"], BASE) is None
    assert evaluate(["role_in:[approver,reviewer]"], BASE) is None
    assert evaluate(["role_in:[approver, reviewer]"], BASE) is None
    f = evaluate(["role_in:approver,author"], BASE)
    assert f == GuardFailure("role_in:approver,author", "role_not_allowed", 403)
    assert evaluate(["role_in:approver"], replace(BASE, caller_roles=frozenset())).status == 403


@pytest.mark.parametrize("data", [{}, {"title": None}, {"title": ""}])
def test_field_required_fails_on_missing_none_and_empty(data):
    f = evaluate(["field_required:title"], replace(BASE, data=data))
    assert f == GuardFailure("field_required:title", "field_missing", 409)


@pytest.mark.parametrize("value", ["x", 0, False, " "])
def test_field_required_passes_on_present_values(value):
    assert evaluate(["field_required:title"], replace(BASE, data={"title": value})) is None


def test_record_not_sealed():
    assert evaluate(["record_not_sealed"], BASE) is None
    for state in ("SEAL_PENDING", "SEALED", "REVOKED"):
        f = evaluate(["record_not_sealed"], replace(BASE, seal_state=state))
        assert f == GuardFailure("record_not_sealed", "record_sealed", 409)


def test_assignee_is_caller_fails_for_other_assignee():
    f = evaluate(["assignee_is_caller"], replace(BASE, task_assignee="someone"))
    assert f == GuardFailure("assignee_is_caller", "not_assignee", 403)


# ------------------------------------------------------- guard sai là lỗi lập trình, không phải GuardFailure
@pytest.mark.parametrize("guard", [
    "no_such_guard", "", "attachments_clean:x", "pii_reviewed:x", "record_not_sealed:x",
    "assignee_is_caller:x", "not_same_actor", "not_same_actor:", "role_in", "role_in:", "role_in:a,,b",
    "role_in:[a,b", "field_required",
])
def test_unknown_or_malformed_guard_raises_value_error(guard):
    with pytest.raises(ValueError):
        evaluate([guard], BASE)


def test_malformed_guard_raises_even_after_earlier_failure():
    # chỉ guard đứng trước mới được đánh giá: lỗi đầu tiên thắng, guard sau không bị đụng tới
    gi = replace(BASE, uploads_pending=1)
    assert evaluate(["attachments_clean", "no_such_guard"], gi).guard == "attachments_clean"


# ---------------------------------------------------------------- review_digest
def test_review_digest_is_order_insensitive():
    a, b = "a" * 64, "b" * 64
    assert review_digest("d" * 64, [a, b], [3, 1, 2]) == review_digest("d" * 64, [b, a], [1, 2, 3])


def test_review_digest_changes_with_every_input():
    base = review_digest("d" * 64, ["a" * 64], [1])
    assert review_digest("e" * 64, ["a" * 64], [1]) != base
    assert review_digest("d" * 64, ["b" * 64], [1]) != base
    assert review_digest("d" * 64, ["a" * 64], [2]) != base
    assert review_digest("d" * 64, ["a" * 64], []) != base


def test_review_digest_matches_documented_formula():
    from dxos_proof.canonical import canonical_bytes, sha256_hex
    expected = sha256_hex(canonical_bytes({"data_digest": "d" * 64, "attachments": ["a" * 64, "b" * 64],
                                           "findings": [1, 2]}))
    assert review_digest("d" * 64, ["b" * 64, "a" * 64], [2, 1]) == expected
