# Ledger Plan 01 (bản sao lúc bàn giao 20/10/2026)

Bản gốc nằm ở `.superpowers/sdd/2026-10-20-dxos-01-nen-mong-m0-m1/progress.md` (git-ignored). Phiên mới: chép tệp này về đường dẫn đó (bỏ 4 dòng đầu) rồi tiếp tục ghi.

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
```
