<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# SDD ledger — plan: docs/superpowers/plans/2026-10-21-dxos-02-tier0-m2.md
Spec: docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md (1.0.3 part A, a3c8560). Plan head at start: aa2e4b0.
Ruling: work directly on main, no worktree/branch — leader's standing instruction (HANDOFF §1: "push thẳng lên main, không cần PR"; confirmed again 21/10 "ok làm đi") — cost if wrong: reviewable branch history lost; every commit still goes through task review.
Env (cloud, no Docker daemon): PG16 127.0.0.1:55432 (dxos_owner/changeme-test, db dxos_test), OpenBao 2.2.0 dev :58200 (root changeme-test-root), SeaweedFS 3.80 S3 :58333, fake-av :53310 — started by scratchpad svc/up.sh. Baseline at aa2e4b0: make check 258 passed; integration 178 passed; witness 18 passed.
Preflight: scan table in preflight.md (agent stopped at time limit; some rows "not checked"). 20 conflicts (10 important, 10 minor, 0 blocker). Rulings (carried into the owning task's dispatch):
Ruling C1: T1 adds "test-flow" to PATHS/load helpers (test_manifest_validator.py, helpers/manifests.py); T3/T12 import load from helpers.manifests; T14 drops that line — plan step order — cost if wrong: none.
Ruling C2: parse_bpmn rule 10: userTask id "creator" → BPMN_INVALID (check_against_manifest keeps its check too) — fixture is tested via parse_bpmn — cost if wrong: none.
Ruling C3: Settings.org_name/org_id/seal_key_validity_days/seal_purpose/key_policy_url, ORG_NAME_DEFAULT, SealKeyExpired, OrgNotConfigured, within_validity are created in T6 (seal/keys.py skeleton + settings); T7 builds on them; make_settings default org_name="Tổ chức thử nghiệm" set in T6 — T6 step 10 needs them, spec 25.3 — cost if wrong: file split differs from plan text.
Ruling C4: "app DISABLED → 404" means the app has no ACTIVE version; a pinned version that is DISABLED only because a newer one is ACTIVE keeps working (P2-D19) — resolves T6 vs P2-D19 — cost if wrong: none.
Ruling C5: T7's AT-27 test keeps DB/ledger assertions; the public-view VALID and verify_bundle assertions after erasure move to T8 (public view) and T9 Step 3 (core→witness bundle test) — those APIs do not exist in T7 — cost if wrong: AT-27 split across 3 tasks.
Ruling C6: execute tasks in numeric order (12 before 14); T14 depends on T12 — check_upgrade used in T14 test — cost if wrong: none.
Ruling C7: take SELECT … FOR SHARE on the record before load_guard_input (T6 step 9) and in :pii-review; T5 integration test calls load_guard_input inside a transaction holding a row lock — spec 25.2 salt only under row lock — cost if wrong: slightly more locking.
Ruling C8: verify-bundle with --anchor-dir requires anchored.sth.tree_size > leaf_index, else INVALID NOT_ANCHORED; add tamper case "leaf after last anchor" — spec 11.5 step 6, AT-17 — cost if wrong: fresh seals not verifiable offline until next anchor (by design).
Ruling C9: each implementer declares every fixture/helper its tests use (one-line contract, shared conftest or helpers module); local_signer/failing_signer move to core/tests/helpers — plan omitted them — cost if wrong: none.
Ruling C10: T11 updates test_production_realm_has_no_users… to exempt service-account users (serviceAccountClientId) — cost if wrong: none.
Ruling C11: parse_bpmn: endEvent id must match ^[A-Za-z_][A-Za-z0-9_-]{0,63}$ — matches records.wf_state CHECK — cost if wrong: none.
Ruling C12: T2 append-only tests seed a row per table and run statements as owner_conn; unique-index test inserts a matching request first; txid-reuse test uses a record with two pii fields — tests must exercise triggers — cost if wrong: none.
Ruling C13: add core/src/dxos_core/db/migrate.py (T2, if until= added) and core/tests/conftest.py (T6) to Files — cost if wrong: none.
Ruling C14: docs/legal-mapping.md is created in T15 only; T7 notes go there — cost if wrong: none.
Ruling C15: deny reasons list adds self_approval (T12), not_pii_reviewer (T6 :pii-review), not_eraser, org_not_configured, seal_key_expired; LOCK_WF and LOCK_KEYSTMT: implementer picks constants distinct from existing advisory-lock keys (grep) — cost if wrong: none.
Ruling C16: DB-side salt stays encode(uuid_send(gen_random_uuid()),'base64') (16 bytes, 122 random bits, no pgcrypto/extension needed in production role); Python new_salt() is 128 bits — spec 25.2 says "128 bit"; 122 bits is far beyond brute force — cost if wrong: deviation from spec wording, flagged to leader.
Ruling C17: remove gateway attribute "default" from the BPMN allow-list — rule 7 requires every gateway flow to carry a decision condition — cost if wrong: BPMN files cannot use default flows.
Ruling C18: T4 sends dxos_intent_id as a task-local variable and historic_intent_id reads historic variable instances by taskId; verify against real Flowable in T4 Step 3 and record in docs/spikes/flowable.md — cost if wrong: T4 spike adjusts.
Ruling C19: runbook says ":erase-pii via API only" (no CLI command in Plan 02) — cost if wrong: none.
Ruling C20: T1 adds policies.seal.revoke_roles (array of $defs/name, uniqueItems) to manifest.schema.json explicitly — cost if wrong: none.
Task 1: dispatched (BASE aa2e4b0, implementer a47f39e3fb7c91c8d, sonnet)
Task 1: implementer DONE_WITH_CONCERNS 15003fa (namespace rule narrowed; sequence without format now invalid)
Task 1: review: spec ✅, quality Approved, 0 critical/important, 6 minor.
Task 1: Ruling: accept narrowed namespace rule (_bad_namespace blocks only "app", "app_*", names with ":"; spec text updated accordingly) so the brief's role "approver" validates — core always prefixes roles as app:<id>:<role> (identity/jwt.py _APP_ROLE), so a role name cannot escape its namespace; AT-12 still covered — cost if wrong: a role named like "application" is now allowed; revert = one function + rename role.
Task 1: Ruling: keep commit trailer "Claude Sonnet 5.5" on 15003fa (accurate: the implementer model wrote it; no history rewrite on pushed main) — cost if wrong: cosmetic.
Task 1: ⚠️ carried to Task 2: spec 10.1 column lists must match migration 003 DDL (task_intents, seal_requests, pii_erasures); records/service.py must handle {n:0W}/reset before any test creates test-flow records.
Task 1: minor (deferred): explicit `reset: never` on a non-sequence field is accepted (use model_fields_set).
Task 1: minor (deferred): role_in parser strips spaces/trailing newline (looser than other guard args).
Task 1: minor (deferred): new rejection tests assert error code only, not e.value.path.
Task 1: minor (deferred): _check_sequence missing type hint for f (FieldSpec).
Task 1: minor (deferred): label schema min/maxLength duplicate the pattern's length bound.
Task 1: minor (deferred): sequence field without `format` is now SCHEMA_INVALID (Plan 01 defaulted to "{n}"); shipped manifests all have format.
Task 1: complete (commits aa2e4b0..15003fa, review clean)
Task 2: dispatched (BASE 15003fa, implementer a5a880a0bf9e57ca2, opus)
Task 2: implementer DONE a789b07
Task 2: review — spec ✅ content; Critical 1: temp tables shadow tables read by record_salt_init / record_seal_guard / upload_record_open (unqualified names, no SET search_path) → bypass seal guard, upload lock, salt creation (reproduced as dxos_core). Minors: m1 client can set pii_erasures.txid; m2 spec 25.2 says 128-bit salt; m3 test drops default-named constraint; m4 Ctx.timezone default duplicates Settings; m5 weak asserts (plan-mandated, covered by strict loop).
Ruling: fix in a NEW migration 004_harden_triggers.sql, not by editing 003 — 003 is already on public main and migrate.py rejects edited applied migrations by sha256 — cost if wrong: one extra small migration file.
Ruling: m1 fixed by BEFORE INSERT trigger forcing NEW.txid := txid_current() (plus column-level grant) — DB-level binding of evidence to the exact transaction is what spec 25.2 promises — cost: none.
Ruling: fix m2, m3, m4 in the same round; m5 left as is (plan-mandated, strict loop already covers).
Task 2: fix round 1 dispatched (resume a5a880a0bf9e57ca2)
Task 2: fix round 1 DONE c57e006 (migration 004)
Task 2: fix round 1 re-review dispatched (sonnet)
Ruling: implementer concern "app queries (ensure_salt) still unqualified" accepted as is — a compromised dxos_core shadowing its own session only fools itself; DB-side guards are now qualified and TEMP is revoked from PUBLIC — cost if wrong: one more hardening pass in final review.
Task 2: c57e006 pushed before re-review (strictly safer than a789b07 already on main)
Task 2: re-review — all findings ADDRESSED, no new breakage. Out-of-scope (parked for final review): spec 10.1 names ensure_salt vs 25.2 new_salt(); redundant txid DEFAULT; stray blank line in test_migrations.py.
Task 2: complete (commits 15003fa..c57e006, review clean after fix round 1)
Task 3: dispatched (BASE c57e006, opus) with task-3-rulings.md (T3-a..g)
Ruling T3-a..g (see task-3-rulings.md): namespace-URI matching, no free text, id pattern for all ids, graph-shape rules so render rebuilds node kinds, sorted flows for stable re-render, all failures → BPMN_INVALID /workflow/bpmn, verify defusedxml license from metadata — they make the brief's tests consistent and close parser-differential gaps — cost if wrong: some valid hand-written BPMN (default flows, gateway chains, documentation text) is rejected and must be rewritten.
Task 3: implementer aa90d71d4b1a72faf (opus)
Task 3: implementer DONE_WITH_CONCERNS 4e37fb5 (161 bpmn tests; make check 505)
Ruling: accept the implementer's stricter BPMN rules (start→userTask, all nodes reachable, guard_failed/cancelled reserved for every node id, strict parent/child structure, exact conditionExpression) — narrower input = smaller attack surface for the JUEL gate — cost if wrong: modeler exports (bpmn.io/Flowable Modeler: incoming/outgoing, exporter attrs) are rejected; Task 14 must hand-write App A/B BPMN and docs/manifest-guide.md must say so.
Ruling: process id follows rule 2 only (dot allowed), T3-c id pattern applies to other ids — T3-c contradicted rule 2 — cost: none.
Ruling: defusedxml iterparse with the same forbid flags instead of fromstring — needed to resolve xsi:type prefixes by scope — cost: none if forbid flags are honored (reviewer to confirm).
Task 3: review dispatched (opus); 4e37fb5 pushed (validator not wired into install path yet)
Task 3: review — spec ✅, Approved, no Critical/Important. Minors parked: m1 dict fields in frozen ProcessModel (unhashable/mutable); m2 render self-check ignores seal_tasks; m3 unprefixed xsi:type accepted regardless of default ns; m4 pre-existing StarletteDeprecationWarning noise; m5 raw {uri}local in error message.
Carry-forward: (a) Task 4/5/12 render only a model returned by check_against_manifest for that same manifest; (b) Task 6 bridge must reject decision outside decisions_by_task[t] before completing; (c) Task 4 should automate deploying render_bpmn output to Flowable; downstream trusts seal_tasks only from parse_bpmn/check_against_manifest; never hash/cache ProcessModel.
Task 3: complete (commits c57e006..4e37fb5, review clean)
Ruling T4 (see task-4-rulings.md): complete() gains local_variables for C18; integration test selects task by instance + unique business key (shared H2 leftovers); flowable_client fixture skip/require like DB; add respx dev dep; 401/403/unexpected 4xx → WorkflowUnavailable; factory returns None when no password file — brief's literal test breaks on re-run and C18 needs task-local vars — cost if wrong: small signature change for Task 6.
Task 4: dispatched (BASE 4e37fb5, implementer a2b8a737a6219b272, sonnet)
Task 4: implementer DONE_WITH_CONCERNS 21d0917 (58 unit + 10 live; integration 236; make check 566; witness 18; compose static 28)
Ruling: list_tasks uses candidateGroups (comma list) — candidateGroupIn is silently ignored by Flowable 7.1.0 (verified live) — cost: none.
Ruling: complete() on 500 consults task history (done → TaskGone, else WorkflowUnavailable) — real loser of a concurrent complete gets 404/500, never 409 — cost if wrong: a genuine engine fault on an already-done task maps to 409.
Ruling: production Flowable admin password stays an env var for the flowable service (image reads no secret file); secret file goes to trust-core-api only — cost: password visible in flowable container env (same host trust boundary).
Ruling: compose.test H2 Flowable + CI wait step unverified (no Docker daemon) — CI will reveal; fallback is dropping the SPRING_DATASOURCE lines — cost: one CI fix commit.
Note for Task 6: undefined decision → Flowable 500 with task left open, so the bridge must validate decision against decisions_by_task first; outcome() on unknown id raises WorkflowUnavailable.
Task 4: review dispatched (sonnet); 21d0917 pushed
Task 4: review — spec ✅; Important: raw ids in URL paths (httpx normalises ../ → admin call retarget, e.g. DELETE deployment). Minors: 404 on wrong base URL looks like "gone"; list_tasks truncates if total missing; trust_env; repr userinfo; per-request client; deploy race; unverified H2 overrides; hand-copied secrets list; double _json.
Ruling: fix round 1 = path-id validation (ValueError, no request) + minors (paging total, trust_env=False, reject userinfo, drop H2 overrides, sync comment, ping(), single _json); defer per-request client and deploy race (Task 12 serialises with advisory lock) — cost: none.
Task 4: fix round 1 dispatched (resume a2b8a737a6219b272)
Task 4: fix round 1 DONE 2e81007; re-review dispatched (sonnet)
Task 4: re-review — all findings ADDRESSED, no new breakage. Out-of-scope: base_url query/fragment not rejected (operator config); callers must map _seg ValueError → 404 (Task 6/API wiring).
Task 4: complete (commits 4e37fb5..2e81007, review clean after fix round 1)
Task 5: dispatched (BASE 2e81007, sonnet) with task-5-rulings.md
Ruling T5: reuse split_guard/parse_role_list; unknown guard → ValueError; data sources pinned (CLEAN via objects join, completions by current instance); fixture flow_record_with_uploads — brief left data sources implicit — cost if wrong: query adjustments in Task 6.
Task 5: implementer a06f707db7fe42823 (sonnet)
Task 5: implementer DONE_WITH_CONCERNS 762d42a (39 unit + 14 integration; make check 632; integration 250)
Ruling: keep Sonnet trailer on 762d42a (accurate attribution of the implementing model) — cost: none.
Ruling: role_in with stray brackets → ValueError in evaluate; Task 1 parse_role_list left as is (validator already rejects malformed at install per Task 1 tests; parked for final review) — cost: none.
Carry-forward: Task 14/15 docs/manifest-guide.md must say assignee_is_caller always fails until a claim API exists; Task 6 and :pii-review take FOR SHARE before load_guard_input.
Task 5: review dispatched (sonnet); 762d42a pushed
Ruling T6 (see task-6-rulings.md): C3/C4/C7/C9/C13/C15/C18 applied; LOCK_WF=724100 (two-int session lock), LOCK_KEYSTMT=724101; ValueError path id → 404; startup ping logs ERROR only; seal hooks injected, fail-closed (500, rollback) when absent until Task 7 — cost if wrong: Task 7 rewires hook injection.
Task 6: dispatched (BASE 762d42a, opus)
Task 5: review — spec ✅, Approved. Minors: m1 ensure_salt read-then-INSERT race under FOR SHARE after erase (PK violation → 500); m2 sha256::text cast defeats index; m3 no cross-record leakage test for uploads/refs/reviews/completions; m4 task named creator — already rejected by validator (Task 1, validator.py:195).
Ruling: fold m1 and m3 into Task 6 (ensure_salt INSERT … ON CONFLICT DO NOTHING + re-select; one cross-record test in test_guard_input.py); m2 parked for final review — Task 6 is the first concurrent caller — cost: none.
Task 5: complete (commits 2e81007..762d42a, review clean)
Task 6: implementer afa50143880b2c5ae (opus)
Task 6: implementer DONE_WITH_CONCERNS 132699a (make check 641; integration 274; witness 18; 3 reruns no flakes)
Ruling: workflow:start calls Flowable inside its FOR UPDATE transaction — brief step 4 mandates it and the 003 upload trigger relies on the row lock to refuse racing uploads — cost: row lock held up to Flowable timeout (10 s) on start.
Ruling: accept implementer-chosen names (deny reasons no_app_role/admin_no_data_access; actions complete/pii_review/list_tasks; problem slugs invalid-decision, invalid-comment, workflow-finalize-failed, workflow-model-mismatch); spec/docs list them in Task 15 — cost: rename later.
Ruling: DXOS_ORG_* in .env.example/compose belongs to Task 7 per its Files list — cost: none.
Process note: RED evidence partly produced after the fact (implementation removed); new unit tests and cross-record test never seen red — reviewer to check those tests can fail.
Task 6: review dispatched (opus); 132699a pushed
Task 6: review — spec ✅, Approved. Minors: m1 ValueError→404 untested (..%2F never reaches service); m2 late Flowable commit after client timeout loses a completion (SoD hole for not_same_actor:<task>); m3 reconcile_all lock/pool acquire order can deadlock; m4 admin reconcile 503 dead code; m5 pre-auth 409s (plan-mandated); m6 missing tests (other-id branch, app-not-active); race test nondeterministic; m7 Starlette warning (pre-existing); m8 latest_statement unused. Also ⚠️ inbox lacks per-record read filter.
Ruling: fix m1, m2, m3, m4, m6 and the inbox read filter now (task-6-fix-1.md) — m2 is a separation-of-duty integrity gap on the core trust path, the rest are cheap — cost: one fix round; no migration.
Ruling: m5 accepted (plan-mandated, ids are server UUIDs); m7 parked for final review; m8 left to Task 7.
Task 6: fix round 1 dispatched (resume afa50143880b2c5ae)
Task 6: fix round 1 DONE 6a339e6 (workflow api 31 ×3; integration 283; make check 651; witness 18)
Ruling: close the residual >30 s late-commit gap with an invariant (every Flowable-finished task of the current instance must have a task_completions row, else recover via intent or fail closed 409 workflow-inconsistent) — timing alone cannot guarantee SoD — cost: one extra Flowable history query per :complete.
Task 6: fix round 2 dispatched (resume afa50143880b2c5ae)
Task 6: fix round 2 DONE 2ac5789 (flowable client 97; workflow api 33 ×2; integration 286; make check 653)
Ruling: a task finished in Flowable by deletion/console cancel also blocks the record (fail closed) — admin must intervene — cost: manual recovery path needed later (Task 12 health shows it).
Task 6: re-review of rounds 1+2 dispatched (opus)
Ruling T7 (see task-7-rulings.md): build on Task 6's keys.py/settings/SealHooks; record_digest = data_digest (no second formula); C5 drop verify/bundle lines from AT-27 (→ T8/T9); C14 legal-mapping note goes to report for T15; health fields added only if a health/status route exists; reason-code lists taken from DB CHECKs — cost if wrong: small rework in T8/T12.
Task 6: re-review — all findings ADDRESSED, no new Critical/Important. Parked for final review: historic_done_tasks returns partial list on empty page while start<total (should raise); no test for invariant-history-unavailable → 503; margin counted from intent created_at (before call); invariant assumes Flowable history level ≥ audit (deploy/docs must keep it); console-deleted tasks fail closed as inconsistent.
Task 6: complete (commits 762d42a..2ac5789, review clean after fix rounds 1–2)
Task 7: dispatched (BASE 2ac5789, opus)
Task 7: implementer a171905d995073568 (opus)
Task 7: implementer DONE_WITH_CONCERNS 6d466d5 (make check 664; integration 311; witness 18; RED recorded first)
Ruling: my .env.example placeholder ruling was wrong (a copied .env would seal the placeholder permanently into an append-only, anchored key statement). Fix in Task 7 fix round: OrgNotConfigured also when org_name is blank or starts with "changeme" (case-insensitive); keep DXOS_ORG_NAME=changeme-ten-to-chuc in .env.example — cost: none.
Ruling: health fields live on /admin/v1/ledger/status until Task 12 builds /admin/v1/health (Task 12 must move/duplicate them) — cost: small move later.
Ruling: accept extras (attempts cap after transient waits, statement/KMS public-key mismatch refusal, anchor-job dedupe rule, SealOutcome REVOKED, problem type not-sealed) subject to review — cost: none.
Task 7: review dispatched (opus); 6d466d5 pushed
Task 7: review — spec ✅, Approved. Minors: m1 OrgNotConfigured/SealKeyExpired paths untested past R-1; m2 key.published appended before sign (ledger lock across KMS); m3 concurrent first seal misreported expired; m4 revoke skips role check if pinned manifest missing (unreachable, FK); m5 race test does not prove race; m6 org predicate in 3 places; m7 seal_key status stale after rotation; m8 alternating errors keep job alive; m9 redundant public_keys().
Ruling: fix round 1 = org placeholder helper + m1–m7 (task-7-fix-1.md); m8 parked (visible via seal_pending), m9 optional — cost: one round.
Task 7: fix round 1 dispatched (resume a171905d995073568)
Ruling T8 (see task-8-rulings.md): C5 public-view-after-erase test here; C8 left to T9; C9 fixtures; shared immutable key cache, unknown version + KMS down → 503 keys-unavailable; issuer null + ERROR if statement missing; labels from pinned version; streaming 256-byte cap — cost if wrong: small API adjustments in T9/T10.
Task 7: fix round 1 DONE d25bd40 (make check 672; integration 323; witness 18); pushed
Ruling: accept seal_key status fallback to latest existing statement when KMS unavailable; LOCK_KEYSTMT + record lock still held while signing first seal (ledger lock no longer) — serialises statement insert — cost: first seal per key version blocks concurrent first seals for KMS latency.
Task 7: re-review dispatched (sonnet)
Task 7: re-review — all findings ADDRESSED, no new breakage. Parked: seal_key fallback may show stale ok when KMS down after rotation (prefer "unknown"); ledger/status now calls KMS public_keys() per request (latency); ensure_key_statement wrapper duplicates insert+publish sequence; cross-host clock skew → SealKeyExpired retry.
Task 7: complete (commits 2ac5789..d25bd40, review clean after fix round 1)
Task 8: dispatched (BASE d25bd40, opus)
Task 8: implementer af0640018ac8da2d5 (opus)
Task 8: implementer DONE_WITH_CONCERNS be77c65 (integration 353; make check 681; witness 18)
Ruling: accept bundle top-level sth_keys — but Task 9 must treat bundle-supplied keys as untrusted hints: with --anchor-dir the keys must equal the anchor repo's keys/…, without it the verdict is at most "VALID (unanchored, self-attested keys)" — cost: Task 9 wording.
Ruling: public view inclusion.anchored must be non-null only when the anchored STH covers the leaf (tree_size > leaf_index); fix in Task 8 fix round (a view must not claim anchoring it does not have) — cost: none.
Ruling: accept pending-seal bundle 200 {seal_id,status:SEAL_PENDING}; POST :bundle on require_file:false → 404; /keys serves cached keys when KMS down — cost: none.
Note for Task 12/15: anchor job retry with fixed tree_size while KMS down publishes STH without key files (added later).
Task 8: review dispatched (opus); be77c65 pushed
Ruling T9 (see task-9-rulings.md): bundle keys are hints (anchor keys win, mismatch → KEY_MISMATCH, no anchor → exit 3); C8 coverage check + tamper case; C5 core→witness erase test; no edits to the dxos-witness-kit repo (controller syncs later) — cost if wrong: kit README lags.
Task 8: review — spec ✅, Approved. Minors: m1 O(ledger) per public request (no proof cache); m2 no negative key cache; m3 statement_sha256 checked only in anchor job; m4 issuer:null untested; m5 key_files uses statement's own version. ⚠️ real uvicorn/APISIX early-413 behaviour on chunked body to confirm in e2e.
Ruling: fix round 1 = anchored coverage (decided) + m3, m4, m5; park m1, m2; early-413 e2e check → Task 10/final review — cost: one round.
Task 8: fix round 1 dispatched (resume af0640018ac8da2d5)
Task 8: fix round 1 DONE cdb8f21 (integration 357; make check 681; witness 18); pushed
Carry-forward to Task 9: bundle omits seal_key.statement entirely when no verified statement (do not require the key; with --anchor-dir report KEY_STATEMENT_NOT_ANCHORED/KEY_STATEMENT, without it INVALID or unpinned per brief); seal_key.public_key may be null.
Parked: R-1 and seal_record read statements unchecked (statement_for) — final review decides whether to switch to verified_statements; owner_bypass test helper needs superuser owner.
Task 8: re-review dispatched (sonnet)
Task 8: re-review — all findings ADDRESSED, no new breakage. Parked: admin/router and workflow R-1 still use unchecked statement_for/latest_statement; verified_statements version-vs-column check tested only via key_files.
Task 8: complete (commits d25bd40..cdb8f21, review clean after fix round 1)
Task 9: dispatched (BASE cdb8f21, opus)
Task 9: implementer a9483535b0c36f3f1 (opus)
Ruling T10 (see task-10-rulings.md): local Caddy 2.10 binary + uvicorn for curl/CSP/308 checks and the Task 8 chunked-413 real-server check; screenshots via Playwright or an explicit TODO (never faked); verify.css for CSP; 503 keys-unavailable shown as temporary; seal_id pattern check — cost if wrong: evidence screenshots deferred to the leader.
Task 9: implementer DONE_WITH_CONCERNS e817066 (witness 75; verify_api 29 incl. 3 core→witness; integration 360; make check 738)
Ruling: accept INVALID NO_STH when no STH covers the leaf (even unpinned) — inclusion unverifiable, fail closed — cost: a just-sealed record's bundle shows INVALID until the next STH (Task 10 page/docs must explain; STH job runs after each seal).
Ruling: accept stricter checks (anchored STH signature even with anchor dir, statement field checks, exact .pub format, strict RFC 3339), issuer only on VALID, sync pinned-key drift detection — cost: none.
Task 9: review dispatched (opus); e817066 pushed
Task 9: review — spec ✅, Approved. Minors: m1 RecursionError escapes CLI (exit 1); m2 printed issuer from bundle's statement copy (NFD variant) not anchored bytes; m3 NFC-colliding keys collapse in dxos_proof canonical (signature passes with visually duplicate keys); m4 sync drift compares base64 strings; m5 revocation note only on VALID; m6 test gaps (consistency code, valid_until boundary).
Ruling: fix m1, m2, m4, m6 and a witness-side reject for m3; do NOT change dxos-proof canonical now (cross-cutting: core data_digest/API inputs) — parked for final review; m5 accepted — cost: one round.
Task 9: fix round 1 dispatched (resume a9483535b0c36f3f1)
Task 9: fix round 1 DONE d7e06b2 (witness 86; verify_api 29; make check 749); pushed; re-review dispatched (sonnet)
Task 9: re-review — all findings ADDRESSED. Parked: dxos-proof canonical_bytes merges NFC-colliding keys (cross-cutting, final review); bundle-without-statement + anchor-dir path not exercised by new tests.
Task 9: complete (commits cdb8f21..d7e06b2, review clean after fix round 1)
Pending controller action: sync witness/template/README.md to PSA-OVNCR/dxos-witness-kit (separate repo) — after Plan 02 tasks, needs repo access.
Task 10: dispatched (BASE d7e06b2, sonnet)
Task 10: implementer a4bfccfa82574fa6d (sonnet)
Ruling T11 (see task-11-rulings.md): C9 fixtures, C10 exempt service-account users in Plan 01 prod-realm test; Keycloak 26.3.0 from GitHub tarball run locally (no Docker); keycloak_upgrade.py gets a direct-kcadm option to be exercised here; reuse the core app-role regex — cost if wrong: upgrade script untested against docker exec path (leader runs it on VPS).
Task 10: implementer DONE_WITH_CONCERNS aee414c (static 15; make check 764; live Caddy 2.10 + uvicorn: 35 Playwright checks, CSP/308, chunked 413 clean close on HTTP/1.1 and HTTP/2; 8 real screenshots)
Ruling: pre-STH shows "Chữ ký hợp lệ — đang chờ công bố vào sổ cái" (not bare "Hợp lệ"); bundle name = server's dxos-seal-<id>.json; fix Plan 01 bug: admin IP allow-list (@blocked) never enforced — security, cheap — in fix round 0 before review; commit Playwright script opt-in — cost: one round.
Ruling: screenshots from Caddy+uvicorn without Docker accepted as evidence; leader re-captures on dev-lite (leader item); Sonnet trailer kept.
Task 10: fix round 0 dispatched (resume a4bfccfa82574fa6d)
Task 10: fix round 0 DONE 14f2f52 (make check 766 + 2 skipped live-caddy; live allow-list 2 passed; browser 39 checks)
Ruling: blocked IPs still get 308 on /apps/verify (redir before handle) — target is 403, nothing leaks — cost: none.
Note for Task 15/CI: live Caddy tests need CADDY_BIN/caddy on PATH in CI, else skipped.
Task 10: review dispatched (sonnet); 14f2f52 pushed
Task 10: review — spec ✅, Approved. Minors: m1 stale-pick race can show false "Khớp"; m2 static tests weaker than names; m3 whole file in memory; m4 evidence doc mixes stale output + warning; m5 allow-list guard only live (CI lacks caddy); m6 invalid seals still render details; m7 308 for blocked IPs (accepted). ⚠️ APISIX routing of ':check'/':bundle' paths and remote_ip behind docker to confirm on dev-lite.
Ruling: fix m1, m2, m4, m5, m6 now; m3 documented — m1 is an integrity issue on the verify page — cost: one round.
Task 10: fix round 1 dispatched (resume a4bfccfa82574fa6d)
Task 10: fix round 1 DONE 8fa55ef (make check 770; tests/deploy 32 with caddy; Playwright 41); pushed; re-review dispatched (sonnet)
Task 10: re-review — 1,2,3,5,m3 ADDRESSED; 4 open (CI live job can pass on skip). Fix round 2 dispatched (resume a4bfccfa82574fa6d).
Task 10: fix round 2 DONE fbf074c (make check 774; tests/deploy 36 with caddy; REQUIRE_CADDY without caddy → 2 failed); pushed; re-review dispatched (sonnet)
Task 10: re-review round 2 — all findings ADDRESSED. Parked: subprocess test asserts exact "2 skipped/2 failed" counts; static test slices function body by formatting.
Leader items from Task 10: re-capture screenshots/curl on dev-lite; confirm APISIX routes ':check'/':bundle' and remote_ip behind Docker; first CI run of caddy-live job.
Task 10: complete (commits d7e06b2..fbf074c, review clean after fix rounds 0–2)
Task 11: dispatched (BASE fbf074c, opus)
Task 11: implementer a1b33f28f656e1465 (opus)
Ruling T12 (see task-12-rulings.md): P2-D14/D21/D12 summarized for the implementer; C9 fixtures; LOCK_INSTALL=724102 serializes approve (Flowable deploy race); move seal_pending/seal_key/org from ledger/status to health; streaming 1 MB cap; identical PENDING resubmission idempotent — cost if wrong: small API adjustments in Task 13 CLI.
Task 11: implementer DONE_WITH_CONCERNS 2cb77ba (make check 839; integration 360; witness 86; live KC 26.3.0 infra 18/18 after upgrade; upgrade 2nd run no-op)
Leader items from Task 11: run ops/keycloak_upgrade.py on VPS and dev stack (--profile dev-lite); put the existing dxos-installer secret from Keycloak into the .env value behind installer-client-secret, recreate trust-core-api; use --admin-user if bootstrap admin changed.
Ruling: accept KeycloakAdmin extra keyword-only verify=True (TLS) — cost: none.
Task 11: review dispatched (opus); 2cb77ba pushed
Task 11: review — spec ✅, Approved. Minors: m1 C10 exemption too broad; m2 live "only manage-realm" test weak; m3 factory per request defeats token cache; m4 upgrade may create client with literal ${…}; m5 cleanup rc ignored / OSError traceback; m6 unnamed "1 warning" in make check (pre-existing). ⚠️ docker-exec path and core→keycloak:8080 admin URL under prod hostname settings unverified (leader on dev-lite).
Ruling: fix m1, m2, m4, m5 now; m3 → Task 12 keeps one KeycloakAdmin (cache keyed by secret); m6 parked — cost: one small round.
Task 11: fix round 1 dispatched (resume a1b33f28f656e1465)
Task 11: fix round 1 DONE 3b2c0e6 (122 focused; make check 844; live KC infra 18); pushed; re-review dispatched (sonnet)
Task 11: re-review — all findings ADDRESSED. Parked: rc stays 0 when only cleanup of in-container kcadm config fails (admin token may remain in /tmp).
Task 11: complete (commits fbf074c..3b2c0e6, review clean after fix round 1)
Task 12: dispatched (BASE 3b2c0e6, opus)
Task 12: implementer a5f3cac36a205c787 (opus)
Ruling T13 (see task-13-rulings.md): issuer derivation only from admin.<domain>; token bound to the server it was issued for (DXOS_TOKEN exempt); atomic 0600 token write; https only except localhost; 1 MB client-side cap; release.yml builds wheel only — cost if wrong: small CLI UX changes.
Task 12: implementer DONE_WITH_CONCERNS 84b329c (make check 891; integration 390; witness 86)
Ruling: Flowable deployment name {id}@{version}#{rendered_sha256[:16]} — deploy reuses by name, a bare name could bind old BPMN — cost: name differs from the brief (docs).
Ruling: accept stricter upgrade rules (field cannot become required, pii cannot be removed/changed, tasks/workflow cannot be dropped; access changes shown in diff, not blocked) — tightening only; App A/B 1.1.0 still passes — cost: Task 14 must stay within them.
Ruling: resubmit of ACTIVE/DISABLED version → 409; disable with no ACTIVE → 404 app-not-active; disable writes status + app.disabled directly — cost: none.
Open for review: approve validates before four-eyes (self-approval of an invalid manifest → 422 without deny).
Task 12: review dispatched (opus); 84b329c pushed
Ruling T14 (see task-14-rulings.md): skip PATHS line (C1, done in T1); hand-written BPMN under Task 3 rules; 1.0.0 fixtures from git HEAD; resolve brief-vs-stricter-upgrade conflicts in favour of a passing upgrade and report; AT-14 hits removed from core/src, never weaken the test — cost if wrong: field requiredness differs from the brief.
Task 12: review — spec ✅, Approved. Minors: m1 four-eyes after validation (no deny leaf for invalid self-approval); m2 lone surrogate → 500; m3 body-cap helper duplicated with verify_router; m4 streaming 413 untested; m5 approve waits on advisory lock without timeout; m6 downgrade allowed; m7 seal_key none/expired outside ok/down format; m8 409 before check_upgrade; m9 indentation. ⚠️ admin-host-only routing not in diff.
Ruling: fix m1–m6, m9 and verify admin-host routing now; m7 → Task 13 note; m8 accepted — cost: one round.
Parked for final review: lone surrogates may cause 500 in other JSON APIs that canonicalize (records) — cross-cutting.
Task 12: fix round 1 dispatched (resume a5f3cac36a205c787)
Controller: progress summary updated (repo 1a91b47 + project doc tong-ket-tien-do.md) with Plan 02 table §11 and VPS/leader to-do §12 (V1–V13); keep §12 updated as tasks add leader items.
Task 12: fix round 1 DONE 2666311 (integration 395; make check 895; witness 86; tests/deploy 40 with caddy); pushed
Ruling: accept non-blocking install lock on submit and disable too (409 install-in-progress) — cost: an admin may need to retry.
Finding fixed in round: public Caddy host passed /admin/* to APISIX (only APISIX host rule stopped it) → public host now 404s /admin* itself.
Task 12: re-review dispatched (sonnet)
Task 12: re-review — all findings ADDRESSED (public-host /admin block verified live against 18 path tricks). Parked: disable docstring says "always possible" but can 409 briefly.
Task 12: complete (commits 3b2c0e6..2666311, review clean after fix round 1)
Task 13: dispatched (BASE 2666311, sonnet)
Task 13: implementer ac7f98e0bc6ada0db (sonnet)
Ruling T15 (see task-15-rulings.md): cloud session writes and statically verifies everything; e2e/AT-13/AT-19/AT-20/release run by leader on VPS; no tags/GHCR/release; CHANGELOG 0.2.0 Unreleased; legal-mapping reader table left empty for the team; no invented evidence — cost if wrong: leader must still run the M2 gate.
Task 13: implementer DONE_WITH_CONCERNS 3cf40b3 (cli 95; make check 990)
Ruling: keep Sonnet trailer; usage errors exit 1; extra modules errors.py/urls.py accepted — cost: none.
Ruling (to fix after review, decided now): store the refresh token in the same 0600 server-bound file and refresh automatically (5-min Keycloak access tokens make the CLI unusable otherwise); verify discovery `issuer` equals the configured issuer (mix-up defence) — cost: one fix round.
Task 13: review dispatched (sonnet); 3cf40b3 pushed
Task 13: review — spec ✅; Important: symlinked config dir redirects token write + chmods target. Minors: device-flow timing trusts server (nan/huge/0 interval); device client trust_env; --ca-file wording; approve/disable non-dict body traceback; Ctrl-C 130 undocumented; URL userinfo echoed; big test file. ⚠️ manifest schema references only workflow.bpmn (to confirm).
Ruling: fix round 1 = refresh token + issuer check (decided) + Important + m1–m6; m7 optional — cost: one round.
Task 13: fix round 1 dispatched (resume ac7f98e0bc6ada0db)
Task 13: ⚠️ resolved — manifest.schema.json references only workflow.bpmn (pattern ^bpmn/[a-z0-9_-]+\.bpmn$).
Task 13: fix round 1 DONE 616a95b (cli 143; make check 1038); pushed
Ruling: refresh network/5xx → exit 2 (credentials may still be valid), rejected/expired refresh → 3; no cross-process refresh lock (loser exits 3, re-login) — cost: rare re-login with two concurrent CLIs.
Leader item (VPS): verify dxos-cli device flow + refresh grant against the real Keycloak (refresh token issued with scope openid).
Task 13: re-review dispatched (sonnet)
Task 13: re-review — all findings ADDRESSED. Parked: token_endpoint not required same-origin as issuer (trusted via validated discovery).
Task 13: complete (commits 2666311..616a95b, review clean after fix round 1)
Task 14: dispatched (BASE 616a95b, sonnet)
Task 14: implementer a3b89e0aaa4dd72a0 (sonnet)
Task 14: implementer DONE_WITH_CONCERNS 9524e70 (make check 1048; integration 395; tests/apps 12)
Ruling: local `test-dated` variant of test-flow in test_records_api.py for date-field tests (adding a date field to test-flow broke installer tests) — cost: one more synthetic manifest variant.
Note: tests/e2e and tests/infra/test_keycloak_realm.py legitimately use real apps (stack-level); AT-14 scans only shipped core code.
Task 14: review dispatched (sonnet); 9524e70 pushed
Task 14: review — spec ✅, Approved. Important (plan-mandated): AT-14 scan logic duplicated in two tests. Minors: scan omits libs/dxos-proof/src and core/README.md (copied into image); hit report uses p.name; no test of gateway branch targets; test_identity uses real app role strings. Controller verified migrated tests: test_records_api + test_ingest 72 passed (reviewer had no DB access).
Ruling: fix round 1 = single scanner helper, scan whole image contents, assert branches, synthetic roles in test_identity — cost: small.
Task 14: fix round 1 dispatched (resume a3b89e0aaa4dd72a0)
Task 14: fix round 1 DONE cb8e2a2 (154 focused; make check 1050); pushed; re-review dispatched (sonnet)
Task 14: re-review — all findings ADDRESSED. Parked: anti-empty guard counts total only; tests/apps imports helper from core/tests via pythonpath.
Task 14: complete (commits 616a95b..cb8e2a2, review clean after fix round 1)
Task 15: dispatched (BASE cb8e2a2, opus)
Task 15: implementer ac0339ab9679624d3 (opus)
Task 15: implementer DONE_WITH_CONCERNS 25fd335 + 8168dd6 (make check 1101; e2e 14 collected/skip; compose release config ok; openapi --check ok)
Ruling: package versions stay 0.1.0 until the leader bumps them at tagging (release check job enforces) — cost: leader runs the bump commands.
Ruling: dev-only user chuyen_vien_tp1 (chuyên viên + trưởng phòng) added so AT-07 hits 403 same_actor — cost: dev stacks rerun keycloak_upgrade --profile dev-lite.
Leader decision needed: VPS e2e needs dev users/dxos-test client on a public host (known passwords) — add/remove commands in task-15-report.md; removal untested.
Task 15: review dispatched (opus); 25fd335+8168dd6 pushed
Task 15: review — spec ❌ (one item: controller failed to carry the Task 6 ruling "names documented in Task 15" into the brief); Important: deny reasons/actions/problem slugs undocumented. Minors m1–m12 (at13 self-approval check fails open, install_apps rc, run_e2e token fetch, App B AT-28 conditional, unseal key in argv, release.yml python, runbook interpretation unmarked, dev-user warning, weak evidence test, CHANGELOG wording, unexplained warning, secrets on command lines in report).
Ruling: my omission — carry the Task 6 naming ruling now with a drift test; fix m1–m10, m12; park m11 (Starlette warning) and upgrade-after-disable (no additive check vs DISABLED) for final review — cost: one round.
Task 15: fix round 1 dispatched (resume ac0339ab9679624d3)
CI: run 39611925345 (8168dd6) unit job failed — compose v2 drops !reset through YAML alias in compose.release.yaml (reproduced locally with compose v2.39.4; logs not downloadable through proxy). Fix added as item 13 of task-15-fix-1.md.
Task 15: fix round 1 DONE d17c755 (make check 1110; release static 14/14 on compose v5.6 + v2.39.4); pushed; re-review dispatched (sonnet); CI watch pending
Task 15: re-review — all 13 items ADDRESSED (release static 14/14 on compose v5.6 and v2.39.4). Parked: drift test regexes tied to call shapes; at13 status_of failure inside wait loop.
Task 15: complete (commits cb8e2a2..d17c755, review clean after fix round 1)
All 15 tasks complete. Next: final whole-branch review (opus) aa2e4b0..HEAD.
CI: d17c755 green (run 39614280316) — compose v2 fix confirmed on GitHub.
Controller: summary §11/§12 updated (f7e59bf), VPS checklist docs/handoff/vps-checklist-plan02.md (215208c), project doc synced. Final review running (opus) on aa2e4b0..d17c755.
Final review (opus): "With fixes". No Critical. Important: I1 pool hold-and-wait in record_lock (API freeze, reproduced); I2 upgrade after disable skips P2-D14/_require_newer. Minors m1–m10 (NFC collision raise, surrogate/deep JSON 422, verified statements on signing path, historic_done_tasks partial page, seal_key unknown, verify page headline only when anchored, Flowable history doc, remove ensure_key_statement, disable docstring, Starlette warning filter). Parked items adjudicated (see final review report). Suites at d17c755: make check 1112, integration 395+1 skip, witness 86, CI green.
Ruling: one final fix dispatch covering I1, I2 and m1–m10 (all cheap) — cost: one round + scoped re-review.
Final fix: dispatched (BASE 215208c, opus, fresh implementer)
Final fix: implementer a4550e351e00b5ded (opus). Leader items added by final review: NTP on VPS (seal clock skew); admin recovery runbook for workflow-inconsistent records; APISIX :check/:bundle + early-413 on dev-lite; at13 status_of loop watch.
Final fix: DONE 87b3ca5 5331d6e 88f9c28 (make check 1125 no warnings; integration 408; witness 86; cli 145; deploy 55); pushed; scoped re-review dispatched (opus)
Final fix re-review (opus): all I1, I2, m1–m10 ADDRESSED; old code fails the new pool tests (TimeoutError); no new breakage. Residuals: (1) version_diff baseline after :disable → fixed by controller inline 0bd62c9 + 1d? (lint wrap) with RED/GREEN test test_diff_after_disable_compares_with_last_active; (2) same-record waiters hold a request connection while queued — acceptable; (3) seal job retries KeyStatementInvalid forever — acceptable (fails closed, health invalid); (4) surrogate manifest → 422 invalid-request — acceptable; (5) history level documented only — acceptable; (6) verify-page evidence doc shows old "Hợp lệ" headline — leader item (re-capture on dev-lite); (7) public :check parser no RecursionError catch — acceptable (256-byte cap).
Controller note: commit 0bd62c9 was pushed with a ruff E501 (my chained command did not stop on make check failure); fixed in the next commit.
CI: 2b78542 green (0bd62c9 red on lint, fixed).
