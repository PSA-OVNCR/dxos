<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 11 — controller rulings and context (binding; refine the brief)

## Preflight rulings
- C9: fixtures `realm()`, `client(name)` (helpers in tests/infra/test_keycloak_realm.py, reading deploy/keycloak/realm-dxos.json — reuse existing helpers there if present), `kc` (KeycloakAdmin with respx-mocked TOKEN/ADMIN URLs, in core/tests/test_keycloak_admin.py), `kc_live` (infra fixture driving a real Keycloak; skip unless the infra marker/env is set, like existing infra tests) — each with a one-line docstring contract.
- C10: the Plan 01 test `test_production_realm_has_no_users_no_test_client_no_literal_secret` will fail once the service-account user is added. Modify it so users that have `serviceAccountClientId` are exempt (and assert that such users have no credentials and no realmRoles); every other user is still forbidden in the production realm.

## Running Keycloak without Docker
- No Docker daemon here. Java is installed (Flowable runs on it). Download the Keycloak 26.3.0 release tarball from GitHub (`https://github.com/keycloak/keycloak/releases/download/26.3.0/keycloak-26.3.0.tar.gz`) into /tmp/claude-0/-home-claude/4180d5ee-f617-5df6-a5ae-a86295cdbc32/scratchpad/svc/bin/ (not the repo), run `bin/kc.sh start-dev --http-port=58180 --http-relative-path=/auth` with bootstrap admin env vars set to changeme-test values, import `realm-dxos-dev.json` (or the prod realm + dev overlay as the build script does), run the infra test against it, then stop it.
- `ops/keycloak_upgrade.py`: by default it runs `docker exec <keycloak container> /opt/keycloak/bin/kcadm.sh …` as the brief says. Add an option (e.g. `--kcadm /path/to/kcadm.sh` or env `DXOS_KCADM`) that runs kcadm directly, so it can be exercised here against the local Keycloak. The ops test checks the generated commands (no network); the real run is: import the v0.1.0 realm (`git show v0.1.0:deploy/keycloak/realm-dxos.json` if the tag exists locally, else the realm at commit 79016d0 — the Plan 01 Task 5 completion), run the upgrade, run the infra test (must pass), run the upgrade again (must report no changes). Record outputs in the report.
- Never put a real secret in the repo; `.env` / compose values stay `changeme…`. The installer client secret goes to a compose secret file mounted only in trust-core-api (`installer-client-secret`), `DXOS_INSTALLER_CLIENT_SECRET_FILE=/run/secrets/installer-client-secret`.

## Other rulings
- `KeycloakAdmin`: token via client_credentials, cached until shortly before `expires_in`; network/5xx/401/403 → `IdpAdminUnavailable` (never log the secret or token); `_APP_ROLE` pattern must be the same one the core uses for app roles (find it in core auth/policy code and import it — do not define a second regex); 409 on POST /roles is success-not-created; return value lists only roles created by this call.
- Settings: 4 fields exactly as the brief; `installer_client_secret_file` read at use time like other *_file secrets; a factory returning None when the file is not configured (Task 12 will return 503 for approve then).
- Spec 15 (threat T5): add the manage-realm risk (the installer secret can create/modify realm roles and clients; mitigations: secret only in trust-core-api, admin events on, roles created only with `app:<id>:` prefix by code, four-eyes approval in Task 12) — keep the spec's existing table format.
- dev-overlay: add `admin2` with `dxos-admin`; regenerate realm-dxos-dev.json with `python ops/build_dev_realm.py` and pass `--check`.
