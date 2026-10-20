# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ghi và kiểm ledger chỉ-thêm (spec 11.2, Plan 01 Task 9).

- ``idx`` liên tục từ 0, cấp dưới ``pg_advisory_xact_lock`` (D2): không bao giờ có lỗ hổng,
  kể cả khi transaction của bên gọi rollback (khi đó lá cũng biến mất cùng transaction).
- Lá: ``leaf_hash = SHA-256(0x00 || canonical({idx, ts, type, app_id, subject, actor_ref, body_sha256}))``.
- Không lưu ``body``, chỉ lưu ``body_sha256``; ``actor_ref`` là HMAC-SHA256 của ``sub``.

``verify_log`` chỉ phát hiện việc sửa trường mà quên tính lại ``leaf_hash`` hoặc xóa dòng. Kẻ có quyền SQL
tính lại được cả ``leaf_hash``; trường hợp đó bị bắt bởi STH đã ký và đã neo (Task 15, 16; AT-15, AT-16).
"""

import hashlib
import hmac as _hmac
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from dxos_proof.canonical import canonical_bytes, rfc3339_utc, sha256_hex
from dxos_proof.merkle import leaf_hash as _leaf_hash

from dxos_core.ledger.events import EVENT_TYPES

LEDGER_LOCK_KEY = 724001

_COLUMNS = "idx, ts, type, app_id, subject, actor_ref, body_sha256, leaf_hash"


@dataclass(frozen=True)
class LedgerEntry:
    idx: int
    ts: str
    type: str
    app_id: str | None
    subject: str
    actor_ref: str | None
    body_sha256: str
    leaf_hash: bytes


@dataclass
class VerifyResult:
    ok: bool
    first_bad_idx: int | None


def entry_bytes(e: LedgerEntry) -> bytes:
    """Bytes chuẩn hóa của lá: đúng 7 trường, ``leaf_hash`` không nằm trong đó."""
    return canonical_bytes({
        "idx": e.idx,
        "ts": e.ts,
        "type": e.type,
        "app_id": e.app_id,
        "subject": e.subject,
        "actor_ref": e.actor_ref,
        "body_sha256": e.body_sha256,
    })


def actor_ref(sub: str, key: bytes) -> str:
    """HMAC-SHA256 dạng hex của ``sub``: ledger công khai được mà không lộ danh tính."""
    return _hmac.new(key, sub.encode("utf-8"), hashlib.sha256).hexdigest()


def _nfc(value: str | None) -> str | None:
    return None if value is None else unicodedata.normalize("NFC", value)


def _row_to_entry(row: asyncpg.Record) -> LedgerEntry:
    return LedgerEntry(
        idx=row["idx"], ts=row["ts"], type=row["type"], app_id=row["app_id"], subject=row["subject"],
        actor_ref=row["actor_ref"], body_sha256=row["body_sha256"], leaf_hash=bytes(row["leaf_hash"]),
    )


async def append(
    conn: asyncpg.Connection,
    *,
    type: str,
    subject: str,
    body: Mapping,
    hmac_key: bytes,
    app_id: str | None = None,
    actor_sub: str | None = None,
) -> LedgerEntry:
    """Thêm một lá vào ledger và trả về lá đó.

    Chạy trong transaction riêng; nếu ``conn`` đang trong transaction của bên gọi thì thành savepoint
    và khóa advisory giữ tới khi transaction ngoài kết thúc, nên lá được ghi nguyên tử cùng thay đổi
    nghiệp vụ.
    """
    if type not in EVENT_TYPES:
        raise ValueError(f"loại sự kiện ledger không hợp lệ: {type!r}")
    body_sha256 = sha256_hex(canonical_bytes(dict(body)))  # số thực... → CanonicalError
    ref = actor_ref(actor_sub, hmac_key) if actor_sub is not None else None
    subject_n, app_id_n = _nfc(subject), _nfc(app_id)
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", LEDGER_LOCK_KEY)
        idx = await conn.fetchval("SELECT COALESCE(MAX(idx), -1) + 1 FROM ledger_entries")
        ts = rfc3339_utc(datetime.now(UTC))
        draft = LedgerEntry(idx=idx, ts=ts, type=type, app_id=app_id_n, subject=subject_n, actor_ref=ref,
                            body_sha256=body_sha256, leaf_hash=b"")
        entry = LedgerEntry(**{**draft.__dict__, "leaf_hash": _leaf_hash(entry_bytes(draft))})
        await conn.execute(
            f"INSERT INTO ledger_entries ({_COLUMNS}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",  # noqa: S608
            entry.idx, entry.ts, entry.type, entry.app_id, entry.subject, entry.actor_ref,
            entry.body_sha256, entry.leaf_hash,
        )
    return entry


async def entries_bytes(conn: asyncpg.Connection, upto: int | None = None) -> list[bytes]:
    """Bytes của các lá theo thứ tự ``idx``; ``upto`` (không bao gồm) giới hạn kích thước cây."""
    if upto is None:
        rows = await conn.fetch(f"SELECT {_COLUMNS} FROM ledger_entries ORDER BY idx")  # noqa: S608
    else:
        rows = await conn.fetch(
            f"SELECT {_COLUMNS} FROM ledger_entries WHERE idx < $1 ORDER BY idx", upto)  # noqa: S608
    return [entry_bytes(_row_to_entry(r)) for r in rows]


async def verify_log(conn: asyncpg.Connection) -> VerifyResult:
    """Kiểm từng lá: ``idx`` liên tục từ 0 và ``leaf_hash`` khớp với các trường đang lưu."""
    # Quy mô demo vài nghìn lá: đọc một lần là đủ (không cần cursor).
    rows = await conn.fetch(f"SELECT {_COLUMNS} FROM ledger_entries ORDER BY idx")  # noqa: S608
    for expected, row in enumerate(rows):
        e = _row_to_entry(row)
        if e.idx != expected:
            return VerifyResult(ok=False, first_bad_idx=expected)
        if e.leaf_hash != _leaf_hash(entry_bytes(e)):
            return VerifyResult(ok=False, first_bad_idx=e.idx)
    return VerifyResult(ok=True, first_bad_idx=None)
