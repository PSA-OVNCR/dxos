<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 13 — controller rulings and context (binding; refine the brief)

- Admin API shapes: read task-12-report.md (section with the exact JSON of each admin route) — the CLI must match it exactly. Problem responses are RFC 7807 with extensions (`code`, `path`, `guard`, `reason` where present).
- C9 fixtures with one-line docstring contracts in cli/tests/conftest.py: `app_dir` (tmp dir with manifest.yaml copied from core/tests/fixtures/manifest-test-flow.yaml and bpmn/test-review.bpmn), `token_env` (sets DXOS_TOKEN to a dummy value), `SUBMITTED` (the 202 body per Task 12), `MANIFEST_WITH_BPMN_PATH(path)` (manifest text with workflow.bpmn replaced). The CLI package must not import dxos_core (it is a separate wheel); tests may read core fixture files by path.
- Issuer: if `--issuer` is omitted, derive it only when the server host starts with `admin.`: `https://<host minus "admin.">/auth/realms/dxos`; otherwise exit 1 asking for `--issuer`. Device endpoints come from the issuer's `.well-known/openid-configuration` (device_authorization_endpoint, token_endpoint), client_id `dxos-cli`, scope `openid`.
- Device flow: honour `interval` (default 5 s), `slow_down` (+5 s), stop on `expired_token`/`access_denied` (exit 1), overall deadline = `expires_in`; print `verification_uri_complete` (or uri + user_code); never print the access/refresh token.
- Token storage: `$XDG_CONFIG_HOME/dxos/token.json` (fallback ~/.config) written atomically (temp file created with os.open(..., 0o600) in the same dir, then os.replace); dir 0700. Store `server` and `issuer` with the token; refuse to use a stored token for a different `--server` (exit 3 "chạy lại dxos login --server …") — never send a token to a host it was not issued for. `DXOS_TOKEN` env wins and is used for any server (CI/e2e).
- Expired token: if `expires_at` passed → exit 3 without a network call; a 401 from the server also → exit 3 with the same message.
- HTTP: `--server` must be https (allow http only for 127.0.0.1/localhost, for tests); `--ca-file` passed as httpx verify; timeouts set; `trust_env` default fine (CLI runs on admin laptops). Network error / 5xx → exit 2; 4xx → exit 1 printing type/detail/code/path.
- `app install`: yaml.safe_load; only the files the manifest references (today `workflow.bpmn`); resolve() inside the app dir, reject symlinks pointing outside and absolute/`..` paths; read text as UTF-8; refuse if the request body would exceed 1 MB (the server cap) with exit 1. After 202, GET the diff and print it; `--json` prints raw JSON.
- `anchor run` and `ledger status` use Plan 01 routes (check core/src/dxos_core/ledger/router.py and admin/router.py for paths).
- LICENSES-THIRD-PARTY.md: list dxos-cli's runtime deps (httpx, PyYAML) if not already listed; no new dependency.
- release.yml: build the dxos-cli wheel next to the others; do not publish anything (no tag, no GHCR push — leader-approval items).
- (from Task 12 review) health values are "ok", "down: …", and for `seal_key` also "none"/"expired": the CLI prints them as-is and treats only "down: …" (and "expired") as problems; exit code of `dxos health` is 0 when the request succeeded (the JSON is informational).
- Admin errors to expect: 409 `version-not-newer`, 409 `install-in-progress`, 403 self-approval (problem type …/forbidden or as in task-12-report.md), 503 `idp-admin-unavailable`.
- (from Task 12 fix round) 409 `install-in-progress` can come from submit, approve and disable: the CLI retries it automatically up to 5 times with 2 s backoff (print a short "đang có thao tác cài khác, thử lại…" line), then exits 1.
