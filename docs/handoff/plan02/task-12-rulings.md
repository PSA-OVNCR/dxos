<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 12 — controller rulings and context (binding; refine the brief)

## Plan decisions the brief references (verbatim summary)
- P2-D14 (upgrade only additive or tightening; check at submit AND again at approve):
  - Old collections and fields keep their type; new fields are not required; new role set ⊇ old.
  - Old tasks keep their role; their guard set ⊇ old guard set.
  - `reveal_roles` new ⊆ old; `revoke_roles` new ⊆ old.
  - `seal` and `verify` must not change — EXCEPT when the app has never had a seal request (no `seal_requests` row for the app) AND no record with `wf_state='running'`: then `seal` (incl. `public_fields`, `revoke_roles`) and `verify` may change (that is `sealed_before=False`).
  - `pii.erase_roles` and field `label` change freely; sequence `format` and `reset` change freely (spec 25.4).
- P2-D21 (four eyes): `approved_by != submitted_by`, unless `DXOS_ALLOW_SELF_APPROVAL=true` (demo only); then `app.installed` body carries `self_approved: true`. Violation → `deny(self_approval)` + 403 (C15 reason).
- P2-D12: health `keycloak_default_roles` "ok" when `default-roles-dxos` composites contain neither `dxos-admin` nor any `app:*` role.

## Preflight rulings
- C9: create the fixtures/helpers with one-line docstring contracts: `mutate(doc, change, version=)` (core/tests/helpers/manifests.py; one branch per change name in the tests, each producing exactly that change), `submit(client, app_id)`, `status_of`, `deployment_of`, `ledger_types`, `FLOW_FILES`, `GOOD_XML` (from the test-review.bpmn fixture), `kc_fake` (stub KeycloakAdmin in core/tests/helpers/ with `.roles`, `.down`), `api_as_member`, `infected_upload`, `admin`, `admin_strict`, `admin2` (`.submitter`, `.approver` with different subs), `deployment_resource(flowable_client, deployment_id)`.
- C15: deny reason `self_approval`.

## Carry-forward from earlier tasks
- Task 3: render/deploy only `render_bpmn(model)` where `model = check_against_manifest(xml, m)` for the SAME manifest version being approved; store `rendered_sha256 = sha256(render bytes)`. Task 6's `process_model` re-renders and compares with `app_deployments.rendered_sha256`, so the bytes must match exactly.
- Task 4: `FlowableClient.deploy(name, …)` is lookup-then-create (two concurrent first deploys of the same name can create two). Serialize approve per app with `pg_advisory_lock(724102, hashtext(app_id))` (new constant `LOCK_INSTALL = 724102`, distinct from 724000/724001/724100/724101) held on a dedicated connection across steps 1–6, released in finally; never hold a DB transaction open while calling Keycloak or Flowable.
- Task 6 / C4: "DISABLED" for the runtime means no ACTIVE version; `:disable` makes the ACTIVE version DISABLED (so the app has none), pinned in-flight versions keep their own manifest rows.
- Task 7: `seal_pending`, `seal_key`, `org` currently live on `/admin/v1/ledger/status`. Move them to `/admin/v1/health` (the canonical place) and remove them from ledger/status; update the Task 7 tests that read them. Reuse `org_configured()` and the seal_key logic (highest KMS version, KMS-down fallback) — do not reimplement.
- Task 11: `KeycloakAdmin` + factory returning None when `installer_client_secret_file` is not set → approve returns 503 `idp-admin-unavailable` (version stays PENDING); health `keycloak_default_roles` "down: not configured".
- Task 6 parked: health is a good place to also expose `task_intents_stuck` (> 2 min, brief) — do exactly the brief's key list, no extra keys.

## Other rulings
- Request size: enforce 1 MB while streaming (same pattern as Task 8's body cap), 413 above.
- File path rules: relative POSIX path, no `..`, no leading `/` or `\`, no drive letters, NFC-normal, exactly the set the manifest references (today only `workflow.bpmn`); BPMN size limit from Task 3 (`MAX_BPMN_BYTES`) applies.
- Same version with different content → 409; identical resubmission of a PENDING version → 202 idempotent (same body).
- `extra_body` merges into the single `app.submitted`/`app.installed` leaf; keys must not collide with existing body keys (assert).
- quarantine: never include names or name hashes; app_id via the upload's record.
- health `openbao`: `sys/health` + one probe signature (`b"dxos-kms-probe"`), each check with a short timeout; any failure → "down: <short reason>" and HTTP 200 overall.
- (from Task 11 review) Keep ONE `KeycloakAdmin` instance (e.g. on app.state, created lazily and re-created only when the secret file content changes) so its token cache works; do not call `keycloak_admin_from_settings` per request.
