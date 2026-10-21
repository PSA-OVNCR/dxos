<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Plan 02 — final fix (from the whole-branch review; one dispatch)
Work on main in /home/claude/dxos. Commit (one or a few Conventional Commits), do NOT push, do NOT tag. Trailers from common-context.md. For every behavioural item: failing test first, record RED/GREEN. Read /home/claude/dxos/.superpowers/sdd/2026-10-21-dxos-02-tier0-m2/common-context.md for environment and rules; services are running.

## Important
I1. Pool hold-and-wait in `record_lock` (core/src/dxos_core/workflow/reconcile.py ~120-143; callers workflow/service.py ~314, reconcile.py ~403). `:complete`/reconcile hold the request connection and then `pool.acquire()` a second connection with no timeout → ~10 parallel calls freeze the API (reviewer reproduced with pool size 2: scratchpad/final-review/scripts/pool_starve.py under /tmp/claude-0/-home-claude/4180d5ee-f617-5df6-a5ae-a86295cdbc32/). Fix: take the session advisory lock on the caller's own connection (`ctx.conn` / the work connection) — `pg_advisory_lock(LOCK_WF, hashtext(rid))` there, unlock in finally, terminate/close that connection if unlock fails — so no second pool connection is ever needed; keep "no transaction open across Flowable" (session lock, not xact lock). If some path truly cannot use its own connection, use `pool.acquire(timeout=…)` → 503 `workflow-busy` with Retry-After. Fix the docstring (reconcile.py ~22-23). Regression test: pool max_size=2, two concurrent `:complete`-like flows complete (no hang; bound the test with a timeout). Check `reconcile_all` and every record_lock caller.
I2. Upgrade after `:disable` skips P2-D14 and `_require_newer` (core/src/dxos_core/registry/installer.py ~282 submit, ~403 approve). Baseline = the ACTIVE version, else the highest-semver version that was ever ACTIVE (status DISABLED). Apply `_require_newer` and `check_upgrade` (with `sealed_before` as now) against that baseline at submit and at approve. Tests: disable 1.1.0 → submit 1.2.0 dropping a field → 422 UPGRADE_NOT_ADDITIVE; submit 1.0.9 → 409 version-not-newer; disable → submit additive 1.2.0 → approve → ACTIVE. Keep docs/legal-mapping.md / runbook advice valid (re-submit a newer additive version to re-enable erase); adjust wording if needed.

## Minor (do all; each is small)
m1. libs/dxos-proof canonical.py ~31-36: raise `CanonicalError` when two keys collide after NFC normalization (byte-compatible for valid inputs). Unit test. Keep the witness-side check. Confirm no core path relies on merging (run full suites).
m2. JSON bodies: a shared helper that, after parsing, rejects lone surrogates (try `json.dumps(v, ensure_ascii=False).encode()`) and RecursionError/deep nesting → 422 (problem type consistent with existing body errors). Use it in records/router.py body parsing, workflow bodies, and admin/apps.py `read_json`. Tests: `"\ud800"` in a record field → 422 not 500; deeply nested → 422.
m3. Signing path / R-1 / health read key statements via `verified_statement_for` (seal/keys.py, seal/service.py ~180, workflow/service.py ~230, admin/ops.py ~66-68). A row that exists but fails verification → clear error (seal job stays SEAL_PENDING with ERROR log; R-1 → 503 `seal-key-expired`-style or a new `key-statement-invalid` slug — then add it to the manifest-guide error table so the drift test passes); never fall through to INSERT.
m4. workflow/flowable.py ~348 `historic_done_tasks`: empty page while start < total → raise WorkflowUnavailable. Add the "history unavailable during the completion check → 503" test.
m5. Health `seal_key`: when KMS is unavailable report `"unknown"` (not a stale "ok"); update docs/manifest-guide (or wherever health values are documented) and CLI help if they list values.
m6. verify-portal/minimal/verify.js ~236-237: headline "Hợp lệ" only when signature valid, inclusion verified AND `inclusion.anchored` non-null; otherwise "Hợp lệ — chưa neo công khai" (distinct class). Update static tests and the opt-in Playwright checks; README of the page.
m7. Note "Flowable history level phải ≥ audit (mặc định); bridge dùng lịch sử Flowable để đối soát" at the flowable service in deploy/compose.yaml (comment) and in docs/spikes/flowable.md.
m8. seal/keys.py ~171-191 `ensure_key_statement`: delete if unused outside tests (update tests), or move to a test helper.
m9. installer.py ~457-458 disable docstring: say it can return 409 install-in-progress.
m10. pytest.ini: scoped `filterwarnings = ignore:Using .httpx. with .starlette\.testclient. is deprecated` with a comment (follow-up: move to httpx.ASGITransport). Test output must then be warning-free.

## Verify before committing
`make check PYTHON=python`, `DXOS_TEST_REQUIRE_DB=1 python -m pytest -m integration -q`, `python -m pytest witness -q`, `python -m pytest cli -q`, `reuse lint`, and tests/deploy with CADDY_BIN=/tmp/claude-0/-home-claude/4180d5ee-f617-5df6-a5ae-a86295cdbc32/scratchpad/svc/bin/caddy. Report exact counts; no warnings.
Write /home/claude/dxos/.superpowers/sdd/2026-10-21-dxos-02-tier0-m2/final-fix-report.md (what changed per item, RED/GREEN, commands + output, concerns). Reply with status, commits, one-line test summary, concerns. Do not dispatch subagents.
