<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Preflight conflict scan: Plan 02 (Tier-0 M2)

Plan: `docs/superpowers/plans/2026-10-21-dxos-02-tier0-m2.md` (HEAD `aa2e4b0`). Spec: `docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md` (§9, §10, §11, §12, §14, §19, §25).
How it was done: I read the plan, the spec sections and the real code (`core/src`, `core/migrations`, `core/tests`, `witness/`, `deploy/`, `libs/dxos-proof`). I did not run any tests. The scan was cut short by the time limit. Rows marked "not checked" were not checked in depth.

## 1. Pairs of tasks that share a file or an interface

| Tasks | Shared file/interface | Producer says | Consumer expects | Finding |
|---|---|---|---|---|
| 1→3 | `ErrorCode "BPMN_INVALID"`, `ManifestError` | T1 adds the code to `ErrorCode` | T3 raises `ManifestError("BPMN_INVALID",…)` | OK |
| 1→12 | `ErrorCode "UPGRADE_NOT_ADDITIVE"` | T1 adds it | T12 `check_upgrade` raises it | OK |
| 1→6,7 | `EVENT_TYPES` (`workflow.*`, `pii.erased`, `key.published`) | T1 + its Bổ sung block | T6 `workflow.started/completed`; T7 `pii.erased`, `key.published` | OK |
| 1→3,12,14 | test loader `load("test-flow")` | T1 creates `manifest-test-flow.yaml`, but does not register it in the test loaders | T1, T3 and T12 tests call `load("test-flow")`; `test_bpmn.py` and `test_upgrade.py` define no `load`; `PATHS` in `test_manifest_validator.py` and `helpers/manifests.py` has no `test-flow` until T14 | **Conflict C1** |
| 1→3 | on_event regex `^process\.completed:[A-Za-z_][A-Za-z0-9_-]{0,63}$` vs BPMN end ids | T1 validates the on_event string | T3 `parse_bpmn` does not limit the end-event id format | **Conflict C11** |
| 1→14 | `FieldSpec.label/reset`, `PiiPolicy.erase_roles`, `SealPolicy.revoke_roles` | T1 model + schema | T14 manifests 1.1.0 | OK, but the schema `seal` block has `additionalProperties:false`, and T1 never says to add `revoke_roles` there (C20) |
| 2→5,6,7 | `ensure_salt`, `data_digest` (`records/digest.py`) | T2: "chỉ gọi khi đã giữ khóa hàng" | T5 `load_guard_input` uses `ensure_salt`; T6 calls it at step 9 (advisory lock only, no row lock) and in `:pii-review` | **Conflict C7** (spec 25.2) |
| 2→6 | triggers `record_in_workflow`, `record_not_open` | T2 migration 003 | T6 catches both in `records/service.py` and `objects/router.py` | OK |
| 2→6 | `task_intents`, `task_intent_outcomes`, `task_completions` (+ `actor_roles`) | T2 DDL | T6 intents, reconcile, finalize | OK |
| 2→6 | `wf_state` CHECK `^ended:[A-Za-z_][A-Za-z0-9_-]{0,63}$` | T2 | T6 writes `ended:<end_event>` and `ended:guard_failed` | OK when end ids are well formed; see C11 |
| 2→7 | `seal_requests`, `seals` FK `(seal_id, record_id)`, signature CHECK (88 chars) | T2 | T7 `request_seal`, `seal_record` | OK (an ed25519 signature in base64 is 88 chars ending in `==`) |
| 2→7 | `record_salts`, `pii_erasures` + trigger exception, `seal_revocation_notes`, `key_statements` | T2 | T7 `:erase-pii` order, revoke notes, `ensure_key_statement` | OK: the order matches spec 25.2 steps 1–5 |
| 2→6,12 | `app_files`, `app_deployments` | T2 | T6 `flow` fixture inserts directly; T12 `save_files`, approve | OK |
| 2 (Plan 01 code) | `next_sequence(conn, app_id, name)` → adds `year=` | real code: 3-arg signature | T2 adds the kw-only `year` | OK (stays backward compatible) |
| 2 (Plan 01 code) | `apply_migrations(dsn, dir)` | real code has no `until` | the T2 fixture `fresh_db_at_002` needs `until="002"` | Minor: `db/migrate.py` is missing from T2 Files (C13) |
| 3→4 | `render_bpmn` output | T3 | T4 live test deploys `render_bpmn(parse_bpmn(...))` | OK |
| 3→6 | `ProcessModel.decisions_by_task`, `seal_tasks` | T3 | T6 step 8 (decision set), step 10 (R-1 probe) | OK |
| 3→12 | `check_against_manifest(xml, m)`, `render_bpmn` | T3 | T12 submit steps 3 and 5, approve recheck | OK |
| 3→14 | `parse_bpmn`, `check_against_manifest` | T3 | T14 test | OK (signature matches) |
| 4→6 | `FlowableClient` (start by definition id, `TaskGone` on 404/409, `outcome`, `cancel`, `historic_intent_id`) | T4 | T6 | OK as interfaces. `historic_intent_id` assumes the variable value at task completion; see C18 |
| 4→12 | `FlowableClient.deploy(name, filename, xml)` (same name → old id) | T4 | T12 approve step 5, retry | OK; T12 also checks `rendered_sha256` |
| 5→6 | `evaluate`, `load_guard_input(conn,*,record,spec,m,p,task_assignee)`, `review_digest` | T5 | T6 steps 9 and finalize; `:pii-review` | OK on signatures; locking per C7 |
| 6→7 | `deny(...)`, `get_version` | T6 | T7 revoke and erase (`not_revoker`, `not_eraser`) | OK |
| 6→7 | `request_seal` (passed in as a parameter), `seal_record`, `SealKeyExpired`, `OrgNotConfigured`, `Settings.org_name`, `ORG_NAME_DEFAULT`, key-statement validity | **T7 produces them** | **T6 step 10 (Bổ sung) and the after-commit path already use them** | **Conflict C3** |
| 6→12 | `deny` reasons | T6 lists a fixed set | T12 uses `deny(self_approval)`; T6 `:pii-review` uses a deny with no reason given | Minor C15 |
| 6↔P2-D19 | "App `DISABLED` → 404" at `:complete` | T6 step 3 | P2-D19: pinned version is used "kể cả khi app … bị `DISABLED`"; T6 test `test_guards_follow_pinned_version_after_upgrade` (0.1.0 becomes DISABLED after the 0.2.0 install, yet expects 200) | **Conflict C4** |
| 7→8 | `seal_signing_bytes`, `sealed_leaf_body`, `seals.payload`, `key_statements` | T7 | T8 bundle, `issuer`, `public_labels` | OK |
| 7→8,9 | AT-27 test inside T7 | T8 bundle/verify API; T9 `verify_bundle` | T7 Step 4 expects PASS | **Conflict C5** |
| 7→12 | health `seal_pending`, `seal_key`, `org` | T7 defines the semantics | T12 health output | OK |
| 8→9 | bundle JSON (`entry` 7 fields, `seal_key{version,public_key,statement}`, `sth`, `anchored`) | T8 | T9 steps 1–9 | OK on shape (`entry_bytes` = 7 fields, matches `leaf_hash(canonical(entry))`). STH selection vs spec 11.5 → **C8** |
| 8→9 | anchor files `keys/<key>/v<n>.pub`, `keys/seal-key/v<n>.json` = `canonical(statement)+"\n"` | T8 `publish_sth(..., keys, statements)` | T9 byte compare | OK |
| 8→9 | `GET /verify/v1/keys` adds top-level `statements` | T8 | T9 `sync` compares keys with anchor `keys/` | OK if `sync` skips `statements`; the existing `sync` only reads `sth-key`, so it is fine |
| 8→10 | public view keys incl. `issuer`, `public_labels`, `require_file` | T8 | T10 page | OK |
| 10→15 | `docs/legal-mapping.md` link | created in T15 | linked by T10; T7 also says "ghi giới hạn này vào `docs/legal-mapping.md`" | Minor C14 |
| 11→12 | `KeycloakAdmin.ensure_app_roles`, `default_role_composites`, `Settings.installer_*` | T11 | T12 approve step 4, health | OK |
| 11→15 | dev user `admin2` (`dxos-admin`) | T11 dev-overlay | T15 `DXOS_APPROVER_TOKEN` | OK (overlay format is `{user: [roles]}`) |
| 11 (Plan 01 tests) | `realm-dxos.json` users | T11 adds the user `service-account-dxos-installer` to the prod realm | existing `tests/infra/test_keycloak_realm.py::test_production_realm_has_no_users_no_test_client_no_literal_secret` | **Conflict C10** (plausible, body of that test not read) |
| 12→13 | admin API (`/admin/v1/apps`, `/diff`, `:approve`, health, quarantine), problem `code`/`path` | T12 | T13 CLI | OK |
| 12→14 | `check_upgrade(old,new,*,sealed_before)` | T12 (due 11/11) | T14 (due 10/11, deps only on 3) test `test_v110_upgrades_v100_only_before_any_seal` | **Conflict C6** |
| 12→14 | P2-D14 exception (seal/verify/revoke_roles change only before any seal; `erase_roles`/`label`/`reset`/`format` free) | T12 | T14 App A/B 1.1.0 changes `public_fields`, adds `revoke_roles`, changes `format`, adds labels | OK: consistent with spec 25.4 |
| 13→15 | `dxos` commands | T13 (no erase command) | T15 runbook: "`dxos` hoặc API `:erase-pii`" | Minor C19 |
| 4,13,15 | `Makefile`; 3,13,15 `LICENSES-THIRD-PARTY.md`; 13,15 `release.yml`; 2,4,7,11,12 `settings.py`; 2,7 `.env.example`; 2,6,7 `integration/conftest.py`; 6,12 `admin/router.py`; 6,12 `registry/store.py`; 2,6 `records/service.py` | sequential edits | — | OK (additive; no contradictory content found) |
| 14 ↔ AT-14 | identifiers scanned in `core/src` etc. | — | real code: no hit today (grep run) | OK at HEAD; not re-checked against new Plan 02 strings |

