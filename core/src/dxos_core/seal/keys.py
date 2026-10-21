# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tuyên bố khóa ``seal-key`` (spec 25.3; Plan 02 Task 6 tạo khung, Task 7 dựng và ghi tuyên bố).

- R-1 (Task 6) đọc tuyên bố đã có (``statement_for``) và kiểm thời hạn (``within_validity``).
- ``ensure_key_statement`` tạo tuyên bố **một lần** cho mỗi phiên bản khóa, ở lần niêm phong đầu bằng phiên
  bản đó, dưới ``pg_advisory_xact_lock(LOCK_KEYSTMT)``: INSERT ``key_statements`` rồi lá ledger
  ``key.published``. ``valid_from`` = ``issued_at`` của lần niêm phong đó.

Tuyên bố **không tự ký**; nó được bảo vệ bằng lá ledger ``key.published`` và tệp trong repo neo.
Không bao giờ tạo tuyên bố với tên tổ chức mặc định: bảng chỉ-thêm, lá đã neo thì không sửa được.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from dxos_proof.canonical import canonical_bytes, rfc3339_utc, sha256_hex

from dxos_core.kms.base import Signer
from dxos_core.ledger.log import append
from dxos_core.settings import ORG_NAME_DEFAULT, Settings

__all__ = ["LOCK_KEYSTMT", "ORG_NAME_DEFAULT", "STATEMENT_FORMAT", "OrgNotConfigured", "SealKeyExpired",
           "build_statement", "ensure_key_statement", "latest_statement", "parse_rfc3339", "statement_for",
           "within_validity"]

STATEMENT_FORMAT = "dxos-key-statement/1"
# Khóa advisory của việc tạo tuyên bố khóa (Task 7). Khác 724000 (migrate), 724001 (ledger), 724100 (LOCK_WF).
LOCK_KEYSTMT = 724101


class SealKeyExpired(Exception):  # noqa: N818 (tên theo spec 25.3)
    """Thời điểm niêm phong nằm ngoài ``valid_from..valid_until`` của tuyên bố khóa: cần xoay khóa."""


class OrgNotConfigured(Exception):  # noqa: N818
    """``DXOS_ORG_NAME`` còn giá trị mặc định: không bao giờ ghi tên giữ chỗ vào tuyên bố chỉ-thêm."""


def parse_rfc3339(ts: str | datetime) -> datetime:
    """Thời điểm RFC 3339 (hoặc datetime có múi giờ) → datetime UTC. Thiếu múi giờ là lỗi."""
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("thời điểm phải có múi giờ")
    return dt.astimezone(UTC)


def within_validity(statement: dict[str, Any], at: str | datetime) -> bool:
    """``valid_from ≤ at ≤ valid_until``, so sánh sau khi parse cả ba thành datetime UTC (không so chuỗi)."""
    return (parse_rfc3339(statement["valid_from"]) <= parse_rfc3339(at)
            <= parse_rfc3339(statement["valid_until"]))


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def statement_for(conn: asyncpg.Connection, version: int) -> dict[str, Any] | None:
    """Tuyên bố của ``seal-key`` phiên bản ``version``; chưa có (chưa niêm phong lần nào bằng nó) → None."""
    raw = await conn.fetchval(
        "SELECT statement FROM core.key_statements WHERE key='seal-key' AND version=$1", version)
    return None if raw is None else _loads(raw)


async def latest_statement(conn: asyncpg.Connection) -> dict[str, Any] | None:
    """Tuyên bố của phiên bản ``seal-key`` lớn nhất đã có tuyên bố; chưa có tuyên bố nào → None."""
    raw = await conn.fetchval(
        "SELECT statement FROM core.key_statements WHERE key='seal-key' ORDER BY version DESC LIMIT 1")
    return None if raw is None else _loads(raw)



def build_statement(settings: Settings, *, version: int, public_key: bytes,
                    valid_from: str) -> dict[str, Any]:
    """Tuyên bố ``dxos-key-statement/1`` đúng các khóa của spec 25.3. Không có chữ ký.

    ``valid_from`` được đưa về chuỗi RFC 3339 UTC giây nguyên; ``valid_until`` = ``valid_from`` +
    ``seal_key_validity_days`` (tối đa 3650 ngày, NĐ 23/2025 Điều 7 khoản 4).
    """
    start = parse_rfc3339(valid_from)
    return {
        "format": STATEMENT_FORMAT,
        "key": "seal-key",
        "version": version,
        "serial": f"seal-key/v{version}",
        "issuer": {"name": settings.org_name, "id": settings.org_id},
        "algorithm": "ed25519",
        "public_key": base64.b64encode(public_key).decode("ascii"),
        "valid_from": rfc3339_utc(start),
        "valid_until": rfc3339_utc(start + timedelta(days=settings.seal_key_validity_days)),
        "purpose": settings.seal_purpose,
        "policy_url": settings.key_policy_url,
    }


async def ensure_key_statement(conn: asyncpg.Connection, *, signer: Signer, settings: Settings,
                               key_version: int, issued_at: str, hmac_key: bytes) -> dict[str, Any]:
    """Tuyên bố của ``seal-key`` phiên bản ``key_version``; chưa có thì tạo với ``valid_from = issued_at``.

    Phải chạy trong transaction của lần niêm phong (rollback cùng nó nếu ký lỗi). ``signer`` chỉ dùng để lấy
    khóa công khai của phiên bản, không ký. ``OrgNotConfigured`` khi tên tổ chức còn mặc định.
    Tuyên bố đã có thì không bao giờ đổi (bảng chỉ-thêm), nên đọc trước khi khóa là an toàn; chỉ đường tạo mới
    mới lấy ``LOCK_KEYSTMT`` và đọc lại dưới khóa.
    """
    if not conn.is_in_transaction():
        raise RuntimeError("ensure_key_statement phải chạy trong transaction của lần niêm phong")
    if settings.org_name == ORG_NAME_DEFAULT:
        raise OrgNotConfigured("DXOS_ORG_NAME chưa được cấu hình")
    existing = await statement_for(conn, key_version)
    if existing is not None:
        return existing
    await conn.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEYSTMT)
    existing = await statement_for(conn, key_version)
    if existing is not None:
        return existing
    public_key = (await signer.public_keys())["seal-key"].get(key_version)
    if public_key is None:
        raise RuntimeError(f"KMS không có khóa công khai của seal-key phiên bản {key_version}")
    statement = build_statement(settings, version=key_version, public_key=public_key, valid_from=issued_at)
    digest = sha256_hex(canonical_bytes(statement))
    await conn.execute(
        "INSERT INTO core.key_statements(key, version, statement, statement_sha256)"
        " VALUES ('seal-key', $1, $2::jsonb, $3)",
        key_version, json.dumps(statement, ensure_ascii=False), digest)
    await append(conn, type="key.published", subject=f"seal-key/v{key_version}",
                 body={"key": "seal-key", "version": key_version, "statement_sha256": digest},
                 hmac_key=hmac_key)
    return statement
