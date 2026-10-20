# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cây Merkle theo RFC 6962 (§2.1) và thuật toán kiểm chứng của RFC 9162 (§2.1.3.2, §2.1.4.2).

``entries`` luôn là dữ liệu lá thô (chưa băm). Mọi hash là ``bytes`` 32 byte (SHA-256).
"""

import hashlib
from collections.abc import Sequence


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(data: bytes) -> bytes:
    """Hash lá: SHA-256(0x00 || data)."""
    return _sha256(b"\x00" + data)


def node_hash(left: bytes, right: bytes) -> bytes:
    """Hash nút trong: SHA-256(0x01 || left || right)."""
    return _sha256(b"\x01" + left + right)


def _split(n: int) -> int:
    """Lũy thừa 2 lớn nhất k với k < n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root(entries: Sequence[bytes]) -> bytes:
    """MTH(D[n]); cây rỗng có root = SHA-256('')."""
    n = len(entries)
    if n == 0:
        return _sha256(b"")
    if n == 1:
        return leaf_hash(entries[0])
    k = _split(n)
    return node_hash(root(entries[:k]), root(entries[k:]))


def inclusion_proof(index: int, entries: Sequence[bytes]) -> list[bytes]:
    """PATH(m, D[n]) theo RFC 6962 §2.1.1."""
    n = len(entries)
    if not 0 <= index < n:
        raise ValueError("index nằm ngoài cây")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_proof(index, entries[:k]) + [root(entries[k:])]
    return inclusion_proof(index - k, entries[k:]) + [root(entries[:k])]


def _subproof(m: int, entries: Sequence[bytes], complete: bool) -> list[bytes]:
    n = len(entries)
    if m == n:
        return [] if complete else [root(entries)]
    k = _split(n)
    if m <= k:
        return _subproof(m, entries[:k], complete) + [root(entries[k:])]
    return _subproof(m - k, entries[k:], False) + [root(entries[:k])]


def consistency_proof(m: int, entries: Sequence[bytes]) -> list[bytes]:
    """PROOF(m, D[n]) theo RFC 6962 §2.1.2, với 1 <= m <= n."""
    if not 1 <= m <= len(entries):
        raise ValueError("cần 1 <= m <= n")
    return _subproof(m, entries, True)


def verify_inclusion(leaf: bytes, index: int, size: int, proof: Sequence[bytes], root_hash: bytes) -> bool:
    """Kiểm chứng inclusion proof (RFC 9162 §2.1.3.2). ``leaf`` là leaf hash."""
    if index < 0 or index >= size:
        return False
    fn, sn, r = index, size - 1, leaf
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root_hash


def verify_consistency(m: int, n: int, root_m: bytes, root_n: bytes, proof: Sequence[bytes]) -> bool:
    """Kiểm chứng consistency proof giữa cây cỡ m và cây cỡ n (RFC 9162 §2.1.4.2)."""
    if m < 1 or m > n:
        return False
    if m == n:
        return len(proof) == 0 and root_m == root_n
    if not proof:
        return False
    path = list(proof)
    if m & (m - 1) == 0:  # m là lũy thừa của 2
        path.insert(0, root_m)
    fn, sn = m - 1, n - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = path[0]
    for c in path[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return sn == 0 and fr == root_m and sr == root_n
