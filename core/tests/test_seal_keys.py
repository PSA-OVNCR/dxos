# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Khung tuyên bố khóa seal-key (Plan 02 Task 6, spec 25.3): kiểm thời hạn bằng datetime, không so chuỗi."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from dxos_core.seal.keys import ORG_NAME_DEFAULT, within_validity
from dxos_core.settings import ORG_NAME_DEFAULT as SETTINGS_DEFAULT

ST = {"valid_from": "2026-10-21T00:00:00Z", "valid_until": "2036-10-18T00:00:00Z"}


def test_org_default_is_shared_with_settings():
    assert ORG_NAME_DEFAULT is SETTINGS_DEFAULT


@pytest.mark.parametrize(("at", "ok"), [
    ("2026-10-21T00:00:00Z", True),                  # biên dưới được tính
    ("2036-10-18T00:00:00Z", True),                  # biên trên được tính
    ("2026-10-20T23:59:59Z", False),
    ("2036-10-18T00:00:01Z", False),
    ("2026-10-21T06:59:59+07:00", False),            # cùng thời điểm 2026-10-20T23:59:59Z
    ("2026-10-21T07:00:00+07:00", True),
])
def test_within_validity_compares_instants(at, ok):
    assert within_validity(ST, at) is ok


def test_within_validity_accepts_aware_datetime_only():
    assert within_validity(ST, datetime(2030, 1, 1, tzinfo=UTC))
    assert not within_validity(ST, datetime(2040, 1, 1, tzinfo=timezone(timedelta(hours=7))))
    with pytest.raises(ValueError):
        within_validity(ST, datetime(2030, 1, 1))     # thiếu múi giờ là lỗi
