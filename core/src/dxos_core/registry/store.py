# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kho manifest (bảng ``apps``). Mỗi app có tối đa một phiên bản ``ACTIVE``.

Installer đầy đủ (duyệt, tạo role Keycloak, deploy BPMN) thuộc Plan 02; ở Plan 01 chỉ có lưu và đọc.
"""

import json
from typing import Literal

import asyncpg
from dxos_proof.canonical import canonical_bytes, sha256_hex

from dxos_core.ledger.log import append
from dxos_core.registry.model import Manifest
from dxos_core.registry.validator import validate_manifest

Status = Literal["PENDING", "ACTIVE", "DISABLED"]
_EVENT = {"PENDING": "app.submitted", "ACTIVE": "app.installed", "DISABLED": "app.disabled"}


def _loads(v):
    return json.loads(v) if isinstance(v, str) else v


async def save_manifest(conn: asyncpg.Connection, m: Manifest, raw: dict, status: Status, actor_sub: str,
                        *, hmac_key: bytes | None = None) -> None:
    """Lưu (hoặc đổi trạng thái) phiên bản ``m.app.version``; ghi ledger nếu có ``hmac_key``."""
    digest = sha256_hex(canonical_bytes(raw))
    async with conn.transaction():
        existing = await conn.fetchrow(
            "SELECT manifest_sha256 FROM apps WHERE id=$1 AND version=$2 FOR UPDATE", m.app.id, m.app.version)
        if existing is not None and existing["manifest_sha256"] != digest:
            raise ValueError(f"{m.app.id} {m.app.version} đã tồn tại với nội dung khác; hãy tăng version")
        if status == "ACTIVE":
            await conn.execute(
                "UPDATE apps SET status='DISABLED', updated_at=now()"
                " WHERE id=$1 AND status='ACTIVE' AND version<>$2",
                m.app.id, m.app.version)
        approved = actor_sub if status == "ACTIVE" else None
        if existing is None:
            await conn.execute(
                "INSERT INTO apps(id, version, manifest, manifest_sha256, status, submitted_by, approved_by)"
                " VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)",
                m.app.id, m.app.version, json.dumps(raw, ensure_ascii=False), digest, status, actor_sub,
                approved)
        else:
            await conn.execute(
                "UPDATE apps SET status=$3, approved_by=COALESCE($4, approved_by), updated_at=now()"
                " WHERE id=$1 AND version=$2", m.app.id, m.app.version, status, approved)
        if hmac_key is not None:
            await append(conn, type=_EVENT[status], subject=f"{m.app.id}@{m.app.version}",
                         body={"manifest_sha256": digest, "status": status}, hmac_key=hmac_key,
                         app_id=m.app.id, actor_sub=actor_sub)


async def get_active(conn: asyncpg.Connection, app_id: str) -> Manifest | None:
    raw = await conn.fetchval("SELECT manifest FROM apps WHERE id=$1 AND status='ACTIVE'", app_id)
    return None if raw is None else validate_manifest(_loads(raw))


async def get_version(conn: asyncpg.Connection, app_id: str, version: str) -> Manifest | None:
    """Manifest của đúng ``version`` ở **mọi** trạng thái (PENDING, ACTIVE, DISABLED).

    Dùng cho bản ghi đã ghim phiên bản lúc bắt đầu quy trình (P2-D19): guard, task và niêm phong theo bản
    đã ghim kể cả khi app đã nâng cấp. Không dùng hàm này để quyết định app có đang hoạt động hay không.
    """
    raw = await conn.fetchval("SELECT manifest FROM apps WHERE id=$1 AND version=$2", app_id, version)
    return None if raw is None else validate_manifest(_loads(raw))


async def get_deployment(conn: asyncpg.Connection, app_id: str, version: str) -> asyncpg.Record | None:
    """Hàng ``app_deployments`` (deployment_id, process_definition_id, rendered_sha256) của một phiên bản."""
    return await conn.fetchrow(
        "SELECT app_id, version, deployment_id, process_definition_id, rendered_sha256, deployed_at"
        " FROM app_deployments WHERE app_id=$1 AND version=$2", app_id, version)
