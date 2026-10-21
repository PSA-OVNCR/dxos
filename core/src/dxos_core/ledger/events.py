# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Loại sự kiện ledger (spec 12.4). Thêm loại mới phải sửa spec trước."""

EVENT_TYPES: frozenset[str] = frozenset({
    "app.submitted",
    "app.installed",
    "app.disabled",
    "record.created",
    "record.updated",
    "upload.staged",
    "object.clean",
    "object.infected",
    "object.rejected",
    "object.read",
    "field.revealed",
    "pii.detected",
    "pii.reviewed",
    "task.completed",
    "record.sealed",
    "record.revoked",
    "policy.denied",
    "sth.published",
    "workflow.started",
    "workflow.completed",
    "pii.erased",
    "key.published",
})
