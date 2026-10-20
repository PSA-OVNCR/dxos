# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Nghiệp vụ nền tảng của Records API: kiểm dữ liệu theo manifest, cấp số, khóa lạc quan, che PII, ledger.

Quy tắc chung:
- ``enforce`` luôn chạy **ngoài** transaction để lá ``policy.denied`` không bị rollback (F3).
- Bản ghi không tồn tại và bản ghi không được phép xem trả **cùng một** 404 (chống IDOR, AT-06).
- Mọi chuỗi được chuẩn hóa NFC trước khi lưu (D5, RF1).
"""

import base64
import json
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import asyncpg
from dxos_proof.canonical import canonical_bytes, sha256_hex

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import Principal
from dxos_core.ledger.log import append
from dxos_core.policy.masking import mask_record, pii_fields_present
from dxos_core.policy.pdp import Action, Forbidden, NotFound, decide, enforce
from dxos_core.records.sequences import next_sequence
from dxos_core.registry.model import CollectionSpec, Manifest
from dxos_core.registry.store import get_active

MAX_STRING = 4000
MAX_BULK = 500
_INT64 = 2**63


@dataclass
class Ctx:
    conn: asyncpg.Connection
    principal: Principal
    hmac_key: bytes


# ---------------------------------------------------------------- lỗi chuẩn
def _not_found() -> ProblemError:
    return ProblemError(404, "not-found", "Not Found")


def _schema_error(errors: list[dict]) -> ProblemError:
    return ProblemError(422, "schema", "Record data does not match the collection schema", errors=errors)


# ---------------------------------------------------------------- tiện ích
def nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {nfc(k): nfc(v) for k, v in value.items()}
    if isinstance(value, list):
        return [nfc(v) for v in value]
    return value


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _check_value(name: str, ftype: str, v: Any) -> str | None:
    if ftype == "string":
        if not isinstance(v, str):
            return "phải là chuỗi"
        if len(v) > MAX_STRING:
            return f"dài quá {MAX_STRING} ký tự"
    elif ftype == "integer":
        if isinstance(v, bool) or not isinstance(v, int) or not -_INT64 <= v < _INT64:
            return "phải là số nguyên 64 bit"
    elif ftype == "boolean":
        if not isinstance(v, bool):
            return "phải là true/false"
    elif ftype == "date":
        if not isinstance(v, str) or len(v) != 10:
            return "phải là ngày dạng YYYY-MM-DD"
        try:
            date.fromisoformat(v)
        except ValueError:
            return "phải là ngày dạng YYYY-MM-DD"
    return None


def validate_data(spec: CollectionSpec, data: Any, *, client_input: dict | None = None) -> dict:
    """Kiểm ``data`` (đã gộp) theo các trường của collection. ``client_input``: phần do client gửi."""
    if not isinstance(data, dict):
        raise _schema_error([{"path": "", "msg": "dữ liệu bản ghi phải là object"}])
    errors = []
    for k in (client_input if client_input is not None else data):
        f = spec.fields.get(k)
        if f is None:
            errors.append({"path": f"/{k}", "msg": "trường không có trong manifest"})
        elif f.type == "sequence":
            errors.append({"path": f"/{k}", "msg": "trường số thứ tự do lõi cấp, không gửi lên"})
    for name, f in spec.fields.items():
        if f.type == "sequence":
            continue
        if name not in data:
            if f.required:
                errors.append({"path": f"/{name}", "msg": "bắt buộc"})
            continue
        msg = _check_value(name, f.type, data[name])
        if msg:
            errors.append({"path": f"/{name}", "msg": msg})
    if errors:
        raise _schema_error(errors)
    return data


def record_out(row: asyncpg.Record, p: Principal, spec: CollectionSpec, can_reveal: bool) -> dict:
    data = _loads(row["data"])
    return {
        "id": str(row["id"]), "app_id": row["app_id"], "collection": row["collection"],
        "data": mask_record(data, spec, can_reveal), "is_owner": row["owner_sub"] == p.sub,
        "version": row["version"], "seal_state": row["seal_state"],
        "created_at": _ts(row["created_at"]), "updated_at": _ts(row["updated_at"]),
    }


async def load_target(ctx: Ctx, app_id: str, collection: str) -> tuple[Manifest, CollectionSpec]:
    m = await get_active(ctx.conn, app_id) if _valid_slug(app_id) else None
    if m is None:
        raise ProblemError(404, "app-not-active", "Application not active", f"no active app {app_id!r}")
    spec = m.collections.get(collection)
    if spec is None:
        raise _not_found()
    return m, spec


def _valid_slug(s: str) -> bool:
    return 2 <= len(s) <= 63 and s[0].isalpha() and all(c.islower() or c.isdigit() or c == "-" for c in s)


async def enforce_or_problem(ctx: Ctx, action: Action, m: Manifest, col: str, owner: str | None,
                             subject: str):
    try:
        return await enforce(ctx.conn, ctx.principal, action, m, col, owner, subject, ctx.hmac_key)
    except NotFound as exc:
        raise _not_found() from exc
    except Forbidden as exc:
        raise ProblemError(403, "forbidden", "Forbidden") from exc


async def _reveal(ctx: Ctx, m: Manifest, col: str, spec: CollectionSpec, datas: list[dict],
                  subject: str) -> bool:
    """True nếu người gọi được xem bản rõ PII; khi đó ghi ``field.revealed`` (F4)."""
    if not decide(ctx.principal, "reveal_pii", m, col, None).allow:
        return False
    fields = sorted({f for d in datas for f in pii_fields_present(d, spec)})
    if fields:
        await append(ctx.conn, type="field.revealed", subject=subject,
                     body={"collection": col, "fields": fields, "count": len(datas)},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return True


async def fetch_record(ctx: Ctx, m: Manifest, col: str, rid: str) -> asyncpg.Record:
    try:
        rid_uuid = uuid.UUID(rid)
    except ValueError as exc:
        raise _not_found() from exc
    row = await ctx.conn.fetchrow(
        "SELECT * FROM records WHERE id=$1 AND app_id=$2 AND collection=$3", rid_uuid, m.app.id, col)
    if row is None:
        raise _not_found()
    return row


# ---------------------------------------------------------------- thao tác
async def _insert(ctx: Ctx, m: Manifest, col: str, spec: CollectionSpec, data: dict) -> asyncpg.Record:
    async with ctx.conn.transaction():
        for name, f in spec.fields.items():
            if f.type == "sequence":
                n = await next_sequence(ctx.conn, m.app.id, f"{col}.{name}")
                data[name] = (f.format or "{n}").replace("{n}", str(n))
        row = await ctx.conn.fetchrow(
            "INSERT INTO records(app_id, collection, data, owner_sub)"
            " VALUES ($1, $2, $3::jsonb, $4) RETURNING *",
            m.app.id, col, json.dumps(data, ensure_ascii=False), ctx.principal.sub)
        await append(ctx.conn, type="record.created", subject=str(row["id"]),
                     body={"collection": col, "version": 1, "data_sha256": sha256_hex(canonical_bytes(data))},
                     hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    return row


async def create(ctx: Ctx, app_id: str, col: str, body: Any) -> dict:
    m, spec = await load_target(ctx, app_id, col)
    await enforce_or_problem(ctx, "create", m, col, None, f"{app_id}/{col}")
    data = validate_data(spec, nfc(body))
    row = await _insert(ctx, m, col, spec, dict(data))
    can_reveal = decide(ctx.principal, "reveal_pii", m, col, None).allow
    return record_out(row, ctx.principal, spec, can_reveal)


async def bulk_create(ctx: Ctx, app_id: str, col: str, body: Any) -> dict:
    m, spec = await load_target(ctx, app_id, col)
    await enforce_or_problem(ctx, "create", m, col, None, f"{app_id}/{col}")
    if not isinstance(body, list) or len(body) > MAX_BULK:
        raise ProblemError(422, "schema", "Bulk body must be a JSON array", f"at most {MAX_BULK} rows")
    results = []
    for i, item in enumerate(body):
        try:
            data = validate_data(spec, nfc(item))
        except ProblemError as exc:
            results.append({"ok": False, "row": i, "error": {
                "type": "https://dxos.dev/problems/schema", "title": exc.title, **exc.extensions}})
            continue
        row = await _insert(ctx, m, col, spec, dict(data))  # mỗi dòng một transaction
        results.append({"ok": True, "id": str(row["id"])})
    return {"results": results}


async def get(ctx: Ctx, app_id: str, col: str, rid: str) -> dict:
    m, spec = await load_target(ctx, app_id, col)
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "read", m, col, row["owner_sub"], str(row["id"]))
    can_reveal = await _reveal(ctx, m, col, spec, [_loads(row["data"])], str(row["id"]))
    return record_out(row, ctx.principal, spec, can_reveal)


def _encode_cursor(row: asyncpg.Record) -> str:
    raw = json.dumps({"c": row["created_at"].isoformat(), "i": str(row["id"])}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        obj = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        return datetime.fromisoformat(obj["c"]), uuid.UUID(obj["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ProblemError(400, "bad-request", "Bad Request", "invalid cursor") from exc


async def list_records(ctx: Ctx, app_id: str, col: str, cursor: str | None, limit: int) -> dict:
    m, spec = await load_target(ctx, app_id, col)
    d = await enforce_or_problem(ctx, "list", m, col, None, f"{app_id}/{col}")
    if not 1 <= limit <= 200:
        raise ProblemError(400, "bad-request", "Bad Request", "limit must be between 1 and 200")
    where, args = ["app_id=$1", "collection=$2"], [m.app.id, col]
    if d.reason == "owner":                    # chỉ có quyền theo chủ sở hữu → chỉ thấy bản ghi của mình
        args.append(ctx.principal.sub)
        where.append(f"owner_sub=${len(args)}")
    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        args += [c_at, c_id]
        where.append(f"(created_at, id) > (${len(args) - 1}, ${len(args)})")
    args.append(limit + 1)
    rows = await ctx.conn.fetch(
        f"SELECT * FROM records WHERE {' AND '.join(where)} ORDER BY created_at, id LIMIT ${len(args)}",  # noqa: S608
        *args)
    page, more = rows[:limit], len(rows) > limit
    can_reveal = await _reveal(ctx, m, col, spec, [_loads(r["data"]) for r in page], f"{app_id}/{col}") \
        if page else False
    return {"items": [record_out(r, ctx.principal, spec, can_reveal) for r in page],
            "next_cursor": _encode_cursor(page[-1]) if more else None}


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise ProblemError(428, "precondition-required", "Precondition Required",
                           "If-Match header is required")
    v = value.strip()
    if v.startswith("W/"):
        v = v[2:]
    if len(v) >= 3 and v[0] == v[-1] == '"' and v[1:-1].isdigit():
        return int(v[1:-1])
    raise ProblemError(400, "bad-request", "Bad Request", 'If-Match must look like "<version>"')


async def patch(ctx: Ctx, app_id: str, col: str, rid: str, body: Any, if_match: str | None) -> dict:
    expected = parse_if_match(if_match)
    m, spec = await load_target(ctx, app_id, col)
    row = await fetch_record(ctx, m, col, rid)
    await enforce_or_problem(ctx, "update", m, col, row["owner_sub"], str(row["id"]))
    if row["seal_state"] != "NONE":
        raise ProblemError(409, "record-sealed", "Record is sealed", f"seal_state={row['seal_state']}")
    if row["version"] != expected:
        raise ProblemError(409, "version-conflict", "Version conflict",
                           f"If-Match {expected} but current version is {row['version']}")
    if not isinstance(body, dict):
        raise _schema_error([{"path": "", "msg": "PATCH body phải là object (JSON merge patch)"}])
    patch_in = nfc(body)
    merged = dict(_loads(row["data"]))
    for k, v in patch_in.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    validate_data(spec, merged, client_input=patch_in)
    try:
        async with ctx.conn.transaction():
            new = await ctx.conn.fetchrow(
                "UPDATE records SET data=$1::jsonb, version=version+1, updated_at=now()"
                " WHERE id=$2 AND version=$3 RETURNING *",
                json.dumps(merged, ensure_ascii=False), row["id"], expected)
            if new is None:
                raise ProblemError(409, "version-conflict", "Version conflict", "record changed concurrently")
            await append(ctx.conn, type="record.updated", subject=str(row["id"]),
                         body={"collection": col, "version": new["version"],
                               "data_sha256": sha256_hex(canonical_bytes(merged))},
                         hmac_key=ctx.hmac_key, app_id=m.app.id, actor_sub=ctx.principal.sub)
    except asyncpg.RaiseError as exc:          # niêm phong xảy ra giữa lúc đọc và lúc ghi
        if "record_sealed" in str(exc):
            raise ProblemError(409, "record-sealed", "Record is sealed") from exc
        raise
    can_reveal = decide(ctx.principal, "reveal_pii", m, col, None).allow
    return record_out(new, ctx.principal, spec, can_reveal)
