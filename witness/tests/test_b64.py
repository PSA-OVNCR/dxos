# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Base64 chuẩn tắc của witness (ruling R29): kiểm tường minh, không phụ thuộc bản CPython."""

import base64

import pytest
from dxos_witness.b64 import b64decode_canonical


@pytest.mark.parametrize("raw", [b"", b"a", b"ab", b"abc", b"abcd", bytes(range(32)), bytes(range(64))])
def test_roundtrip_of_canonical_encodings(raw):
    assert b64decode_canonical(base64.b64encode(raw).decode()) == raw


@pytest.mark.parametrize("bad", [
    "AAAA=", "AAAA==", "AAAA===", "AAAA=======", "AAA===", "AA====", "A===", "AAA", "AA", "A", "=", "====",
    "AA=A", "AAAA\n", " AAAA", "AA AA", "AAAA==\n", "AA-_", "AAA=٣", "é", "QUJDRA===",
])
def test_non_canonical_is_rejected_on_every_python(bad):
    with pytest.raises(ValueError):
        b64decode_canonical(bad)


def test_non_str_is_rejected():
    for bad in (b"QUJD", None, 1, ["QUJD"]):
        with pytest.raises(ValueError):
            b64decode_canonical(bad)
