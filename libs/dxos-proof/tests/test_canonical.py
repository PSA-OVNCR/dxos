# SPDX-FileCopyrightText: 2026 DX-OS Trust Core contributors
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta, timezone

import pytest

from dxos_proof.canonical import CanonicalError, canonical_bytes, rfc3339_utc, sha256_hex


def test_sorted_keys_no_whitespace():
    assert canonical_bytes({"b": 1, "a": "x"}) == b'{"a":"x","b":1}'


def test_rejects_float():
    with pytest.raises(CanonicalError):
        canonical_bytes({"x": 1.5})


def test_rejects_non_string_key():
    with pytest.raises(CanonicalError):
        canonical_bytes({1: "a"})


def test_unicode_not_escaped():
    assert canonical_bytes({"t": "ễ"}) == '{"t":"ễ"}'.encode()


def test_nfc_normalization_values_and_keys():  # Review Focus 1
    nfd, nfc = "Nguyễn", "Nguyễn"
    assert canonical_bytes({"t": nfd}) == canonical_bytes({"t": nfc})
    assert canonical_bytes({nfd: 1}) == canonical_bytes({nfc: 1})


def test_rfc3339_utc_converts_offset():  # Review Focus 5
    dt = datetime(2026, 10, 20, 7, 30, tzinfo=timezone(timedelta(hours=7)))
    assert rfc3339_utc(dt) == "2026-10-20T00:30:00Z"


def test_rfc3339_rejects_naive():
    with pytest.raises(CanonicalError):
        rfc3339_utc(datetime(2026, 10, 20))


def test_rejects_datetime_object_directly():
    with pytest.raises(CanonicalError):
        canonical_bytes({"ts": datetime.now(UTC)})


def test_sha256_hex():
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
