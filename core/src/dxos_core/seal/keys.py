# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tuyên bố khóa ``seal-key`` (spec 25.3) — khung tối thiểu do Plan 02 Task 6 tạo.

Task 6 chỉ cần đủ để kiểm trước task cuối (R-1): ngoại lệ, kiểm thời hạn và đọc tuyên bố đã có.
Task 7 thêm ``build_statement`` và ``ensure_key_statement`` (tạo tuyên bố ở lần niêm phong đầu của mỗi phiên
bản khóa, dưới ``pg_advisory_xact_lock(LOCK_KEYSTMT)``, ghi ledger ``key.published``).

Tuyên bố **không tự ký**; nó được bảo vệ bằng lá ledger ``key.published`` và tệp trong repo neo.
"""

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from dxos_core.settings import ORG_NAME_DEFAULT

__all__ = ["LOCK_KEYSTMT", "ORG_NAME_DEFAULT", "STATEMENT_FORMAT", "OrgNotConfigured", "SealKeyExpired",
           "latest_statement", "statement_for", "within_validity"]

STATEMENT_FORMAT = "dxos-key-statement/1"
# Khóa advisory của việc tạo tuyên bố khóa (Task 7). Khác 724000 (migrate), 724001 (ledger), 724100 (LOCK_WF).
LOCK_KEYSTMT = 724101


class SealKeyExpired(Exception):  # noqa: N818 (tên theo spec 25.3)
    """Thời điểm niêm phong nằm ngoài ``valid_from..valid_until`` của tuyên bố khóa: cần xoay khóa."""


class OrgNotConfigured(Exception):  # noqa: N818
    """``DXOS_ORG_NAME`` còn giá trị mặc định: không bao giờ ghi tên giữ chỗ vào tuyên bố chỉ-thêm."""


def _parse(ts: str | datetime) -> datetime:
    if isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("thời điểm phải có múi giờ")
    return dt.astimezone(UTC)


def within_validity(statement: dict[str, Any], at: str | datetime) -> bool:
    """``valid_from ≤ at ≤ valid_until``, so sánh sau khi parse cả ba thành datetime UTC (không so chuỗi)."""
    return _parse(statement["valid_from"]) <= _parse(at) <= _parse(statement["valid_until"])


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
