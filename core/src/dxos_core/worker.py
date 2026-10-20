# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tiến trình trust-core-worker (khung, Task 8).

Hiện chỉ kiểm tra kết nối DB định kỳ và ghi heartbeat để Docker healthcheck đọc.
Task 14 bổ sung vòng lấy việc từ bảng ``jobs`` (``FOR UPDATE SKIP LOCKED``).

Chạy: ``python -m dxos_core.worker``; healthcheck: ``python -m dxos_core.worker --check``.
"""

import argparse
import asyncio
import logging
import sys
import tempfile
import time
from pathlib import Path

import asyncpg

from dxos_core.db.pool import create_pool
from dxos_core.settings import Settings

log = logging.getLogger("dxos_core.worker")

DEFAULT_HEARTBEAT = Path(tempfile.gettempdir()) / "dxos-worker.heartbeat"
HEARTBEAT_MAX_AGE = 60.0
_DB_ERRORS = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)


def touch_heartbeat(path: Path) -> None:
    path.touch()


def heartbeat_fresh(path: Path, *, max_age: float = HEARTBEAT_MAX_AGE) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age
    except FileNotFoundError:
        return False


async def run(settings: Settings, *, heartbeat: Path = DEFAULT_HEARTBEAT, interval: float = 5.0,
              once: bool = False) -> None:
    pool = await create_pool(settings.database_url, min_size=0, max_size=2)
    try:
        while True:
            try:
                async with pool.acquire(timeout=5) as conn:
                    await conn.fetchval("SELECT 1")
            except _DB_ERRORS as exc:
                log.warning("DB chưa sẵn sàng: %s", type(exc).__name__)
            else:
                touch_heartbeat(heartbeat)
            if once:
                return
            await asyncio.sleep(interval)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dxos_core.worker")
    parser.add_argument("--check", action="store_true", help="healthcheck: heartbeat còn mới thì thoát 0")
    parser.add_argument("--heartbeat", type=Path, default=DEFAULT_HEARTBEAT)
    args = parser.parse_args(argv)
    if args.check:
        return 0 if heartbeat_fresh(args.heartbeat) else 1
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(Settings(), heartbeat=args.heartbeat))
    return 0


if __name__ == "__main__":
    sys.exit(main())
