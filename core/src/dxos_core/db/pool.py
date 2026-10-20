# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Pool kết nối asyncpg của lõi. Mọi bảng nằm trong schema ``core`` (spec 10.1)."""

import asyncpg

SEARCH_PATH = "core"


async def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Tạo pool tới ``dsn`` với ``search_path=core``.

    ``min_size=0`` cho phép tạo pool khi DB chưa sẵn sàng (kết nối khi cần);
    app dùng chế độ này để ``/healthz`` vẫn sống còn ``/readyz`` báo 503.
    """
    return await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        server_settings={"search_path": SEARCH_PATH, "application_name": "dxos-core"},
    )
