# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cấp số văn bản theo app. Gọi trong cùng transaction với việc tạo bản ghi: rollback thì số không bị mất."""

import asyncpg


async def next_sequence(conn: asyncpg.Connection, app_id: str, name: str) -> int:
    return await conn.fetchval(
        "INSERT INTO sequences(app_id, name, value) VALUES ($1, $2, 1)"
        " ON CONFLICT (app_id, name) DO UPDATE SET value = sequences.value + 1 RETURNING value",
        app_id, name)
