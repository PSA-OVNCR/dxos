# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cam kết có salt tới dữ liệu bản ghi (spec 25.2, P2-D22).

Ledger lưu ``body_sha256`` mãi mãi. Nếu body chứa mã băm không salt của ``data``, ai có bản sao ledger và
biết các trường công khai có thể thử từng CCCD cho tới khi khớp. Vì vậy mọi cam kết tới ``data`` dùng
``data_digest`` với salt riêng của bản ghi, nằm ở bảng xóa được ``record_salts``: xóa salt thì cam kết cũ
không còn nối được với dữ liệu.
"""

import base64
import secrets
import uuid

import asyncpg
from dxos_proof.canonical import canonical_bytes, sha256_hex


def new_salt() -> str:
    """Salt mới: base64 của 16 byte ngẫu nhiên (128 bit), 24 ký tự kết thúc ``==``."""
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def data_digest(data: dict, salt_b64: str) -> str:
    """``SHA-256(canonical({"salt": salt, "data": data}))`` dạng hex."""
    return sha256_hex(canonical_bytes({"salt": salt_b64, "data": data}))


async def ensure_salt(conn: asyncpg.Connection, record_id: uuid.UUID) -> str:
    """Trả salt của bản ghi; chưa có (đã bị xóa khi xóa PII) thì tạo bằng ``new_salt()``.

    Chỉ gọi khi đã giữ khóa hàng của bản ghi (``FOR UPDATE``, hoặc trong cùng transaction với UPDATE bản ghi),
    để ``:erase-pii`` không xóa salt chen giữa.
    """
    salt = await conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", record_id)
    if salt is None:
        salt = new_salt()
        await conn.execute("INSERT INTO record_salts(record_id, salt) VALUES ($1, $2)", record_id, salt)
    return salt
