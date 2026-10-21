# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``POST …/records/{rid}:erase-pii``: xóa trường có khai ``pii`` (spec 25.2; Plan 02 Task 7; P2-D23, P2-D24).

- Quyền: đọc được bản ghi theo manifest ACTIVE, và có role thuộc ``pii.erase_roles`` của bản ACTIVE
  (chính sách hiện hành). Không thì ``policy.denied`` (``not_eraser``) + 404. App không có bản ACTIVE → 404
  ``app-not-active``.
- Trường xóa được: trường có khai ``pii`` ở bản ACTIVE **hoặc** ở bản đã ghim ``wf_app_version`` của bản ghi.
- Đã niêm phong vẫn xóa được (chữ ký phủ ``record_digest``, không phủ ``data``). Đang ``running`` → 409
  ``record-in-workflow``; ``SEAL_PENDING`` → 409 ``seal-pending``.
- Một transaction giữ ``FOR UPDATE`` **trước** mọi việc với salt (C7), kiểm lại trạng thái trên hàng đã khóa,
  rồi theo đúng thứ tự: bằng chứng ``pii_erasures`` (trigger ``record_seal_guard`` cần hàng này, cùng txid) →
  bỏ trường khỏi ``data`` → xóa salt, ghi chú thu hồi, thay hash tên tệp gốc → ledger ``pii.erased``.
- Trường không có trong ``data`` vẫn ghi sự kiện; gọi lại cho cùng kết quả.
"""

import hashlib
import secrets
import uuid
from typing import Any

import asyncpg

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import app_roles
from dxos_core.ledger.log import append
from dxos_core.policy import pdp
from dxos_core.records.service import (
    Ctx,
    enforce_or_problem,
    fetch_record,
    load_target,
    parse_if_match,
    record_out,
)
from dxos_core.registry.store import get_version

# Mã lý do theo Điều 14 khoản 1 Luật 91/2025 (spec 25.2): đúng danh sách CHECK của pii_erasures
# (migration 003).
ERASE_REASONS: frozenset[str] = frozenset({"data_subject_request", "purpose_completed", "retention_expired",
                                           "authority_decision", "agreement"})
MAX_FIELDS = 64                                   # CHECK cardinality(fields) BETWEEN 1 AND 64


def _unprocessable(detail: str) -> ProblemError:
    return ProblemError(422, "invalid-request", "Invalid erase request", detail)


def _check_state(row: asyncpg.Record, expected: int) -> None:
    if row["wf_state"] == "running":
        raise ProblemError(409, "record-in-workflow", "Record is in a running workflow")
    if row["seal_state"] == "SEAL_PENDING":
        raise ProblemError(409, "seal-pending", "Record is waiting to be sealed")
    if row["version"] != expected:
        raise ProblemError(409, "version-conflict", "Version conflict",
                           f"If-Match {expected} but current version is {row['version']}")


async def _lock_record(conn: asyncpg.Connection, rid: uuid.UUID) -> asyncpg.Record:
    """``SELECT … FOR UPDATE`` trên bản ghi (test chen trạng thái mới ngay trước bước này)."""
    return await conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", rid)


async def erase_pii(ctx: Ctx, app: str, col: str, rid: str, body: Any, if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    m, spec = await load_target(ctx, app, col)               # không có bản ACTIVE → 404 app-not-active
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "read", m, col, row["owner_sub"], str(row["id"]))
    if not set(m.policies.pii.erase_roles) & app_roles(ctx.principal, m.app.id):
        await pdp.deny(ctx.conn, ctx.principal, m, action="erase_pii", reason="not_eraser",
                       subject=str(row["id"]), hmac_key=ctx.hmac_key)
        raise ProblemError(404, "not-found", "Not Found")
    # Kiểm body.
    if not isinstance(body, dict) or set(body) != {"fields", "reason_code"}:
        raise _unprocessable("body must be {fields, reason_code}")
    fields, reason = body["fields"], body["reason_code"]
    if not isinstance(fields, list) or not fields or not all(isinstance(f, str) for f in fields):
        raise _unprocessable("fields must be a non-empty array of field names")
    if len(set(fields)) != len(fields) or len(fields) > MAX_FIELDS:
        raise _unprocessable(f"fields must be distinct, at most {MAX_FIELDS}")
    pii = {n for n, f in spec.fields.items() if f.pii}
    if row["wf_app_version"] is not None:
        pinned = await get_version(ctx.conn, m.app.id, row["wf_app_version"])
        pinned_spec = pinned.collections.get(col) if pinned is not None else None
        if pinned_spec is not None:
            pii |= {n for n, f in pinned_spec.fields.items() if f.pii}
    bad = sorted(set(fields) - pii)
    if bad:
        raise _unprocessable(f"not pii fields of this collection: {bad}")
    if reason not in ERASE_REASONS:
        raise _unprocessable(f"reason_code must be one of {sorted(ERASE_REASONS)}")
    fields = sorted(fields)
    # Kiểm nhanh (chưa khóa), để trả lỗi sớm.
    _check_state(row, expected)
    async with ctx.conn.transaction():
        locked = await _lock_record(ctx.conn, row["id"])
        _check_state(locked, expected)                       # kiểm lại trên hàng đã khóa
        await ctx.conn.execute(
            "INSERT INTO core.pii_erasures(record_id, fields, reason_code, erased_by)"
            " VALUES ($1, $2, $3, $4)",
            row["id"], fields, reason, ctx.principal.sub)
        new = await ctx.conn.fetchrow(
            "UPDATE core.records SET data = data - $2::text[], version = version + 1, updated_at = now()"
            " WHERE id = $1 AND version = $3 RETURNING *", row["id"], fields, expected)
        if new is None:  # ném ra trong transaction → rollback cả bằng chứng
            raise ProblemError(409, "version-conflict", "Version conflict", "record changed concurrently")
        await ctx.conn.execute("DELETE FROM core.record_salts WHERE record_id=$1", row["id"])
        await ctx.conn.execute(
            "DELETE FROM core.seal_revocation_notes WHERE seal_id IN"
            " (SELECT seal_id FROM core.seals WHERE record_id=$1)", row["id"])
        for up in await ctx.conn.fetch("SELECT id FROM core.uploads WHERE record_id=$1", row["id"]):
            await ctx.conn.execute(
                "UPDATE core.uploads SET original_name_hash=$2, updated_at=now() WHERE id=$1",
                up["id"], hashlib.sha256(secrets.token_bytes(32)).hexdigest())
        await append(ctx.conn, type="pii.erased", subject=str(row["id"]),
                     body={"collection": col, "fields": fields, "reason_code": reason,
                           "version": new["version"]},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return record_out(new, ctx.principal, spec, can_reveal=False)
