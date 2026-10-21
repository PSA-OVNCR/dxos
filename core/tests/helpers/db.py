# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: chèn hàng tối thiểu vào các bảng của migration 003 (Plan 02 Task 2)."""

import base64
import uuid

import asyncpg

# Chữ ký ed25519 64 byte hợp lệ về dạng (88 ký tự base64, kết thúc "=="); không cần ký thật ở mức DB.
SEAL_SIGNATURE = base64.b64encode(b"\x01" * 64).decode("ascii")


async def ensure_app(conn: asyncpg.Connection, app_id: str = "test-app", version: str = "0.1.0") -> None:
    """Có sẵn một dòng ``apps`` (PENDING, manifest rỗng) để thỏa khóa ngoại; đã có thì giữ nguyên."""
    await conn.execute(
        "INSERT INTO apps(id, version, manifest, manifest_sha256) VALUES ($1, $2, '{}', $3)"
        " ON CONFLICT (id, version) DO NOTHING", app_id, version, "0" * 64)


async def insert_seal_request(conn: asyncpg.Connection, record_id: uuid.UUID, *, seal_id: str) -> None:
    """Ghi một ``seal_requests`` tối thiểu cho ``record_id`` (app test-app 0.1.0)."""
    await ensure_app(conn)
    await conn.execute(
        "INSERT INTO seal_requests(seal_id, record_id, app_id, app_version, record_digest, attachments,"
        " public_fields) VALUES ($1, $2, 'test-app', '0.1.0', $3, '[]', '{}')", seal_id, record_id, "a" * 64)


async def insert_seal(conn: asyncpg.Connection, record_id: uuid.UUID, *, seal_id: str,
                      signature: str = SEAL_SIGNATURE) -> None:
    """Ghi một ``seals`` (leaf_index 0); mặc định chữ ký 88 ký tự base64 hợp lệ."""
    await conn.execute(
        "INSERT INTO seals(seal_id, app_id, record_id, payload, signature, key_version, leaf_index)"
        " VALUES ($1, 'test-app', $2, '{}', $3, 1, 0)", seal_id, record_id, signature)


async def insert_upload(conn: asyncpg.Connection, record_id: uuid.UUID) -> uuid.UUID:
    """Ghi một ``uploads`` STAGING cho ``record_id``; trả id."""
    return await conn.fetchval(
        "INSERT INTO uploads(record_id, staging_key, original_name_hash, size) VALUES ($1, 'k', $2, 1)"
        " RETURNING id", record_id, "b" * 64)


async def insert_intent_and_completion(conn: asyncpg.Connection, record_id: uuid.UUID, *,
                                       task_id: str) -> int:
    """Ghi ``task_intents`` + ``task_intent_outcomes`` (completed) + ``task_completions``; trả id ý định."""
    intent = await conn.fetchval(
        "INSERT INTO task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub, actor_roles,"
        " decision) VALUES ($1, $2, 'i1', 'review', 'u1', '{reviewer}', 'approve') RETURNING id",
        task_id, record_id)
    await conn.execute("INSERT INTO task_intent_outcomes(intent_id, outcome) VALUES ($1, 'completed')",
                       intent)
    await conn.execute(
        "INSERT INTO task_completions(task_id, intent_id, record_id, wf_instance_id, task_key, actor_sub,"
        " decision) VALUES ($1, $2, $3, 'i1', 'review', 'u1', 'approve')", task_id, intent, record_id)
    return intent
