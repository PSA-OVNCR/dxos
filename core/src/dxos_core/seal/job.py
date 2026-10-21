# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Việc nền ``seal``: ký ảnh chụp của bản ghi ``SEAL_PENDING`` (Plan 02 Task 7; spec 13.2, 25.3).

- KMS không sẵn sàng, khóa hết hạn, tên tổ chức chưa cấu hình: **không bao giờ** ``fail``. Thử lại sau
  ``min(900, 30 * 2 ** min(attempts, 5))`` giây, ghi log WARNING. Admin thấy số bản ghi chờ ở trạng thái
  quản trị (``seal_pending``).
- Tuyên bố khóa trong DB không qua kiểm (``KeyStatementInvalid``, bị sửa ngoài lõi): cũng chờ như trên, nhưng
  log ERROR; bản ghi giữ ``SEAL_PENDING`` và tự niêm phong tiếp khi admin đã sửa (rà soát cuối, m3).
- Lỗi khác đi đường lỗi chung của worker (backoff, quá ``MAX_ATTEMPTS`` thì ``FAILED``).
"""

import logging
import uuid

from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, complete, retry_later
from dxos_core.kms.base import KmsUnavailable
from dxos_core.seal.keys import KeyStatementInvalid, OrgNotConfigured, SealKeyExpired
from dxos_core.seal.service import seal_record

log = logging.getLogger("dxos_core.seal.job")

MAX_DELAY_S = 900
# Lỗi "chờ được": chỉ cần người vận hành mở khóa OpenBao, xoay khóa hoặc đặt DXOS_ORG_NAME.
WAITABLE = (KmsUnavailable, SealKeyExpired, OrgNotConfigured, KeyStatementInvalid)


def backoff_s(attempts: int) -> int:
    return min(MAX_DELAY_S, 30 * 2 ** min(attempts, 5))


async def process_seal_job(ctx: WorkerContext, job: Job) -> None:
    rid = uuid.UUID(job.payload["record_id"])
    try:
        async with ctx.pool.acquire() as conn:
            out = await seal_record(conn, signer=ctx.signer, hmac_key=ctx.hmac_key, settings=ctx.settings,
                                    record_id=rid)
    except WAITABLE as exc:
        delay = backoff_s(job.attempts)
        level = logging.ERROR if isinstance(exc, KeyStatementInvalid) else logging.WARNING
        log.log(level, "chưa niêm phong được bản ghi %s (%s: %s); thử lại sau %ss", rid, type(exc).__name__,
                exc, delay)
        async with ctx.pool.acquire() as conn, conn.transaction():
            await retry_later(conn, job.id, delay, f"{type(exc).__name__}: {exc}"[:500])
            # Lần chờ KMS không ăn vào số lần thử dành cho lỗi khác: không thì sau một đợt KMS khóa dài,
            # một lỗi thoáng qua bất kỳ làm việc FAILED ngay và bản ghi kẹt SEAL_PENDING.
            await conn.execute("UPDATE core.jobs SET attempts=LEAST(attempts, 5) WHERE id=$1", job.id)
        return
    async with ctx.pool.acquire() as conn:
        await complete(conn, job.id)
    log.info("việc niêm phong #%s: bản ghi %s %s", job.id, rid, out.state)
