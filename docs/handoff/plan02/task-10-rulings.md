<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 10 — controller rulings and context (binding; refine the brief)

## Public view JSON (from Task 8; see task-8-report.md for the exact shape)
- Keys: `seal_id, status (VALID|REVOKED), app_id, issued_at, key_version, public_fields, require_file, attachments_count, signature_valid, inclusion {leaf_index, tree_size, verified, anchored {tree_size, repo, commit_sha} | null}, issuer {name, id} | null, public_labels`. Pending → only `{seal_id, status: "SEAL_PENDING"}`. 404 → not found (same body for unknown/hidden). 503 `keys-unavailable` → show "Tạm thời chưa kiểm được chữ ký, thử lại sau" (never "Không hợp lệ").
- `inclusion.anchored` is non-null only when the anchored STH covers the leaf (Task 8 fix). Show "Đã neo công khai (repo, commit)" only then; otherwise "Chưa neo công khai".
- "Không hợp lệ" when `signature_valid === false` or `inclusion.verified === false`. `issuer` null → line "Đơn vị niêm phong: (không xác định)".
- `:check` → `{"match": bool}` (pending → `{"match": false, "status": "SEAL_PENDING"}`); 415/413/422 never happen from the page (it sends `{"sha256"}` JSON only).
- Bundle: require_file false → `GET …/bundle`; true → `POST …:bundle` with the matched sha256; download as `<seal_id>.dxos-bundle.json` via an object URL of the RESPONSE text (creating a Blob from the server's response for download is fine; never put the user's File/Blob into fetch).

## Wording
- Title, subtitle, labels exactly as the brief. The legal sentence: copy spec 25.1's unified sentence VERBATIM (open docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md §25.1; strip markdown emphasis only). Link: https://github.com/PSA-OVNCR/dxos/blob/main/docs/legal-mapping.md (the file is created in Task 15; the link is intentional).
- All Vietnamese UI text in index.html/verify.js; `<html lang="vi">`, UTF-8, mobile-friendly CSS in a same-origin file or inline style tag? → CSP is `style-src 'self'`: use a separate `verify.css` (add it to Files) — no inline styles, no inline scripts, no `style=` attributes set from JS strings (use classList).

## Step 3 verification without Docker (no Docker daemon here)
- A Caddy 2.10.0 binary is at /tmp/claude-0/-home-claude/4180d5ee-f617-5df6-a5ae-a86295cdbc32/scratchpad/svc/bin/caddy (same minor as the compose image). Run `caddy validate --config deploy/caddy/Caddyfile --adapter caddyfile` (set the env vars the Caddyfile needs to dummy values) and `caddy adapt` to confirm `/apps/verify/*` is matched before `/apps/*`.
- Then run a throwaway Caddy on a high localhost port with a small test Caddyfile in the scratchpad that imports/reproduces the same `handle_path /apps/verify/*` block and redirect (point `root` at verify-portal/minimal, reverse-proxy `/verify/v1/*` to a uvicorn instance of the core API on the test DB), and check with curl: 200 + CSP on `/apps/verify/` and `/apps/verify/verify.js`, 308 on `/apps/verify`. Also curl a chunked >256-byte body to `:check` through Caddy→uvicorn and record the status and whether the connection closes cleanly (Task 8 review asked for this real-server check).
- Screenshot evidence (`docs/evidence/`): use Playwright with the pre-installed Chromium against that local setup, with a seal created by the integration harness (or a small seeding script) — one screenshot with the correct file (Hợp lệ + khớp) and one with a 1-byte-modified file (không khớp). If seeding a sealed record outside pytest is impractical, write the screenshots from a pytest that drives the page; if even that is impractical, say so in the report and leave a TODO line in docs/evidence/README.md for the leader to capture on dev-lite — do not fake screenshots.
- Kill every process you start (caddy, uvicorn) before finishing; no files outside the repo except the scratchpad.

## Tests
- Brief's static tests plus: no `innerHTML`/`insertAdjacentHTML`/`outerHTML`/`document.write`/`eval`/`new Function` in verify.js; no inline `<script>` body or `style=` in index.html; every fetch URL is built from `encodeURIComponent(sealId)` after checking `^[A-Z2-7]{26}$`.
- (from Task 9) An offline bundle of a seal whose leaf no STH covers yet verifies as INVALID NO_STH. The page should show the bundle button only when `inclusion.verified` is true, and otherwise a line "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp".
