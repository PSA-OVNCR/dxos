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
from dxos_core.pii.job import PII_JOB, detectable
from dxos_core.records.service import _ts
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
            await _drop_staging(ctx, upload_id)
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
            await asyncio.to_thread(partial(ctx.store.move_to_quarantine, upload_id, data=data,
                                            delete_staging=False))
            await _finish(conn, ctx, job, up, status="INFECTED", event="object.infected", sha=sha,
                          reason=scan.signature)
            await _drop_staging(ctx, upload_id)
            return
        max_bytes = await _max_bytes(conn, ctx, up["app_id"], up["collection"])
        chk = await asyncio.to_thread(check_pdf, data, max_bytes)
        if not chk.ok:
            await asyncio.to_thread(partial(ctx.store.move_to_quarantine, upload_id, data=data,
                                            delete_staging=False))
            await _finish(conn, ctx, job, up, status="REJECTED", event="object.rejected", sha=sha,
                          reason=chk.reason)
            await _drop_staging(ctx, upload_id)
            return
        await asyncio.to_thread(partial(ctx.store.promote, upload_id, sha, data=data, delete_staging=False))
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
            await conn.execute(      # tệp đã có bản che (CAS): bản ghi mới dùng chung bản che đó
                "INSERT INTO object_refs(record_id, sha256, role)"
                " SELECT $1, redacted_sha256, 'redacted' FROM pii_redactions"
                " WHERE sha256 = $2 ON CONFLICT DO NOTHING",
                up["record_id"], sha)
            await conn.execute("UPDATE uploads SET status='CLEAN', sha256=$2, updated_at=now() WHERE id=$1",
                               upload_id, sha)
            await _enqueue_pii_scan(conn, up["app_id"], sha)
            await append(conn, type="object.clean", subject=str(upload_id),
                         body={"upload_id": str(upload_id), "sha256": sha, "size": len(data),
                               "record_id": str(up["record_id"])},
                         hmac_key=ctx.hmac_key, app_id=up["app_id"])
            await complete(conn, job.id)
        await _drop_staging(ctx, upload_id)


async def _enqueue_pii_scan(conn: asyncpg.Connection, app_id: str, sha: str) -> None:
    """Xếp việc ``pii_detect`` cùng transaction với ``object.clean`` (S1), nếu manifest đang hoạt động của app
    khai ``policies.pii.document_detect`` có loại bộ dò hỗ trợ và tệp này chưa được dò (CAS: cùng nội dung
    đến từ upload khác thì không dò lại)."""
    m = await get_active(conn, app_id)
    types = detectable(m.policies.pii.document_detect) if m else []
    if types and not await conn.fetchval("SELECT 1 FROM pii_scans WHERE sha256=$1", sha):
        await enqueue(conn, PII_JOB, {"sha256": sha})


async def _drop_staging(ctx: WorkerContext, upload_id: uuid.UUID) -> None:
    """Xóa bản staging **sau** khi DB đã commit; lỗi ở đây chỉ để lại rác, không mất dữ liệu."""
    try:
        await asyncio.to_thread(ctx.store.delete_staging, upload_id)
    except Exception:  # noqa: BLE001
        log.warning("không xóa được staging %s (sẽ còn rác trong bucket staging)", upload_id)


def upload_status(row: asyncpg.Record) -> dict:
    out = {"status": row["status"]}
    if row["status"] == "CLEAN":
        out["sha256"] = row["sha256"]
    elif row["status"] in ("INFECTED", "REJECTED"):
        out["reason"] = row["reason"]
    return out


async def list_uploads(conn: asyncpg.Connection, record_id: uuid.UUID, *,
                       expect_pii: bool = False) -> list[dict]:
    """Mọi upload của một bản ghi, cũ trước. ``sha256`` chỉ có khi CLEAN, ``reason`` chỉ khi INFECTED/REJECTED
    (đúng như ``upload_status``); không trả tên tệp (chỉ lưu hash), kích thước hay khóa lưu trữ.

    ``pii`` (Plan 04 Task 5): ``{"status", "findings", "redacted"}`` cho upload CLEAN **khi collection đòi dò
    PII tài liệu** (``expect_pii``); ``status`` là ``DONE``/``TOO_LARGE``/``FAILED`` theo ``pii_scans``, hoặc
    ``PENDING`` khi chưa có hàng nào; ``redacted`` là có bản che để tải (``variant=redacted``). Mọi trường hợp
    khác (chưa CLEAN, collection không dò) thì ``pii`` là ``null``."""
    rows = await conn.fetch(
        "SELECT u.id, u.status, u.sha256, u.reason, u.created_at, s.status AS scan_status, s.findings,"
        " r.sha256 IS NOT NULL AS redacted"
        " FROM uploads u LEFT JOIN pii_scans s ON s.sha256 = u.sha256"
        " LEFT JOIN pii_redactions r ON r.sha256 = u.sha256 WHERE u.record_id=$1"
        " ORDER BY u.created_at, u.id", record_id)
    out = []
    for row in rows:
        s = upload_status(row)
        pii = None
        if expect_pii and row["status"] == "CLEAN":
            pii = ({"status": "PENDING", "findings": 0, "redacted": False} if row["scan_status"] is None else
                   {"status": row["scan_status"], "findings": row["findings"], "redacted": row["redacted"]})
        out.append({"upload_id": str(row["id"]), "status": s["status"], "sha256": s.get("sha256"),
                    "reason": s.get("reason"), "created_at": _ts(row["created_at"]), "pii": pii})
    return out
