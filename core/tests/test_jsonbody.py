# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bộ đọc thân JSON dùng chung (rà soát cuối Plan 02, m2): surrogate lẻ và lồng quá sâu bị từ chối rõ ràng."""

import pytest
from dxos_core.jsonbody import MAX_JSON_DEPTH, JsonBodyError, parse_json


def nested(depth: int) -> bytes:
    return b"[" * depth + b"]" * depth


def test_valid_json_is_returned_unchanged():
    assert parse_json(b'{"a": [1, {"b": "H\\u1ed3 s\\u01a1"}]}') == {"a": [1, {"b": "Hồ sơ"}]}
    assert parse_json(nested(MAX_JSON_DEPTH)) is not None


@pytest.mark.parametrize("raw", [b"{", b"\xff\xfe\x00", b""], ids=["truncated", "not-utf", "empty"])
def test_malformed_json_is_flagged_malformed(raw):
    with pytest.raises(JsonBodyError) as e:
        parse_json(raw)
    assert e.value.malformed


@pytest.mark.parametrize("raw", [b'{"title": "x\\ud800y"}', b'{"\\udc00": 1}', b'[["\\ud83d"]]'],
                         ids=["value", "key", "nested"])
def test_lone_surrogate_is_rejected(raw):
    with pytest.raises(JsonBodyError) as e:
        parse_json(raw)
    assert not e.value.malformed and "surrogate" in e.value.detail


@pytest.mark.parametrize("depth", [MAX_JSON_DEPTH + 1, 5000, 200_000])
def test_deep_nesting_is_rejected(depth):
    with pytest.raises(JsonBodyError) as e:
        parse_json(nested(depth))
    assert not e.value.malformed and "deep" in e.value.detail
