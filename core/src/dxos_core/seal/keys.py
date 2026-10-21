# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tuyên bố khóa ``seal-key`` (spec 25.3; Plan 02 Task 6 tạo khung, Task 7 dựng và ghi tuyên bố).

- R-1 (Task 6), đường ký và health đọc tuyên bố đã có qua ``checked_statement_for`` (đã kiểm hash và phiên
  bản; hàng có mà không qua kiểm → ``KeyStatementInvalid``, không bao giờ coi như "chưa có") rồi kiểm thời
  hạn (``within_validity``).
- ``insert_statement_once`` tạo tuyên bố **một lần** cho mỗi phiên bản khóa, ở lần niêm phong đầu bằng phiên
  bản đó, dưới ``pg_advisory_xact_lock(LOCK_KEYSTMT)``; bên gọi ghi lá ledger ``key.published``
  (``publish_leaf``) sau khi ký. ``valid_from`` = ``issued_at`` của lần niêm phong đó.

Tuyên bố **không tự ký**; nó được bảo vệ bằng lá ledger ``key.published`` và tệp trong repo neo.
Không bao giờ tạo tuyên bố với tên tổ chức mặc định: bảng chỉ-thêm, lá đã neo thì không sửa được.
"""

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
from dxos_proof.canonical import canonical_bytes, rfc3339_utc, sha256_hex

from dxos_core.ledger.log import append
from dxos_core.settings import ORG_NAME_DEFAULT, Settings, org_configured

__all__ = ["LOCK_KEYSTMT", "ORG_NAME_DEFAULT", "STATEMENT_FORMAT", "KeyStatementInvalid", "OrgNotConfigured",
           "SealKeyExpired", "build_statement", "checked_statement_for", "insert_statement_once",
           "org_configured", "parse_rfc3339", "publish_leaf", "statement_for", "verified_statement_for",
           "verified_statements", "within_validity"]

log = logging.getLogger("dxos_core.seal.keys")

STATEMENT_FORMAT = "dxos-key-statement/1"
# Khóa advisory của việc tạo tuyên bố khóa (Task 7). Khác 724000 (migrate), 724001 (ledger), 724100 (LOCK_WF).
LOCK_KEYSTMT = 724101


class SealKeyExpired(Exception):  # noqa: N818 (tên theo spec 25.3)
    """Thời điểm niêm phong nằm ngoài ``valid_from..valid_until`` của tuyên bố khóa: cần xoay khóa."""


class KeyStatementInvalid(Exception):  # noqa: N818
    """Hàng ``key_statements`` của phiên bản khóa có trong DB nhưng không qua kiểm (hash hoặc phiên bản không
    khớp: bị sửa ngoài lõi). Fail-closed: không ký, không ghi đè; admin phải điều tra (rà soát cuối, m3)."""


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
    """Tuyên bố **thô, chưa kiểm** của ``seal-key/v<version>`` (chưa có → None). Đường ký, R-1 và health dùng
    ``checked_statement_for``; hàm này chỉ để đọc lại đúng thứ đã lưu (test, đối chiếu)."""
    raw = await conn.fetchval(
        "SELECT statement FROM core.key_statements WHERE key='seal-key' AND version=$1", version)
    return None if raw is None else _loads(raw)


async def verified_statements(conn: asyncpg.Connection,
                              version: int | None = None) -> dict[int, dict[str, Any]]:
    """Tuyên bố ``seal-key`` đã kiểm, ``{version: tuyên bố}`` (chỉ ``version`` nếu có): dùng chung cho job
    neo, ``/verify/v1/keys``, trang công khai và gói bằng chứng (Plan 02 Task 8, fix vòng 1).

    Hàng mà ``sha256(canonical(statement)) != statement_sha256``, hoặc ``statement.key``/``statement.version``
    khác cột của hàng → log ERROR và **bỏ qua**: không bao giờ phục vụ tuyên bố chưa kiểm.
    """
    sql = "SELECT version, statement, statement_sha256 FROM core.key_statements WHERE key='seal-key'"
    rows = await (conn.fetch(sql + " AND version=$1", version) if version is not None
                  else conn.fetch(sql + " ORDER BY version"))
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        st = _loads(r["statement"])
        ok = (isinstance(st, dict) and st.get("key") == "seal-key" and st.get("version") == r["version"]
              and sha256_hex(canonical_bytes(st)) == r["statement_sha256"])
        if not ok:
            log.error("tuyên bố seal-key/v%s không khớp statement_sha256 hoặc phiên bản: bỏ qua",
                      r["version"])
            continue
        out[r["version"]] = st
    return out


async def verified_statement_for(conn: asyncpg.Connection, version: int) -> dict[str, Any] | None:
    """Tuyên bố đã kiểm của ``seal-key/v<version>``; chưa có hoặc không qua kiểm → None."""
    return (await verified_statements(conn, version)).get(version)


async def checked_statement_for(conn: asyncpg.Connection, version: int) -> dict[str, Any] | None:
    """Tuyên bố đã kiểm của ``seal-key/v<version>``; chưa có hàng → None; có hàng mà không qua kiểm →
    ``KeyStatementInvalid`` (khác ``verified_statement_for``: không lẫn "bị sửa" với "chưa có")."""
    st = await verified_statement_for(conn, version)
    if st is not None:
        return st
    if await conn.fetchval("SELECT EXISTS (SELECT 1 FROM core.key_statements WHERE key='seal-key'"
                           " AND version=$1)", version):
        raise KeyStatementInvalid(f"tuyên bố seal-key/v{version} có trong DB nhưng không qua kiểm")
    return None


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


async def insert_statement_once(conn: asyncpg.Connection, *, settings: Settings, key_version: int,
                                public_key: bytes, issued_at: str) -> tuple[dict[str, Any], bool]:
    """Tuyên bố của phiên bản ``key_version``; chưa có thì INSERT (``valid_from = issued_at``). Trả
    ``(tuyên bố, True nếu chính lời gọi này vừa tạo)``. KHÔNG ghi ledger: bên gọi ghi ``key.published``
    (``publish_leaf``) trong cùng transaction, sau khi ký xong.

    Phải chạy trong transaction. ``OrgNotConfigured`` khi tên tổ chức chưa đặt thật (``org_configured``);
    ``KeyStatementInvalid`` khi hàng đã có không qua kiểm (không bao giờ INSERT thay).
    Tuyên bố đã có thì không bao giờ đổi (bảng chỉ-thêm), nên đọc trước khi khóa là an toàn; chỉ đường tạo mới
    mới lấy ``LOCK_KEYSTMT`` và đọc lại dưới khóa.
    """
    if not conn.is_in_transaction():
        raise RuntimeError("tạo tuyên bố khóa phải chạy trong transaction của lần niêm phong")
    if not org_configured(settings):
        raise OrgNotConfigured("DXOS_ORG_NAME chưa được cấu hình")
    existing = await checked_statement_for(conn, key_version)
    if existing is not None:
        return existing, False
    await conn.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEYSTMT)
    existing = await checked_statement_for(conn, key_version)
    if existing is not None:
        return existing, False
    statement = build_statement(settings, version=key_version, public_key=public_key, valid_from=issued_at)
    await conn.execute(
        "INSERT INTO core.key_statements(key, version, statement, statement_sha256)"
        " VALUES ('seal-key', $1, $2::jsonb, $3)",
        key_version, json.dumps(statement, ensure_ascii=False), sha256_hex(canonical_bytes(statement)))
    return statement, True


async def publish_leaf(conn: asyncpg.Connection, statement: dict[str, Any], *, hmac_key: bytes) -> None:
    """Lá ledger ``key.published {key, version, statement_sha256}``, ``subject = "seal-key/v<n>"``."""
    v = statement["version"]
    digest = sha256_hex(canonical_bytes(statement))
    await append(conn, type="key.published", subject=f"seal-key/v{v}",
                 body={"key": "seal-key", "version": v, "statement_sha256": digest}, hmac_key=hmac_key)
