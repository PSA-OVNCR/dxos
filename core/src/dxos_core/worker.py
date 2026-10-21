# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tiến trình trust-core-worker: lấy việc từ bảng ``jobs`` và chạy (quét tệp, neo STH, niêm phong).

- Mỗi vòng: kiểm DB, ghi heartbeat (healthcheck của container đọc tệp này), lấy và chạy một việc.
- Việc lỗi không làm dừng worker: ghi ``last_error``, thử lại với backoff;
  quá ``MAX_ATTEMPTS`` thì ``FAILED``.

Chạy: ``python -m dxos_core.worker``; healthcheck: ``python -m dxos_core.worker --check``.
"""

import argparse
import asyncio
import logging
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import asyncpg

from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, claim, fail, retry_later
from dxos_core.ledger.anchor_job import ANCHOR_JOB, maybe_schedule, process_anchor_job
from dxos_core.objects.ingest import SCAN_JOB, process_scan_job
from dxos_core.seal.job import process_seal_job
from dxos_core.seal.service import SEAL_JOB
from dxos_core.settings import Settings, read_secret

log = logging.getLogger("dxos_core.worker")

DEFAULT_HEARTBEAT = Path(tempfile.gettempdir()) / "dxos-worker.heartbeat"
HEARTBEAT_MAX_AGE = 60.0
MAX_ATTEMPTS = 10
RENEW_EVERY_S = 3600.0
_DB_ERRORS = (OSError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError)

Handler = Callable[[WorkerContext, Job], Awaitable[None]]
HANDLERS: dict[str, Handler] = {SCAN_JOB: process_scan_job, ANCHOR_JOB: process_anchor_job,
                                SEAL_JOB: process_seal_job}


def touch_heartbeat(path: Path) -> None:
    path.touch()


def heartbeat_fresh(path: Path, *, max_age: float = HEARTBEAT_MAX_AGE) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= max_age
    except FileNotFoundError:
        return False


async def run_once(ctx: WorkerContext) -> bool:
    """Lấy và chạy tối đa một việc. Trả True nếu đã có việc để chạy."""
    async with ctx.pool.acquire() as conn:
        job = await claim(conn, list(HANDLERS))
    if job is None:
        return False
    try:
        await HANDLERS[job.kind](ctx, job)
    except Exception as exc:  # noqa: BLE001 (một việc hỏng không được làm dừng worker)
        err = f"{type(exc).__name__}: {exc}"[:500]
        log.exception("việc %s #%s lỗi (lần %s)", job.kind, job.id, job.attempts)
        async with ctx.pool.acquire() as conn:
            if job.attempts >= MAX_ATTEMPTS:
                await fail(conn, job.id, err)
            else:
                await retry_later(conn, job.id, min(3600, 30 * 2 ** (job.attempts - 1)), err)
    return True


def _make_context(settings: Settings, pool: asyncpg.Pool) -> WorkerContext:
    from dxos_core.kms.openbao import OpenBaoTransit
    from dxos_core.objects.storage import ObjectStore

    return WorkerContext(pool=pool, store=ObjectStore(settings), settings=settings,
                         hmac_key=read_secret(settings.actor_hmac_key_file).encode("utf-8"),
                         signer=OpenBaoTransit(settings.openbao_addr,
                                               read_secret(settings.openbao_token_file)))


async def _renew_token(ctx: WorkerContext) -> None:
    renew = getattr(ctx.signer, "renew_self", None)
    if renew is None:
        return
    try:
        ttl = await renew()
        log.info("đã gia hạn token OpenBao, TTL %ss", ttl)
    except Exception as exc:  # noqa: BLE001 (OpenBao khóa/không tới được: lần sau thử lại)
        log.warning("không gia hạn được token OpenBao: %s", exc)


async def run(settings: Settings, *, heartbeat: Path = DEFAULT_HEARTBEAT, interval: float = 5.0,
              once: bool = False) -> None:
    pool = await create_pool(settings.database_url, min_size=0, max_size=4)
    ctx: WorkerContext | None = None
    buckets_ready = False
    last_renew = 0.0
    try:
        while True:
            try:
                async with pool.acquire(timeout=5) as conn:
                    await conn.fetchval("SELECT 1")
            except _DB_ERRORS as exc:
                log.warning("DB chưa sẵn sàng: %s", type(exc).__name__)
                db_ok = False
            else:
                touch_heartbeat(heartbeat)
                db_ok = True
            if db_ok:
                try:
                    if ctx is None:
                        ctx = _make_context(settings, pool)
                    if not buckets_ready:
                        try:
                            await asyncio.to_thread(ctx.store.ensure_buckets)
                            buckets_ready = True
                        except Exception as exc:  # noqa: BLE001 (S3 chưa lên thì lần sau thử lại)
                            log.warning("S3 chưa sẵn sàng: %s", type(exc).__name__)
                    if not once and time.monotonic() - last_renew > RENEW_EVERY_S:
                        last_renew = time.monotonic()
                        await _renew_token(ctx)
                    if buckets_ready and not once:
                        if settings.anchor_remote:
                            async with pool.acquire() as conn:
                                await maybe_schedule(conn)
                        while await run_once(ctx):
                            touch_heartbeat(heartbeat)
                except Exception:  # noqa: BLE001 (DB rớt giữa vòng: ghi log, vòng sau làm tiếp)
                    log.exception("vòng worker lỗi; thử lại sau %ss", interval)
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
