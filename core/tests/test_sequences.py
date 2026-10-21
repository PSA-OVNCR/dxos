# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Định dạng số văn bản (spec 25.4, P2-D26)."""

import pytest
from dxos_core.records.sequences import format_sequence


@pytest.mark.parametrize("fmt,n,out", [("{n}/QĐ", 7, "7/QĐ"), ("{n:02}/QĐ-SM", 7, "07/QĐ-SM"),
                                       ("{n:02}", 123, "123")])
def test_format_sequence(fmt, n, out):
    assert format_sequence(fmt, n) == out


@pytest.mark.parametrize("fmt,n,out", [(None, 7, "7"), ("{n:09}", 42, "000000042"),
                                       ("CN-{n:03}/2026", 5, "CN-005/2026")])
def test_format_sequence_more(fmt, n, out):
    assert format_sequence(fmt, n) == out


def test_format_sequence_does_not_interpret_other_braces():
    assert format_sequence("{x}-{n}", 3) == "{x}-3"
