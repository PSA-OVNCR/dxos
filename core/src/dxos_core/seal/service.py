# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Niêm phong theo ảnh chụp, thu hồi và thông tin niêm phong (Plan 02 Task 7; spec 11.5, 13.2, 25.2, 25.3;
P2-D6, P2-D7, P2-D8, P2-D18, P2-D19, P2-D22, P2-D24, P2-D25).

- ``request_seal`` chạy **trong** transaction hoàn tất task cuối (``reconcile.finalize``): chụp nội dung lúc
  đó vào ``seal_requests`` (``record_digest`` có salt, tệp CLEAN, ``public_fields``, ``app_version``) và
  xếp job.
- ``seal_record`` ký **đúng** ảnh chụp đó, không đọc lại ``data``, ``object_refs`` hay manifest ACTIVE: app có
  bị nâng cấp hay ``DISABLED`` thì niêm phong vẫn chạy. Một bản ghi tối đa một niêm phong: ``FOR UPDATE`` trên
  bản ghi, ``SEALED``/``REVOKED`` thì trả luôn. Lỗi KMS, khóa hết hạn, tổ chức chưa cấu hình → rollback và
  raise; bản ghi giữ ``SEAL_PENDING``, job thử lại (``seal.job``).
- ``revoke``: role thuộc ``seal.revoke_roles`` của **phiên bản đã niêm phong**; mã lý do cố định, ghi chú
  tự do (nếu có) ở bảng xóa được ``seal_revocation_notes``. ``REVOKED`` là trạng thái cuối.
