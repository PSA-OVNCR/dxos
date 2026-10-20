# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Hàng đợi việc: ``QUEUED → RUNNING → DONE | FAILED``; ``RUNNING`` quá 5 phút (worker chết) được lấy lại."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import asyncpg

STALE_AFTER = "5 minutes"


@dataclass
class Job:
    id: int
    kind: str
    payload: dict
    attempts: int


async def enqueue(conn: asyncpg.Connection, kind: str, payload: dict,
                  run_after: datetime | None = None) -> int:
    return await conn.fetchval(
        "INSERT INTO jobs(kind, payload, run_after) VALUES ($1, $2::jsonb, COALESCE($3, now())) RETURNING id",
        kind, json.dumps(payload, ensure_ascii=False), run_after)


async def claim(conn: asyncpg.Connection, kinds: Sequence[str]) -> Job | None:
    row = await conn.fetchrow(
        f"""
        UPDATE jobs SET state='RUNNING', attempts=attempts+1, updated_at=now()
        WHERE id = (
            SELECT id FROM jobs
            WHERE kind = ANY($1::text[]) AND run_after <= now()
              AND (state = 'QUEUED' OR (state = 'RUNNING' AND updated_at < now() - interval '{STALE_AFTER}'))
            ORDER BY run_after, id
            FOR UPDATE SKIP LOCKED
            LIMIT 1)
        RETURNING id, kind, payload, attempts
        """,  # noqa: S608 (STALE_AFTER là hằng số)
        list(kinds))
    if row is None:
        return None
    payload = row["payload"]
    return Job(row["id"], row["kind"], json.loads(payload) if isinstance(payload, str) else payload,
               row["attempts"])


async def complete(conn: asyncpg.Connection, job_id: int) -> None:
    await conn.execute("UPDATE jobs SET state='DONE', updated_at=now() WHERE id=$1", job_id)


async def retry_later(conn: asyncpg.Connection, job_id: int, delay_s: int, error: str | None = None) -> None:
    await conn.execute(
        "UPDATE jobs SET state='QUEUED', run_after=now() + make_interval(secs => $2), updated_at=now(),"
        " last_error=COALESCE($3, last_error) WHERE id=$1", job_id, float(delay_s), error)


async def fail(conn: asyncpg.Connection, job_id: int, error: str) -> None:
    await conn.execute("UPDATE jobs SET state='FAILED', last_error=$2, updated_at=now() WHERE id=$1",
                       job_id, error)
