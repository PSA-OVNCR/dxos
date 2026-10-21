# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Route tệp: tải lên vào staging, xem trạng thái kiểm dịch, tải tệp sạch (Plan 01 Task 14).

- Không có route nào đọc staging hay quarantine (AT-04).
- Chỉ trả tệp ``CLEAN`` khi người gọi được ``read`` một bản ghi tham chiếu tới nó (F1).
"""

import asyncio
import logging
import re
import uuid

import asyncpg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile

from dxos_core.errors import ProblemError
from dxos_core.identity.deps import require_principal
from dxos_core.identity.jwt import Principal
from dxos_core.ledger.log import append
from dxos_core.objects.ingest import register_upload, upload_status
from dxos_core.objects.storage import IntegrityError
from dxos_core.policy.pdp import decide
from dxos_core.records import service
from dxos_core.records.router import ctx_dep
from dxos_core.registry.store import get_active

log = logging.getLogger("dxos_core.objects.router")
router = APIRouter(tags=["objects"])
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FORM_OVERHEAD = 64 * 1024


def _too_large(limit: int) -> ProblemError:
    return ProblemError(413, "payload-too-large", "Payload Too Large", f"attachment limit is {limit} bytes")


def _not_open() -> ProblemError:
    return ProblemError(409, "record-not-open", "Record is not open for attachments",
                        "record is in a running workflow or sealed")


def _drop_staging_quietly(store, upload_id: uuid.UUID) -> None:
    """Xóa bản staging của upload bị từ chối; lỗi ở đây chỉ để lại rác trong bucket staging."""
    try:
        store.delete_staging(upload_id)
    except Exception:  # noqa: BLE001
        log.warning("không xóa được staging %s của upload bị từ chối", upload_id)


def _put_staging(store, upload_id: uuid.UUID, data: bytes) -> None:
    try:
        store.put_staging(upload_id, data)
    except ClientError as exc:                   # bucket chưa có (worker chưa khởi động lần nào)
        if exc.response.get("Error", {}).get("Code") != "NoSuchBucket":
            raise
        store.ensure_buckets()
        store.put_staging(upload_id, data)


@router.post("/api/v1/apps/{app}/collections/{col}/records/{rid}/attachments", status_code=202)
async def upload_attachment(app: str, col: str, rid: str, request: Request,
                            p: Principal = Depends(require_principal)) -> JSONResponse:  # noqa: B008
    """Kiểm quyền (giữ kết nối DB thật ngắn) → nhận thân request → ghi staging → ghi upload (kết nối mới).

    Không giữ kết nối DB trong lúc client gửi tệp: 10 upload chậm không được làm cạn pool.
    """
    pool, hmac_key, settings = request.app.state.pool, request.app.state.hmac_key, request.app.state.settings
    async with pool.acquire() as conn:
        ctx = service.Ctx(conn=conn, principal=p, hmac_key=hmac_key, timezone=settings.timezone)
        m, spec = await service.load_target(ctx, app, col)
        row = await service.fetch_record(ctx, m, col, rid)
        await service.enforce_or_problem(ctx, "update", m, col, row["owner_sub"], str(row["id"]))
        if row["seal_state"] != "NONE":
            raise ProblemError(409, "record-sealed", "Record is sealed")
        if row["wf_state"] == "running":
            raise _not_open()
    limit = (spec.attachments.max_mb if spec.attachments else settings.max_upload_mb_default) * 2**20
    declared = request.headers.get("content-length")
    if declared is None or not declared.isdigit():
        raise ProblemError(411, "length-required", "Length Required",
                           "Content-Length is required for uploads")
    if int(declared) > limit + _FORM_OVERHEAD:
        raise _too_large(limit)
    form = await request.form(max_files=1, max_fields=4)
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ProblemError(400, "bad-request", "Bad Request", "multipart field 'file' is required")
        data = await file.read(limit + 1)
        filename, content_type = file.filename or "", file.content_type
    finally:
        await form.close()
    if len(data) > limit:
        raise _too_large(limit)
    upload_id = uuid.uuid4()
    try:
        await asyncio.to_thread(_put_staging, request.app.state.store, upload_id, data)
    except (ClientError, BotoCoreError) as exc:
        raise ProblemError(503, "storage-unavailable", "Object storage unavailable") from exc
    try:
        async with pool.acquire() as conn:
            await register_upload(conn, upload_id=upload_id, record_id=row["id"], app_id=m.app.id,
                                  filename=filename, size=len(data), declared_type=content_type,
                                  actor_sub=p.sub, hmac_key=hmac_key)
    except asyncpg.RaiseError as exc:
        # Quy trình bắt đầu (hoặc niêm phong) trong lúc tệp đang tải lên: trigger upload_record_open chặn ở
        # mức DB, để không tệp nào lọt vào sau khi đã duyệt (P2-D4).
        if "record_not_open" not in str(exc):
            raise
        await asyncio.to_thread(_drop_staging_quietly, request.app.state.store, upload_id)
        raise _not_open() from exc
    return JSONResponse({"upload_id": str(upload_id), "status": "STAGING"}, status_code=202)


@router.get("/api/v1/uploads/{upload_id}")
async def get_upload(upload_id: str, ctx: service.Ctx = Depends(ctx_dep)) -> dict:  # noqa: B008
    try:
        uid = uuid.UUID(upload_id)
    except ValueError as exc:
        raise ProblemError(404, "not-found", "Not Found") from exc
    row = await ctx.conn.fetchrow(
        "SELECT u.status, u.sha256, u.reason, r.app_id, r.collection, r.owner_sub"
        " FROM uploads u JOIN records r ON r.id = u.record_id WHERE u.id=$1", uid)
    m = await get_active(ctx.conn, row["app_id"]) if row else None
    if row is None or m is None:
        raise ProblemError(404, "not-found", "Not Found")
    await service.enforce_or_problem(ctx, "read", m, row["collection"], row["owner_sub"], upload_id)
    return upload_status(row)


@router.get("/api/v1/objects/{sha256}")
async def get_object(sha256: str, request: Request, variant: str = "original",
                     ctx: service.Ctx = Depends(ctx_dep)) -> Response:  # noqa: B008
    if not _SHA.fullmatch(sha256) or variant != "original":
        raise ProblemError(404, "not-found", "Not Found")
    obj = await ctx.conn.fetchrow("SELECT status, mime_sniffed FROM objects WHERE sha256=$1", sha256)
    if obj is None or obj["status"] != "CLEAN":
        raise ProblemError(404, "not-found", "Not Found")
    refs = await ctx.conn.fetch(
        "SELECT r.id, r.app_id, r.collection, r.owner_sub"
        " FROM object_refs o JOIN records r ON r.id = o.record_id"
        " WHERE o.sha256=$1 AND o.role='original' ORDER BY r.created_at", sha256)
    manifests: dict = {}
    chosen = None
    for ref in refs:
        if ref["app_id"] not in manifests:
            manifests[ref["app_id"]] = await get_active(ctx.conn, ref["app_id"])
        m = manifests[ref["app_id"]]
        if m and decide(ctx.principal, "read", m, ref["collection"], ref["owner_sub"]).allow:
            chosen = (ref, m)
            break
    if chosen is None:
        first = next(((r, manifests[r["app_id"]]) for r in refs if manifests.get(r["app_id"])), None)
        if first is not None:   # ghi policy.denied rồi trả 404
            ref0, m0 = first
            await service.enforce_or_problem(ctx, "read", m0, ref0["collection"], ref0["owner_sub"], sha256)
        raise ProblemError(404, "not-found", "Not Found")
    ref, m = chosen
    try:
        data = await asyncio.to_thread(request.app.state.store.read_object, sha256)
    except IntegrityError as exc:
        raise ProblemError(500, "integrity-error", "Stored object failed its integrity check") from exc
    except (ClientError, BotoCoreError) as exc:
        raise ProblemError(503, "storage-unavailable", "Object storage unavailable") from exc
    await append(ctx.conn, type="object.read", subject=sha256,
                 body={"sha256": sha256, "record_id": str(ref["id"])},
                 hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return Response(content=data, media_type=obj["mime_sniffed"], headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Disposition": f'attachment; filename="{sha256}.pdf"'})
