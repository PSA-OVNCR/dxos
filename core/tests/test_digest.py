# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cam kết có salt tới dữ liệu bản ghi (spec 25.2, P2-D22)."""

import base64
import re

from dxos_core.records.digest import data_digest, new_salt
from dxos_proof.canonical import canonical_bytes, sha256_hex


def test_data_digest_is_salted_and_stable():
    data, salt = {"title": "x", "cccd": "001099012345"}, new_salt()
    assert re.fullmatch(r"[A-Za-z0-9+/]{22}==", salt)
    assert data_digest(data, salt) == data_digest(dict(reversed(data.items())), salt)
    assert data_digest(data, salt) != data_digest(data, new_salt()) != sha256_hex(canonical_bytes(data))


def test_new_salt_is_16_random_bytes():
    salts = {new_salt() for _ in range(64)}
    assert len(salts) == 64 and all(len(base64.b64decode(s, validate=True)) == 16 for s in salts)


def test_data_digest_matches_documented_formula():
    salt = "AAAAAAAAAAAAAAAAAAAAAA=="
    expected = sha256_hex(b'{"data":{"a":1},"salt":"AAAAAAAAAAAAAAAAAAAAAA=="}')
    assert data_digest({"a": 1}, salt) == expected
