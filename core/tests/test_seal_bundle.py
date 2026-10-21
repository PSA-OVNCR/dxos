# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Hàm thuần của cổng đối soát và gói bằng chứng (Plan 02 Task 8): chọn STH, 7 trường lá, thân ``{sha256}``,
nhãn công khai, cache khóa công khai."""

import pytest
from dxos_core.errors import ProblemError
from dxos_core.kms.base import KmsUnavailable
from dxos_core.kms.cache import KeysUnavailable, PublicKeyCache
from dxos_core.ledger.log import LedgerEntry, entry_bytes
from dxos_core.ledger.sth import TreeHead
from dxos_core.seal.bundle import AnchorRef, choose_sth, entry_fields
from dxos_core.seal.verify_router import MAX_BODY, parse_hash_body, public_labels
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import leaf_hash
from helpers.manifests import manifest


def th(size: int) -> TreeHead:
    return TreeHead(tree_size=size, root_hash="ab" * 32, ts="2026-10-21T00:00:00Z", key_version=1,
                    signature="c2ln")


def anchor(size: int) -> AnchorRef:
    return AnchorRef(sth=th(size), repo="file:///r.git", commit_sha="a" * 40)


# ---------- chọn STH (brief "Chọn STH") ----------

def test_anchored_sth_covering_leaf_wins():
    c = choose_sth(5, anchor(8), th(12))
    assert c.sth == th(8) and c.anchored == anchor(8)


def test_newest_sth_when_anchor_does_not_cover():
    c = choose_sth(5, anchor(5), th(12))           # tree_size 5 phủ lá 0..4: chưa phủ lá 5
    assert c.sth == th(12) and c.anchored == anchor(5)
    c = choose_sth(5, None, th(6))
    assert c.sth == th(6) and c.anchored is None


def test_no_sth_covers_leaf():
    assert choose_sth(5, None, None).sth is None
    c = choose_sth(5, anchor(3), th(5))
    assert c.sth is None and c.anchored is None


# ---------- lá ledger ----------

def test_entry_fields_are_exactly_the_leaf_fields():
    draft = LedgerEntry(idx=41, ts="2026-10-21T01:02:03Z", type="record.sealed", app_id="test-flow",
                        subject="A" * 26, actor_ref=None, body_sha256="cd" * 32, leaf_hash=b"")
    e = LedgerEntry(**{**draft.__dict__, "leaf_hash": leaf_hash(entry_bytes(draft))})
    f = entry_fields(e)
    assert set(f) == {"idx", "ts", "type", "app_id", "subject", "actor_ref", "body_sha256"}
    assert leaf_hash(canonical_bytes(f)) == e.leaf_hash


# ---------- thân {sha256} ----------

def test_parse_hash_body_accepts_only_strict_shape():
    h = "0f" * 32
    assert parse_hash_body(b'{"sha256": "' + h.encode() + b'"}') == h
    for bad in (b"", b"{", b"[]", b"null", b'{"sha256": 1}', b'{"sha256": "' + h.upper().encode() + b'"}',
                b'{"sha256": "' + h[:-1].encode() + b'"}', b'{"sha256": "' + h.encode() + b'\\n"}',
                b'{"sha256": "' + h.encode() + b'", "x": 1}',
                b'{"sha256": "' + h.encode() + b'", "sha256": "' + h.encode() + b'"}', b"\xff\xfe"):
        with pytest.raises(ProblemError) as e:
            parse_hash_body(bad)
        assert e.value.status == 422, bad
    assert MAX_BODY == 256


# ---------- nhãn công khai ----------

def test_public_labels_only_public_fields_with_label():
    m = manifest("test-flow")
    assert public_labels(m, "doc", ["ref", "title"]) == {"title": "Tiêu đề"}
    assert public_labels(m, "doc", ["ref"]) == {}
    assert public_labels(m, "khong-co", ["title"]) == {}


# ---------- cache khóa công khai ----------

class CountingSigner:
    def __init__(self) -> None:
        self.calls, self.down = 0, False
        self.keys = {"seal-key": {1: b"\x01" * 32}, "sth-key": {1: b"\x02" * 32}}

    async def public_keys(self):
        self.calls += 1
        if self.down:
            raise KmsUnavailable("down")
        return {k: dict(v) for k, v in self.keys.items()}


async def test_cache_fetches_only_unknown_versions():
    s, cache = CountingSigner(), PublicKeyCache()
    assert await cache.get(s, "seal-key", 1) == b"\x01" * 32
    assert await cache.get(s, "sth-key", 1) == b"\x02" * 32
    assert s.calls == 1                                    # đã biết: không hỏi lại
    s.down = True
    assert await cache.get(s, "seal-key", 1) == b"\x01" * 32
    with pytest.raises(KeysUnavailable):                   # phiên bản lạ + KMS khóa → không đoán
        await cache.get(s, "seal-key", 2)
    s.down = False
    s.keys["seal-key"][2] = b"\x03" * 32
    assert await cache.get(s, "seal-key", 2) == b"\x03" * 32
    assert await cache.get(s, "seal-key", 9) is None        # KMS trả lời mà không có: khóa không tồn tại


async def test_cache_never_replaces_known_key():
    s, cache = CountingSigner(), PublicKeyCache()
    await cache.get(s, "seal-key", 1)
    s.keys["seal-key"][1] = b"\x09" * 32                     # KMS đổi khóa của một phiên bản đã biết
    assert (await cache.all(s))["seal-key"][1] == b"\x01" * 32


async def test_cache_all_falls_back_when_kms_down():
    s, cache = CountingSigner(), PublicKeyCache()
    s.down = True
    with pytest.raises(KmsUnavailable):
        await cache.all(s)                                  # chưa biết gì: báo lỗi như trước
    s.down = False
    first = await cache.all(s)
    s.down = True
    assert await cache.all(s) == first
