# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Signed Tree Head (spec 11.3; Plan 01 Task 15).

Thứ tự bắt buộc trong ``make_sth``, tất cả trong **một** transaction:
1. Ghi lá ``sth.published`` (body ``{tree_size_before}``) — STH luôn phủ cả sự kiện công bố chính nó.
2. Tính root trên toàn bộ lá (kể cả lá vừa ghi).
3. Ký bằng ``sth-key`` (phiên bản mới nhất).
4. Chèn ``tree_heads``.
Ký lỗi (``KmsUnavailable``) thì rollback hết, kể cả lá ``sth.published`` (F8).
"""

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_proof.canonical import canonical_bytes, rfc3339_utc
from dxos_proof.merkle import root

from dxos_core.kms.base import KmsUnavailable, Signer
from dxos_core.ledger.log import LEDGER_LOCK_KEY, append, entries_bytes


@dataclass
class TreeHead:
    tree_size: int
    root_hash: str     # hex
    ts: str            # RFC 3339 UTC
    key_version: int
    signature: str     # base64


def sth_signing_bytes(tree_size: int, root_hash: str, ts: str, key_version: int) -> bytes:
    return canonical_bytes(
        {"tree_size": tree_size, "root_hash": root_hash, "ts": ts, "key_version": key_version})


def verify_sth(th: TreeHead, pubkey: bytes) -> bool:
    try:
        sig = base64.b64decode(th.signature, validate=True)
        Ed25519PublicKey.from_public_bytes(pubkey).verify(
            sig, sth_signing_bytes(th.tree_size, th.root_hash, th.ts, th.key_version))
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False


def _row(r: asyncpg.Record) -> TreeHead:
    return TreeHead(r["tree_size"], r["root_hash"], r["ts"], r["key_version"], r["signature"])


async def make_sth(conn: asyncpg.Connection, signer: Signer) -> TreeHead:
    versions = (await signer.public_keys()).get("sth-key") or {}
    if not versions:
        raise KmsUnavailable("không có phiên bản sth-key nào")
    key_version = max(versions)
    async with conn.transaction():
        # Giữ khóa advisory của ledger tới hết transaction: không lá nào chen vào giữa 4 bước.
        # (append() lấy lại cùng khóa trong cùng phiên, không bị chặn.)
        await conn.execute("SELECT pg_advisory_xact_lock($1)", LEDGER_LOCK_KEY)
        before = await conn.fetchval("SELECT count(*) FROM ledger_entries")
        await append(conn, type="sth.published", subject="sth", body={"tree_size_before": before},
                     hmac_key=b"")
        leaves = await entries_bytes(conn)
        tree_size, root_hash = len(leaves), root(leaves).hex()
        ts = rfc3339_utc(datetime.now(UTC))
        signed = await signer.sign("sth-key", sth_signing_bytes(tree_size, root_hash, ts, key_version),
                                   key_version=key_version)
        if signed.key_version != key_version:
            raise KmsUnavailable(f"KMS ký bằng phiên bản {signed.key_version}, mong đợi {key_version}")
        sig_b64 = base64.b64encode(signed.signature).decode("ascii")
        th = TreeHead(tree_size, root_hash, ts, key_version, sig_b64)
        await conn.execute(
            "INSERT INTO tree_heads(tree_size, root_hash, ts, key_version, signature)"
            " VALUES ($1, $2, $3, $4, $5)",
            th.tree_size, th.root_hash, th.ts, th.key_version, th.signature)
    return th


async def latest_sth(conn: asyncpg.Connection) -> TreeHead | None:
    r = await conn.fetchrow("SELECT * FROM tree_heads ORDER BY tree_size DESC LIMIT 1")
    return _row(r) if r else None


async def get_sth(conn: asyncpg.Connection, tree_size: int) -> TreeHead | None:
    r = await conn.fetchrow("SELECT * FROM tree_heads WHERE tree_size=$1", tree_size)
    return _row(r) if r else None
