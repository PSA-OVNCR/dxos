# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cấp số văn bản theo app. Gọi trong cùng transaction với việc tạo bản ghi: rollback thì số không bị mất.

Đánh số theo năm (spec 25.4, P2-D26): khóa của năm là ``"<name>@<năm>"`` trong cùng bảng ``sequences``.
"""

import re

import asyncpg

_TOKEN = re.compile(r"\{n(?::0([2-9]))?\}")
_YEARLY_LOCK = "dxos.sequences.yearly"


def format_sequence(fmt: str | None, n: int) -> str:
    """``{n}`` → ``str(n)``; ``{n:0W}`` → số đệm 0 đủ W chữ số. ``fmt`` rỗng → ``str(n)``."""
    if not fmt:
        return str(n)
    return _TOKEN.sub(lambda m: f"{n:0{int(m.group(1))}d}" if m.group(1) else str(n), fmt)


async def _bump(conn: asyncpg.Connection, app_id: str, key: str) -> int:
    return await conn.fetchval(
        "INSERT INTO sequences(app_id, name, value) VALUES ($1, $2, 1)"
        " ON CONFLICT (app_id, name) DO UPDATE SET value = sequences.value + 1 RETURNING value",
        app_id, key)


async def next_sequence(conn: asyncpg.Connection, app_id: str, name: str, *, year: int | None = None) -> int:
    """Số kế tiếp của ``name``. ``year`` khác None: bộ đếm riêng của năm đó.

    Lần đầu tạo khóa của một năm mà chưa có khóa ``name@…`` nào (trường vừa chuyển ``never`` → ``yearly``):
    bắt đầu từ giá trị của khóa cũ ``name`` + 1, để không trùng số trong năm chuyển chế độ.
    Đã có khóa của năm khác: bắt đầu từ 1.
    """
    if year is None:
        return await _bump(conn, app_id, name)
    key = f"{name}@{year}"
    async with conn.transaction():          # savepoint nếu bên gọi đã mở transaction
        hit = await conn.fetchval(
            "UPDATE sequences SET value = value + 1 WHERE app_id=$1 AND name=$2 RETURNING value", app_id, key)
        if hit is not None:
            return hit
        # Khóa của năm chưa có: tuần tự hóa việc tạo để hai lần tạo đầu tiên đồng thời không cùng đọc khóa cũ.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2 || '/' || $3))",
                           _YEARLY_LOCK, app_id, name)
        start = await conn.fetchval(
            "SELECT CASE WHEN EXISTS"
            " (SELECT 1 FROM sequences WHERE app_id=$1 AND starts_with(name, $2 || '@')) THEN 1"
            " ELSE COALESCE((SELECT value FROM sequences WHERE app_id=$1 AND name=$2), 0) + 1 END",
            app_id, name)
        return await conn.fetchval(
            "INSERT INTO sequences(app_id, name, value) VALUES ($1, $2, $3)"
            " ON CONFLICT (app_id, name) DO UPDATE SET value = sequences.value + 1 RETURNING value",
            app_id, key, start)
