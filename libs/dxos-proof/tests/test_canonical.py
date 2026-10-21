# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
import unicodedata
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


def test_keys_colliding_after_nfc_are_rejected():  # rà soát cuối Plan 02, m1
    """Hai khóa khác nhau chỉ ở dạng Unicode (NFD/NFC) không được gộp im lặng thành một: lỗi rõ."""
    nfc, nfd = "Hồ sơ", unicodedata.normalize("NFD", "Hồ sơ")
    assert nfc != nfd
    with pytest.raises(CanonicalError):
        canonical_bytes({nfc: 1, nfd: 2})
    with pytest.raises(CanonicalError):
        canonical_bytes({"a": [{nfd: 1, nfc: 1}]})              # lồng sâu, kể cả cùng giá trị
    assert canonical_bytes({nfd: 1, "b": 2}) == canonical_bytes({nfc: 1, "b": 2})
