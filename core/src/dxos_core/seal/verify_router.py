# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cổng đối soát công khai của niêm phong (spec 11.5, 12.2, 25.3; Plan 02 Task 8). Ẩn danh, APISIX giới hạn
tốc độ (``limit-req`` của route ``/verify/v1/*``).

Quy tắc chung của mọi route ``seals/{seal_id}``, đúng thứ tự:
1. ``seal_id`` sai dạng → 404.
2. Không có ``seal_requests`` → 404.
3. Manifest của **phiên bản đã niêm phong** có ``verify.public`` khác ``true`` → 404 (kiểm trước bước 4 để
   không lộ niêm phong có tồn tại hay đang chờ). Cả ba trường hợp trả **cùng một** thân 404.
4. Chưa có ``seals`` → ``SEAL_PENDING``.

- Trang công khai không trả ``record_id``, hash tệp, trường không ``public`` (chỉ ``attachments_count``).
  Gói bằng chứng là ngoại lệ duy nhất (cần payload đầy đủ để kiểm chữ ký); niêm phong ``require_file`` chỉ lấy
  được gói khi gửi đúng hash một tệp.
- ``:check`` và ``:bundle`` chỉ nhận ``application/json`` (415), thân tối đa 256 byte đọc theo luồng (413, kể
  cả chunked), đúng dạng ``{"sha256": "<64 hex thường>"}`` (422). Thân được đọc trước khi lấy kết nối DB.
- Mọi đọc DB nằm trong một transaction ``READ ONLY`` ``REPEATABLE READ``: không route nào ghi ledger.
- Khóa công khai lấy qua cache dùng chung (``app.state.public_keys``): OpenBao khóa vẫn trả lời được; phiên
  bản lạ khi KMS khóa → 503 ``keys-unavailable``, không bao giờ báo chữ ký sai.
"""

import json
import logging
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dxos_core.errors import ProblemError
from dxos_core.kms.cache import KeysUnavailable
from dxos_core.registry.model import Manifest
from dxos_core.registry.store import get_version
from dxos_core.seal.bundle import (
    Evidence,
    SealRow,
    build_bundle,
    inclusion_ok,
    load_evidence,
    seal_row,
    signature_ok,
    sth_versions,
)
from dxos_core.seal.keys import statement_for

log = logging.getLogger("dxos_core.seal.verify")
router = APIRouter(prefix="/verify/v1/seals", tags=["verify"])

SEAL_ID = re.compile(r"[A-Z2-7]{26}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_BODY = 256
_NO_STORE = {"Cache-Control": "no-store"}          # trạng thái (thu hồi) có thể đổi


def _not_found() -> ProblemError:
    return ProblemError(404, "not-found", "Not Found")


def _invalid() -> ProblemError:
    return ProblemError(422, "invalid-request", "Body must be {\"sha256\": \"<64 lowercase hex>\"}")


# ---------------------------------------------------------------- thân {sha256}
def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("khóa JSON trùng")
    return dict(pairs)


def parse_hash_body(raw: bytes) -> str:
    """``{"sha256": "<64 hex thường>"}`` chính xác (không khóa khác, không khóa trùng) → giá trị hash;
    sai → 422."""
    try:
        body = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _invalid() from exc
    if not isinstance(body, dict) or set(body) != {"sha256"}:
        raise _invalid()
    value = body["sha256"]
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise _invalid()
    return value


async def read_hash_body(request: Request) -> str:
    """Content-Type trước (415), rồi đọc luồng với trần cứng ``MAX_BODY`` (413 ngay khi vượt, không đọc thêm),
    rồi kiểm JSON (422)."""
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media != "application/json":
        raise ProblemError(415, "unsupported-media-type", "Unsupported Media Type",
                           "only application/json {sha256} is accepted; files are never uploaded here")
    too_large = ProblemError(413, "payload-too-large", "Payload Too Large", f"body limit is {MAX_BODY} bytes")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_BODY:
                raise too_large
        except ValueError as exc:
            raise ProblemError(400, "bad-request", "Bad Request", "invalid Content-Length") from exc
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_BODY:
            raise too_large
    return parse_hash_body(bytes(buf))


# ---------------------------------------------------------------- tra niêm phong
@dataclass(frozen=True)
class Target:
    seal_id: str
    m: Manifest
    collection: str
    seal: SealRow | None


@asynccontextmanager
async def _snapshot(request: Request) -> AsyncIterator[asyncpg.Connection]:
    async with request.app.state.pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            yield conn


async def _resolve(conn: asyncpg.Connection, seal_id: str) -> Target:
    """Bước 1-4 của quy tắc chung; ``seal`` = None nghĩa là đang ``SEAL_PENDING``."""
    if not SEAL_ID.fullmatch(seal_id):
        raise _not_found()
    req = await conn.fetchrow(
        "SELECT q.app_id, q.app_version, r.collection FROM core.seal_requests q"
        " JOIN core.records r ON r.id = q.record_id WHERE q.seal_id=$1", seal_id)
    if req is None:
        raise _not_found()
    m = await get_version(conn, req["app_id"], req["app_version"])
    verify = m.policies.verify if m is not None else None
    if verify is None or verify.public is not True:
        raise _not_found()
    s = await conn.fetchrow(
        "SELECT seal_id, app_id, payload, signature, key_version, leaf_index, status FROM core.seals"
        " WHERE seal_id=$1", seal_id)
    return Target(seal_id, m, req["collection"], seal_row(s) if s is not None else None)


def _pending(seal_id: str) -> JSONResponse:
    return JSONResponse({"seal_id": seal_id, "status": "SEAL_PENDING"}, headers=_NO_STORE)


async def _statement(conn: asyncpg.Connection, seal: SealRow) -> dict[str, Any] | None:
    st = await statement_for(conn, seal.key_version)
    if st is None:   # mọi niêm phong của Plan 02 tạo tuyên bố trước khi ký: thiếu là bất nhất nội bộ
        log.error("niêm phong %s: không có tuyên bố seal-key/v%s", seal.seal_id, seal.key_version)
    return st


async def _keys(request: Request, ev: Evidence) -> tuple[bytes | None, dict[int, bytes | None]]:
    cache, signer = request.app.state.public_keys, request.app.state.signer
    try:
        seal_pk = await cache.get(signer, "seal-key", ev.seal.key_version)
        sth_pks = {v: await cache.get(signer, "sth-key", v) for v in sorted(sth_versions(ev))}
    except KeysUnavailable as exc:
        raise ProblemError(503, "keys-unavailable", "Public keys unavailable",
                           "key service is locked and this key version is not cached yet") from exc
    return seal_pk, sth_pks


def public_labels(m: Manifest, collection: str, fields: Iterable[str]) -> dict[str, str]:
    """``{trường: label}`` của phiên bản đã niêm phong, chỉ trường trong ``fields`` có ``label``."""
    col = m.collections.get(collection)
    if col is None:
        return {}
    return {f: col.fields[f].label for f in fields if f in col.fields and col.fields[f].label}


# ---------------------------------------------------------------- route
@router.get("/{seal_id}")
async def seal_view(seal_id: str, request: Request) -> JSONResponse:
    async with _snapshot(request) as conn:
        t = await _resolve(conn, seal_id)
        if t.seal is None:
            return _pending(seal_id)
        ev = await load_evidence(conn, t.seal)
        statement = await _statement(conn, t.seal)
    seal_pk, sth_pks = await _keys(request, ev)
    p = t.seal.payload
    anchored = None
    if ev.anchored is not None:
        anchored = {"tree_size": ev.anchored.sth.tree_size, "repo": ev.anchored.repo,
                    "commit_sha": ev.anchored.commit_sha}
    issuer = statement.get("issuer") if statement is not None else None
    return JSONResponse({
        "seal_id": t.seal.seal_id,
        "status": t.seal.status,
        "app_id": t.seal.app_id,
        "issued_at": p["issued_at"],
        "key_version": t.seal.key_version,
        "public_fields": p["public_fields"],
        "require_file": t.m.policies.verify.require_file,
        "attachments_count": len(p["attachments"]),
        "signature_valid": signature_ok(t.seal, seal_pk),
        "inclusion": {"leaf_index": t.seal.leaf_index, "tree_size": ev.sth.tree_size if ev.sth else None,
                      "verified": inclusion_ok(ev, sth_pks), "anchored": anchored},
        "issuer": issuer,
        "public_labels": public_labels(t.m, t.collection, p["public_fields"]),
    }, headers=_NO_STORE)


@router.post("/{seal_id}:check")
async def seal_check(seal_id: str, request: Request) -> JSONResponse:
    sha = await read_hash_body(request)
    async with _snapshot(request) as conn:
        t = await _resolve(conn, seal_id)
    if t.seal is None:
        return JSONResponse({"match": False, "status": "SEAL_PENDING"}, headers=_NO_STORE)
    return JSONResponse({"match": sha in t.seal.payload["attachments"]}, headers=_NO_STORE)


async def _bundle_response(request: Request, t: Target, ev: Evidence,
                           statement: dict[str, Any] | None) -> JSONResponse:
    seal_pk, sth_pks = await _keys(request, ev)
    body = build_bundle(ev, seal_public_key=seal_pk, statement=statement, sth_keys=sth_pks)
    return JSONResponse(body, headers={
        **_NO_STORE, "Content-Disposition": f'attachment; filename="dxos-seal-{t.seal_id}.json"'})


@router.get("/{seal_id}/bundle")
async def seal_bundle_get(seal_id: str, request: Request) -> JSONResponse:
    """Gói cho niêm phong ``require_file: false``; loại kia → 404 (chỉ qua ``POST :bundle``)."""
    async with _snapshot(request) as conn:
        t = await _resolve(conn, seal_id)
        if t.m.policies.verify.require_file:
            raise _not_found()
        if t.seal is None:
            return _pending(seal_id)
        ev, statement = await load_evidence(conn, t.seal), await _statement(conn, t.seal)
    return await _bundle_response(request, t, ev, statement)


@router.post("/{seal_id}:bundle")
async def seal_bundle_post(seal_id: str, request: Request) -> JSONResponse:
    """Gói cho niêm phong ``require_file: true``, chỉ khi ``sha256`` khớp một tệp đã niêm phong (khác → 404).
    Hash nằm trong thân request, không trong URL, nên không vào log của proxy."""
    sha = await read_hash_body(request)
    async with _snapshot(request) as conn:
        t = await _resolve(conn, seal_id)
        if not t.m.policies.verify.require_file:
            raise _not_found()
        if t.seal is None:
            return _pending(seal_id)
        if sha not in t.seal.payload["attachments"]:
            raise _not_found()
        ev, statement = await load_evidence(conn, t.seal), await _statement(conn, t.seal)
    return await _bundle_response(request, t, ev, statement)
