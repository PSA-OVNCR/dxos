# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Nạp manifest ở trạng thái ACTIVE **tạm thời** cho tới khi có installer (Plan 02).

    python -m dxos_core.registry.seed apps/<app>/manifest.yaml ...   # dùng DXOS_DATABASE_URL

Mỗi lần nạp đều ghi ledger (``app.submitted`` rồi ``app.installed``), actor là ``--actor``.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import yaml

from dxos_core.db.pool import SEARCH_PATH
from dxos_core.registry.store import get_active, save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_core.settings import read_secret


async def seed(dsn: str, paths: list[Path], actor: str, hmac_key: bytes) -> list[str]:
    conn = await asyncpg.connect(dsn, server_settings={"search_path": SEARCH_PATH})
    done = []
    try:
        for p in paths:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            m = validate_manifest(raw)
            current = await get_active(conn, m.app.id)
            if current is not None and current.app.version == m.app.version:
                done.append(f"{m.app.id}@{m.app.version} (đã ACTIVE)")
                continue
            await save_manifest(conn, m, raw, "PENDING", actor, hmac_key=hmac_key)
            await save_manifest(conn, m, raw, "ACTIVE", actor, hmac_key=hmac_key)
            done.append(f"{m.app.id}@{m.app.version}")
    finally:
        await conn.close()
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dxos_core.registry.seed")
    ap.add_argument("manifests", nargs="+", type=Path)
    ap.add_argument("--actor", default="seed")
    args = ap.parse_args(argv)
    dsn = os.environ.get("DXOS_DATABASE_URL")
    key_file = os.environ.get("DXOS_ACTOR_HMAC_KEY_FILE")
    if not dsn or not key_file:
        print("cần DXOS_DATABASE_URL và DXOS_ACTOR_HMAC_KEY_FILE", file=sys.stderr)
        return 2
    for line in asyncio.run(seed(dsn, args.manifests, args.actor, read_secret(Path(key_file)).encode())):
        print(f"seed: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
