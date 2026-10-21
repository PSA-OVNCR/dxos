# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test ledger: loại sự kiện, bytes của lá, HMAC actor (Plan 01 Task 9)."""

import hashlib
import hmac

from dxos_core.ledger.events import EVENT_TYPES
from dxos_core.ledger.log import LedgerEntry, actor_ref, entry_bytes
from dxos_proof.canonical import canonical_bytes


def test_entry_bytes_is_canonical_of_seven_fields():
    e = LedgerEntry(idx=7, ts="2026-10-20T00:00:00Z", type="object.read", app_id=None, subject="s",
                    actor_ref=None, body_sha256="0" * 64, leaf_hash=b"")
    assert entry_bytes(e) == canonical_bytes({
        "idx": 7, "ts": "2026-10-20T00:00:00Z", "type": "object.read", "app_id": None,
        "subject": "s", "actor_ref": None, "body_sha256": "0" * 64})


def test_event_types_are_exactly_spec_12_4():              # gồm phần thêm của 1.0.3 (A và B)
    assert EVENT_TYPES == frozenset({
        "app.submitted", "app.installed", "app.disabled", "record.created", "record.updated", "upload.staged",
        "object.clean", "object.infected", "object.rejected", "object.read", "field.revealed", "pii.detected",
        "pii.reviewed", "task.completed", "record.sealed", "record.revoked", "policy.denied",
        "sth.published", "workflow.started", "workflow.completed", "pii.erased", "key.published"})


def test_actor_ref_function():
    assert actor_ref("u", b"k") == hmac.new(b"k", b"u", hashlib.sha256).hexdigest()
    assert actor_ref("u", b"k") != actor_ref("u", b"k2")


def test_workflow_events_registered():
    assert {"workflow.started", "workflow.completed"} <= EVENT_TYPES


def test_erasure_and_key_events_registered():
    assert {"pii.erased", "key.published"} <= EVENT_TYPES
