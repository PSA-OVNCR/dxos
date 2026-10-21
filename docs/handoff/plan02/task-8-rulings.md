<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 8 — controller rulings and context (binding; refine the brief)

## Preflight rulings
- C5: the AT-27 public-view leg moves here. Add a test: seal a record with PII (`cccd`), `:erase-pii` it (Task 7 API, as approver), then `GET /verify/v1/seals/{sid}` → status VALID, signature_valid true, and the public view text contains neither the erased value nor the old salt. (The bundle leg of AT-27 is Task 9 Step 3.)
- C8 is Task 9's (witness requires the anchored STH to cover the leaf, else NOT_ANCHORED). Task 8 builds the bundle exactly as the brief's "Chọn STH" says; just make sure `anchored.sth.tree_size` and `inclusion.leaf_index` are present so Task 9 can apply C8.
- C9: create the fixtures the tests use, each with a one-line docstring contract, in core/tests/integration/conftest.py: `verify` (async HTTP client against the running API's public `/verify/v1/` routes, no auth; plus `stream_post(path, chunks)` sending a chunked body with content-type application/json), `kms_down` (callable that makes the signer's `public_keys()`/`sign()` raise KmsUnavailable from then on), `anchor_env` (bare remote + clone + settings + `anchor_once()` running the real anchor job path + `overwrite_remote(rel, text)` committing a change to the remote), `sealed_once` (one completed seal so `key_statements` has a row). Move shared git fixtures from test_anchor.py into conftest only if anchor_env needs them; keep test_anchor.py passing. Add `flow` helpers the tests call (`sealed_ids`, `pending_seal_id(verify_public=...)`, `sealed_with_file`, `revoked_seal_id`, `attachment_hashes`, `record_data_of`) to the existing `flow` fixture.

## Behaviour rulings
- Public key cache: one cache object shared by `ledger/router.py` `/keys` and the verify router (e.g. on app.state). Key material per (key, version) is immutable: cache forever; refetch from the signer only for an unknown version. If the version is unknown AND the signer is unavailable → 503 `keys-unavailable` for that request (never report signature_valid=false because the KMS is down).
- `issuer` = `{name, id}` from the key statement of `key_version` (`statement_for`). Every Plan 02 seal creates its statement before signing, so a missing statement is an internal inconsistency: log ERROR and return `issuer: null` (key still present, so the exact-key-set test holds).
- `public_labels` from the PINNED app version (`seal_requests.app_version` via `get_version`), only fields in `public_fields` that have a `label`.
- Status: `seals.status` VALID/REVOKED → public status; bundle `status` mirrors it and is outside the signed payload (Task 9 treats REVOKED offline as "check online").
- Body limits for `:check` and `:bundle`: enforce Content-Type application/json first (415 otherwise, including multipart), then read the stream with a hard 256-byte cap (413 as soon as the cap is exceeded, chunked or not, without buffering more); then strict JSON `{"sha256": <64 lowercase hex>}` (422 otherwise). Never write the ledger from any /verify route.
- Ordering of the common seal_id checks exactly as the brief (shape → seal_requests → verify.public of the sealed version → pending), so a non-public app never reveals pending/existence.
- Anchor repo files: `keys/<key>/v<n>.pub` = base64(raw ed25519) + "\n" for seal-key and sth-key; `keys/seal-key/v<n>.json` = canonical_bytes(statement) + "\n". Existing file with different bytes → `AnchorError("ANCHOR_CONFLICT")`, same as STH files; identical → no-op. Commit all new files of one run in the same commit as the STH.
- `GET /verify/v1/keys` gains top-level `statements: {"seal-key": {"<n>": statement}}`; keep existing keys unchanged (witness `sync` reads only sth-key).
- Bundle `ledger.entry` = exactly the 7 fields used for the leaf hash; verify in a unit test that `leaf_hash(canonical(entry))` reproduces the stored leaf.