## 2. Each task checked against itself

| Task | Self-consistency: tests vs code specified, files created vs files later touched, Bổ sung block vs original text | Finding |
|---|---|---|
| 1 | Tests use `load("test-flow")`, but the validator test file's `PATHS` has no `test-flow`. The schema `seal` block has `additionalProperties:false`; adding `revoke_roles` there is implied, not stated. Bổ sung: `ref` becomes `{n:02}/TF` + `reset: yearly` + label, consistent with the T8 `public_labels` test | C1, C20 |
| 2 | `test_new_tables_are_insert_only` runs on mostly empty tables. Row triggers do not fire on 0 rows, so the test passes only because `dxos_core` lacks UPDATE/DELETE, not because of the trigger. The "one seal per record" assertion is also satisfied by the FK mismatch `(B, record_id)`, not by the unique index. In the last line of `test_sealed_data_changes_only_with_erasure_row`, the data mismatch alone already blocks the change, so the "reused txid" claim goes untested. `pending_app` must be `test-flow@0.1.0` (FK on app_files), but its content is not stated. Salt is 122 random bits, but spec 25.2 says "128 bit" | C12, C13, C16 |
| 3 | `BAD` includes `task-named-creator`, but `parse_bpmn` rules 1–9 do not ban `creator`; only `check_against_manifest` does, so `test_rejects_dangerous_bpmn` would fail. Rule 4 allows a gateway `default` attribute, while rule 7 requires every gateway outflow to carry a condition. End-event ids are unconstrained | C2, C17, C11 |
| 4 | Tests match the interfaces. `candidateGroupIn` is not yet verified (the plan says so). `dxos_intent_id` sent as a process-scope variable would be overwritten by later completions | C18 (minor) |
| 5 | Integration test uses fixture `flow_record_with_uploads`, which no task declares. `load_guard_input` → `ensure_salt` without a row lock | C9, C7 |
| 6 | Fixtures `failing_signer` (exists only locally in `integration/test_sth.py`) and `other_app_task` are not declared; `flow.token(...)` and `as_="r1"` are mixed. Step 10 Bổ sung uses T7 symbols. DISABLED wording vs P2-D19 | C3, C4, C9 |
| 7 | The AT-27 test needs `verify` (T8) and `verify_bundle` (T9). Fixtures `local_signer`, `flaky_signer` and `verify` are not declared in conftest (`local_signer` exists only in `test_sth.py`). The `make_settings` change touches `core/tests/conftest.py`, which is not in Files. It writes to `docs/legal-mapping.md` before T15 creates it. `LOCK_KEYSTMT` value unspecified | C5, C9, C13, C14, C15 |
| 8 | `anchor_env` (with `anchor_once`, `overwrite_remote`, `repo`), `sealed_once` and `kms_down` are not declared. The existing `test_anchor.py` only has `bare_remote` and `tmp_bare_repo_clone`. `anchor_once` must raise `AnchorError`, but `process_anchor_job` catches it and calls `fail()`. STH selection rule | C9, C8 |
| 9 | `bundle_env`, `fake_ledger` (`publish_keys_to`, `rotate_key_same_version`, `url`), `anchor_dir`, `state_dir` are not declared; the witness conftest only has `server`/`FakeLedger`. Bổ sung step 2 (statement) and original step 2 (`.pub`) can coexist. The Step 3 core test imports `dxos_witness` | C9 |
| 10 | Static tests are consistent with the spec 25.1 wording (markdown stripped). The fetch regex would trip on `fetch(...).then(r => r.blob())`, which an implementer must avoid. Links to `docs/legal-mapping.md` before it exists | C14 (minor) |
| 11 | Tests call `realm()`/`client()`, but the existing helpers are `_load(PROD)`/`_client(realm, id)`. `kc`, `kc_live`, `TOKEN`, `ADMIN` are undefined. The prod realm gains a user | C9, C10 |
| 12 | `mutate`, `submit`, `status_of`, `deployment_of`, `ledger_types`, `FLOW_FILES`, `GOOD_XML`, `kc_fake`, `api_as_member`, `infected_upload` are not defined (some only described in prose). `deny(self_approval)` is not in the T6 reason list | C9, C15 |
| 13 | `app_dir`, `token_env`, `SUBMITTED`, `MANIFEST_WITH_BPMN_PATH`, `DEVICE`, `TOKEN`, `ISS`, `save_token` import are not defined. Otherwise consistent | C9 (minor part) |
| 14 | Uses `check_upgrade` (T12), but its dependencies list only T3 and it is due before T12. The `seal_tasks` assert with a conditional expression parses correctly. The README quote test needs the `> ` prefix copied too | C6 |
| 15 | Runbook mentions a `dxos` erase path that T13 does not provide. Otherwise consistent with spec 25.5 docs | C19 |

