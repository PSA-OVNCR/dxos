<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# DX-OS Trust Core: HTTP contract AS IMPLEMENTED (code, not spec)

Paths below are relative to the repository root. Snapshot of `main` at commit `4f25a34` (22/10/2026), plus the three generic Tier-2
endpoints added by Plan 03 Task 1 (sections 2.9, 3.4 and 14; they are marked **[Plan 03 T1]**, line numbers for them are not given).
Method: all claims read from code; cites are `file:line`. Nothing here was run against a live stack (no Docker). The only
things executed were (a) Python `dxos_proof`/witness to generate sample bundles and (b) a Node 22 WebCrypto reference
verifier (section 6.6) against them. "UNVERIFIED" marks anything inferred from config rather than code.

Short names: `S` = core/src/dxos_core. `rec`=S/records, `wf`=S/workflow, `sealpkg`=S/seal.

---------------------------------------------------------------------------------------------------
## 0. Cross-cutting rules

### 0.1 Routing and base URLs
- Browser-visible origin = Caddy `https://{DXOS_DOMAIN}` (deploy/caddy/Caddyfile:33). `/api/* /admin/* /verify/* /view/*` are proxied to APISIX
  (Caddyfile:8-12); `/auth/*` to Keycloak (Caddyfile:39-41); `/apps/*` is static files (Caddyfile:26-29). `/admin/*` is 404 on the public host (Caddyfile:45-48).
- Same-origin SPA: there is NO CORS config anywhere (no CORSMiddleware in S/app.py; no cors plugin in deploy/apisix/apisix.yaml). SPAs must be served from
  the same origin as `/api` (they are: `/apps/<name>/`). Dev server on another origin (vite :5173) would be blocked by the browser unless proxied.
- FastAPI app: S/app.py:74-91. Routers: health, identity, records, seal, objects, app_view (`registry/app_router.py`, **[Plan 03 T1]**), workflow, verify(ledger), seal_verify, admin.

### 0.2 Auth
- Every `/api/v1/*` route needs `Authorization: Bearer <access_token>`. Missing/blank -> 401 `unauthenticated` detail "missing bearer token" + `WWW-Authenticate: Bearer realm="dxos"`
  (S/identity/deps.py:17-22). Bad token -> 401 `unauthenticated` detail "invalid token" + `WWW-Authenticate: Bearer realm="dxos", error="invalid_token"` (deps.py:28-30).
  JWKS fetch failure -> 503 `idp-unavailable` (deps.py:26-27).
- Core checks: RS256 only, `iss` == Keycloak issuer, `aud` contains `dxos-api`, `exp`, `sub` required, leeway 10 s (S/identity/jwt.py:23, 104-106). Roles from `realm_access.roles` (jwt.py:112-114).
- APISIX ALSO validates the bearer (openid-connect, bearer_only) on /api and /admin before the core (deploy/apisix/apisix.yaml:27-33). UNVERIFIED: the body/format of a 401 produced by APISIX itself
  (not by core) is not asserted anywhere; tests only assert status 401 (tests/e2e/test_m1_flow.py:106, tests/infra/test_network_live.py:36). Treat a 401 as possibly non-problem+json.
- `/verify/v1/*` is anonymous (apisix.yaml:56-67: no openid-connect plugin).

