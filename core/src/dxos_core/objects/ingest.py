# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Luồng một tệp: staging → quét AV → kiểm PDF → CAS (spec 10.2, 13.1; Plan 01 Task 14).

Thứ tự D1: **quét AV trước**, kiểm PDF sau, để mọi mã độc (kể cả tệp không phải PDF) đều bị cách ly
và ghi ``object.infected`` thay vì chỉ bị ``REJECTED``.
ClamAV lỗi → việc được thử lại sau 30 giây, upload vẫn ``STAGING`` (fail-closed, F8, AT-20).
"""

import asyncio
import hashlib
import logging
import unicodedata
import uuid
from functools import partial

import asyncpg

from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, complete, enqueue, retry_later
from dxos_core.ledger.log import append
from dxos_core.objects.clamd import ScannerUnavailable, clamd_version, instream_scan
from dxos_core.objects.pdfcheck import check_pdf
from dxos_core.registry.store import get_active

log = logging.getLogger("dxos_core.objects.ingest")
SCAN_JOB = "scan"
CLAMD_RETRY_S = 30


def name_hash(filename: str) -> str:
    """Tên tệp gốc chỉ được lưu dạng hash (spec 10.1)."""
    return hashlib.sha256(unicodedata.normalize("NFC", filename).encode("utf-8")).hexdigest()


async def register_upload(conn: asyncpg.Connection, *, upload_id: uuid.UUID, record_id: uuid.UUID,
                          app_id: str, filename: str, size: int, declared_type: str | None, actor_sub: str,
                          hmac_key: bytes) -> None:
    """Ghi upload ``STAGING``, xếp việc quét và ghi ledger ``upload.staged`` trong một transaction."""
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO uploads(id, record_id, staging_key, original_name_hash, size, declared_type)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            upload_id, record_id, str(upload_id), name_hash(filename), size, declared_type)
        await enqueue(conn, SCAN_JOB, {"upload_id": str(upload_id)})
        await append(conn, type="upload.staged", subject=str(upload_id),
                     body={"upload_id": str(upload_id), "record_id": str(record_id), "size": size},
                     hmac_key=hmac_key, app_id=app_id, actor_sub=actor_sub)


async def _max_bytes(conn: asyncpg.Connection, ctx: WorkerContext, app_id: str, collection: str) -> int:
    m = await get_active(conn, app_id)
    spec = m.collections.get(collection) if m else None
    mb = spec.attachments.max_mb if spec and spec.attachments else ctx.settings.max_upload_mb_default
    return mb * 2**20


async def _finish(conn: asyncpg.Connection, ctx: WorkerContext, job: Job, up: asyncpg.Record, *, status: str,
                  event: str, sha: str, reason: str | None) -> None:
    async with conn.transaction():
        await conn.execute("UPDATE uploads SET status=$2, sha256=$3, reason=$4, updated_at=now() WHERE id=$1",
                           up["id"], status, sha, reason)
        await append(conn, type=event, subject=str(up["id"]),
                     body={"upload_id": str(up["id"]), "sha256": sha, "reason": reason},
                     hmac_key=ctx.hmac_key, app_id=up["app_id"])
        await complete(conn, job.id)


async def process_scan_job(ctx: WorkerContext, job: Job) -> None:
    upload_id = uuid.UUID(str(job.payload["upload_id"]))       # payload hỏng → ValueError, worker ghi lỗi
    async with ctx.pool.acquire() as conn:
        up = await conn.fetchrow(
            "SELECT u.*, r.app_id, r.collection FROM uploads u JOIN records r ON r.id = u.record_id"
            " WHERE u.id=$1",
            upload_id)
        if up is None:
            raise ValueError(f"upload {upload_id} không tồn tại")
        if up["status"] != "STAGING":                          # đã xử lý (việc chạy lại sau khi worker chết)
            await complete(conn, job.id)
            return
        data = await asyncio.to_thread(ctx.store.read_staging, upload_id)
        sha = hashlib.sha256(data).hexdigest()
        try:
            scan = await instream_scan(ctx.settings.clamd_host, ctx.settings.clamd_port, data)
        except ScannerUnavailable as exc:
            log.warning("ClamAV không sẵn sàng, thử lại sau %ss: %s", CLAMD_RETRY_S, exc)
            await retry_later(conn, job.id, CLAMD_RETRY_S, str(exc))
            return
        if not scan.clean:
            await asyncio.to_thread(partial(ctx.store.move_to_quarantine, upload_id, data=data))
            await _finish(conn, ctx, job, up, status="INFECTED", event="object.infected", sha=sha,
                          reason=scan.signature)
            return
        max_bytes = await _max_bytes(conn, ctx, up["app_id"], up["collection"])
        chk = await asyncio.to_thread(check_pdf, data, max_bytes)
        if not chk.ok:
            await asyncio.to_thread(partial(ctx.store.move_to_quarantine, upload_id, data=data))
            await _finish(conn, ctx, job, up, status="REJECTED", event="object.rejected", sha=sha,
                          reason=chk.reason)
            return
        await asyncio.to_thread(partial(ctx.store.promote, upload_id, sha, data=data))
        try:
            version = await clamd_version(ctx.settings.clamd_host, ctx.settings.clamd_port)
        except ScannerUnavailable:
            version = None
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO objects(sha256, size, mime_sniffed, status, scanner_version, scanned_at,"
                " storage_key) VALUES ($1, $2, 'application/pdf', 'CLEAN', $3, now(), $4)"
                " ON CONFLICT (sha256) DO NOTHING",
                sha, len(data), version, f"{ctx.settings.s3_bucket_objects}/{sha}")
            await conn.execute(
                "INSERT INTO object_refs(record_id, sha256, role) VALUES ($1, $2, 'original')"
                " ON CONFLICT DO NOTHING",
                up["record_id"], sha)
            await conn.execute("UPDATE uploads SET status='CLEAN', sha256=$2, updated_at=now() WHERE id=$1",
                               upload_id, sha)
            await append(conn, type="object.clean", subject=str(upload_id),
                         body={"upload_id": str(upload_id), "sha256": sha, "size": len(data),
                               "record_id": str(up["record_id"])},
                         hmac_key=ctx.hmac_key, app_id=up["app_id"])
            await complete(conn, job.id)


def upload_status(row: asyncpg.Record) -> dict:
    out = {"status": row["status"]}
    if row["status"] == "CLEAN":
        out["sha256"] = row["sha256"]
    elif row["status"] in ("INFECTED", "REJECTED"):
        out["reason"] = row["reason"]
    return out

