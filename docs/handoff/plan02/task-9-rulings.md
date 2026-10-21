<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 9 — controller rulings and context (binding; refine the brief)

## Bundle shape (from Task 8 — read task-8-report.md "bundle JSON shape" section for the exact keys)
- Task 8 added a top-level `sth_keys: {"<n>": "<b64 raw ed25519>"}` so STH signatures can be checked offline. Ruling: bundle-supplied keys are untrusted hints.
  - With `--anchor-dir`: seal-key and sth-key come ONLY from the anchor repo `keys/…/v<n>.pub`; if the bundle carries a key (seal_key.public_key or sth_keys[n]) for the same version and it differs → `INVALID KEY_MISMATCH`.
  - Without `--anchor-dir`: use the bundle's keys, `pinned=False`, exit code 3 when otherwise VALID (never 0).
- Unknown top-level keys are ignored (brief).

## Preflight rulings
- C8 (spec 11.5 step 6, AT-17): with `--anchor-dir`, the anchored STH must COVER the leaf: `anchored.sth.tree_size > inclusion.leaf_index`, otherwise `INVALID NOT_ANCHORED` (in addition to the brief's file/byte checks). Without `--anchor-dir`, a bundle whose anchored is null or does not cover the leaf can be at most VALID-unpinned (exit 3), detail says "chưa neo". Add tamper case `leaf_after_last_anchor` to the parametrized list (bundle where the only anchored STH has tree_size ≤ leaf_index).
- C5 (AT-27 bundle leg): add the core integration test in core/tests/integration/test_verify_api.py: a sealed record with PII is `:erase-pii`'d, then its bundle (fetched the right way for require_file) passes `dxos_witness.bundle.verify_bundle` with a `file://` anchor repo produced by the real anchor job (reuse Task 8's `anchor_env`/`sealed_once` fixtures). Also the plain "core bundle passes verify_bundle" test from the brief's Step 3.
- C9: create `bundle_env` (witness/tests/conftest.py; builds keys, payload, ledger entries, Merkle tree, STHs, anchor dir with sth/ and keys/ files using its OWN code + dxos-proof only — never import dxos_core), `tampered(name) -> (bundle, anchor_dir)`, `with_issued_at_after_valid_until()`; `fake_ledger` extensions (`publish_keys_to(anchor_dir)`, `rotate_key_same_version(key)`), `anchor_dir`, `state_dir` reuse existing test_sync fixtures where they exist — each with a one-line docstring contract.

## Other rulings
- Anchor file formats (Task 8): `keys/<key>/v<n>.pub` = base64(raw key) + "\n"; `keys/seal-key/v<n>.json` = canonical_bytes(statement) + "\n"; `sth/<tree_size 12 digits>.json` = canonical(sth) (check Plan 01 anchor.py for whether a trailing newline is part of the STH file and compare exactly the same way).
- `BundleResult` gains `issuer: str | None` ("<name> (<id>)" or name only when id is null).
- Datetime comparison: parse RFC 3339 (accept "Z") to aware UTC; never compare strings.
- `dxos-witness-kit` repo README: do NOT touch another repository. Update `witness/template/README.md` here (it is the kit's template); the controller syncs the kit repo separately.
- witness depends only on dxos-proof and its own deps; no new dependency.
- (from Task 8 fix round) `seal_key.statement` is OMITTED from the bundle when the server has no verified statement (missing row or sha mismatch); `seal_key.public_key` may be null. Do not crash on missing keys: missing statement → with `--anchor-dir` follow the brief (KEY_STATEMENT_NOT_ANCHORED if the anchor file is missing, else compare the anchored file and use it), without `--anchor-dir` → INVALID `KEY_STATEMENT_MISSING`.
