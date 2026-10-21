<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 6 — controller rulings and context (binding; refine the brief)

## Preflight rulings that bind this task
- C3: Task 6 creates what step 10 needs and Task 7 builds on:
  - `Settings` fields `org_name`, `org_id`, `seal_key_validity_days`, `seal_purpose`, `key_policy_url` (read spec 25.3 for meaning/defaults; env names `DXOS_ORG_NAME`, …), constant `ORG_NAME_DEFAULT`, and `make_settings` in tests defaulting `org_name="Tổ chức thử nghiệm"` so the default never trips tests.
  - `core/src/dxos_core/seal/keys.py` skeleton: exceptions `SealKeyExpired`, `OrgNotConfigured`; `within_validity(statement, now) -> bool`; a reader for the latest seal-key key statement from `core.key_statements` (003). Task 7 adds creation/publishing; keep the skeleton minimal and documented.
- C4: "App DISABLED → 404 app-not-active" means the app has NO ACTIVE version. A pinned `wf_app_version` that is DISABLED only because a newer version is ACTIVE keeps working (P2-D19; `test_guards_follow_pinned_version_after_upgrade` relies on it).
- C7: take `SELECT … FOR SHARE` (or FOR UPDATE) on the record row in the same transaction before `load_guard_input` — in step 9 and in `:pii-review`. finalize already holds FOR UPDATE.
- C9: shared fixtures you need must exist with a one-line docstring contract. Move `local_signer`/`failing_signer` from core/tests/integration/test_sth.py to core/tests/integration/conftest.py (keep test_sth.py working). Create `flow`, `other_app_task`, `break_finalize_once`, `flowable_down_once`, `guard_flips_after_flowable` as the brief describes.
- C13: you may add core/tests/conftest.py if a fixture must be visible to unit and integration tests.
- C15: deny reasons are exactly: `guard:<guard>:<reason>`, `not_task_role`, `kms_unavailable`, `seal_key_expired`, `org_not_configured`, `not_pii_reviewer` (for `:pii-review` when decide("reveal_pii") refuses); Task 7/12 add `not_revoker`, `not_eraser`, `self_approval`. Advisory lock keys: `LOCK_WF = 724100` (two-int form `pg_advisory_lock(LOCK_WF, hashtext(record_id::text))`, session lock on a dedicated pool connection, released in `finally`), reserve `LOCK_KEYSTMT = 724101` for Task 7. Existing keys: 724000 (migrate), 724001 (ledger).
- C18: send `dxos_intent_id` as a TASK-LOCAL variable: `await flowable.complete(task_id, {"decision": d}, local_variables={"dxos_intent_id": str(intent_id)})`. `historic_intent_id(task_id)` reads it back (verified live in Task 4).

## Carry-forward from Tasks 3–5
- Only deploy/parse a model obtained from `check_against_manifest`/`parse_bpmn` for that same app version's manifest and BPMN (the `flow` fixture deploys `render_bpmn(check_against_manifest(xml, m))`). Trust `seal_tasks`/`decisions_by_task` only from that parse. Do not hash or cache `ProcessModel` by value; cache by `(app_id, wf_app_version)` key.
- Validate `decision` (pattern + `decisions_by_task[task_key]`) BEFORE any Flowable call: a decision matching no gateway condition makes Flowable return 500 and leaves the task open.
- `FlowableClient` raises `ValueError` for a malformed path id: map it to 404 in the router (task_id comes from the URL).
- Real Flowable `complete` loser gets 404 or 500 (client maps to TaskGone when history shows the task done). `outcome()` on an unknown id raises WorkflowUnavailable.
- `app.state.flowable = flowable_from_settings(settings)`; when None every workflow route returns 503 `workflow-unavailable`. In the app lifespan, if a client exists, call `ping()` once and log ERROR (do not crash startup) on failure — a wrong base URL otherwise makes everything look "gone".
- Guards: `evaluate`, `load_guard_input`, `review_digest` in core/src/dxos_core/workflow/guards.py; `load_guard_input` does not lock (C7 above). `assignee_is_caller` always fails in Plan 02.

## Task 7 dependency (request_seal / seal_record)
Task 7 implements sealing. In Task 6, `:complete` receives `request_seal` and `seal_record` as injected callables (e.g. on `app.state.seal_hooks`, set by Task 7). Ruling: when a workflow reaches the seal end and no hooks are configured, `finalize` must FAIL CLOSED — raise inside the transaction (rollback, 500), never set SEAL_PENDING without a seal_requests row. No Task 6 test reaches the seal end with hooks absent; add one unit/integration test proving the fail-closed path. Task 7 wires the real hooks.

## Test environment
- Real Flowable 7.1.0 (H2) at http://127.0.0.1:58080/flowable-rest/service is shared and keeps state between runs: give every record/business key a fresh uuid and select tasks by process instance id; never assume an empty task list globally (inbox tests: filter to this test's records, or create users/roles unique per test if the inbox would see leftovers — say which in the report).
- Test tokens: core/tests/helpers/tokens.py. Running API: `running_api` pattern from Plan 01 integration tests.

## Problem types
Guard failure → problem `type=…/guard-failed` with extensions `guard`, `reason`, status 403/409 per Task 5's table. Reuse Plan 01's problem helpers and type URI base.

## Small fixes folded in from the Task 5 review
- `ensure_salt` (core/src/dxos_core/records/digest.py) is read-then-INSERT; two holders of FOR SHARE on a record whose salt was erased can both INSERT → PK violation → 500. Make the INSERT `ON CONFLICT (record_id) DO NOTHING` and re-select the stored salt (whichever won), keeping its docstring accurate about the lock it needs. Add an integration test: two concurrent `ensure_salt` calls after the salt row is deleted return the same salt, no error.
- Add one cross-record test in core/tests/integration/test_guard_input.py: a second record with its own STAGING upload, CLEAN ref, pii review and task completion must not change the first record's GuardInput (uploads_pending, clean_attachments, last_review_digest, completions).
