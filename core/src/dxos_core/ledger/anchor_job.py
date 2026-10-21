# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Việc nền ``anchor_sth``: lập STH (nếu payload chưa chỉ định) rồi đẩy lên repo neo.

- ``PUSH_FAILED`` → thử lại sau 60 giây (GitHub sự cố: neo xếp hàng, spec 11.3).
- ``ANCHOR_CONFLICT`` → việc ``FAILED`` ngay: repo neo có STH khác cùng kích thước, cần người xem.
- Lịch tự động: STH mới mỗi 10 phút nếu ledger có lá mới (``maybe_schedule``).
- Plan 02 Task 8: cùng commit với STH là khóa công khai (``signer.public_keys()``) và mọi tuyên bố khóa
  (bảng ``key_statements``). Lần thử lại của một STH đã ký không cần KMS: KMS khóa thì neo STH, tệp khóa để
  lần sau.
"""

import json
import logging
from pathlib import Path

import asyncpg
from dxos_proof.canonical import canonical_bytes, sha256_hex

from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, complete, enqueue, fail, retry_later
from dxos_core.kms.base import KmsUnavailable
from dxos_core.ledger.anchor import AnchorError, ensure_clone, publish_sth
from dxos_core.ledger.sth import get_sth, make_sth

log = logging.getLogger("dxos_core.ledger.anchor_job")
ANCHOR_JOB = "anchor_sth"
PUSH_RETRY_S = 60
AUTO_INTERVAL = "10 minutes"


async def process_anchor_job(ctx: WorkerContext, job: Job) -> None:
    s = ctx.settings
    async with ctx.pool.acquire() as conn:
        if "tree_size" in job.payload:
            th = await get_sth(conn, int(job.payload["tree_size"]))
            if th is None:
                raise ValueError(f"không có STH cỡ {job.payload['tree_size']}")
        else:
            th = await make_sth(conn, ctx.signer)
            # Ghi lại cỡ cây vào việc: lần thử lại (khi đẩy lỗi) dùng đúng STH này, không ký STH mới.
            await conn.execute("UPDATE jobs SET payload=$2::jsonb WHERE id=$1", job.id,
                               json.dumps({"tree_size": th.tree_size}))
        if not s.anchor_remote:
            log.info("chưa cấu hình DXOS_ANCHOR_REMOTE: STH %s đã ký nhưng không neo", th.tree_size)
            await complete(conn, job.id)
            return
        repo = Path(s.anchor_repo_dir)
        keys = await _public_keys(ctx)
        statements = await _statements(conn)
        try:
            await ensure_clone(s.anchor_remote, repo, s.anchor_git_ssh_command)
            commit = await publish_sth(th, repo, s.anchor_git_ssh_command, keys=keys, statements=statements)
        except AnchorError as exc:
            if exc.code == "ANCHOR_CONFLICT":
                log.error("XUNG ĐỘT NEO tại STH %s: %s", th.tree_size, exc)
                await fail(conn, job.id, str(exc))
            else:
                log.warning("neo STH %s lỗi, thử lại sau %ss: %s", th.tree_size, PUSH_RETRY_S, exc)
                await retry_later(conn, job.id, PUSH_RETRY_S, str(exc)[:500])
            return
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO anchors(tree_size, repo, commit_sha) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                th.tree_size, s.anchor_remote, commit)
            await complete(conn, job.id)


async def _public_keys(ctx: WorkerContext) -> dict | None:
    if ctx.signer is None:
        return None
    try:
        return await ctx.signer.public_keys()
    except KmsUnavailable as exc:
        log.warning("KMS không trả lời: neo STH lần này không kèm tệp khóa công khai (%s)", exc)
        return None


async def _statements(conn: asyncpg.Connection) -> list[dict]:
    """Mọi tuyên bố khóa; hàng có ``statement_sha256`` không khớp nội dung thì không công bố (log ERROR)."""
    out = []
    rows = await conn.fetch(
        "SELECT version, statement, statement_sha256 FROM key_statements ORDER BY key, version")
    for r in rows:
        st = json.loads(r["statement"]) if isinstance(r["statement"], str) else r["statement"]
        if sha256_hex(canonical_bytes(st)) != r["statement_sha256"]:
            log.error("tuyên bố khóa v%s không khớp statement_sha256: không công bố", r["version"])
            continue
        out.append(st)
    return out


async def maybe_schedule(conn: asyncpg.Connection) -> int | None:
    """Xếp một việc neo nếu ledger có lá mới, STH gần nhất đã cũ và chưa có việc neo đang chờ."""
    due = await conn.fetchval(
        f"""
        SELECT (SELECT count(*) FROM ledger_entries) > COALESCE((SELECT max(tree_size) FROM tree_heads), 0)
           AND NOT EXISTS (SELECT 1 FROM jobs WHERE kind = $1 AND state IN ('QUEUED', 'RUNNING'))
           AND COALESCE((SELECT max(created_at) FROM jobs WHERE kind = $1), 'epoch')
               < now() - interval '{AUTO_INTERVAL}'
        """, ANCHOR_JOB)  # noqa: S608 (AUTO_INTERVAL là hằng số)
    return await enqueue(conn, ANCHOR_JOB, {}) if due else None
