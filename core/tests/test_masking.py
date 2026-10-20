# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test che PII (Plan 01 Task 12, F4)."""

import pytest
from dxos_core.policy.masking import mask_record, mask_value
from helpers.manifests import manifest


@pytest.mark.parametrize("v,t,out", [("079203001234", "CCCD", "07********34"),
                                     ("0912345678", "PHONE", "09******78"),
                                     ("an.nguyen@saomai.vn", "EMAIL", "a***@saomai.vn"),
                                     ("Nguyễn Văn An", "NAME", "N. V. A.")])
def test_mask_value(v, t, out):
    assert mask_value(v, t) == out


@pytest.mark.parametrize("v,t,out", [
    ("1234", "CCCD", "****"), ("12", "PHONE", "**"), ("", "BANK_ACCOUNT", ""),
    ("0123456789012", "BANK_ACCOUNT", "01*********12"),
    ("khong-co-a-cong", "EMAIL", "***"), ("@x.vn", "EMAIL", "***@x.vn"),
    ("  Trần   Thị  ", "NAME", "T. T."), ("Ánh", "NAME", "Á."),
])
def test_mask_value_edges(v, t, out):
    assert mask_value(v, t) == out


def test_mask_value_unknown_type_rejected():
    with pytest.raises(ValueError):
        mask_value("x", "PASSPORT")


def test_mask_record():
    spec = manifest("test-app").collections["item"]
    data = {"title": "Hồ sơ", "secret_code": "079203001234"}
    assert mask_record(data, spec, can_reveal=False) == {"title": "Hồ sơ", "secret_code": "07********34"}
    assert mask_record(data, spec, can_reveal=True) == data
    assert data["secret_code"] == "079203001234"  # noqa: S105 (không sửa dict gốc)


def test_mask_record_skips_missing_and_non_string():
    spec = manifest("test-app").collections["item"]
    assert mask_record({"title": "t"}, spec, can_reveal=False) == {"title": "t"}
    assert mask_record({"secret_code": None}, spec, can_reveal=False) == {"secret_code": None}
