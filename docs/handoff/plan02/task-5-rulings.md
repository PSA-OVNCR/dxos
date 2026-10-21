<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 5 — controller rulings and context (binding; refine the brief)

- C7 (preflight): callers take `SELECT … FOR SHARE` on the record row before `load_guard_input` (Task 6 step 9, :pii-review). `load_guard_input` itself does not lock, but its docstring must state that contract. The integration test calls it inside a transaction that holds `SELECT 1 FROM core.records WHERE id=$1 FOR SHARE` (spec 25.2: salt is read/created only under the row lock).
- Reuse Task 1's parsing: `split_guard` and `parse_role_list` in core/src/dxos_core/registry/validator.py, and `GUARD_CATALOG`. Do not write a second guard-string parser. `evaluate` on a guard not in the catalog, or with a malformed argument, raises `ValueError` (manifests are validated at install, so this is a programming error, not a GuardFailure).
- Data sources for `load_guard_input` (read core/migrations/001–004 for exact columns):
  - `uploads_pending` = count of `core.uploads` with status 'STAGING' for the record.
  - `clean_attachments` = sorted sha256 of `core.object_refs` role 'original' for the record joined with `core.objects` status 'CLEAN'.
  - `finding_ids` = sorted ids of `core.pii_findings` whose sha256 is in clean_attachments.
  - `last_review_digest` = review_digest of the newest `core.pii_reviews` row for the record (ORDER BY id DESC LIMIT 1), else None.
  - `completions` = (task_key, actor_sub) from `core.task_completions` for the record AND the record's current workflow instance id (the column on records added in 003; if the record has no current instance → empty tuple), ordered by completed_at, task_id.
  - `owner_sub`, `seal_state`, `data` from the passed `record` row; `caller_sub` = p.sub; `caller_roles` = app roles for `m.app.id` with prefix stripped (use Plan 01's `app_roles`).
  - `attachments_min` = spec.attachments.min if the collection has attachments else 0.
  - `pii_required` = any field in spec has `pii` set, or `m.policies.pii.document_detect` non-empty.
  - `data_digest` = `data_digest(record["data"], await ensure_salt(conn, record_id))` using the Task 2 helpers in core/src/dxos_core/records/digest.py (check actual names/signatures there).
- Fixture `flow_record_with_uploads` (core/tests/integration/conftest.py or the test module): a test-flow record (collection `doc`) with 1 CLEAN upload whose object_ref exists, 1 INFECTED upload (no object_ref), 1 STAGING upload; returns the kwargs dict for load_guard_input (`record`, `spec`, `m`, `p`, `task_assignee`). Use helpers.manifests `load("test-flow")` + validate_manifest. Also add integration tests for: completions limited to the current instance; finding_ids only from CLEAN files; last_review_digest picks the newest; data_digest equals data_digest(data, salt) and is stable across two calls.
- Unit tests: brief Step 1 plus one test per catalog guard pass/fail with exact (guard, reason, status) from the table, `role_in` with several roles, `field_required` with None and "", `record_not_sealed`, unknown guard → ValueError, `review_digest` is order-insensitive for attachments and findings.
- The spec 9.3 guard table was already written in Task 1; if your semantics differ from spec 9.3 in any cell, stop and report NEEDS_CONTEXT rather than editing the spec.
