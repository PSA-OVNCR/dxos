<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 15 — controller rulings and context (binding; refine the brief)

## What this cloud session can and cannot do
- No Docker daemon, no VPS, no APISIX runtime, no public actions. Therefore:
  - WRITE everything (e2e tests, ops scripts, compose overlay, workflows, docs) and verify what can be verified here: `pytest --collect-only -m e2e tests/e2e` collects without errors; e2e tests SKIP cleanly when the stack env is absent (follow tests/e2e/conftest.py from Plan 01); `bash -n` on every shell script (shellcheck is not installed — say so); `docker compose -f deploy/compose.yaml -f deploy/compose.release.yaml config` can run without a daemon (the CLI is installed) — run it; workflow YAML parses; static tests pin the key strings.
  - Do NOT run: the e2e on a stack, ops/at13_reuse.sh, AT-19 (APISIX limit-req), AT-20 (`docker exec … bao operator seal`), the release (tag, GHCR push). Those are leader/VPS items — list each with the exact command in the report under "Việc cho VPS/trưởng nhóm".
  - Do NOT create tags, push images, or create GitHub releases. release.yml may contain the GHCR push job (it only runs when the leader pushes a tag); it must use `${{ secrets.GITHUB_TOKEN }}` with `packages: write`, build from the tag, record the digest in the Release notes.
- CHANGELOG: add the section as `## [0.2.0] - Chưa phát hành` (Unreleased) with the M2 content; the leader sets the date when tagging. README "Trạng thái v0.2.0": say "đang hoàn thiện; chưa gắn tag" — do not claim the release or AT results that were not run.
- docs/progress/2026-11-16.md (productivity gate) and the M2 e2e evidence file are written by the leader after the VPS run — do NOT create them with invented results; create only templates if useful, clearly marked "MẪU — chưa chạy".

## Content rulings
- `docs/legal-mapping.md`: first sentence exactly *"Diễn giải kỹ thuật của đội, không phải tư vấn pháp lý."*; spec §25.1 unified sentence VERBATIM; copy the tables "Căn cứ đã đối chiếu" and "Ánh xạ 4 yêu cầu của Đ22 k2" from spec §25.1 with source links and check dates exactly as the spec has them (do not invent links or dates; if the spec lacks one, write "chưa có link"); "Không đạt" section and "Giới hạn về dữ liệu cá nhân" (I5 "Không thuộc" from §25.2, pre-1.0.3 ledger leaves, DISABLED app must be re-enabled to erase — Task 7 note). The final "members who read each article" table: leave it with EMPTY name/date cells for the team to fill — never invent names or dates.
- `docs/runbook-pii-erasure.md` per spec §25.2 and the brief; reason codes exactly `data_subject_request, purpose_completed, retention_expired, authority_decision, agreement` with the Luật 91/2025 Điều 14 khoản 1 mapping as the spec states.
- `docs/manifest-guide.md`: manifest 1.0.3 structure, guard table (spec 9.3 / Task 5 — say `assignee_is_caller` always fails until a claim API exists), BPMN rules (Task 3 allow-list: hand-written BPMN; modeler exports with incoming/outgoing are rejected; reserved ids), install lifecycle (submit → diff → four-eyes approve → ACTIVE; disable; 409 install-in-progress / version-not-newer; deployment name `id@version#hash16`), upgrade rules (P2-D14 + the stricter rules accepted in Task 12), "Trường công khai là công bố vĩnh viễn", "Đánh số theo năm". Examples from `test-flow` (core/tests/fixtures/manifest-test-flow.yaml).
- BUILD.md: DXOS_ORG_NAME (sealing refused while empty/default/`changeme…`), DXOS_ORG_ID, DXOS_SEAL_KEY_VALIDITY_DAYS, DXOS_SEAL_PURPOSE, DXOS_KEY_POLICY_URL, DXOS_TIMEZONE, DXOS_ALLOW_SELF_APPROVAL (demo only), DXOS_INSTALLER_CLIENT_SECRET, Flowable history level ≥ audit, `ops/keycloak_upgrade.py`.
- README.md / README_EN.md "Bản chất pháp lý của niêm phong" with the §25.1 sentence (English: close translation) and a link to docs/legal-mapping.md.
- E2E tests: two tokens (`DXOS_TOKEN` admin1 submits, `DXOS_APPROVER_TOKEN` admin2 approves); App A steps 1–11, App B steps, attacks (AT-19 with 40 concurrent requests + forged X-Forwarded-For; AT-20 with docker exec bao seal/unseal), AT-27/AT-28 checks (issuer.name == DXOS_ORG_NAME env; keys/seal-key/v1.json in the anchor clone). Use the `dxos` CLI (Task 13) for install/approve in ops/e2e/install_apps.sh; `ops/e2e/run_e2e.sh` switches from seed_manifests.py to the CLI; seed_manifests.py marked "chỉ dùng cho test lõi".
- `make openapi` generates docs/api/openapi.json from the FastAPI app deterministically (sorted keys, stable); commit the generated file; add a static/unit test that regenerating gives identical bytes.
- `deploy/compose.release.yaml`: trust-core-api and trust-core-worker use `image: ghcr.io/psa-ovncr/trust-core@sha256:${DXOS_TRUST_CORE_DIGEST}` and no `build:`; compose `config` with a dummy digest must pass.

## Split
This task is large; do it in two commits on main: (1) e2e + ops + compose.release + release.yml + Makefile openapi + openapi.json; (2) docs (manifest-guide, legal-mapping, runbook-pii-erasure, README/README_EN, BUILD.md, CHANGELOG, LICENSES-THIRD-PARTY, docs/evidence/README). The last commit uses the brief's message with "(chưa phát hành)" — e.g. `chore(release): prepare v0.2.0 — e2e M2 suites, AT-13 reuse script, manifest guide, legal mapping, OpenAPI`.
