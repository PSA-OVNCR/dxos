# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Áp dụng migration SQL ``NNN_ten.sql`` theo thứ tự, ghi vết trong ``core.schema_migrations``.

- Chạy bằng role ``dxos_owner``; mỗi tệp chạy trong một transaction (lỗi thì không để lại gì).
- Khóa advisory để hai tiến trình khởi động cùng lúc không chạy chồng.
- Tệp đã áp dụng mà bị sửa nội dung, hoặc DB có migration mà mã không có: dừng với ``MigrationError``.

Dòng lệnh (entrypoint của container trust-core-api)::

    DXOS_MIGRATE_DATABASE_URL=postgresql://dxos_owner:...@core-db:5432/dxos \\
    DXOS_CORE_DB_PASSWORD=... python -m dxos_core.db.migrate
"""

import asyncio
import hashlib
import os
import re
import sys
from pathlib import Path

import asyncpg

MIGRATION_NAME = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")
LOCK_KEY = 724000  # khác khóa ghi ledger (724001, Task 9)
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_BOOTSTRAP = """
CREATE SCHEMA IF NOT EXISTS core;
CREATE TABLE IF NOT EXISTS core.schema_migrations (
    filename   text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


class MigrationError(RuntimeError):
    """Trạng thái migration của DB không khớp với tệp trong mã nguồn."""


def discover(migrations_dir: Path) -> list[tuple[str, str, str]]:
    """Trả về ``[(tên tệp, nội dung, sha256)]`` sắp theo tên."""
    found = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if not MIGRATION_NAME.fullmatch(path.name):
            raise MigrationError(f"tên migration không đúng dạng NNN_ten.sql: {path.name}")
        sql = path.read_text(encoding="utf-8")
        found.append((path.name, sql, hashlib.sha256(sql.encode("utf-8")).hexdigest()))
    return found


async def apply_migrations(dsn: str, migrations_dir: Path, *, until: str | None = None) -> list[str]:
    """Áp dụng các migration chưa chạy; trả về danh sách tên tệp vừa áp dụng.

    ``until``: tiền tố số (ví dụ ``"002"``) của migration cuối cùng được áp; các tệp sau đó bỏ qua.
    Dùng cho test thử migration mới trên DB dừng ở mốc cũ.
    Không có tệp nào mang tiền tố này → ``MigrationError``.
    """
    files = discover(migrations_dir)
    if until is not None:
        if not any(name.startswith(f"{until}_") for name, _, _ in files):
            raise MigrationError(f"không có migration {until}_*.sql")
        files = [f for f in files if f[0][:3] <= until]
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
        await conn.execute(_BOOTSTRAP)
        applied = {r["filename"]: r["sha256"]
                   for r in await conn.fetch("SELECT filename, sha256 FROM core.schema_migrations")}
        unknown = sorted(set(applied) - {name for name, _, _ in files})
        if unknown:
            raise MigrationError(f"DB đã có migration mà mã nguồn không có: {', '.join(unknown)}")
        done: list[str] = []
        for name, sql, digest in files:
            if name in applied:
                if applied[name] != digest:
                    raise MigrationError(
                        f"{name} đã bị sửa sau khi áp dụng (sha256 khác); hãy tạo migration mới")
                continue
            async with conn.transaction():
                await conn.execute("SET LOCAL search_path TO core, public")
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO core.schema_migrations(filename, sha256) VALUES ($1, $2)", name, digest)
            done.append(name)
        return done
    finally:
        await conn.close()  # đóng kết nối cũng nhả khóa advisory


async def set_core_password(conn: asyncpg.Connection, password: str) -> None:
    """Đặt mật khẩu đăng nhập cho role ``dxos_core`` (role do 001_core.sql tạo, không mật khẩu)."""
    if not password:
        raise ValueError("mật khẩu dxos_core rỗng")
    stmt = await conn.fetchval(
        "SELECT format('ALTER ROLE dxos_core WITH LOGIN PASSWORD %L', $1::text)", password)
    await conn.execute(stmt)


async def _main() -> int:
    dsn = os.environ.get("DXOS_MIGRATE_DATABASE_URL")
    if not dsn:
        print("thiếu DXOS_MIGRATE_DATABASE_URL (DSN của dxos_owner)", file=sys.stderr)
        return 2
    migrations_dir = Path(os.environ.get("DXOS_MIGRATIONS_DIR", str(DEFAULT_MIGRATIONS_DIR)))
    done = await apply_migrations(dsn, migrations_dir)
    print(f"migration: đã áp dụng {done or 'không có tệp mới'}")
    password = os.environ.get("DXOS_CORE_DB_PASSWORD")
    if password:
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            await set_core_password(conn, password)
        finally:
            await conn.close()
        print("migration: đã đặt mật khẩu role dxos_core")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