### 0.3 Concurrency / ETag / If-Match (records, workflow, seal)
- Version = integer column `records.version` (starts 1, +1 on every data change/state change). It is exposed as body field `version` AND as response header `ETag: "<version>"` (QUOTED, e.g. `ETag: "3"`),
  set by `_with_etag` (rec/router.py:38-39) on: POST create (201), GET one, PATCH, workflow:start, :pii-review, :erase-pii, :revoke; and on tasks/{id}:complete (wf/router.py:56, value = `record.version`).
  NOT sent on: list, /seal, uploads, attachments POST and GET, manifest view, objects, whoami, /verify/*.
- `If-Match` is REQUIRED on: PATCH, :erase-pii, workflow:start, :pii-review, :revoke, tasks/{id}:complete. Parsed by `parse_if_match` (rec/service.py:279-288):
  - header absent -> 428 `precondition-required` detail "If-Match header is required".
  - accepted forms: `"<digits>"` and `W/"<digits>"` (weak prefix stripped). Anything else (bare `3`, `*`, `"abc"`, `""`) -> 400 `bad-request` detail `If-Match must look like "<version>"`.
  - so: send `If-Match: "3"` (with the double quotes). Bare integer is REJECTED (400).
  - stale version -> 409 `version-conflict`, detail `If-Match <n> but current version is <m>` (rec/service.py:300-302; wf/service.py:68-70; seal/service.py:237-239; erase.py:54-56).
- For tasks/{task_id}:complete the If-Match value is the RECORD's version (not a task version) (wf/service.py:337-338). The inbox item has no version, so the client must GET the record first (e2e does exactly that:
  tests/e2e/conftest.py:173-176).
- Version bumps (needed to know when to re-GET): create=1; PATCH +1; workflow:start +1 (wf/service.py:140-143); each task complete +1 (reconcile.py:274); :pii-review +1 (wf/service.py:424-425);
  :erase-pii +1 (erase.py:102-104); :revoke +1 (seal/service.py:283-285). The SEAL_PENDING -> SEALED transition does NOT bump the version (seal/service.py:207-208), but the task-complete that sets SEAL_PENDING does.

### 0.4 Error format (RFC 9457 problem+json)
- Media type `application/problem+json`. Body: `{"type": "https://dxos.dev/problems/<slug>", "title": str, "status": int, "detail"?: str, ...extensions}` (S/errors.py:20,56-73). `detail` is OMITTED when None.
  Extension members are merged at top level; they cannot clash with type/title/status/detail (errors.py:66-68).
- Generic HTTP errors (unknown route, 405, etc.) map via HTTP_SLUGS (errors.py:29-46): 400 bad-request, 401 unauthorized, 403 forbidden, 404 not-found, 405 method-not-allowed, 406, 409 conflict, 412, 413 payload-too-large,
  415 unsupported-media-type, 422 invalid-request, 428 precondition-required, 429 rate-limited, 500 internal, 503 unavailable; others `http-error` (errors.py:94-98). `detail` only if the Starlette detail is a str != reason phrase.
- FastAPI validation errors (bad query param types, missing required query like `first`/`second`) -> 422 `invalid-request`, title "Request validation failed", extension `errors: [{loc:[..], msg, type}]` (errors.py:101-104).
- Unhandled -> 500 `internal` title "Internal Server Error", no detail (errors.py:111-113).
- Extensions used: `errors` (list) on `schema` and FastAPI-422; `guard` + `reason` on `guard-failed`; `code` (+ more) on `manifest-invalid` (admin only, S/registry/installer.py:79); `counts` on admin workflow-unavailable. Header `Retry-After` on `workflow-pending`.
- No `code` field exists on record/workflow/seal errors: the machine key is the `type` slug (and `guard`/`reason` for guards).

### 0.5 Body parsing for JSON endpoints (records/workflow/seal)
- `_json_body` (rec/router.py:27-35): does NOT check Content-Type. Invalid JSON -> 400 `bad-request` detail "body must be JSON"; lone surrogate or nesting >64 -> 422 `invalid-request` (jsonbody.py:211-248). A string or key containing U+0000 (`\u0000`, not representable in PostgreSQL jsonb) -> 422 `invalid-request` detail "body contains U+0000 (not representable in PostgreSQL jsonb)"; the same check applies to `POST /admin/v1/apps` (Plan 03 final review, I3). Empty body is invalid JSON (400) for POST create/PATCH/erase/revoke/complete.
  workflow:start and :pii-review do NOT read a body at all.
- The `/verify/v1/seals/{id}:check|:bundle` bodies are different: Content-Type must be exactly application/json (else 415), max 256 bytes (413), shape exactly `{"sha256": "<64 lowercase hex>"}` (else 422 `invalid-request`), duplicate keys rejected
  (seal/verify_router.py:57,70-98; http_body.py:16-37).
- Strings are NFC-normalised server side before storing/hashing (rec/service.py:62-69).

### 0.6 Gateway limits
- APISIX limit-req (key = `X-Forwarded-For`, `rejected_code: 429`): `/api/v1/*` rate 50 r/s burst 100 (apisix.yaml:15-26); `/admin/v1/*` 10 r/s burst 20, host-bound (35-47); `/verify/v1/*` 5 r/s burst 10 (56-67).
  limit-req delays within burst and returns 429 beyond (tests/e2e/test_m2_attacks.py:127-140 asserts 429 appears). 429 body is produced by APISIX (UNVERIFIED format; the verify portal only checks `resp.status === 429`, verify-portal/minimal/verify.js:351).
- Max request body: nginx `client_max_body_size 20m` for all routes (deploy/apisix/config.yaml:101). Over that -> nginx 413 (UNVERIFIED body format, probably not problem+json).
- `request-id` plugin with `include_in_response: true` on all three routes -> response header `X-Request-Id` (apisix.yaml:19-20; header name is APISIX default, UNVERIFIED).
- Core limits: string field <= 4000 chars (rec/service.py:33); bulk <= 500 rows (service.py:35); attachment size = collection `attachments.max_mb` (15 MB in App A) or `max_upload_mb_default` 15 (settings.py:49); JSON nesting <= 64.

---------------------------------------------------------------------------------------------------
## 1. GET /api/v1/whoami  (S/identity/deps.py:43-45)
- Headers: Authorization only. Role: any valid token (no app role needed; admin ok).
- 200: `{"sub": string, "roles": string[] (sorted), "is_admin": boolean}`. That is ALL (no name/username/email/exp).
  - `roles` = every realm role in the token (jwt.py:112-114), including Keycloak built-ins (`default-roles-dxos`, `offline_access`, `uma_authorization`) and `app:<app_id>:<role>` and `dxos-admin`.
  - `is_admin` = `"dxos-admin" in roles` (jwt.py:67).
  - App roles are plain strings of form `app:<app_id>:<role>`; regex `^app:([a-z][a-z0-9-]{1,62}):([a-z][a-z0-9_]{0,62})$` (jwt.py:25). Client must parse them itself. `dxos-admin` does NOT grant any app data access (pdp.py:44-46).
- Display name: not returned; read `preferred_username` / `name` from the access/ID token (realm `profile` scope has mappers `preferred_username` and full-name, realm-dxos.json profile scope; dxos-spa has `profile` default scope).
- Errors: 401 `unauthenticated`, 503 `idp-unavailable`.

---------------------------------------------------------------------------------------------------
## 2. Records API  (prefix `/api/v1/apps/{app}/collections/{col}`; S/records/router.py:18)

### 2.0 Common
- `{app}` = app_id slug, `{col}` = collection name, `{rid}` = UUID string.
- Unknown/non-ACTIVE app -> 404 `app-not-active` detail `no active app 'x'` (rec/service.py:138-142). Unknown collection -> 404 `not-found` (service.py:144).
  Invalid-UUID or other-app/collection rid -> 404 `not-found` (service.py:175-184).
- Authorisation (PDP S/policy/pdp.py:43-62): caller needs >=1 role of THAT app (`app:<app>:*`), else denied. Access lists come from the manifest per collection: `read`, `create`, `update` (default `["owner"]`, model.py:44),
  entries are `role:<name>` or `owner`. "owner" = the record's creator (`owner_sub`).
  - list/create denied -> 403 `forbidden` (title "Forbidden", no detail) (service.py:158-159; pdp.py:79-80).
  - read/update of a record denied -> 404 `not-found` (anti-IDOR, same body as nonexistent) (pdp.py:81).
  - every denial writes ledger `policy.denied` (pdp.py:76-78).
- Record timestamps `created_at`/`updated_at`: ISO-8601 UTC with `Z`, microseconds present unless zero, e.g. `2026-10-21T09:00:00.123456Z` (rec/service.py:72-73).

### 2.1 Record representation (used by GET one, create, PATCH, start, pii-review, erase, revoke)  rec/service.py:128-135
```
{
  "id": "<uuid>", "app_id": "phong-ho-so", "collection": "van_ban",
  "data": { <field name>: <value>, ... },       // see masking 2.7; sequence fields (e.g. so_hieu) are server-assigned
  "is_owner": boolean,                           // caller == owner_sub; owner sub itself is NOT returned
  "version": integer >= 1,
  "seal_state": "NONE" | "SEAL_PENDING" | "SEALED" | "REVOKED",     // migration 001_core.sql:63-64
  "wf_state": null | "running" | "ended:<end_event_id>",            // 003_workflow_seal.sql:197-199; values seen: "ended:approved", "ended:rejected", "ended:guard_failed", "ended:cancelled" (reconcile.py:272,313)
  "created_at": "<iso>", "updated_at": "<iso>"
}
```
NOT present: attachments list, upload ids, sha256s, filenames, seal_id, creator identity, current task, process instance, app version. (Gaps listed in section 13; the attachment list is now `GET .../attachments`, section 3.4.)

### 2.2 GET list  `GET .../records?cursor=&limit=`  (rec/router.py:42-45; service.py:255-276)
- Role: manifest `read` list (or owner). Note: if the caller qualifies ONLY via `owner` then the list is filtered to own records (service.py:261-263; pdp.py:60). App A `chuyen_vien` is only "owner" -> sees own; truong_phong/giam_doc/van_thu/nhan_vien see all.
- Query: `limit` int default 50, must be 1..200 else 400 `bad-request` "limit must be between 1 and 200" (service.py:258-259); non-int -> 422 `invalid-request`. `cursor` opaque (base64url JSON {c: created_at iso, i: uuid}); bad -> 400 `bad-request` "invalid cursor" (service.py:242-252).
- NO filters (no status/search/owner/wf_state). Order: `created_at ASC, id ASC` (oldest first) (service.py:270). Keyset pagination.
- 200: `{"items": [Record...], "next_cursor": string | null}` (service.py:275-276). Same record shape as 2.1 (PII masked unless caller may reveal, see 2.7).
- Errors: 401, 403 `forbidden`, 404 `app-not-active`/`not-found`, 400, 422.

### 2.3 POST create  `POST .../records`  (rec/router.py:48-51; service.py:208-213)
- Role: manifest `create` list (App A: `role:chuyen_vien`; App B: `role:can_bo_clb`). No If-Match.
- Request body = the DATA OBJECT itself (not wrapped): e.g. `{"trich_yeu":"...","loai_van_ban":"...","nguoi_lien_he_cccd":"..."}`. Unknown keys rejected; `sequence` fields must NOT be sent (server assigns, e.g. "07/QĐ-SM"); `required` fields mandatory.
  Types: string (<=4000 chars), integer (int64, no bool), boolean, date (`YYYY-MM-DD` valid calendar date) (service.py:80-99, 102-125).
- 201 + `ETag: "1"` + Record (2.1). PII fields are ALWAYS masked in the create response (service.py:213).
- Errors: 422 `schema` title "Record data does not match the collection schema", extension `errors: [{"path": "/field", "msg": "<Vietnamese text>"}]` (service.py:57-58,102-125). Path "" for non-object body. Messages seen: "bắt buộc", "phải là chuỗi",
  "dài quá 4000 ký tự", "phải là số nguyên 64 bit", "phải là true/false", "phải là ngày dạng YYYY-MM-DD", "trường không có trong manifest", "trường số thứ tự do lõi cấp, không gửi lên". 400 invalid JSON; 403; 404.

### 2.4 POST records:bulk  `POST .../records:bulk`  (rec/router.py:54-56; service.py:216-231)
- Role: same as create. Body: JSON ARRAY of data objects (same shape as create), max 500 rows. Not an array or >500 -> 422 `schema` title "Bulk body must be a JSON array", detail "at most 500 rows".
- Always HTTP 200 (no ETag) with `{"results": [ ... ]}`, one entry per input row IN ORDER:
  - success: `{"ok": true, "id": "<uuid>"}` (no version/record - client must GET if it needs the version; e2e does so)
  - failure: `{"ok": false, "row": <index int>, "error": {"type": "https://dxos.dev/problems/schema", "title": "Record data does not match the collection schema", "errors": [{"path","msg"}]}}` (no `status`, no `detail` in `error`).
- NOT atomic: each valid row is its own transaction and is committed; invalid rows are reported and skipped (service.py:229 comment). Only validation failures are reported per row (other exceptions would abort the whole call as 5xx).
- Bulk creates records only; starting workflows is a separate call per record (tests/e2e/test_m2_app_b.py:136-140).

### 2.5 GET one  `GET .../records/{rid}`  (service.py:234-239)
- Role: manifest `read` list or owner (non-owner without role -> 404). 200 + `ETag: "<version>"` + Record (2.1). Writes ledger `field.revealed` if the caller is allowed to see PII in clear and the record has PII fields.

### 2.6 PATCH  `PATCH .../records/{rid}`  (rec/router.py:64-68; service.py:291-333)
- Role: manifest `update` list (default `["owner"]`: only the creator in both shipped apps). Header `If-Match: "<version>"` REQUIRED. No Content-Type check.
- Body: JSON-merge-patch of the DATA object (NOT wrapped): top-level keys replace; a key with `null` deletes the field; absent keys unchanged (service.py:306-311). Result re-validated (required fields etc.). Sequence fields cannot be sent.
  DANGER for UI: GET returns MASKED PII strings; PATCHing a masked value back would overwrite the real value. Only send changed fields.
- 200 + new `ETag` + Record. PII masked unless caller can reveal.
- Errors (order of checks, service.py:292-312): 428/400 If-Match; 404; 409 `record-sealed` (detail `seal_state=<s>`) when seal_state != NONE; 409 `record-in-workflow` ("Record is in a running workflow") when wf_state == running; 409 `version-conflict`;
  422 `schema` (non-object body: path "" msg "PATCH body phải là object (JSON merge patch)"). DB-trigger races map to the same 409s (service.py:326-331).
- After a rejected/ended workflow (wf_state `ended:*`, seal NONE) editing is allowed again.

### 2.7 PII masking (S/policy/masking.py)
- Applies to fields declared `pii: <TYPE>` in the manifest and only when the value is a string. Reveal (clear text) only if caller has a role in `policies.pii.reveal_roles` (pdp.py:50-54; App A: giam_doc, van_thu; App B: truong_clb).
- Formats (masking.py:12-25): CCCD/PHONE/BANK_ACCOUNT: len<=4 -> all `*`, else first 2 + `*`*(n-4) + last 2 (e.g. `07********34`); EMAIL: `a***@domain` (no `@` -> `***`); NAME: initials `N. V. A.`.
- Always masked (even for revealers) in: create response, workflow:start, :pii-review, :erase-pii, :revoke, tasks:complete (`can_reveal=False`). Revealed in: GET one, list, PATCH for reveal roles.

### 2.8 :erase-pii  `POST .../records/{rid}:erase-pii`  (rec/router.py:71-75; rec/erase.py)
- Role: caller must be able to `read` the record AND hold a role in `policies.pii.erase_roles` (App A: van_thu; App B: truong_clb); else ledger `policy.denied not_eraser` + 404 `not-found` (erase.py:68-72). If-Match required.
- Body EXACTLY `{"fields": ["name", ...], "reason_code": "<code>"}` (keys must be exactly these two) (erase.py:74-80). `fields`: non-empty, distinct, <=64, each must be a `pii` field of the collection (active or pinned version).
  `reason_code` in {`data_subject_request`,`purpose_completed`,`retention_expired`,`authority_decision`,`agreement`} (erase.py:40-41).
- 200 + ETag + Record (masked; erased fields simply absent from `data`). Works on SEALED records (seal stays VALID).
- Errors: 422 `invalid-request` title "Invalid erase request" with detail text; 409 `record-in-workflow`; 409 `seal-pending` ("Record is waiting to be sealed"); 409 `version-conflict`; 404.

### 2.9 GET manifest view  `GET /api/v1/apps/{app}/manifest`  **[Plan 03 T1]**  (`S/registry/app_router.py`, `S/registry/client_view.py`)
- Role: caller must hold at least one `app:<app>:*` role. Any role of the app is enough (it does not need to be in an access list).
  - `{app}` not a valid slug or not ACTIVE -> 404 `app-not-active` (same as 2.0).
  - ACTIVE but caller has no `app:<app>:*` role -> ledger `policy.denied` (`action: read_manifest`, `reason: no_app_role`, subject = the app id) + **404 `not-found`**
    (the same body as any other `not-found`; the caller learns nothing about the app's roles or content). `dxos-admin` without an app role is treated the same way (reason stays `no_app_role`).
- 200 + `Cache-Control: private, max-age=60`. No ETag. Body is built key by key from the ACTIVE manifest (never the whole manifest):
```
{
  "app": {"id": string, "version": string, "name": string},
  "roles": string[],                                   // role names without the app:<app>: prefix, manifest order
  "collections": { "<col>": {
      "fields": { "<field>": {"type": "string"|"sequence"|"integer"|"boolean"|"date", "required": bool, "public": bool,
                              "pii": null|"CCCD"|"PHONE"|"BANK_ACCOUNT"|"EMAIL"|"NAME", "format": string|null, "label": string|null} },
      "attachments": null | {"kinds": ["pdf"], "max_mb": int, "min": int},
      "access": {"read": string[], "create": string[], "update": string[]}   // entries are "owner" or "role:<name>"; update defaults to ["owner"]
  } },
  "workflow": null | {"tasks": {"<task_key>": {"role": string, "guards": string[]}},
                      "decisions": {"<task_key>": string[]}},               // see below
  "policies": {"pii": {"reveal_roles": string[], "erase_roles": string[]},
               "seal": null | {"public_fields": string[], "revoke_roles": string[]},
               "verify": null | {"public": bool, "require_file": bool}}
}
```
- `workflow.decisions`: for each task, the values the core accepts for `decision` on `tasks/{id}:complete` (section 4.3), sorted, read from the BPMN deployed for THAT version
  (`decisions_by_task`). An EMPTY list means the BPMN does not restrict the value (any string matching `[a-z][a-z0-9_]{0,31}` passes the core's check).
- Deliberately NOT in the view: `apiVersion`, `app.spaces`, the BPMN path or content, `policies.pii.document_detect`, `policies.seal.on_event`/`target`, `attachments.quarantine`, `fields.<f>.reset`.
- Errors: 401; 404 `app-not-active`; 404 `not-found`; for an app WITH a workflow also 409 `app-not-deployed` (no deployed BPMN for the active version) or 503 `workflow-unavailable` (workflow engine not configured); 500 `workflow-model-mismatch`.
  It does not call Flowable, so a Flowable outage does not break it.

---------------------------------------------------------------------------------------------------
## 3. Attachments, uploads, objects  (S/objects/router.py)

### 3.1 POST attachment  `POST /api/v1/apps/{app}/collections/{col}/records/{rid}/attachments`  (router.py:64-116)
- Role: `update` on the record (default owner only). Record must have seal_state NONE (else 409 `record-sealed`) and wf_state != running (else 409 `record-not-open` "Record is not open for attachments") (router.py:77-80; also DB trigger -> same 409, :109-115).
- Request: `multipart/form-data` with exactly ONE file part named **`file`** (router.py:88-92; `max_files=1, max_fields=4`). Missing -> 400 `bad-request` "multipart field 'file' is required".
  `Content-Length` header REQUIRED else 411 `length-required` (router.py:82-85) (browsers set it for FormData bodies; chunked/streamed bodies would 411).
- Size: limit = `attachments.max_mb` of the collection (App A 15 MB; App B has no attachments block -> default 15 MB) (router.py:81). `Content-Length > limit + 64 KiB` -> 413 `payload-too-large` detail `attachment limit is <n> bytes`; actual bytes > limit -> same 413.
  Gateway cap 20m (apisix config.yaml:101).
- Filename: only a SHA-256 of the (NFC) filename is stored (ingest.py:31-33, 44). The original name is NEVER retrievable. `Content-Type` of the part is stored as declared type but not used. Only PDF is accepted at scan time (see 3.2).
- 202: `{"upload_id": "<uuid>", "status": "STAGING"}` (router.py:116). No ETag, no record version change.
- Other errors: 404 (record/app), 403 never (update denied -> 404), 503 `storage-unavailable`, 409s above.
- Clients should poll 3.2. e2e: `wait_upload` polls every 2 s up to 180 s (tests/e2e/conftest.py:139-146).

### 3.2 GET upload status  `GET /api/v1/uploads/{upload_id}`  (router.py:119-132; ingest.py:139-145)
- Role: `read` on the owning record (owner or manifest read roles); else 404 (and ledger policy.denied). Bad UUID -> 404.
- 200 bodies (exactly):
  - `{"status": "STAGING"}`
  - `{"status": "CLEAN", "sha256": "<64 hex>"}`
  - `{"status": "INFECTED", "reason": "<ClamAV signature name or null>"}` (e.g. EICAR signature)
  - `{"status": "REJECTED", "reason": "<code>"}` with code in `EMPTY | TOO_LARGE | BAD_MAGIC | ENCRYPTED | PARSE_ERROR | NO_TEXT_LAYER` (objects/pdfcheck.py:14; ingest.py:98-103). `OK` is never stored.
- Does NOT return record_id, size, filename, timestamps. To rediscover a record's `upload_id`s after a reload use the list in 3.4.
- Flow: AV scan first (INFECTED), then PDF check (REJECTED), then promote to CAS (CLEAN) (ingest.py:69-128). ClamAV down -> stays STAGING and retried every 30 s (ingest.py:28,86-89).

### 3.3 GET object  `GET /api/v1/objects/{sha256}?variant=original`  (router.py:135-174)
- `sha256` must be 64 lowercase hex; `variant` default "original" and ONLY `original` exists: any other value (e.g. `redacted`) -> 404 `not-found` (router.py:138).
- Role: caller must be allowed `read` on at least one record that references this sha with role `original` (router.py:143-155); only CLEAN objects; otherwise 404 (policy.denied logged for the first ref).
- 200 body = raw bytes (read via fetch + Blob, since a Bearer header is needed). Headers: `Content-Type: application/pdf` (column `mime_sniffed`, always 'application/pdf' written by ingest.py:114),
  `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `Content-Disposition: attachment; filename="<sha256>.pdf"` (router.py:172-174). Each successful read appends ledger `object.read`.
- Errors: 404, 500 `integrity-error`, 503 `storage-unavailable`.
- Note: the attachment sha256s of a record are not exposed on the record; they appear only in (a) upload status of CLEAN uploads, (b) the public seal payload/bundle (`payload.attachments`), never in `GET /seal`.

### 3.4 GET attachment list  `GET /api/v1/apps/{app}/collections/{col}/records/{rid}/attachments`  **[Plan 03 T1]**  (S/objects/router.py `list_attachments`, S/objects/ingest.py `list_uploads`)
- Role: same permission path as GET record (2.5): owner or a role in the collection's `read` list. Anything else, an unknown record, a bad UUID, or another app's/collection's record -> the same 404 `not-found`;
  a denial writes ledger `policy.denied` (`read`). Unknown/non-ACTIVE app -> 404 `app-not-active`; unknown collection -> 404 `not-found`.
- Works at any `seal_state`/`wf_state`. Does NOT write `field.revealed` and does not return record data.
- 200 `{"items": [AttachmentItem]}`, ordered `created_at` ascending (then `id`), `{"items": []}` when there are none (no ETag):
```
AttachmentItem = {"upload_id": "<uuid>", "status": "STAGING"|"CLEAN"|"INFECTED"|"REJECTED",
                  "sha256": "<64 hex>"|null,      // non-null only when CLEAN
                  "reason": string|null,           // non-null only when INFECTED (signature name, may still be null) or REJECTED (code of 3.2)
                  "created_at": "<iso Z>"}         // same format as record created_at (2.0)
```
  `status`/`sha256`/`reason` follow exactly the rules of 3.2. The original filename is never stored, so it is not returned. `sha256` is what `GET /api/v1/objects/{sha256}` (3.3) takes.
- Errors: 401, 404.

---------------------------------------------------------------------------------------------------
## 4. Workflow  (S/workflow/router.py, service.py)

Workflow engine absent/unreachable -> 503 `workflow-unavailable` on all of these (wf/router.py:23-28; reconcile.py:108-118).

### 4.1 POST workflow:start  `POST .../collections/{col}/records/{rid}/workflow:start`  (wf/service.py:120-147)
- Role: `update` on record (owner). Header If-Match required. No body.
- 200 + new ETag + Record (wf_state "running", version+1). PII masked.
- Errors (checks in order): 404; 409 `no-workflow` (app has none); 409 `record-sealed`; 409 `already-running`; 409 `attachments-pending` (detail "<n> pending"); 409 `attachments-not-clean` (detail "<c> clean, at least <min> required");
  409 `version-conflict`; 409 `app-not-deployed`; 503 `workflow-unavailable`; 500 `workflow-model-mismatch`.

### 4.2 GET tasks  `GET /api/v1/apps/{app}/tasks?assigned=me`  (wf/router.py:40-45; wf/service.py:158-183)
- Role: any role of the app (else 403 `forbidden` + ledger denied; 404 `app-not-active`). Only `assigned=me` accepted (default "me"); other value -> 400 `bad-request`.
- "Mine" = tasks whose candidate group is one of the caller's `app:<app>:<role>` roles (not an assignee), restricted to records the caller may read.
- 200: `{"items": [ {"task_id": string, "task_key": string, "name": string, "record_id": "<uuid>", "collection": string, "created": string} ]}` (service.py:179-182).
  - `task_id` = Flowable task id (opaque; goes into the URL of :complete). `task_key` = BPMN userTask id (App A: `duyet_noi_dung`, `ban_hanh`; App B: `phe_duyet`). `name` = BPMN name ("Duyệt nội dung", "Ban hành", "Phê duyệt").
  - `created` = Flowable `createTime` passed through VERBATIM (flowable.py:171); sample in tests is `2026-10-21T13:14:30.393+07:00` (tests/test_flowable_client.py:36): offset form, NOT the `Z` form of `created_at`. Parse with Date; don't string-compare.
  - NO record version, no record title/data, no task due date. Sorted by (created, task_id).
- Empty -> `{"items": []}`.

### 4.3 POST tasks/{task_id}:complete  (wf/router.py:48-56; wf/service.py:281-393)
- URL literally `/api/v1/apps/{app}/tasks/{task_id}:complete`. Role: must hold the task's manifest role (`workflow.tasks.<key>.role`) AND be able to read the record; else ledger denied `not_task_role` + **404** `not-found` (service.py:314-318). If-Match = record version.
- Body: `{"decision": "<string>", "comment"?: "<string>"}`.
  - `decision` must match `[a-z][a-z0-9_]{0,31}` and be one of the values accepted by the gateway after the task in the BPMN (`decisions_by_task`). In both shipped apps: **`approve` or `reject`** (apps/*/bpmn/*.bpmn conditionExpressions). Wrong -> 422 `invalid-decision` (detail lists allowed values) (service.py:193-207).
  - `comment` optional string <= 1000 chars else 422 `invalid-comment`. The comment is VALIDATED BUT NOT STORED anywhere (workflow/service.py docstring :12; P2-D24).
  - non-object body -> 422 `invalid-request` "Request body must be an object".
- 200 + `ETag: "<record.version>"` + body:
  `{"record": Record(2.1, PII masked), "seal_state": "NONE"|"SEAL_PENDING"|"SEALED", "seal_id": string|null}` (service.py:389-393).
  `seal_id` is non-null only when this completion reached the sealing end event; `seal_state` can already be "SEALED" (sealed inline) or "SEAL_PENDING" (worker will finish; poll GET record until SEALED, as `wait_sealed` does, tests/e2e/conftest.py:183-192).
  A `reject` ends the process: `record.wf_state = "ended:rejected"`, `seal_state` stays NONE.
- Errors, in the order they can occur:
  - 404 `not-found` (task unknown/other app/bad id/not your role/record not running); 409 `task-gone` ("Task is no longer open"); 409 `task-unknown`; 404 `app-not-active`.
  - 409 `version-conflict`.
  - 422 `invalid-decision` / `invalid-comment`.
  - 403 or 409 `guard-failed` with extensions `{"guard": "<guard string from manifest, e.g. not_same_actor:creator>", "reason": "<code>"}` (service.py:77-78). Guard->(reason,status) table (guards.py:72-110):
    `not_same_actor:<creator|task_key>` -> same_actor 403; `role_in:[..]` -> role_not_allowed 403; `assignee_is_caller` -> not_assignee 403; `field_required:<f>` -> field_missing 409;
    `attachments_clean` -> attachments_not_clean 409; `pii_reviewed` -> pii_scan_pending 409 (a CLEAN file has no `pii_scans` row yet; retry after the background scan) or pii_not_reviewed 409; `record_not_sealed` -> record_sealed 409. Guards are evaluated for `reject` too.
    App A guards: duyet_noi_dung=[attachments_clean, not_same_actor:creator]; ban_hanh=[attachments_clean, pii_reviewed, not_same_actor:creator, not_same_actor:duyet_noi_dung]. App B: phe_duyet=[not_same_actor:creator].
    A guard that fails only after Flowable ran returns 409 `guard-failed` and the record ends in `wf_state "ended:guard_failed"` (reconcile.py:313).
  - 503 `kms-unavailable` | `key-statement-invalid` | `seal-key-expired` | `org-not-configured` (R-1 pre-check before the sealing task; wf/service.py:217-241).
  - 503 `workflow-pending` + header `Retry-After: <s>` (previous completion outcome unknown; retry) (service.py:258-260). 409 `workflow-inconsistent`. 500 `workflow-finalize-failed` (completion will be reconciled). 503 `workflow-unavailable`.

### 4.4 POST :pii-review  `POST .../collections/{col}/records/{rid}:pii-review`  (wf/router.py:59-62; wf/service.py:397-428)
- Role: can `read` the record AND role in `policies.pii.reveal_roles` (App A: giam_doc, van_thu); else ledger denied `not_pii_reviewer` + 404. If-Match required, no body.
- Records a review digest over (data digest, CLEAN attachment shas, PII findings, and the `pii_scans` state `sha256:status` of those files when any exists). Works while the workflow is running (version+1, data unchanged), also while a scan is still pending. 200 + new ETag + Record (masked).
- Errors: 409 `record-sealed`, 409 `version-conflict`, 404. After ANY data/attachment change the review is stale and `pii_reviewed` guard fails again (guards.py:100-104).
- Required before App A `ban_hanh` completes (guard `pii_reviewed`); only applies when the collection has `pii` fields or `policies.pii.document_detect` (guards.py:154).
- Scan wait (Plan 04 Task 4): when the active manifest has `policies.pii.document_detect` with a supported type (CCCD, PHONE, BANK_ACCOUNT; EMAIL and NAME have no detector yet), every CLEAN upload queues a background `pii_detect` job in the same transaction as `object.clean`. Until that job has written the file's `pii_scans` row the guard `pii_reviewed` fails with 409 `guard-failed`, `reason: "pii_scan_pending"` (before `pii_not_reviewed`). A review made while the scan was pending is stale once the scan finishes: the reviewer must call `:pii-review` again. `pii_scans.status` is `DONE`, `TOO_LARGE` (over 200 pages, not scanned) or `FAILED` (PDFium or detector error); the last two count as "has findings, review required" and also change the review digest. Findings (`pii_findings`: type, 1-based page, boxes in displayed-page points, no value and no hash) and the ledger event `pii.detected` (`sha256`, counts by type, `detector`) are written in the same transaction as the `pii_scans` row.

---------------------------------------------------------------------------------------------------
## 5. Seal (authenticated)  (S/seal/router.py, service.py)

### 5.1 GET seal info  `GET .../collections/{col}/records/{rid}/seal`  (service.py:293-311)
- Role: same as GET record (read/owner). 404 `not-found` (detail "record has no seal") until a seal_request exists (i.e. until the sealing end event was reached).
- 200: `{"seal_id": "<26 chars [A-Z2-7]>", "seal_state": "SEAL_PENDING"|"SEALED"|"REVOKED", "issued_at": "<RFC3339 Z>" | null, "key_version": int | null, "public_fields": {name: value}, "verify_url": "<public_base_url>/apps/verify/#<seal_id>"}`.
  - `issued_at`/`key_version` are null while SEAL_PENDING. `public_fields` come from the request snapshot (manifest `policies.seal.public_fields` present in data), available even when pending.
  - `verify_url` is the ONLY "QR payload" the API provides: `https://{DXOS_DOMAIN}/apps/verify/#<seal_id>` (DXOS_PUBLIC_BASE_URL, settings.py:73, compose.yaml:37). No separate QR/image endpoint. The verify page is the static page at `/apps/verify/` (see 9).
  - No signature, status VALID/REVOKED word, inclusion proof here (use /verify/v1). Note `seal_state` here is the record's seal_state, whose REVOKED matches seals.status REVOKED.

### 5.2 POST :revoke  `POST .../records/{rid}:revoke`  (service.py:242-289)
- Role: must be able to read the record AND (if a seal_request exists) hold a role in `policies.seal.revoke_roles` OF THE SEALED APP VERSION (App A: giam_doc; App B: truong_clb); else ledger denied `not_revoker` + 404 (service.py:247-258). If-Match required.
- Body: `{"reason_code": "<code>", "note"?: "<1..500 chars>"}`; extra keys -> 422 `invalid-request` "Body must be {reason_code, note?}". `reason_code` in {`superseded`,`issued_in_error`,`content_error`,`legal_order`,`other`}, else 422 `invalid-reason-code`
  (detail lists allowed). Bad note -> 422 `invalid-note`. Note is stored in an erasable table; not echoed.
- 200 + new ETag + Record (`seal_state: "REVOKED"`, version+1). Terminal state.
- Errors: 409 `not-sealed` (detail `seal_state=<s>`; also when the record has no seal request or already REVOKED), 409 `version-conflict`, 404.

---------------------------------------------------------------------------------------------------
## 6. Public verification  (anonymous; S/seal/verify_router.py, S/ledger/router.py)

### 6.1 Resolution rules for `seals/{seal_id}` (verify_router.py:117-133)
1. `seal_id` must match `[A-Z2-7]{26}` else 404 `not-found`. 2. No seal_request -> 404. 3. Sealed app version's manifest must have `policies.verify.public == true` else 404 (identical body to 1 and 2: `{"type":".../not-found","title":"Not Found","status":404}`).
4. No `seals` row yet -> the "pending" form below. All responses `Cache-Control: no-store`.
- Pending (HTTP 200) for GET view, GET bundle, POST :bundle: `{"seal_id": "<id>", "status": "SEAL_PENDING"}` (verify_router.py:136-137). For :check: `{"match": false, "status": "SEAL_PENDING"}` (:205-206).

### 6.2 GET /verify/v1/seals/{seal_id}  (verify_router.py:167-197)
200 (non-pending):
```
{
  "seal_id": "<id>",
  "status": "VALID" | "REVOKED",
  "app_id": "chung-nhan",
  "issued_at": "2026-10-21T09:00:00Z",
  "key_version": 1,
  "public_fields": { "<field>": <string|int|bool>, ... },     // ONLY manifest policies.seal.public_fields
  "require_file": boolean,                                     // manifest policies.verify.require_file (App A true, App B false)
  "attachments_count": integer,
  "signature_valid": boolean,                                  // server-side Ed25519 check of payload (bundle.py:135-143)
  "inclusion": { "leaf_index": int, "tree_size": int|null, "verified": boolean,
                 "anchored": null | {"tree_size": int, "repo": string, "commit_sha": string} },   // anchored only if the anchored STH covers the leaf (tree_size > leaf_index) (verify_router.py:178-181)
  "issuer": null | {"name": string, "id": string|null},        // from the verified key statement
  "public_labels": { "<field>": "<label>" }                    // labels (Vietnamese) from sealed manifest version, only fields in public_fields with a label (verify_router.py:158-163)
}
```
- `inclusion.tree_size` is null and `verified` false until an STH covers the leaf (right after sealing). That is "waiting", NOT invalid (see verify-portal/minimal/README.md:19-34 state table). Never contains record_id, file hashes, non-public fields.
- Errors: 404; 503 `keys-unavailable` (detail "key service is locked and this key version is not cached yet") (:151-154); 429 from gateway.

### 6.3 POST /verify/v1/seals/{seal_id}:check  (verify_router.py:200-207)
- Body `{"sha256":"<64 lowercase hex>"}`, Content-Type application/json. 200 `{"match": boolean}` (membership in `payload.attachments`). Errors 415/413/422/404.

### 6.4 Bundle endpoints (verify_router.py:210-245)
- `GET /verify/v1/seals/{id}/bundle` -> only when manifest `require_file == false` (App B); for `require_file == true` seals this GET returns 404.
- `POST /verify/v1/seals/{id}:bundle` with `{"sha256": ...}` -> only when `require_file == true` (App A) AND sha is in the sealed attachments (else 404); for `require_file == false` seals returns 404.
- 200 JSON body = bundle (6.5) with headers `Cache-Control: no-store`, `Content-Disposition: attachment; filename="dxos-seal-<seal_id>.json"`. Pending -> the pending JSON above.

### 6.5 Bundle format `dxos-seal-bundle/1`  (build: S/seal/bundle.py:185-210)
```
{
 "format": "dxos-seal-bundle/1",
 "status": "VALID"|"REVOKED",              // NOT signed; offline verifiers must ignore it (bundle.py:13,197)
 "payload": {                               // exactly seal_payload() (seal/service.py:77-82)
    "seal_id": str, "app_id": str, "record_id": "<uuid>", "record_digest": "<64 hex>",
    "attachments": ["<sha256 hex>", ...sorted], "issued_at": "YYYY-MM-DDTHH:MM:SSZ",
    "public_fields": {..}, "key_version": int },
 "signature": "<base64 Ed25519 signature, 64 bytes, 88 chars incl '=='>",
 "seal_key": { "version": int, "public_key": "<base64 32-byte raw Ed25519>"|null,
               "statement": { <dxos-key-statement/1> }  // key omitted if no verified statement },
 "ledger": { "entry": {"idx","ts","type":"record.sealed","app_id","subject":<seal_id>,"actor_ref":null,"body_sha256":"<hex>"},
             "body":  {"seal_id": str, "payload_sha256": "<hex>"} },
 "inclusion": { "leaf_index": int, "tree_size": int|null, "proof": ["<hex32>", ...] },
 "sth": null | {"tree_size": int, "root_hash": "<hex>", "ts": "<RFC3339 Z>", "key_version": int, "signature": "<b64>"},
 "sth_keys": { "<key_version as string>": "<base64 raw 32-byte Ed25519 pubkey>" },   // extra hint field of this implementation
 "anchored": null | {"sth": {same 5 fields}, "repo": str, "commit_sha": str, "consistency": ["<hex32>", ...]},
 "generated_at": "<RFC3339 Z>"
}
```
Notes: `sth` is null when no STH covers the leaf yet (bundle then fails NO_STH - for require_file=false the GET still returns it; the portal hides the button until `inclusion.verified`). `entry.actor_ref` is always null for this leaf (the seal leaf is appended without actor, seal/service.py:200-201).
Key statement fields (seal/keys.py:123-143): `{"format":"dxos-key-statement/1","key":"seal-key","version":int,"serial":"seal-key/v<n>","issuer":{"name":str,"id":str|null},"algorithm":"ed25519","public_key":"<b64>","valid_from":"<RFC3339 Z>","valid_until":"<RFC3339 Z>","purpose":str,"policy_url":str|null}`.
STH selection (bundle.py:78-83): newest ANCHORED STH that covers the leaf -> `sth == anchored.sth`, `consistency == []`; else newest STH covering the leaf with `anchored` = latest anchor (maybe null / not covering) + consistency proof to `sth`; else `sth=null, anchored=null`.

### 6.6 Exact byte construction for browser verification (WebCrypto)
All of this is validated by the working reference `sdk/js/test/reference/verify-bundle.mjs` (Node 22 `crypto.subtle`, Ed25519, 3 sample bundles incl. tamper cases: payload, signature, proof, root). Canonical output was also diffed byte-for-byte against Python.

**canonical_bytes(value)** (libs/dxos-proof/src/dxos_proof/canonical.py:24-51): `UTF-8( json.dumps(normalize(v), ensure_ascii=False, separators=(",",":"), sort_keys=True, allow_nan=False) )`, where normalize = NFC on every string AND every object key
(two keys equal after NFC -> error), ints only (no floats; bool/null ok), tuples->arrays. No spaces, no trailing newline.
 - JS notes: sort keys by CODE POINT (Python), not by UTF-16 unit (`Array.sort()` default differs only for astral chars; all real keys are ASCII field names, but use a code-point comparator to be safe). Use `JSON.stringify(str)` for string escaping: it is identical to Python's ensure_ascii=False
   (escapes `"` `\` and control chars <0x20 as `\n \r \t \b \f \u00xx` lowercase; does not escape U+2028/9 or U+007F) - verified identical on a mixed sample.
 - **Big-integer hazard:** integer `public_fields` values may exceed 2^53 (int64 allowed, rec/service.py:86-88). Plain `JSON.parse` would corrupt them and break the signature. Parse bundle with a lossless parser (BigInt for integers) or keep `payload` text.
 - Do NOT re-serialize with `JSON.stringify(obj)` (key order + NFC would differ).

**Seal signature** (seal/service.py:85-87,193; verify bundle.py:139-140; witness bundle.py:314-315):
`Ed25519.verify(pubkey = base64decode(seal_key.public_key) [32 raw bytes], sig = base64decode(signature) [64 bytes], msg = canonical_bytes(payload))`. Whole `payload` object (8 keys), not a hash. WebCrypto: `subtle.importKey("raw", pub32, {name:"Ed25519"}, false, ["verify"])`, `subtle.verify({name:"Ed25519"}, key, sig, msg)`.
(Ed25519 in WebCrypto: Chrome >=137, Firefox >=129, Safari >=17 per MDN; feature-detect with importKey in try/catch and fall back to a JS lib like @noble/ed25519 - UNVERIFIED browser matrix, not from the repo.)

**Leaf link** (witness bundle.py:323-333): all must hold
 - `ledger.body.payload_sha256 == hex(SHA256(canonical_bytes(payload)))`; `ledger.body.seal_id == payload.seal_id`
 - `ledger.entry.body_sha256 == hex(SHA256(canonical_bytes(ledger.body)))` (body = `{"seal_id","payload_sha256"}`, seal/service.py:90-92)
 - `entry.type == "record.sealed"`, `entry.subject == payload.seal_id`, `entry.idx == inclusion.leaf_index`.

**Leaf hash** (ledger/log.py:50-60, 106; dxos_proof/merkle.py:16-18): `leaf_hash = SHA256( 0x00 || canonical_bytes(entry) )` where entry = EXACTLY the 7 keys
`{idx, ts, type, app_id, subject, actor_ref, body_sha256}` (bundle.py:86-89) - use `ledger.entry` as given (it has exactly those 7). `actor_ref` may be null -> canonical `null`.

**Inclusion** (merkle.py:75-93; RFC 9162 §2.1.3.2): `verify_inclusion(leaf_hash, index = inclusion.leaf_index, size = sth.tree_size, proof = inclusion.proof (each hex32 -> 32 bytes), root = hex32(sth.root_hash))`.
 node hash = `SHA256(0x01 || left || right)` (merkle.py:21-23). Algorithm (fn=index, sn=size-1, r=leaf): for each p: if sn==0 fail; if (fn&1) or fn==sn: r=H(p,r) and if fn even: shift fn,sn right while fn even and fn!=0; else r=H(r,p); then fn>>=1, sn>>=1. Accept iff sn==0 and r==root.
 Also require `inclusion.tree_size == sth.tree_size`. (Reference implementation in the .mjs file.)

**STH signature** (ledger/sth.py:37-49; witness bundle.py:170-172): message = `canonical_bytes({"tree_size":int,"root_hash":"<hex>","ts":"<str>","key_version":int})` (exactly these 4 keys; `signature` excluded; `root_hash` as the hex STRING, not bytes); sig = base64decode(sth.signature); pubkey = base64decode(`sth_keys[String(sth.key_version)]`) (or the pinned `keys/sth-key/v<n>.pub`).
 Same for `anchored.sth`.

**Consistency** (merkle.py:96-126; RFC 9162 §2.1.4.2): when `anchored.sth.tree_size != sth.tree_size`: require `a.tree_size < sth.tree_size` and `verify_consistency(a.tree_size, sth.tree_size, hex32(a.root_hash), hex32(sth.root_hash), anchored.consistency)`; when equal sizes: `consistency == []` and roots equal.
 Empty tree root (n=0) = SHA256("") - not needed for bundles (tree_size >= 1).

**Key/statement checks** (witness bundle.py:231-252, 293-311; unpinned mode):
 - `seal_key.version == payload.key_version`; `seal_key.public_key` present (else KEY_MISSING); statement present (else KEY_STATEMENT_MISSING).
 - statement: `format=="dxos-key-statement/1"`, `key=="seal-key"`, `version==key_version` (int), `algorithm=="ed25519"`, `base64(statement.public_key) == seal pub`, `issuer.name` non-empty string, `issuer.id` null or string.
 - Validity: `valid_from <= payload.issued_at <= valid_until` compared as instants (parse RFC3339).
 - Pinned mode (needs the public transparency-log git repo, `keys/seal-key/v<n>.pub`, `keys/sth-key/v<n>.pub`, `keys/seal-key/v<n>.json == canonical_bytes(statement)+"\n"`, `sth/<tree_size 12-digit>.json == canonical_bytes(anchored.sth)`) cannot be done from a browser without fetching that repo (witness bundle.py:293-296,350-359). Unpinned result = "self-consistent only" (CLI exits 3 with a warning, witness/cli.py:62-66).
 - Optional file check: `file_sha256.lower() in payload.attachments`.
 - `status` field of the bundle is unsigned and must not be trusted; revocation always needs a live GET /verify/v1/seals/{id} (witness bundle.py:33-34, 389).
Order/codes of failure (witness bundle.py:6-31): FORMAT, KEY_VERSION, KEY_MISSING/KEY_NOT_ANCHORED/KEY_MISMATCH, KEY_STATEMENT(_MISSING/_NOT_ANCHORED), KEY_NOT_VALID_AT_ISSUE, SIGNATURE, LEAF_LINK, NO_STH, INCLUSION, STH_SIGNATURE, NOT_ANCHORED, ANCHORED_SIGNATURE, CONSISTENCY, FILE_NOT_IN_SEAL, MALFORMED.
`dxos-witness verify-bundle <file> [--anchor-dir DIR] [--file PDF]`: exit 0 = VALID and pinned, 3 = VALID but unpinned, 2 = INVALID (witness/src/dxos_witness/cli.py:9-11).

### 6.7 Other public endpoints (S/ledger/router.py)
- `GET /verify/v1/sth/latest` -> 200 `{"tree_size":int,"root_hash":"<hex>","ts":"<RFC3339 Z>","key_version":int,"signature":"<b64>"}`; 404 `not-found` detail "no signed tree head yet" (router.py:28-34; TreeHead sth.py:28-34).
- `GET /verify/v1/sth/consistency?first=&second=` -> 200 `{"first":int,"second":int,"proof":["<hex32>",...]}`; 400 `bad-request` "need 1 <= first <= second <= latest tree_size"; 422 if params missing/non-int (router.py:37-45).
- `GET /verify/v1/keys` -> 200 `{"seal-key": {"<version>":"<b64 pubkey>"}, "sth-key": {"<version>":"<b64>"}, "statements": {"seal-key": {"<version>": <statement>}}}`; 503 `kms-unavailable` (router.py:48-60). Keys are immutable per version; safe to cache.

---------------------------------------------------------------------------------------------------
## 7. Is there ANY endpoint for a SPA to fetch the app manifest / field labels / its own roles?
- **Yes since Plan 03 T1: `GET /api/v1/apps/{app}/manifest` (section 2.9)** serves the client-safe manifest view (types, `required`/`public`/`pii`/`format`/`label`, access lists, attachment limits, workflow tasks and `decisions`, PII/seal/verify roles).
  The paragraph below is the state at `4f25a34` and is kept for history; where it says "no endpoint" or "SPAs must hard-code the schema", 2.9 now supersedes it. Own roles still come from `whoami` (section 1); the view does not say which roles the caller holds.
- (At `4f25a34`:) **No.** Complete route list of the process (grep of `@router.*` in S/): whoami; records/*; attachments; uploads; objects; tasks; workflow:start; :pii-review; :erase-pii; :revoke; seal; /verify/v1/*; /admin/v1/* (apps, apps/{id}/versions/{v}/diff, :approve, :disable, health, quarantine, anchor:run, ledger/status, workflow:reconcile); /healthz; /readyz.
  No `GET /api/v1/apps`, no `GET /api/v1/apps/{app}` or `/manifest`. `/admin/v1/apps*` returns manifests/versions but requires `dxos-admin` AND the admin host (Caddyfile:45-48,56-72; apisix.yaml:35-38); a Tier-2 SPA cannot use it.
- Field labels are only exposed (a) publicly, for public fields only, as `public_labels` on `GET /verify/v1/seals/{id}` (verify_router.py:196), and (b) nowhere else. Field types, `required`, `pii`, `public`, `sequence` format are not served: SPAs must hard-code the schema (apps/*/manifest.yaml is the source; also tests/apps/fixtures/*.yaml copies).
- Own roles: `GET /api/v1/whoami` `roles` (raw `app:<app>:<role>` strings) is the only server-side source (also decodable from the access token's `realm_access.roles`). The server does not return per-collection permissions (can create? can reveal PII?); infer from roles + hard-coded manifest.
- Permission checks that the UI can mirror from the manifests (shipped apps): App A `phong-ho-so`/`van_ban`: create=chuyen_vien; read=owner+truong_phong,giam_doc,van_thu,nhan_vien; update=owner (default); reveal PII=giam_doc,van_thu; erase PII=van_thu; revoke=giam_doc;
  tasks: duyet_noi_dung=truong_phong, ban_hanh=giam_doc; seal public_fields=[so_hieu, loai_van_ban, trich_yeu, chuc_vu_nguoi_ky]; attachments pdf, max 15 MB, min 1; verify public, require_file true. App B `chung-nhan`/`chung_nhan`: create=can_bo_clb; read=can_bo_clb,truong_clb; update=owner; reveal/erase/revoke=truong_clb;
  task phe_duyet=truong_clb; public_fields=[so_chung_nhan, ho_ten, su_kien, ngay_cap]; no attachments; verify public, require_file false. (apps/phong-ho-so/manifest.yaml, apps/chung-nhan/manifest.yaml)

---------------------------------------------------------------------------------------------------
## 8. problem+json `type` slugs actually raised (prefix `https://dxos.dev/problems/`)
Auth/generic: unauthenticated(401), forbidden(403), not-found(404), app-not-active(404), bad-request(400), invalid-request(422), precondition-required(428), unsupported-media-type(415), payload-too-large(413), length-required(411), idp-unavailable(503), internal(500), not-ready(503, /readyz), plus HTTP_SLUGS defaults (errors.py:29-46).
Records: schema(422, `errors[]`), record-sealed(409), record-in-workflow(409), version-conflict(409), seal-pending(409, erase-pii only), record-not-open(409, attachments).
Objects: storage-unavailable(503), integrity-error(500).
Workflow: guard-failed(403|409, ext `guard`,`reason`), already-running, no-workflow, attachments-pending, attachments-not-clean, app-not-deployed, task-gone, task-unknown, workflow-inconsistent (all 409), invalid-decision(422), invalid-comment(422), workflow-unavailable(503), workflow-pending(503 + Retry-After), workflow-finalize-failed(500), workflow-model-mismatch(500),
  kms-unavailable(503), key-statement-invalid(503), seal-key-expired(503), org-not-configured(503) (wf/service.py:217-241).
Seal: not-sealed(409), invalid-reason-code(422), invalid-note(422). Verify: keys-unavailable(503), kms-unavailable(503, /keys).
Admin only: ledger-entries 422 reuses `invalid-request` (section 14); manifest-invalid(422, ext `code`), app-version-not-found(404), version-not-newer, install-in-progress, app-version-conflict, deployment-mismatch, app-version-not-pending (409), idp-admin-unavailable(503).
`guard` values = the literal guard string in the manifest (e.g. `attachments_clean`, `pii_reviewed`, `not_same_actor:creator`, `not_same_actor:duyet_noi_dung`); catalog: attachments_clean, pii_reviewed, not_same_actor, role_in, field_required, record_not_sealed, assignee_is_caller (registry/validator.py:26-29).
Ledger-only denial reasons (not returned to the client; `read_manifest` is the `action` of the 2.9 denial): no_app_role, admin_no_data_access, not_in_access_list, unknown_collection, not_task_role, not_eraser, not_revoker, not_pii_reviewer, guard:<guard>:<reason>.

---------------------------------------------------------------------------------------------------
## 9. SPA deployment: Caddy / Keycloak / APISIX
### 9.1 How content reaches /apps today
- Caddy mounts the NAMED volume `apps-static` read-only at `/srv/apps` (deploy/compose.yaml:60; volume declared :314). Nothing writes to it: no service, script, Dockerfile, CI job, or Make target populates `apps-static` (repo-wide grep for `apps-static` finds only compose.yaml, Caddyfile comment, a test, and a plan note). Currently `/apps/<anything>` except `/apps/verify/` returns 404 (empty volume).
- Serving rules (Caddyfile:26-29): `handle /apps/* { root * /srv; file_server }` => URL `/apps/phong-ho-so/index.html` maps to `/srv/apps/phong-ho-so/index.html`, i.e. volume subdir `phong-ho-so/`. `file_server` serves `index.html` for directory URLs. NO `try_files` SPA fallback (so history-mode deep links 404 -> use hash routing or add `try_files` to the Caddyfile), NO `encode`/gzip, NO Cache-Control, NO CSP for /apps/* (only /apps/verify/ gets a CSP, Caddyfile:19-23).
- `/apps/verify/` is reserved: separate read-only bind mount `../verify-portal/minimal:/srv/verify:ro` (compose.yaml:62), vanilla HTML/JS, anonymous; more specific handle wins (Caddyfile:14-25). `redir /apps/verify /apps/verify/ 308`. Do not use the name `verify` for a SPA.
- The Caddy container has only the two mounts; to ship SPAs you need to add content to the volume (e.g. a one-shot copy service/`docker run -v dxos_apps-static:/dst`, or change the mount to a bind mount). The compose project name is `dxos` so the volume is `dxos_apps-static`.
- Hosts: public host `{$DXOS_DOMAIN}` (users, SPAs, verify); admin host `{$DXOS_ADMIN_HOST}` IP-allow-listed. Dev: `DXOS_DOMAIN=localhost`, admin `admin.localhost`, Caddy internal CA (tests/e2e/conftest.py:29-30).
### 9.2 Keycloak realm `dxos` client `dxos-spa` (deploy/keycloak/realm-dxos.json:234-262; identical in realm-dxos-dev.json)
- publicClient true; standardFlowEnabled true; implicit false; directAccessGrants false (so NO password grant for SPAs); no service account; frontchannelLogout true.
- redirectUris: exactly `["https://${DXOS_DOMAIN}/apps/*"]` (asserted by tests/infra/test_keycloak_realm.py:111). webOrigins: `["+"]` (= allow origins of the redirect URIs, for CORS on the token endpoint). `post.logout.redirect.uris` = `https://${DXOS_DOMAIN}/apps/*`.
  Consequence: `http://localhost:5173` dev servers are NOT allowed redirect targets (changing it requires editing the realm JSON, the dev overlay builder ops/build_dev_realm.py and that test; and `ops/keycloak_upgrade.py` for already-imported realms, since `--import-realm` is skipped when the realm exists, ops/README.md:88-91).
- PKCE: attribute `pkce.code.challenge.method = S256` (enforced). Default client scopes: web-origins, acr, basic, profile, roles, dxos-api-audience. No optional scopes.
- Token audience: scope `dxos-api-audience` has an `oidc-audience-mapper` adding `dxos-api` to `aud` of the ACCESS token (realm-dxos.json:209-225) - required, core rejects tokens without `aud` containing `dxos-api` (settings.py:36, jwt.py:104). `roles` scope maps realm roles to `realm_access.roles`.
- Lifetimes: access token 300 s (realm-dxos.json:13); SSO idle 1800 s, SSO max 36000 s; `revokeRefreshToken: true`, `refreshTokenMaxReuse: 0` (line 16) => refresh tokens are single-use: serialise refresh calls (two tabs/parallel refreshes will invalidate each other). Brute force protection on.
- Endpoints (issuer `https://{DXOS_DOMAIN}/auth/realms/dxos`, Keycloak under `/auth`, KC_HTTP_RELATIVE_PATH=/auth, compose.yaml:108): `/auth/realms/dxos/protocol/openid-connect/{auth,token,logout,certs}`, discovery `/auth/realms/dxos/.well-known/openid-configuration`.
- Other clients: `apisix` (confidential, token check), `dxos-installer` (service account), `dxos-cli` (device flow). DEV ONLY `dxos-test` (realm-dxos-dev.json:347): public, direct-access (password) grants, same scopes (so includes audience) - used by tests/e2e.
- Dev realm users (all password `dev-only-password`, temporary=false; deploy/keycloak/dev-overlay.json:2,10-23; realm-dxos-dev.json:381-580):
  chuyen_vien1 -> app:phong-ho-so:chuyen_vien
  chuyen_vien_tp1 -> app:phong-ho-so:chuyen_vien + app:phong-ho-so:truong_phong (can create but cannot self-approve: guard not_same_actor)
  truong_phong1 -> app:phong-ho-so:truong_phong
  giam_doc1 -> app:phong-ho-so:giam_doc
  van_thu1 -> app:phong-ho-so:van_thu
  nhan_vien1 -> app:phong-ho-so:nhan_vien
  can_bo_clb1 -> app:chung-nhan:can_bo_clb
  truong_clb1 -> app:chung-nhan:truong_clb
  owner_a1, owner_b1 -> app:test-app:member (test app only)
  admin1, admin2 -> dxos-admin (two admins for four-eyes app approval)
  (+ service-account-dxos-installer). Emails `<user>@dev.dxos.invalid`, firstName = username, lastName "Dev". Production realm has NO human users (only the installer service account); app roles are created by the installer on `:approve`.
### 9.3 APISIX (deploy/apisix/apisix.yaml, config.yaml): standalone/YAML
- Routes: `api-v1` `/api/v1/*` (OIDC bearer + limit-req 50/s burst 100), `admin-v1` `/admin/v1/*` host-bound (10/s burst 20), `verify-v1` `/verify/v1/*` anonymous (5/s burst 10), `view` `/view/*` disabled (status 0). All keyed by `X-Forwarded-For`. No CORS plugin, no response rewriting.
- `/healthz`, `/readyz` are NOT routed through Caddy/APISIX (not in the path list) - internal only.
- Body cap 20m (config.yaml:101). NOTE for SPAs: a `/verify` page that checks many seals quickly (> 5 req/s sustained) will hit 429.

---------------------------------------------------------------------------------------------------
## 10. tests/e2e/conftest.py `Stack` helper: reference call sequences
Auth: `POST {base}/auth/realms/dxos/protocol/openid-connect/token` form `grant_type=password&client_id=dxos-test&username=..&password=dev-only-password&scope=openid` (conftest.py:71-75) (SPA must instead use auth-code+PKCE on `dxos-spa`).
Helpers (conftest.py:104-246): `records(app,col)=/api/v1/apps/{app}/collections/{col}/records`; `create` POST json -> expect 201; `bulk` POST `records:bulk` list -> 200, `results[*].ok/id`; `get`; `version`=GET.version; `upload` multipart `files={"file": (name, bytes, "application/pdf")}` -> 202 `upload_id`;
`wait_upload` poll GET /api/v1/uploads/{id} every 2 s <=180 s until status != STAGING; `start` = GET version then POST `workflow:start` with `If-Match: "<v>"`; `task` poll `GET /api/v1/apps/{app}/tasks?assigned=me` (1 s, <=30 s) for item with matching `record_id` and `task_key`;
`complete` POST `/api/v1/apps/{app}/tasks/{task_id}:complete` `{"decision": d}` + `If-Match: "<record version>"`; `complete_task` = task() then GET version then complete(); `pii_review` = GET version + POST `:pii-review` If-Match; `wait_sealed` poll GET record until `seal_state == "SEALED"` (2 s, <=120 s);
`seal_id` = GET `.../records/{rid}/seal`.seal_id; `public` GET /verify/v1/seals/{id}; `wait_anchored` = (admin) POST admin `/admin/v1/anchor:run` then poll public view until `inclusion.anchored != null` (3 s, <=240 s).
**App A flow** (tests/e2e/test_m2_app_a.py:23-112): chuyen_vien_tp1 creates `{trich_yeu, loai_van_ban, chuc_vu_nguoi_ky, nguoi_lien_he_cccd}` -> upload EICAR + clean PDF -> wait: INFECTED / CLEAN -> start (200) -> same user completes `duyet_noi_dung` approve => 403 `reason=="same_actor"` ->
truong_phong1 completes `duyet_noi_dung` approve (200) -> giam_doc1 completes `ban_hanh` approve => 409 `guard=="pii_reviewed"` -> van_thu1 `:pii-review` (200) -> giam_doc1 `ban_hanh` approve (200) -> wait SEALED -> GET seal -> public view (VALID, signature_valid, inclusion.verified; `issuer.name` == org) ->
`:check` with pdf sha256 (match true) / tampered (false) -> `POST :bundle {sha256}` -> `dxos-witness verify-bundle --anchor-dir --file` exit 0 -> van_thu1 `:erase-pii {"fields":["nguoi_lien_he_cccd"],"reason_code":"data_subject_request"}` (200) -> giam_doc1 `:revoke {"reason_code":"superseded"}` (200, `seal_state=="REVOKED"`) -> public status "REVOKED".
**App B flow** (test_m2_app_b.py:130-169): can_bo_clb1 `records:bulk` of 3 `{ho_ten, su_kien, ngay_cap:"2026-11-10", email}` -> start each -> truong_clb1 completes `phe_duyet` approve for each -> wait SEALED -> GET seal -> public view `require_file false`, `attachments_count 0`, `public_fields.ho_ten`, no `email` -> `GET /verify/v1/seals/{id}/bundle` 200 `format == "dxos-seal-bundle/1"`.

---------------------------------------------------------------------------------------------------
## 11. ops/ (tracked files) and Make targets
ops/: README.md, at13_reuse.sh (AT-13 evidence on VPS), build_dev_realm.py (builds realm-dxos-dev.json; `--check`), capacity_report.py, changelog_section.py (release notes), keycloak_upgrade.py, measure.sh (RAM per container), netcheck.py, openapi.py (writes docs/api/openapi.json), pin_images.py, seed_manifests.py (core tests only),
e2e/install_apps.sh (installs apps A/B via CLI, four-eyes: DXOS_TOKEN submitter + DXOS_APPROVER_TOKEN), e2e/run_e2e.sh (runs tests/e2e inside python:3.12-slim next to the dev-lite stack; needs /out/caddy-root.crt, DXOS_ORG_NAME).
- **`ops/deploy.sh` does NOT exist** (only mentioned in ops/README.md:5 as "Plan 03"). **There is no `demo-seed` script or `make demo-seed` target** (only referenced in plan/spec text: docs/superpowers/plans/...00...md:335, specs/...design.md:818).
- Makefile targets (Makefile:10-74): help, dev-install, lint, test, reuse, check, up, down, ps, logs, netcheck, test-infra, test-db-up, test-integration, pin-images, openapi. `make up PROFILE=p16|p8|dev-lite` => `docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.$(PROFILE).yaml up -d --build`. No target for apps, SPAs, npm, e2e.
- docs/api/openapi.json exists (32 paths, generated from FastAPI) but is mostly useless as a contract: handlers return bare `dict`/`JSONResponse`, so 2xx response schemas are empty `{}`/generic objects, and ETag/If-Match/problem types are absent. Use this file instead.
- sdk/js/README.md and viewer/README.md are placeholder READMEs only ("Hiện thực ở Plan 03/04"). verify-portal/minimal is the only existing browser client code (vanilla JS, 457 lines) and is a good reference for state handling of the public API.

---------------------------------------------------------------------------------------------------
## 12. Node/npm tooling and CI
- NO `package.json`, lockfile, tsconfig, vite config, .nvmrc anywhere in the tracked tree (git ls-files: none). Only JS in repo: verify-portal/minimal/verify.js and tests/deploy/browser/*.js (Playwright scripts run via Node, `npm i -g playwright`, opt-in: verify-portal/minimal/README.md:46-54).
- .github/workflows/ci.yml (trigger: push to main + PRs; `permissions: contents: read`):
  - `reuse`: `pip install reuse; reuse lint` (every file needs SPDX headers - new TS/Vue files will need them or REUSE.toml coverage; see REUSE.toml).
  - `lint`: `pip install ruff; ruff check .`.
  - `unit`: `make dev-install; pytest -m "not integration and not infra"` (includes tests/apps, tests/deploy static, tests/ops, tests/repo hygiene).
  - `integration`: compose.test.yaml up (core-db, seaweedfs, openbao, flowable) + wait for Flowable REST; `make dev-install; pytest -m integration -v`.
  - `caddy-live`: downloads Caddy 2.10.0 (sha512-pinned) and runs tests/deploy/test_caddy_admin_allowlist_live.py.
  - `secrets`: gitleaks v8.18.4 via docker.
- nightly.yml (cron 19:00 UTC + manual): `real-clamav` job: real ClamAV container + core integration ingest tests. release.yml (tag `v*.*.*`): `check` (versions match tag, CHANGELOG), `image` (build+push ghcr trust-core), `release` (wheels, source tar.gz, syft SBOM, gh release).
- Repo tests that will constrain new SPA work: tests/repo/test_repo_hygiene.py, tests/repo/test_docs_m2.py, tests/deploy/test_verify_page_static.py (mount layout assertion `apps-static:/srv/apps:ro` at :269), tests/infra/test_compose_static.py (compose/network matrix), tests/infra/test_keycloak_realm.py:111 (redirectUris). Also REUSE.toml and LICENSES-THIRD-PARTY.md (third-party notes) - not inspected in depth.

---------------------------------------------------------------------------------------------------
## 13. Gaps and gotchas that affect an SDK/SPA design (all verified in code)
1. **[Resolved by Plan 03 T1: `GET .../records/{rid}/attachments`, section 3.4]** (at `4f25a34` there was no way to list a record's attachments/uploads or get their CLEAN sha256s; the client had to keep `upload_id`s). Original filename is never stored/returned.
2. Record has no `seal_id`: get it from the `seal_id` field of the tasks:complete response or GET .../seal (404 until sealing requested).
3. Task inbox item lacks record version/title/data: N+1 GETs needed; `created` format differs from `created_at`.
4. Complete/start/revoke etc. need current record version in `If-Match: "<n>"` (quoted). Bare integer = 400. Re-GET after any state-changing call (list in 0.3); SEALED does not bump version, SEAL_PENDING does.
5. Bulk response gives only ids; per-row errors are `{ok:false,row,error:{type,title,errors}}`; HTTP 200 even when all rows fail; partial commit.
6. `comment` on complete is never stored. `decision` values are `approve`/`reject` (BPMN-derived; since Plan 03 T1 discoverable in `workflow.decisions` of the manifest view, section 2.9).
7. PATCH is a raw merge-patch of `data` (null deletes); GET data may be masked -> never write masked values back.
8. Only `owner` can PATCH/attach/start (default update list). App A reviewers cannot edit.
9. `GET /records` has no filters and is oldest-first: "my tasks" views must use the tasks inbox; "my records" for owner-only roles is automatic (owner filter), other roles see everything.
10. Objects: `variant` only `original`; download needs Bearer -> fetch+Blob; `Content-Disposition` filename is `<sha256>.pdf`.
11. verify_url = `/apps/verify/#<seal_id>`; QR must be generated client-side from that string (hash fragment so seal_id is not in server logs).
12. Public bundle for `require_file:true` apps needs the file hash (POST :bundle) - compute in-browser with `crypto.subtle.digest("SHA-256", await file.arrayBuffer())`, as verify.js:376-380 does.
13. Rate limit on /verify is 5 req/s per client IP (X-Forwarded-For) burst 10; /api 50 req/s.
14. 401/413/429 coming from APISIX/nginx may not be problem+json (UNVERIFIED): SDK error parsing should fall back to status-only.
15. Sample bundles + a working WebCrypto verifier for regression tests: `sdk/js/test/reference/` (bundle-anchored_is_sth.json, bundle-newer_sth.json, bundle-anchor_before_leaf.json, verify-bundle.mjs). These were generated with the witness TEST builder (witness/tests/conftest.py:BundleEnv.build), not by a live server, but its output format is identical to `build_bundle` (same fields); issuer/test data only.

---------------------------------------------------------------------------------------------------
## 14. Admin: ledger entries  **[Plan 03 T1]**  (S/admin/router.py `ledger_entries`)
`GET /admin/v1/ledger/entries?type=<event type>&limit=<1..100>`
- Role: `dxos-admin` only (like every `/admin/v1/*` route: 401 without a token, 403 `forbidden` without the role), and only on the admin host (Caddy/APISIX, section 0.1/0.6). No `Cache-Control`.
- `type` (optional): one of the ledger event types (`S/ledger/events.py`: `policy.denied`, `record.created`, `field.revealed`, `task.completed`, ...); omitted = all types. Unknown -> 422 `invalid-request`
  (title "Request validation failed", `detail` lists the allowed types).
- `limit` (optional, default 20): integer 1..100; outside the range or not an integer -> 422 `invalid-request` with `errors[]` (FastAPI validation, section 0.4).
- 200 `{"items": [{"idx": int, "ts": "<RFC3339 UTC>", "type": string, "app_id": string|null, "subject": string, "actor_ref": string|null}]}`, newest first (`idx` descending).
  Only these six leaf fields: no `body_sha256`, `leaf_hash`, and no ledger body (bodies are not stored). `actor_ref` is the HMAC of the caller's `sub`, not the `sub`.
- Read-only; it adds no ledger entry. There is still no admin API that edits or deletes the ledger.