## 3. Conflicts

| id | severity | where in the plan (task + short quote) | spec | suggested resolution |
|---|---|---|---|---|
| C1 | important | T1 Step 1 `doc = load("test-flow")`; T3 `validate_manifest(load("test-flow"))`; T12 `load("test-flow")`; T14 Files "Thêm `test-flow` vào `PATHS`" | — | In T1, add `"test-flow"` to `PATHS` in `core/tests/test_manifest_validator.py` and `core/tests/helpers/manifests.py`. T3 and T12 should import `load` from `helpers.manifests`. Drop the PATHS line from T14 |
| C2 | important | T3 `BAD = [... "task-named-creator" ...]` tested through `parse_bpmn`; the creator ban sits only under `check_against_manifest`: "Không task nào được tên `creator`" | — | Add rule 10 to `parse_bpmn` (userTask id `creator` → BPMN_INVALID), or move that fixture to a `check_against_manifest` test |
| C3 | important | T6 step 10 *Bổ sung*: "kiểm thêm tuyên bố khóa … `DXOS_ORG_NAME` còn giá trị mặc định"; "Sau commit … `SealKeyExpired` hoặc `OrgNotConfigured` (Task 7)" | 25.3 "Kiểm trước task cuối (R-1) cũng kiểm hai điều trên" | Move `Settings.org_name/org_id/seal_key_validity_days`, `ORG_NAME_DEFAULT`, the exception classes, `within_validity` and the `make_settings(org_name=…)` default into T6 (or a small pre-step), or defer the step 10 Bổ sung checks to T7 and say so |
| C4 | important | T6 step 3 "App đang `DISABLED` → 404 … Disable **đóng băng** quy trình đang chạy" vs P2-D19 "kể cả khi app đã nâng cấp hoặc bị `DISABLED`" and test `test_guards_follow_pinned_version_after_upgrade` | — | State it precisely: "the app has no ACTIVE version → 404". A pinned version that is DISABLED only because a newer one is ACTIVE must still work. Fix the P2-D19 wording |
| C5 | important | T7 Bổ sung test `test_erase_pii_keeps_seal_valid…` uses `verify.get("/verify/v1/seals/…")` and `verify_bundle(...)`; T7 Step 4 "Expected: PASS" | 25.5 / AT-27 | Move the bundle and verify assertions of this test to T8/T9 (or to T9 Step 3, which already adds a core↔witness test). Keep only the DB and ledger parts in T7 |
| C6 | important | T14 Bổ sung test calls `check_upgrade`; table: "14 … Hạn 10/11 … Phụ thuộc 3" vs "12 … 11/11" | 25.5 "nâng App A/B từ 1.0.0 lên 1.1.0 hợp lệ khi chưa niêm phong" | Make T14 depend on T12 and swap the due dates (or move that test to T12) |
| C7 | important | T2 `ensure_salt` "Chỉ gọi khi đã giữ khóa hàng"; T5 Bổ sung "`load_guard_input` tính `data_digest` bằng `ensure_salt`"; T6 step 9 evaluates guards before any `FOR UPDATE`; `:pii-review` has no lock stated | 25.2 "Salt chỉ được đọc hoặc tạo lại khi đã giữ khóa hàng" (§25 wins) | Take `SELECT … FOR SHARE/UPDATE` on the record before `load_guard_input` in step 9 and in `:pii-review`, or give `load_guard_input` a precomputed digest. Make the T5 integration test call it inside a transaction with a row lock |
| C8 | important | T8 "Không có STH đã neo nào phủ lá → dùng STH mới nhất phủ lá. `anchored` … STH đã neo gần nhất … consistency từ STH đó tới `sth`"; T9 step 7 accepts this with `--anchor-dir` | 11.5 step 6 "STH ≤ STH đã neo"; AT-17 "chỉ với khóa công khai + STH đã neo" | With `--anchor-dir`, require `anchored.sth.tree_size > leaf_index` (the anchored STH covers the leaf). Otherwise return INVALID `NOT_ANCHORED` (or a separate "VALID, not anchored yet" result with exit 3). Add a tamper case "leaf after last anchor" |
| C9 | important | Fixtures and helpers used but declared by no task: T5 `flow_record_with_uploads`; T6 `failing_signer` (module-local in `test_sth.py`), `other_app_task`; T7 `local_signer`, `flaky_signer` (class only), `verify`; T8 `anchor_env`, `sealed_once` (named, not specified), `kms_down`; T9 `bundle_env`, `fake_ledger`, `anchor_dir`, `state_dir`; T11 `realm()`, `client()`, `kc`, `kc_live`; T12 `mutate`, `submit`, `status_of`, `deployment_of`, `ledger_types`, `FLOW_FILES`, `GOOD_XML`, `api_as_member`, `infected_upload`; T13 `app_dir`, `token_env`, `SUBMITTED`, `MANIFEST_WITH_BPMN_PATH` | — | Each task's Step 1 should list these with a one-line contract and the file they go in (`integration/conftest.py`, `witness/tests/conftest.py`, …). Move `local_signer`/`failing_signer` from `test_sth.py` to the shared conftest |
| C10 | important (plausible) | T11 "Người dùng service account `service-account-dxos-installer` …" added to `deploy/keycloak/realm-dxos.json` | — | The existing `test_production_realm_has_no_users_no_test_client_no_literal_secret` probably fails. List that test under T11 Modify (exempt users that have `serviceAccountClientId`) |
| C11 | minor | T3 rules list has no format rule for `endEvent id`; T6 writes `wf_state='ended:<end_event>'` | — | Add to `parse_bpmn`: end id must match `^[A-Za-z_][A-Za-z0-9_-]{0,63}$`. Otherwise an id like `end.ok` passes, Flowable completes, and the DB CHECK fails after the fact |
| C12 | minor | T2 `test_new_tables_are_insert_only` ("UPDATE seal_requests…", "DELETE FROM app_files"…, on empty tables, run as `core_conn`); `test_seal_must_match_its_request` last assert; `test_sealed_data_changes_only_with_erasure_row` last assert | 25.5 "dùng lại bằng chứng của transaction cũ → bị chặn" | Seed one row per table and run the statements as `owner_conn` so the trigger itself is tested. Insert a request whose `seal_id` matches before testing the unique index. For txid reuse, erase field A in tx1, then in tx2 change `data` back or remove A again with data still containing A (use a record with two pii fields) |
| C13 | minor | T2 Files (no `core/src/dxos_core/db/migrate.py` though `until=` may be added); T7 "Fixture `make_settings` … đặt `org_name`" (no `core/tests/conftest.py` in Files) | — | Add both files to Files |
| C14 | minor | T7 "Ghi giới hạn này vào `docs/legal-mapping.md`"; T10 link; T15 "`docs/legal-mapping.md` (mới)" | 25.5 | Create a stub in T7 (or move the note to T15) |
| C15 | minor | T6 "Định dạng `reason` thống nhất: …" omits `self_approval` (T12) and the `:pii-review` reason; `LOCK_WF`, `LOCK_KEYSTMT` have no values | — | Extend the list (e.g. `self_approval`, `not_pii_reviewer`). Fix the constants (≠ 724000/724001) in T6/T7 |
| C16 | minor | T2 "16 byte … (122 bit ngẫu nhiên)" via `uuid_send(gen_random_uuid())` | 25.2 "salt 128 bit" | Use `gen_random_bytes(16)` (pgcrypto), or have the API insert the salt; or amend spec 25.2 to "≥122 bit" (needs the team lead's approval because §25 wins) |
| C17 | minor | T3 rule 4 "Riêng cổng có thêm `default`" vs rule 7 "tới một cổng mà mọi flow ra đều có điều kiện `decision`" | — | Remove `default` from the gateway allow-list, or define it in rule 7 |
| C18 | minor | T4 `historic_intent_id` "biến dxos_intent_id lúc task hoàn thành"; T6 `complete(task, {"decision", "dxos_intent_id"})` | — | Send the variables as task-local (Flowable REST variable `scope: local`), or read `historic-detail`. Verify in the T4 Step 3 spike |
| C19 | minor | T15 runbook "→ `dxos` hoặc API `:erase-pii`" | 25.2 | Either add `dxos record erase-pii` to T13 or say "API only" |
| C20 | minor | T1 Produces `SealPolicy.revoke_roles`, but the schema changes listed are only the on_event pattern and the Bổ sung fields | — | Say explicitly: add `revoke_roles` (array of `$defs/name`, uniqueItems) to `policies.seal` in `manifest.schema.json` |

Counts: blocker 0 · important 10 (C1–C10; C10 not confirmed) · minor 10 (C11–C20).

Not checked: T10 Caddy routing against the real `Caddyfile` beyond the snippet structure; T15 e2e scripts; T13 device-flow details; the AT-14 identifier scan against new Plan 02 strings; full spec §12/§14 table rows other than those cited.
