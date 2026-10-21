# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bằng chứng của một niêm phong: chọn STH, inclusion/consistency proof, gói ``dxos-seal-bundle/1``
(Plan 02 Task 8; spec 11.5, 25.3; P2-D16). Bên kiểm ngoại tuyến là ``dxos-witness verify-bundle`` (Task 9).

Chọn STH (``choose_sth``):
1. STH đã neo gần nhất phủ được lá (``tree_size > leaf_index``) → dùng nó; ``anchored.sth`` chính là ``sth``,
   ``consistency = []``.
2. Không thì STH mới nhất phủ lá; ``anchored`` là STH đã neo gần nhất (có thể không có), kèm consistency proof
   từ nó tới ``sth``.
3. Chưa có STH nào phủ lá → ``sth = None``, ``anchored = None``, proof rỗng.

``status`` của gói **không** nằm trong phần đã ký: ngoại tuyến, trạng thái thu hồi luôn là "cần tra trực
tuyến". Module này chỉ đọc DB.
"""

import base64
import binascii
import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_proof.canonical import canonical_bytes, rfc3339_utc, sha256_hex
from dxos_proof.merkle import (
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    verify_consistency,
    verify_inclusion,
)

from dxos_core.ledger.log import LedgerEntry, entries_bytes, entry_bytes
from dxos_core.ledger.ots import receipts_ots
from dxos_core.ledger.sth import TreeHead, verify_sth
from dxos_core.seal.service import seal_signing_bytes, sealed_leaf_body

BUNDLE_FORMAT = "dxos-seal-bundle/1"


@dataclass(frozen=True)
class AnchorRef:
    sth: TreeHead
    repo: str
    commit_sha: str


@dataclass(frozen=True)
class SthChoice:
    sth: TreeHead | None
    anchored: AnchorRef | None


@dataclass(frozen=True)
class SealRow:
    seal_id: str
    app_id: str
    payload: dict[str, Any]
    signature: str          # base64
    key_version: int
    leaf_index: int
    status: str             # VALID | REVOKED


@dataclass(frozen=True)
class Evidence:
    seal: SealRow
    entry: LedgerEntry
    sth: TreeHead | None
    anchored: AnchorRef | None
    proof: list[bytes]          # inclusion của lá trong ``sth``
    consistency: list[bytes]    # từ ``anchored.sth`` tới ``sth`` (rỗng khi trùng nhau)
    anchored_ots: bytes | None = None   # tệp .ots của ``anchored.sth`` (Plan 03 Task 14), nếu có biên nhận


def choose_sth(leaf_index: int, latest_anchor: AnchorRef | None, latest: TreeHead | None) -> SthChoice:
    if latest_anchor is not None and latest_anchor.sth.tree_size > leaf_index:
        return SthChoice(latest_anchor.sth, latest_anchor)
    if latest is not None and latest.tree_size > leaf_index:
        return SthChoice(latest, latest_anchor)
    return SthChoice(None, None)


def entry_fields(e: LedgerEntry) -> dict[str, Any]:
    """Đúng 7 trường dùng để băm lá: ``leaf_hash(canonical(entry_fields(e)))`` là hash lá đã lưu."""
    return {"idx": e.idx, "ts": e.ts, "type": e.type, "app_id": e.app_id, "subject": e.subject,
            "actor_ref": e.actor_ref, "body_sha256": e.body_sha256}


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _th(r: asyncpg.Record) -> TreeHead:
    return TreeHead(r["tree_size"], r["root_hash"], r["ts"], r["key_version"], r["signature"])


def seal_row(r: asyncpg.Record) -> SealRow:
    return SealRow(seal_id=r["seal_id"], app_id=r["app_id"], payload=_loads(r["payload"]),
                   signature=r["signature"],
                   key_version=r["key_version"], leaf_index=r["leaf_index"], status=r["status"])


async def load_evidence(conn: asyncpg.Connection, seal: SealRow) -> Evidence:
    """Lá của niêm phong, STH đã chọn và các proof. Gọi trong một transaction chỉ-đọc để thấy cùng một ảnh."""
    r = await conn.fetchrow(
        "SELECT idx, ts, type, app_id, subject, actor_ref, body_sha256, leaf_hash FROM ledger_entries"
        " WHERE idx=$1",
        seal.leaf_index)
    if r is None:
        raise RuntimeError(f"niêm phong {seal.seal_id}: không có lá {seal.leaf_index}")
    entry = LedgerEntry(idx=r["idx"], ts=r["ts"], type=r["type"], app_id=r["app_id"], subject=r["subject"],
                        actor_ref=r["actor_ref"], body_sha256=r["body_sha256"],
                        leaf_hash=bytes(r["leaf_hash"]))
    a = await conn.fetchrow(
        "SELECT t.*, a.repo, a.commit_sha FROM anchors a JOIN tree_heads t ON t.tree_size = a.tree_size"
        " ORDER BY a.tree_size DESC, a.anchored_at DESC LIMIT 1")
    latest_anchor = AnchorRef(_th(a), a["repo"], a["commit_sha"]) if a else None
    t = await conn.fetchrow("SELECT * FROM tree_heads ORDER BY tree_size DESC LIMIT 1")
    choice = choose_sth(seal.leaf_index, latest_anchor, _th(t) if t else None)
    proof: list[bytes] = []
    consistency: list[bytes] = []
    if choice.sth is not None:
        leaves = await entries_bytes(conn, upto=choice.sth.tree_size)
        proof = inclusion_proof(seal.leaf_index, leaves)
        if choice.anchored is not None and choice.anchored.sth.tree_size != choice.sth.tree_size:
            consistency = consistency_proof(choice.anchored.sth.tree_size, leaves)
    anchored_ots = None
    if choice.anchored is not None:
        a_sth = choice.anchored.sth
        anchored_ots = await receipts_ots(conn, a_sth.tree_size, dataclasses.asdict(a_sth))
    return Evidence(seal=seal, entry=entry, sth=choice.sth, anchored=choice.anchored, proof=proof,
                    consistency=consistency, anchored_ots=anchored_ots)


# ---------------------------------------------------------------- kiểm phía máy chủ (trang công khai)
def signature_ok(seal: SealRow, public_key: bytes | None) -> bool:
    if public_key is None:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            base64.b64decode(seal.signature, validate=True), seal_signing_bytes(seal.payload))
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False


def inclusion_ok(ev: Evidence, sth_keys: dict[int, bytes | None]) -> bool:
    """Lá ↔ payload, inclusion trong ``sth``, chữ ký STH, và consistency từ STH đã neo (nếu khác ``sth``)."""
    seal, e = ev.seal, ev.entry
    if ev.sth is None:
        return False
    linked = (e.idx == seal.leaf_index and e.type == "record.sealed" and e.subject == seal.seal_id
              and e.body_sha256 == sha256_hex(canonical_bytes(sealed_leaf_body(seal.payload))))
    if not linked:
        return False
    if not verify_inclusion(leaf_hash(entry_bytes(e)), e.idx, ev.sth.tree_size, ev.proof,
                            bytes.fromhex(ev.sth.root_hash)):
        return False

    def sth_ok(th: TreeHead) -> bool:
        pk = sth_keys.get(th.key_version)
        return pk is not None and verify_sth(th, pk)

    if not sth_ok(ev.sth):
        return False
    a = ev.anchored
    if a is None or a.sth == ev.sth:
        return True
    return sth_ok(a.sth) and verify_consistency(a.sth.tree_size, ev.sth.tree_size,
                                                bytes.fromhex(a.sth.root_hash),
                                                bytes.fromhex(ev.sth.root_hash), ev.consistency)


def sth_versions(ev: Evidence) -> set[int]:
    out = {ev.sth.key_version} if ev.sth else set()
    if ev.anchored is not None:
        out.add(ev.anchored.sth.key_version)
    return out


# ---------------------------------------------------------------- gói bằng chứng
def _b64(raw: bytes | None) -> str | None:
    return None if raw is None else base64.b64encode(raw).decode("ascii")


def build_bundle(ev: Evidence, *, seal_public_key: bytes | None, statement: dict[str, Any] | None,
                 sth_keys: dict[int, bytes | None], now: datetime | None = None) -> dict[str, Any]:
    """Gói ``dxos-seal-bundle/1``. Ngoài các khóa của brief có thêm ``sth_keys`` (``{"<n>": b64}``, khóa
    ``sth-key`` của ``sth`` và ``anchored.sth``) để kiểm được chữ ký STH khi không có repo neo; bên kiểm bỏ
    qua khóa lạ ở mức gốc."""
    seal = ev.seal
    anchored = None
    if ev.anchored is not None:
        anchored = {"sth": dataclasses.asdict(ev.anchored.sth), "repo": ev.anchored.repo,
                    "commit_sha": ev.anchored.commit_sha, "consistency": [p.hex() for p in ev.consistency]}
    return {
        "format": BUNDLE_FORMAT,
        "status": seal.status,                       # KHÔNG được ký: ngoại tuyến phải tra trực tuyến
        "payload": seal.payload,
        "signature": seal.signature,
        # Không có tuyên bố đã kiểm → BỎ khóa ``statement`` (không bao giờ phục vụ tuyên bố chưa kiểm).
        "seal_key": {"version": seal.key_version, "public_key": _b64(seal_public_key),
                     **({"statement": statement} if statement is not None else {})},
        "ledger": {"entry": entry_fields(ev.entry), "body": sealed_leaf_body(seal.payload)},
        "inclusion": {"leaf_index": seal.leaf_index, "tree_size": ev.sth.tree_size if ev.sth else None,
                      "proof": [p.hex() for p in ev.proof]},
        "sth": dataclasses.asdict(ev.sth) if ev.sth else None,
        "sth_keys": {str(v): _b64(k) for v, k in sorted(sth_keys.items()) if k is not None},
        "anchored": anchored,
        "generated_at": rfc3339_utc(now or datetime.now(UTC)),
        # Biên nhận OpenTimestamps của ``anchored.sth`` (Plan 03 Task 14): chỉ có khi đã có biên nhận. Người
        # kiểm tự nâng cấp/kiểm bằng ``ots``; dxos-witness chỉ ghi chú, không đổi kết quả.
        **({"timestamps": [{"type": "opentimestamps", "tree_size": ev.anchored.sth.tree_size,
                            "ots": _b64(ev.anchored_ots)}]}
           if ev.anchored is not None and ev.anchored_ots is not None else {}),
    }
