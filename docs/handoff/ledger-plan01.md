# Ledger Plan 01 (bản sao, cập nhật 21/10/2026)

Bản gốc nằm ở `.superpowers/sdd/2026-10-20-dxos-01-nen-mong-m0-m1/progress.md` (git-ignored). Phiên mới: chép tệp này về đường dẫn đó (bỏ 4 dòng đầu và dòng ``` cuối) rồi tiếp tục ghi.

```text
# SDD ledger — plan: docs/superpowers/plans/2026-10-20-dxos-01-nen-mong-m0-m1.md

Pre-flight (Tasks 1–3 in scope): Task 3 consumes nothing from Task 2 at interface level (merkle independent of canonical); Task 1 produces make targets used by later tasks. No conflicts.
Scope ruling: Ruling: execute only Tasks 1–3 + directory scaffold per Plan 00 §2 — user asked local-only, GitHub/VPS later — cost if wrong: remaining tasks resume from this ledger.
Ruling: local Python is 3.13 (container) while constraint says 3.12 — package declares requires-python>=3.12, CI will pin 3.12 — cost if wrong: a 3.13-only construct slips in; CI on 3.12 catches it.
Task 1: Ruling: GitHub step (Step 5) skipped — user asked local-only, GitHub later — cost if wrong: none, step remains on todo.
Task 1: Ruling: own short Code of Conduct instead of Contributor Covenant 2.1 — verbatim CC text not fetchable offline; reproducing from memory risks inaccuracy — cost if wrong: swap file later.
Task 1: Ruling: Makefile exports PYTHONDONTWRITEBYTECODE=1 — reuse 6.2 flagged gitignored __pycache__ pyc as unlicensed — cost if wrong: slightly slower test imports.
Task 1: Ruling: copyright holder "2026 DX-OS Trust Core contributors" — team name not chosen yet — cost if wrong: one sed across headers.
Task 1: Ruling: added scaffold commit (READMEs per Plan 00 §2) — user asked for full code structure — cost if wrong: none.
Task 1: complete (commits 78b473b..65130b4, tests: make check → ============================== 4 passed in 0.02s ===============================)
Task 2: Ruling: Makefile/CI call `$(PYTHON) -m pytest` instead of bare `pytest` — bare pytest may come from an isolated tool env without the editable packages — cost if wrong: none.
Task 2: complete (commits 65130b4..4e0fe7f, tests: python3 -m pytest libs/dxos-proof/tests/test_canonical.py → ============================== 9 passed in 0.03s ===============================)
Task 2: note: lint failure slipped into commit 4e0fe7f (chained command did not stop on make failure); fixed in follow-up style commit; make check now green 13/13.
Task 3: complete (commits f6d0dc4..07bdd38, tests: make check → ============================== 27 passed in 0.06s ==============================)
Final review: self-review (no reviewer subagent spawned — session policy forbids spawning agents without explicit user request); scope Tasks 1–3 only.
Final: minor (deferred): canonical_bytes raises UnicodeEncodeError (not CanonicalError) on lone surrogate strings — Records API (Task 13) must validate input before hashing.
Final: minor (deferred): rfc3339_utc truncates sub-second precision — acceptable for ledger timestamps; ordering uses idx.
Final: minor (deferred): merkle root/proofs recompute subtrees (O(n log n)) — fine at demo scale; cache in ledger layer if needed.
Final: minor (deferred): gitleaks image tag v8.18.4 not verified to exist — verify on first GitHub CI run.
Final: minor (deferred): pyproject uses PEP 639 license string with setuptools>=68 floor — raise floor to >=77 when touching packaging.
Final: minor (deferred): REUSE.toml labels all **/fixtures/** as Apache-2.0 — re-check when third-party sample files are added.
Ruling: plan workspace/ledger kept (not deleted) — only Tasks 1–3 executed; Tasks 4–17 resume from this ledger — cost if wrong: none.
Ruling: copyright holder changed to "2026 PSA_OVNCR" after user named the team — supersedes Task 1 placeholder ruling — cost if wrong: one sed.
GitHub: repo PSA-OVNCR/dxos public; PR #1 (Tasks 1–3) merged by user, CI 4/4 green (gitleaks v8.18.4 verified). Ruleset protect-main = block force push + restrict deletion only. User: push straight to main, no PR/review required.
Task 4: Ruling: work directly on main — user said "cứ up lên là dc" (no PR, no review) — cost if wrong: a red CI lands on main; fixed by follow-up commit.
Task 4: Ruling: image digests NOT pinned in this commit; test_images_pinned_by_digest marked xfail(strict=True) + ops/pin_images.py added — workspace cannot reach any container registry (Docker Hub/quay/ghcr denied by egress policy) — cost if wrong: unpinned tags until user runs `make pin-images`; strict xfail forces removing the marker once pinned.
Task 4: Ruling: live steps 6–7 (make up, netcheck, test-infra) deferred to user's Docker Desktop; checklist in docs/progress/2026-10-20-task4-kiem-tra-song.md — no image pulls possible here — cost if wrong: config errors surface only when user runs it.
Task 4: Ruling: gateway authenticates only (openid-connect bearer); dxos-admin role check for /admin/v1 left to trust-core PDP (Task 10/12) — APISIX openid-connect has no realm-role check; authz-keycloak too heavy — cost if wrong: one defense-in-depth layer missing at gateway.
Task 4: Ruling: no APISIX_STAND_ALONE env; own config.yaml with config_provider yaml mounted ro — image entrypoint would overwrite config.yaml when that env is set — cost if wrong: none.
Task 4: Ruling: dev-lite overlay keeps service name `clamav` and swaps to build ./fake-av via `image: !reset null` (compose ≥2.24) — clients keep `clamav:3310`, matrix unchanged — cost if wrong: requires newer compose.
Task 4: Ruling: added Keycloak admin-console block on public host + KC_HOSTNAME_ADMIN on admin host; added extra probes (30 total) and static tests (every service in matrix; probes agree with membership; healthcheck+restart) — spec 6.2 consequences made testable — cost if wrong: none.
Task 4: Ruling: .env.example now carries runnable localhost values; repo-hygiene test changed to "secret keys/URL passwords must start with changeme" — old test forbade any non-placeholder value — cost if wrong: weaker check on non-secret keys.
Task 4: Ruling: added fake-av unit tests (tests/deploy) and netcheck/pin_images unit tests (tests/ops) beyond the plan's list — needed to verify these tools without Docker — cost if wrong: none.
Task 4: Ruling: compose.test.yaml uses fake-av (not real ClamAV) behind name `clamav` — integration runs stay fast/offline; official acceptance (AT-*) runs on p8/p16 with real ClamAV per spec 16.1 — cost if wrong: a clamd-protocol quirk of real ClamAV missed until acceptance run.
Task 4: partial — static part done (make check: 58 passed, 2 xfailed(digest)); live steps 6–7 + pin-images pending on user's Docker Desktop. NOT marked complete.
Task 4: live run on user's Docker Desktop via File Explorer + PowerShell script (user granted computer access): run1 netcheck 30/30, 401 ok, but token_endpoint lacked /auth and apisix/flowable healthchecks broken; fixed in f07815e; run2 13/13 healthy, 30/30, issuer+token_endpoint keep /auth.
Task 4: Ruling: Keycloak runs with KC_HTTP_RELATIVE_PATH=/auth and Caddy keeps the prefix; APISIX discovery = http://keycloak:8080/auth/realms/dxos/ (plan said /realms/dxos) — stripping the prefix made Keycloak emit backchannel URLs without /auth — cost if wrong: none (verified live).
Task 4: Ruling: live steps executed by a PowerShell equivalent of netcheck/test_network_live, not `pytest -m infra` — user's Windows machine has no verified Python test env — cost if wrong: pytest live tests still unexecuted; run on WSL/VPS later.
Task 4: complete (commits 403c28e..f07815e, tests: make check → ======================= 64 passed, 5 deselected in 0.69s =======================)
Task 5: Ruling: realm JSON written by hand (reviewable, reproducible) instead of console click + export — same artifact, no export noise/IDs — cost if wrong: none.
Task 5: Ruling: realm-dxos-dev.json generated from realm-dxos.json + dev-overlay.json by ops/build_dev_realm.py; static test fails on drift — Keycloak imports one file per realm, so dev must be a full copy — cost if wrong: none.
Task 5: Ruling: standard client scopes (basic, profile, roles, web-origins, acr) declared explicitly — declaring clientScopes disables Keycloak's defaults; first live run had tokens without realm_access/sub — cost if wrong: realm JSON longer.
Task 5: Ruling: live tests (plan Step 4) run against Keycloak 26.3.0 distribution started locally (start-dev, H2, --http-relative-path=/auth) — workspace cannot pull images; stack run on user's Docker Desktop prepared (chay-task5.bat) but blocked (another app held focus) — cost if wrong: an image-vs-distribution difference; same version, low.
Task 5: complete (commits 9a79723..79016d0, tests: python3 -m pytest -p no:cacheprovider tests/infra/test_keycloak_realm.py → ============================== 18 passed in 1.00s ==============================)
Task 5: stack run on user's Docker Desktop passed (realm imported, 10/10 tokens, SPA grant 400, APISIX 401/401/pass); evidence docs/progress/2026-10-20-task5-realm-keycloak.md.
Task 6: Ruling: smoke written in Python stdlib (flowable_smoke.py) run inside net-wf via pinned python image; flowable-smoke.sh is the wrapper — Flowable has no published port; Windows teammates have no bash — cost if wrong: none.
Task 6: Ruling: compose already had flowable/flowable-db on net-wf/net-fldb from Task 4, so Task 6 "Modify compose" step is a no-op — cost if wrong: none.
Task 6: Ruling: image license evidenced by Flowable maintainer label + engine version 7.1.0 + Apache-2.0 license.txt of the official 7.1.0 release (image holds an exploded app, hash comparison impossible) — cost if wrong: image contents differ from release; low.
Task 6: complete (commits 2350c7d..9d98631, tests: python3 -m pytest -p no:cacheprovider tests/infra/test_compose_static.py → ============================== 25 passed in 0.49s ==============================)
Task 7: in progress — tooling committed 34d1c10 (measure.sh, capacity_report.py, 9 tests); live measurement NOT run (chay-task7b.bat ready on user machine); proposed to defer to VPS, awaiting user decision.
Handoff: 20/10/2026 22:10 — work transferred to another Claude account; see docs/handoff/HANDOFF.md.
Takeover: 20/10/2026 22:20 — new Claude account resumed; local repo fast-forwarded c0e7fad..18ee9c3 via git bundle (device shell cannot reach GitHub); this ledger restored from docs/handoff/ledger-plan01.md.
Ruling: Task 7 deferred until VPS exists — user 20/10: not on VPS yet, VPS will have 16 GB — cost if wrong: AT-22 unmeasured until VPS; M0 "measured" criterion slips.
Ruling: no TV-A/B/C split; whole team works on tasks jointly — user 20/10 — cost if wrong: none.
Note: user will run Claude Code on the VPS later and will notify.
Task 8: Ruling: tables in schema `core` (spec 10.1); search_path=core via pool server_settings + ALTER DATABASE SET search_path; SQL in code/tests stays unqualified — cost if wrong: none.
Task 8: Ruling: tree_heads has NO anchor_commit column; Task 16 adds an append-only `anchors` table in 002_*.sql — spec 10.1 lists anchor_commit but filling it later would need UPDATE on an append-only table — cost if wrong: one extra table in Task 16.
Task 8: Ruling: ledger_entries.ts and tree_heads.ts stored as text (domain rfc3339_utc), not timestamptz — the exact string is part of the canonical Merkle leaf — cost if wrong: time-range queries need a cast.
Task 8: Ruling: apps PK (id, version) + partial unique index (one ACTIVE per id) — keeps manifest history on upgrade — cost if wrong: Task 11 store queries filter by status.
Task 8: Ruling: guards beyond plan: sealed record cannot be DELETEd; TRUNCATE blocked on ledger/tree_heads; objects sha256/storage_key immutable (column grants + trigger); REVOKED is terminal — cost if wrong: none (relax in a later migration).
Task 8: Ruling: migrations run at trust-core-api start (core/docker/api-entrypoint.sh, owner DSN), then the owner DSN is unset before exec uvicorn; no separate migrate service, so network matrix unchanged — cost if wrong: owner credentials visible in container config (docker inspect); move to one-shot job on VPS if needed.
Task 8: Ruling: secrets via compose top-level `secrets: {environment: VAR}` mounted at /run/secrets; Settings reads *_file paths — cost if wrong: needs Compose >= 2.23 (config verified on v5.6 here; live run on Docker Desktop 2.39 pending).
Task 8: Ruling: minimal worker (DB ping + heartbeat file, `--check` healthcheck) created now; Task 14 adds job loop — compose needs a real worker process — cost if wrong: none.
Task 8: Ruling: pypdfium2 NOT added yet; deferred to Task 14 after checking licences of components bundled in its wheel (PDFium, FreeType, ...) — cost if wrong: Task 14 adds one dependency line.
Task 8: Ruling: integration fixture creates a fresh database per test; skips without DB unless DXOS_TEST_REQUIRE_DB=1; new CI job `integration` (compose.test core-db) — cost if wrong: ~1 min more CI.
Task 8: Ruling: pytest-asyncio >= 0.24 with asyncio_mode=auto — plan test samples are bare async defs — cost if wrong: none.
Task 8: Ruling: local verification in the cloud uses system PostgreSQL 16 (same role/port/password as compose.test.yaml) — image pulls blocked here; CI runs postgres:17 — cost if wrong: a PG17-only difference surfaces in CI.
Task 8: Ruling: problem() takes slug or full https://dxos.dev/problems/<slug>, plus kw-only extensions (instance allowed; type/title/status/detail reserved) — Task 13 needs extension members (errors) — cost if wrong: none.
Task 8: env: PyPI enabled by user 20/10 22:39 (only via agent proxy: run pip with NO_PROXY= no_proxy= empty).
Task 8: complete (commits 18ee9c3..ee72b95, tests: make check → 105 passed, 51 deselected; make test-integration → 34 passed (PostgreSQL 16 local); CI run 39451826958 green 5/5 incl. integration on postgres:17). Evidence docs/progress/2026-10-20-task8-trust-core.md.
Task 8: live Docker run (image build, api/worker healthy, secrets, migration at start) prepared as _claude-run/chay-task8.bat — NOT yet run.
Task 8: live run on Docker Desktop PASSED (13/13 healthy, api+worker uid 10001, migration at start, owner DSN gone from PID1 env, core UPDATE ledger denied, token via APISIX reaches core -> 404 problem+json); evidence commit 82d97c2.
Task 9: Ruling: append() stores subject/app_id in NFC (same form that goes into canonical leaf) — avoid DB value differing from hashed value — cost if wrong: none.
Task 9: Ruling: append() uses conn.transaction() so inside a caller transaction it becomes a savepoint and the advisory xact lock is held until the outer commit — ledger write atomic with business change, rollback leaves no gap — cost if wrong: long caller transactions serialize ledger writers.
Task 9: Ruling: verify_log reads all rows in one fetch (demo scale) and reports first gap or first leaf mismatch — cost if wrong: memory at very large logs; switch to cursor.
Task 9: complete (commits 82d97c2..aad846d, tests: make check → 108 passed; make test-integration → 47 passed; concurrent test 10/10; CI green 5/5). Evidence docs/progress/2026-10-20-task9-ledger.md.
Task 10: complete (commits aad846d..9982fed, tests: make check → 136 passed). JwksVerifier RS256-only, app_roles strict parse, require_principal/require_admin, /api/v1/whoami, ProblemError.
Task 11: Ruling: spec 9.1 so_hieu gets public: true (spec 1.0.2) — seal.public_fields lists so_hieu but validator requires public fields; plan also requires the verbatim manifest to validate — cost if wrong: one field flag.
Task 11: Ruling: validator order FLOOR → NAMESPACE → schema → guards → references, so floor/namespace codes win over generic schema errors (AT-11/12 expect those codes) — cost if wrong: none.
Task 11: Ruling: save_manifest(..., hmac_key=None) optional ledger events; same version with different content rejected; one ACTIVE per app — cost if wrong: installer (Plan 02) adapts.
Task 11: complete (commits 9982fed..19406fb, tests: make check → 173 passed; integration → 52 passed).
Task 12: Ruling: decide() checks roles before owner; list with reason 'owner' = own records only; extra reason unknown_collection — cost if wrong: none.
Task 12: Ruling: enforce() refuses to log a denial inside a caller transaction (RuntimeError) so policy.denied cannot be rolled back (F3) — cost if wrong: callers must call enforce outside transactions (Records API does).
Task 12: complete (commits 19406fb..68beb4a, tests: make check → 201 passed; integration → 61 passed).
Task 13: Ruling: ruff per-file-ignores S105/S106 under tests (sample CCCD/passwords) — cost if wrong: none.
Task 13: complete (commits 68beb4a..37004ff, tests: make check → 201 passed; integration → 98 passed; CI green).
Task 14: Ruling: access.update defaults to [owner] when omitted (spec 1.0.2) — App A manifest has no update list but creators must attach PDFs to their own draft — cost if wrong: owners of collections without explicit update can edit unsealed records.
Task 14: Ruling: pypdfium2 added as planned; its wheel bundles PDFium + ICU, FreeType (FTL/GPL-2.0), libjpeg-turbo, libpng, zlib, OpenJPEG, lcms2, abseil...; installed at build time, not in repo (G4). LEADER MUST APPROVE (outside MIT/BSD/Apache/PSF/ISC list) — fallback: pypdf (BSD-3, pure Python).
Task 14: Ruling: ObjectStore methods sync (boto3) called via asyncio.to_thread; promote/move take optional data= to avoid slow server-side copy on SeaweedFS — cost if wrong: none.
Task 14: Ruling: rejected (non-PDF/encrypted/no text) files also moved to quarantine, not deleted — cost if wrong: quarantine bucket grows.
Task 14: Ruling: S3 test buckets shared per test session (SeaweedFS first write to a new bucket ~4s) — cost if wrong: tests must not rely on empty buckets (they don't).
Task 14: complete (commits 37004ff..61e95f0, tests: make check → 221 passed; integration → 125 passed; CI green incl. SeaweedFS).
Task 15: Ruling: Signer.sign(..., key_version=) and make_sth signs with max sth-key version, version is inside signed bytes — cost if wrong: none.
Task 15: Ruling: keep deploy/openbao/openbao.hcl (plan said config.hcl); whole deploy/openbao mounted ro at /openbao/dxos so init.sh runs in the container — cost if wrong: path rename only.
Task 15: Ruling: policy dxos-core also allows auth/token/renew-self + lookup-self — init.sh token is periodic and must renew (found by running init.sh) — cost if wrong: none.
Task 15: complete (commits 61e95f0..26f34de, tests: make check → 230 passed; integration → 147 passed incl. real OpenBao 2.2.0; CI green).
Task 16: Ruling: anchoring optional via DXOS_ANCHOR_REMOTE (+ deploy/compose.anchor.yaml with deploy key secret); STH still signed without it — cost if wrong: none.
Task 16: Ruling: anchor:run signs STH in the API (OpenBao in net-data) and enqueues publication for the worker (only worker has egress) — cost if wrong: none.
Task 16: Ruling: witness pins sth-key per version in state; changed key for same version → BAD_SIGNATURE — cost if wrong: legitimate key replacement needs state reset.
Task 16: Ruling: image installs git + openssh-client (independent programs, G2) — cost if wrong: +~40 MB image.
Task 16: complete (commits 26f34de..90eb048, tests: make check → 241 passed; integration → 163 passed; CI green). Manual Step 5 (repo dxos-transparency-log, ruleset, deploy key, AT-18 screenshot) PENDING for leader: docs/runbook-anchor.md.
Task 17: partial — e2e suite, run_e2e.sh, compose.e2e.yaml, seed, release.yml, nightly.yml committed a4175b8 (make check → 244 passed; integration → 165 passed). Live e2e (chay-task17.bat) NOT yet run; tag v0.1.0 NOT created (needs leader decision; plan date 09/11, VPS not ready).
Review: independent whole-branch review (Tasks 8–17) found 10 issues (witness missed rewrite of anchored history; staging deleted before commit; PII revealed without ledger on create/PATCH; pii on non-string fields; OpenBao token not renewed; new STH per failed push; git without timeout; upload held DB connection; deploy key perms; worker loop died on DB error). Fixed in 28b114b (make check → 258 passed; integration → 178 passed; witness → 18 passed; CI green). #9 documented in docs/runbook-anchor.md (56bac6e).
Task 17: Ruling: EICAR fixture stored as XOR 0x5A + base64 (eicar.xor5a.b64) — Windows Defender blocked plain base64 file on user's disk (live run 1) — cost if wrong: none.
Task 17: live e2e run 1 on Docker Desktop at a4175b8: 4/5 passed (IDOR/admin least privilege, PII mask/reveal, gateway 401 + public verify, admin API not public); test_m1_end_to_end FAILED before any request (OSError reading eicar.b64, blocked by Defender). Evidence docs/progress/2026-10-20-task17-e2e.md.
Task 17: Ruling: rerun e2e on VPS Linux, not on Windows — user 21/10 — cost if wrong: upload→AV→CAS→ledger→STH→anchor→witness path stays unverified end-to-end until VPS exists.
Task 17: still partial — e2e main flow, pytest -m infra, tag v0.1.0 pending (VPS + leader decision). NOT marked complete.
Docs: BTC answers G14–G17 recorded (Project doc OLP2026-TONG-HOP-DU-AN.md §3, HANDOFF §2.1), commit 56bac6e. Summary docs/progress/2026-10-21-tong-ket-tien-do.md.
Next: write Plan 02 (M2, 16/11).
```
