# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""API xác minh công khai cho witness (spec 12.2): không cần token, gateway giới hạn tốc độ.

``/keys`` đọc khóa công khai qua cache dùng chung với cổng đối soát (``app.state.public_keys``, Plan 02
Task 8): OpenBao khóa thì vẫn trả các khóa đã biết; chưa biết khóa nào thì 503.
"""

import base64
import dataclasses
import json

from dxos_proof.merkle import consistency_proof
from fastapi import APIRouter, Request

from dxos_core.errors import ProblemError
from dxos_core.kms.base import KmsUnavailable
from dxos_core.ledger.log import entries_bytes
from dxos_core.ledger.sth import latest_sth

router = APIRouter(prefix="/verify/v1", tags=["verify"])


def _bad(detail: str) -> ProblemError:
    return ProblemError(400, "bad-request", "Bad Request", detail)


@router.get("/sth/latest")
async def sth_latest(request: Request) -> dict:
    async with request.app.state.pool.acquire() as conn:
        th = await latest_sth(conn)
    if th is None:
        raise ProblemError(404, "not-found", "Not Found", "no signed tree head yet")
    return dataclasses.asdict(th)


@router.get("/sth/consistency")
async def sth_consistency(request: Request, first: int, second: int) -> dict:
    async with request.app.state.pool.acquire() as conn:
        th = await latest_sth(conn)
        if th is None or not 1 <= first <= second or second > th.tree_size:
            raise _bad("need 1 <= first <= second <= latest tree_size")
        leaves = await entries_bytes(conn, upto=second)
    proof = consistency_proof(first, leaves)
    return {"first": first, "second": second, "proof": [p.hex() for p in proof]}


@router.get("/keys")
async def keys(request: Request) -> dict:
    """``{"seal-key": {"<n>": b64}, "sth-key": {...}, "statements": {"seal-key": {"<n>": tuyên bố}}}``."""
    try:
        pub = await request.app.state.public_keys.all(request.app.state.signer)
    except KmsUnavailable as exc:
        raise ProblemError(503, "kms-unavailable", "Key service unavailable") from exc
    async with request.app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT version, statement FROM key_statements WHERE key='seal-key' ORDER BY version")
    out: dict = {name: {str(v): base64.b64encode(k).decode("ascii") for v, k in sorted(vers.items())}
                 for name, vers in pub.items()}
    out["statements"] = {"seal-key": {
        str(r["version"]): json.loads(r["statement"]) if isinstance(r["statement"], str) else r["statement"]
        for r in rows}}
    return out
