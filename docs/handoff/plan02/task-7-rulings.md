<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 7 — controller rulings and context (binding; refine the brief)

## What Task 6 already built (do not recreate)
- `Settings` fields `org_name` (default `ORG_NAME_DEFAULT = "Tổ chức chưa cấu hình"` in settings.py), `org_id`, `seal_key_validity_days`, `seal_purpose`, `key_policy_url`; `make_settings` test default `org_name="Tổ chức thử nghiệm"`. Check them against the brief (e.g. `Field(3650, ge=1, le=3650)`) and fix only what differs.
- `core/src/dxos_core/seal/keys.py` skeleton: `STATEMENT_FORMAT`, `LOCK_KEYSTMT = 724101`, `SealKeyExpired`, `OrgNotConfigured`, `within_validity`, `statement_for(conn, version)`, `latest_statement(conn)`. Add `build_statement` and `ensure_key_statement` here. `latest_statement` currently has no caller: use it in the health check (`seal_key` status) or remove it.
- Seal hooks: `SealHooks(request_seal, seal_record)` in core/src/dxos_core/workflow/reconcile.py, read from `app.state.seal_hooks`; finalize fails closed (`SealHooksMissing`) when absent. Task 7 sets `app.state.seal_hooks = SealHooks(request_seal=..., seal_record=...)` in app.py so the real path is wired; the signature contract is in the SealHooks docstring — keep it, or update both sides together.
- R-1 in `:complete` already probes KMS and checks `statement_for(probe.key_version)` validity and org name.
- `ensure_salt`/`data_digest` in core/src/dxos_core/records/digest.py (ON CONFLICT-safe). `record_digest` MUST be the same function (alias or thin wrapper of `data_digest`) — no second implementation of the formula.
- Fixtures: `flow`, `local_signer`, `failing_signer` in core/tests/integration/conftest.py; tasks completed through the real Flowable (shared H2: isolate by fresh uuids and instance id).

## Preflight rulings
- C5: AT-27 in this task keeps the DB/ledger assertions only. Drop the two lines that need APIs which do not exist yet (`verify.get("/verify/v1/seals/{sid}")` → Task 8 public view, `verify_bundle(await flow.bundle(sid))` → Task 9 Step 3); leave a comment pointing there. Do not create the `verify` fixture or `bundle()` helper now.
- C14: `docs/legal-mapping.md` is created only in Task 15. Put the "erase requires an ACTIVE app" limitation as a note in your report under "For Task 15"; do not create the doc.
- C7: `:erase-pii` holds FOR UPDATE before any salt/digest work (it deletes the salt).

## Data and DB facts (verify in core/migrations/003 and 004)
- `pii_erasures`: dxos_core may INSERT only `(record_id, fields, reason_code, erased_by)`; `txid` is forced by a trigger to `txid_current()`; the record trigger allows `data = OLD.data - fields` only with that row in the same transaction. Insert it BEFORE the UPDATE, same transaction.
- dxos_core has SELECT/INSERT/DELETE (no UPDATE) on `record_salts`, `seal_revocation_notes`.
- Revocation `reason_code` set (spec 25.2): `superseded, issued_in_error, content_error, legal_order, other`; erasure reason codes: `data_subject_request, purpose_completed, retention_expired, authority_decision, agreement`. Use the DB CHECK lists as the single source if they exist (read them), and keep the API validation identical.
- `seal_requests` unique per record (`seal_requests_one_per_record`); `seals` one per record — the job/inline race test relies on FOR UPDATE + the SEALED/REVOKED idempotent return.

## Other rulings
- `flaky_signer` goes in core/tests/helpers/local_signer.py (brief Step 3) and a fixture of the same name in integration/conftest.py; the probe bytes `b"dxos-kms-probe"` always succeed.
- `dump_core_tables()` runs as owner and includes every table in schema core (append-only ones too).
- `/admin/v1/health`: add `seal_pending` (count), `seal_key` (`ok`/`expired`/`none`), `org` (`ok`/`down: not configured`) now if the health route exists; if `/admin/v1/health` does not exist yet (Task 12), add them to whatever admin status route exists and note it in the report — do not build the full health endpoint.
- Worker: `HANDLERS["seal"] = process_seal_job`; backoff `min(900, 30 * 2 ** min(attempts, 5))` for KmsUnavailable, SealKeyExpired, OrgNotConfigured; never `fail` for those.
- `.env.example`: add the DXOS_ORG_* and seal-key settings with placeholder values only (e.g. `DXOS_ORG_NAME=changeme-ten-to-chuc`); compose passes them to trust-core-api and worker.
- `verify_url = f"{public_base_url}/apps/verify/#{seal_id}"` exactly.
- Keep the problem-type naming used by Task 6 (`…/seal-pending`, `…/record-in-workflow`, `…/version-conflict`, `…/org-not-configured`).