"""

import base64
import json
import logging
import secrets
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import asyncpg
from dxos_proof.canonical import canonical_bytes, rfc3339_utc, sha256_hex

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import app_roles
from dxos_core.jobs.queue import enqueue
from dxos_core.kms.base import Signer
from dxos_core.ledger.anchor_job import ANCHOR_JOB
from dxos_core.ledger.log import append
from dxos_core.policy import pdp
from dxos_core.records.digest import data_digest, ensure_salt
from dxos_core.records.service import (
    Ctx,
    enforce_or_problem,
    fetch_record,
    load_target,
    parse_if_match,
    record_out,
)
from dxos_core.registry.model import Manifest
from dxos_core.registry.store import get_version
from dxos_core.seal.keys import SealKeyExpired, ensure_key_statement, within_validity
from dxos_core.settings import Settings

log = logging.getLogger("dxos_core.seal")

SEAL_JOB = "seal"
# Mã lý do thu hồi (spec 25.2, P2-D24): đúng danh sách CHECK của seal_revocations (migration 003).
REVOKE_REASONS: frozenset[str] = frozenset({"superseded", "issued_in_error", "content_error", "legal_order",
                                            "other"})
MAX_NOTE = 500                                    # CHECK length(note) BETWEEN 1 AND 500


class SealStateError(RuntimeError):
    """``seal_record`` gọi cho bản ghi không ở ``SEAL_PENDING``/``SEALED``/``REVOKED``, hoặc thiếu ảnh
    chụp."""


# ---------------------------------------------------------------- hàm thuần
def new_seal_id() -> str:
    """128 bit ngẫu nhiên, base32 không padding: 26 ký tự ``[A-Z2-7]``."""
    return base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")


def record_digest(data: dict, salt_b64: str) -> str:
    """``record_digest`` của niêm phong = ``data_digest`` (một công thức duy nhất, P2-D22)."""
    return data_digest(data, salt_b64)


def seal_payload(*, seal_id: str, app_id: str, record_id: str, record_digest: str, attachments: Sequence[str],
                 public_fields: Mapping[str, Any], issued_at: str, key_version: int) -> dict:
    """Payload niêm phong của spec 11.5; ``attachments`` đã sắp xếp."""
    return {"seal_id": seal_id, "app_id": app_id, "record_id": record_id, "record_digest": record_digest,
            "attachments": sorted(attachments), "issued_at": issued_at, "public_fields": dict(public_fields),
            "key_version": key_version}


def seal_signing_bytes(payload: dict) -> bytes:
    """Bytes được ký bằng ``seal-key`` (P2-D7)."""
    return canonical_bytes(payload)


def sealed_leaf_body(payload: dict) -> dict:
    """Body của lá ``record.sealed``: không chứa payload, chỉ mã băm của bytes đã ký."""
    return {"seal_id": payload["seal_id"], "payload_sha256": sha256_hex(seal_signing_bytes(payload))}


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


# ---------------------------------------------------------------- yêu cầu niêm phong (transaction task cuối)
async def request_seal(conn: asyncpg.Connection, *, record: asyncpg.Record, m: Manifest) -> str:
    """Chụp nội dung được duyệt vào ``seal_requests`` và xếp job niêm phong; trả ``seal_id``.

    Người gọi (``finalize``) đang ở trong transaction đã ``UPDATE`` hàng bản ghi sang ``SEAL_PENDING``, nên
    khóa hàng được giữ (điều kiện của ``ensure_salt``). ``m`` là phiên bản đã ghim của bản ghi. Salt không
    được ghi vào ``seal_requests``.
    """
    if not conn.is_in_transaction():
        raise RuntimeError("request_seal phải chạy trong transaction hoàn tất task cuối")
    seal = m.policies.seal
    if seal is None:
        raise RuntimeError(f"{m.app.id}@{m.app.version} không có policies.seal")
    rid: uuid.UUID = record["id"]
    data = _loads(record["data"])
    salt = await ensure_salt(conn, rid)
    attachments: list[str] = []
    if "attachments" in seal.target:
        attachments = [r["sha256"] for r in await conn.fetch(
            "SELECT r.sha256 FROM core.object_refs r JOIN core.objects o ON o.sha256 = r.sha256"
            " WHERE r.record_id=$1 AND r.role='original' AND o.status='CLEAN' ORDER BY r.sha256", rid)]
    public_fields = {f: data[f] for f in seal.public_fields if f in data}
    seal_id = new_seal_id()
    await conn.execute(
        "INSERT INTO core.seal_requests(seal_id, record_id, app_id, app_version, record_digest, attachments,"
        " public_fields) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)",
        seal_id, rid, record["app_id"], record["wf_app_version"], record_digest(data, salt),
        json.dumps(attachments), json.dumps(public_fields, ensure_ascii=False))
    await enqueue(conn, SEAL_JOB, {"record_id": str(rid)})
    return seal_id


# ---------------------------------------------------------------- ký
@dataclass(frozen=True)
class SealOutcome:
    seal_id: str
    state: Literal["SEALED", "SEAL_PENDING", "REVOKED"]


async def _schedule_anchor(conn: asyncpg.Connection) -> None:
    """Xếp việc lập STH + neo nếu chưa có việc neo nào **sẽ** phủ lá mới.

    Việc ``QUEUED`` không có ``tree_size`` sẽ lập STH khi chạy (sau commit này) nên đã phủ lá mới. Việc đang
    ``RUNNING`` hay việc thử lại với ``tree_size`` cố định thì không, nên vẫn xếp việc mới.
    """
    pending = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM core.jobs WHERE kind=$1 AND state='QUEUED'"
        " AND NOT (payload ? 'tree_size'))",
        ANCHOR_JOB)
    if not pending:
        await enqueue(conn, ANCHOR_JOB, {})


async def seal_record(conn: asyncpg.Connection, *, signer: Signer, hmac_key: bytes, settings: Settings,
                      record_id: uuid.UUID, now: datetime | None = None) -> SealOutcome:
    """Ký ảnh chụp của bản ghi ``SEAL_PENDING``; idempotent. ``now`` chỉ dùng trong test.

    ``KmsUnavailable``, ``SealKeyExpired``, ``OrgNotConfigured`` → rollback và raise (bản ghi giữ
    ``SEAL_PENDING``). Không bao giờ ghi ``seals`` thiếu chữ ký.
    """
    async with conn.transaction():
        row = await conn.fetchrow("SELECT id, seal_state FROM core.records WHERE id=$1 FOR UPDATE", record_id)
        if row is None:
            raise SealStateError(f"không có bản ghi {record_id}")
        req = await conn.fetchrow("SELECT * FROM core.seal_requests WHERE record_id=$1", record_id)
        if row["seal_state"] in ("SEALED", "REVOKED") and req is not None:
            return SealOutcome(req["seal_id"], row["seal_state"])
        if row["seal_state"] != "SEAL_PENDING" or req is None:
            raise SealStateError(f"bản ghi {record_id}: seal_state={row['seal_state']}, "
                                 f"seal_request={'có' if req else 'không'}")
        # Bước 3: phiên bản khóa và thời điểm, tính MỘT lần.
        pubkeys = (await signer.public_keys())["seal-key"]
        if not pubkeys:
            raise RuntimeError("KMS không có phiên bản seal-key nào")
        key_version = max(pubkeys)
        issued_at = rfc3339_utc(now or datetime.now(UTC))
        # Tuyên bố khóa trước khi ký (spec 25.3): tạo ở lần đầu, kiểm thời hạn bằng chính issued_at.
        statement = await ensure_key_statement(conn, signer=signer, settings=settings,
                                               key_version=key_version, issued_at=issued_at,
                                               hmac_key=hmac_key)
        if base64.b64decode(statement["public_key"]) != pubkeys[key_version]:
            raise RuntimeError(f"tuyên bố seal-key/v{key_version} không khớp khóa công khai của KMS")
        if not within_validity(statement, issued_at):
            raise SealKeyExpired(f"{issued_at} nằm ngoài thời hạn của seal-key/v{key_version}: cần xoay khóa")
        # Payload chỉ từ ảnh chụp (P2-D18, P2-D19).
        payload = seal_payload(
            seal_id=req["seal_id"], app_id=req["app_id"], record_id=str(record_id),
            record_digest=req["record_digest"], attachments=_loads(req["attachments"]),
            public_fields=_loads(req["public_fields"]), issued_at=issued_at, key_version=key_version)
        signed = await signer.sign("seal-key", seal_signing_bytes(payload), key_version=key_version)
        if signed.key_version != key_version:
            raise RuntimeError(f"KMS ký bằng seal-key/v{signed.key_version}, yêu cầu v{key_version}")
        entry = await append(conn, type="record.sealed", subject=req["seal_id"],
                             body=sealed_leaf_body(payload), hmac_key=hmac_key, app_id=req["app_id"])
        await conn.execute(
            "INSERT INTO core.seals(seal_id, app_id, record_id, payload, signature, key_version, leaf_index)"
            " VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)",
            req["seal_id"], req["app_id"], record_id, json.dumps(payload, ensure_ascii=False),
            base64.b64encode(signed.signature).decode("ascii"), key_version, entry.idx)
        await conn.execute(
            "UPDATE core.records SET seal_state='SEALED', updated_at=now() WHERE id=$1", record_id)
        if settings.sth_after_seal:
            await _schedule_anchor(conn)
    log.info("đã niêm phong bản ghi %s (%s, seal-key/v%s)", record_id, req["seal_id"], key_version)
    return SealOutcome(req["seal_id"], "SEALED")


# ---------------------------------------------------------------- thu hồi
def _check_revoke_body(body: Any) -> tuple[str, str | None]:
    if not isinstance(body, dict) or set(body) - {"reason_code", "note"}:
        raise ProblemError(422, "invalid-request", "Body must be {reason_code, note?}")
    reason = body.get("reason_code")
    if reason not in REVOKE_REASONS:
        raise ProblemError(422, "invalid-reason-code", "Invalid reason_code",
                           f"reason_code must be one of {sorted(REVOKE_REASONS)}")
    note = body.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise ProblemError(422, "invalid-note", "Invalid note", "note must be a string")
        note = unicodedata.normalize("NFC", note)
        if not 1 <= len(note) <= MAX_NOTE:
            raise ProblemError(422, "invalid-note", "Invalid note", f"note must be 1..{MAX_NOTE} characters")
    return reason, note


def _not_sealed(state: str) -> ProblemError:
    return ProblemError(409, "not-sealed", "Record is not sealed", f"seal_state={state}")


def _version_conflict(expected: int, current: int) -> ProblemError:
    return ProblemError(409, "version-conflict", "Version conflict",
                        f"If-Match {expected} but current version is {current}")


async def revoke(ctx: Ctx, app: str, col: str, rid: str, body: Any, if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    m, spec = await load_target(ctx, app, col)
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "read", m, col, row["owner_sub"], str(row["id"]))
    req = await ctx.conn.fetchrow("SELECT seal_id, app_version FROM core.seal_requests WHERE record_id=$1",
                                  row["id"])
    sealed_m = await get_version(ctx.conn, m.app.id, req["app_version"]) if req is not None else None
    revoke_roles = set(sealed_m.policies.seal.revoke_roles) if sealed_m and sealed_m.policies.seal else set()
    if sealed_m is not None and not revoke_roles & app_roles(ctx.principal, m.app.id):
        await pdp.deny(ctx.conn, ctx.principal, m, action="revoke", reason="not_revoker",
                       subject=str(row["id"]), hmac_key=ctx.hmac_key)
        raise ProblemError(404, "not-found", "Not Found")
    reason, note = _check_revoke_body(body)

    def check(r: asyncpg.Record) -> None:
        if req is None or r["seal_state"] != "SEALED":
            raise _not_sealed(r["seal_state"])
        if r["version"] != expected:
            raise _version_conflict(expected, r["version"])

    check(row)
    async with ctx.conn.transaction():
        row = await ctx.conn.fetchrow("SELECT * FROM core.records WHERE id=$1 FOR UPDATE", row["id"])
        check(row)
        seal_id = req["seal_id"]
        done = await ctx.conn.fetchval(
            "UPDATE core.seals SET status='REVOKED', revoked_at=now() WHERE seal_id=$1 AND status='VALID'"
            " RETURNING seal_id", seal_id)
        if done is None:
            raise _not_sealed("REVOKED")
        await ctx.conn.execute(
            "INSERT INTO core.seal_revocations(seal_id, reason_code, revoked_by) VALUES ($1, $2, $3)",
            seal_id, reason, ctx.principal.sub)
        if note is not None:
            await ctx.conn.execute("INSERT INTO core.seal_revocation_notes(seal_id, note) VALUES ($1, $2)",
                                   seal_id, note)
        new = await ctx.conn.fetchrow(
            "UPDATE core.records SET seal_state='REVOKED', version=version+1, updated_at=now() WHERE id=$1"
            " RETURNING *", row["id"])
        await append(ctx.conn, type="record.revoked", subject=seal_id,
                     body={"seal_id": seal_id, "reason_code": reason},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return record_out(new, ctx.principal, spec, can_reveal=False)


# ---------------------------------------------------------------- thông tin niêm phong
async def seal_info(ctx: Ctx, app: str, col: str, rid: str, public_base_url: str) -> dict:
    """``GET …/records/{rid}/seal``: quyền như ``get``; chưa có yêu cầu niêm phong → 404."""
    m, _ = await load_target(ctx, app, col)
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "read", m, col, row["owner_sub"], str(row["id"]))
    req = await ctx.conn.fetchrow("SELECT seal_id, public_fields FROM core.seal_requests WHERE record_id=$1",
                                  row["id"])
    if req is None:
        raise ProblemError(404, "not-found", "Not Found", "record has no seal")
    seal = await ctx.conn.fetchrow("SELECT payload, key_version FROM core.seals WHERE seal_id=$1",
                                   req["seal_id"])
    return {
        "seal_id": req["seal_id"],
        "seal_state": row["seal_state"],
        "issued_at": _loads(seal["payload"])["issued_at"] if seal else None,
        "key_version": seal["key_version"] if seal else None,
        "public_fields": _loads(req["public_fields"]),
        "verify_url": f"{public_base_url}/apps/verify/#{req['seal_id']}",
    }
