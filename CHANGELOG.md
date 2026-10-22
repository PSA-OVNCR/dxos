# Changelog

Mọi thay đổi đáng kể được ghi tại đây, theo định dạng [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/) và [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

## [0.3.0] - Chưa phát hành
Mốc M3 (Tầng 1 hoàn tất cho client: SDK, hai ứng dụng Tầng 2 có giao diện, cổng đối soát Vue, triển khai theo tag).
Mã đã xong và đã qua test đơn vị, integration và Playwright với API giả ở cloud; **chưa chạy trên stack thật** (mục
"Known limitations"). Trưởng nhóm thay "Chưa phát hành" bằng ngày khi gắn tag `v0.3.0` (sau `v0.2.0`, V18 rồi V33); workflow
`release` từ chối mục chưa có ngày.

### Added
- **Ba endpoint chung cho client Tầng 2** (không chứa định danh app nào): `GET /api/v1/apps/{app}/manifest` (phần
  manifest an toàn cho client, kèm giá trị `decision` của từng task đọc từ BPMN đã triển khai; người không có vai trò
  của app nhận 404 và lá `policy.denied`), `GET .../records/{rid}/attachments` (liệt kê tệp đính kèm, quyền như đọc
  bản ghi, không ghi `field.revealed`) và `GET /admin/v1/ledger/entries` (các lá ledger mới nhất, chỉ `dxos-admin`).
  `docs/api/contract-tier2.md`: hợp đồng HTTP của lõi đối chiếu theo mã, cập nhật cho ba endpoint này.
- **SDK `dxos-sdk-js`** (`sdk/js/`, npm workspace; chưa công bố lên npm): client HTTP `DxosClient` (`If-Match` luôn
  lấy từ một lần GET ngay trước, không tự thử lại yêu cầu ghi), đăng nhập OIDC Authorization Code + PKCE `createAuth`
  (token chỉ nằm trong `sessionStorage`, làm mới single-flight), bộ kiểm gói bằng chứng trên trình duyệt `verifyBundle`
  (dịch từng bước `dxos-witness verify-bundle`, hai bên chạy chung một bộ vector; còn hai khác biệt đã biết, xem Known limitations), thành phần Vue
  (`QuarantineStatus`, `SealQr`, `VerifyLink`, `RecordForm`, `ProblemMessage`, `AppShell`, `SealPanel`, `PiiPanel`,
  `ConfirmDialog`, `boot`) và công cụ test `dxos-sdk-js/testing` (`fakeFetch`, `fakeClient`, `problem`). Hướng dẫn: `sdk/js/README.md`.
- **Cổng đối soát Vue** `/apps/verify/` (`verify-portal/app/`, AT-25): hash tệp và tự kiểm gói bằng chứng ngay trên trình
  duyệt, tệp không bao giờ rời máy; có `VITE_ANCHOR_RAW_BASE` thì đối chiếu thêm với repo neo (ghim). Trang tối giản cũ
  chuyển sang `/apps/verify-lite/` làm dự phòng. Bộ Playwright của cổng chạy trong job `web` của CI.
- **App A "Phòng hồ sơ số"** (`apps/phong-ho-so/web`, `/apps/phong-ho-so/`): danh sách và tạo văn bản, tải tệp kèm
  trạng thái kiểm dịch, nộp duyệt, hộp việc, rà soát và xóa PII, niêm phong có mã QR, thu hồi, tải bản đã niêm phong,
  **Sổ đăng ký văn bản đi** (spec 25.4).
- **App B "Chứng nhận số"** (`apps/chung-nhan/web`, `/apps/chung-nhan/`): nhập CSV (UTF-8 có/không BOM, CP1258 và
  UTF-16 của Excel; phân tách `,` `;` hoặc tab), duyệt theo lô, giấy chứng nhận có mã QR, trang in A4 ngang (không in
  email), câu tuyên bố phạm vi (spec mục 14).
- `make web-check` (`npm run check`: typecheck, test, build mọi workspace), `make web-build` (`ops/web_build_docker.sh`
  dựng các SPA trong một container Node dùng một lần vào volume `apps-static`), `ops/build_web.sh` (dựng vào thư mục
  tạm rồi mới thay; ghi `BUILD-INFO.json`), CI job `web`, và bộ Playwright "live" chạy trên trình duyệt thật
  (`make web-live`, `tests/web/live`; mặc định bỏ qua, chỉ chạy khi `DXOS_WEB_LIVE=1`).
- `ops/vuot_rao.py` (`make vuot-rao`): bảng thử vượt rào, 10 kịch bản tấn công qua cổng thật bằng token dev (tự duyệt,
  đọc chéo, sai app, admin đọc dữ liệu app, sửa văn bản đã niêm phong, ban hành thiếu rà PII, tệp tới `:check`, EICAR,
  manifest nới sàn, task của app khác), in bảng kết quả và 20 lá `policy.denied` gần nhất. Các kịch bản bị chặn bởi lõi đòi đúng
  `problem` slug của lõi, không chỉ đúng mã HTTP. Chỉ chạy trên stack có realm dev.
- `docs/acceptance.md`: ma trận AT-01..AT-28 (test tự động, nơi chạy, bằng chứng); `tests/repo/test_at_matrix.py` bắt
  buộc đủ 28 dòng và mọi test được dẫn phải tồn tại.
- `ops/deploy.sh <vX.Y.Z>` và `docs/runbook-deploy.md`: triển khai VPS theo tag (R-3): lấy tag không `--force`, đọc digest
  image từ Release, dựng SPA, `compose pull` rồi `up -d --wait`, kiểm sức khỏe, ghi `deploy/deployments.log`; hỏng thì in
  lệnh quay lại bản trước (không tự quay lui). Release có thêm `dxos-web-X.Y.Z.tar.gz` (các SPA đã dựng).
- Hướng dẫn "Viết app DX-OS trong 30 phút" (`docs/tutorial-app-30-phut.md`), ví dụ chạy được `examples/so-muon-sach/`
  (manifest, BPMN và SPA nhỏ, cài không sửa `core/`) và `docs/at26-checklist.md` cho người thử ngoài đội (AT-26).
- Biên nhận OpenTimestamps cho STH đã neo (Đ2, P3-D10), **mặc định tắt**: đặt `DXOS_OTS_CALENDARS`
  (URL https cách nhau dấu phẩy) thì sau mỗi lần neo mới, việc `ots_stamp` gửi digest STH tới các calendar. Biên nhận
  được lưu vào bảng chỉ-thêm `ots_receipts` (migration 005) và commit thành `ots/<n>.ots` trong repo neo. Gói bằng
  chứng có thêm `timestamps`. Client calendar tự viết, không thêm phụ thuộc; mỗi lần gọi có hạn tổng thời gian và
  giới hạn kích thước phản hồi (đọc theo luồng); bộ đọc `.ots` kiểm chặt như bộ đọc chính thức. Calendar lỗi không chặn việc neo.
  `dxos-witness` chỉ ghi chú, không đổi kết quả. Người kiểm dùng `ots upgrade` + `ots verify` (`docs/runbook-anchor.md` mục 6).

### Changed
- Trang đối soát tối giản chuyển từ `/apps/verify/` sang `/apps/verify-lite/`; `/apps/verify/` giờ phục vụ cổng Vue từ
  volume `apps-static`. Trên stack dev đang chạy, `/apps/verify/` trả 404 cho tới khi chạy `make web-build`.
- Đăng nhập, phiên, khởi động ứng dụng, khung ứng dụng, hộp xác nhận, panel niêm phong và panel rà soát PII được chuyển
  vào SDK để App A, App B và ví dụ dùng chung (hành vi của App A không đổi).
- `QuarantineStatus` thăm dò tiếp khi gặp lỗi tạm thời (408, 429, 5xx, lỗi mạng) thay vì dừng; nhận `initial` để hiện
  ngay trạng thái đã biết từ danh sách tệp.
- Kho npm: `package.json` gốc khai workspace (`sdk/js`, `verify-portal/app`, `apps/*/web`, `examples/*/web`), khóa
  chính xác `packageManager: npm@11.6.2`, `engines` Node 22; jsdom ghim 29.1.1 và `overrides` cho `@vue/*` (3.5.43) và
  `nopt` (9.0.0) vì Node 22.22.0. Chi tiết: `BUILD.md`.
- `core/tests/helpers/at14.py` (helper test, không nằm trong image lõi) lấy thêm định danh từ `examples/*/manifest.yaml`;
  AT-14 vẫn không cho phép định danh app, kể cả của ví dụ, trong mã lõi phát hành.

### Security
- Caddy gắn cho `/apps/*` CSP `default-src 'self'` (không `unsafe-inline`), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`; HTML `no-cache`, `assets/` cache một năm. `/apps/verify/` và `/apps/verify-lite/` giữ CSP
  chặt hơn của riêng chúng; `DXOS_ANCHOR_RAW_ORIGIN` chỉ mở thêm đúng một origin cho `connect-src` của cổng.
- Kiểm tự động mã web (`tests/repo/test_web_hygiene.py`): cấm `v-html`, `innerHTML`, `eval`, `new Function`, `localStorage`,
  URL `http://` và CDN; mọi phiên bản npm ghim chính xác (không `^`, `~`); mọi tệp có header SPDX.
- Cổng đối soát: tệp người dùng chỉ được băm tại trình duyệt, chỉ hash gửi đi; `payload.seal_id` đã ký phải khớp mã đang
  kiểm (chống máy chủ giả trả gói của niêm phong khác); máy chủ chỉ có thể hạ nhãn kết quả, không nâng; nguồn neo hỏng
  không bao giờ hạ một gói giả xuống "chưa đối chiếu" (kiểm khóa cố định trước khi rơi về không ghim); mã trạng thái lạ hoặc thân phản hồi không đọc được hiện
  "chưa kiểm được", không phải "không hợp lệ".
- `vuot_rao.py` đòi cả mã trạng thái lẫn slug `problem` của lõi nên không xác nhận nhầm một lỗi định tuyến là "bị chặn".
- Review cuối Plan 03: lõi từ chối thân JSON có U+0000 (khóa hoặc giá trị) bằng 422 `invalid-request` thay vì 500 khi ghi
  `jsonb`; App B coi ký tự điều khiển C0 (trừ TAB, CR, LF) và DEL là chữ vỡ, nên tệp UTF-16 không BOM bị từ chối theo dòng.
  `ops/web_build_docker.sh` và `ops/web_live.sh` không chép tệp `.env*`, `.secrets/`, `deploy/release.env` vào container npm.
  `ops/build_web.sh` từ chối `<out_dir>` nguy hiểm (có thành phần `.`/`..`, `/`, repo, thư mục cha của repo, `$HOME`, thư mục
  không đọc được hoặc thư mục lạ không rỗng).
  `ops/deploy.sh` chỉ bỏ xác minh TLS (`curl -k`) khi `DXOS_DOMAIN` là `localhost`/`*.localhost`.

### Known limitations
Mọi mục dưới đây **chưa chạy** vì môi trường dựng mã (cloud) không có Docker, trình duyệt thật cho stack, VPS hay mạng ra
calendar OpenTimestamps; việc cần làm ghi ở `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 13.
- Bộ Playwright live trên App A, App B và cổng đối soát, và `make web-build` với image Node thật: chưa chạy (V27). Digest
  `NODE_IMAGE` và `PLAYWRIGHT_IMAGE` đã ghim ngày 22/10/2026 bằng `make pin-images` trên máy trưởng nhóm (V35).
- `ops/vuot_rao.py` chưa chạy trên stack thật (V28); `ops/deploy.sh` mới được kiểm bằng `git`, `docker`, `curl` giả, chưa chạy
  trên VPS (V29); `release.yml` bước dựng SPA chưa chạy trên Actions (V33).
- Biên nhận OpenTimestamps: client calendar mới kiểm với calendar giả; chưa gọi calendar thật, chưa `ots verify` (V32). Test
  đối chiếu với client chính thức (`DXOS_OTS_CLIENT=ots`) chưa chạy.
- Cổng đối soát chỉ đối chiếu repo neo khi build có `VITE_ANCHOR_RAW_BASE` và `.env` có `DXOS_ANCHOR_RAW_ORIGIN` khớp nhau; repo neo
  thật chưa có (V34). AT-26 (người ngoài đội làm theo hướng dẫn) chưa tổ chức (V31).
- Chưa kiểm AT-20 sau bản sửa bước mở khóa OpenBao của test (`40d6d64`; V36). Phần mềm build có giấy phép MPL-2.0, BlueOak-1.0.0,
  MIT-0, CC0-1.0 (`mdn-data`) chỉ nằm trong công cụ build, không vào bundle; chờ trưởng nhóm xác nhận (V30).
- `verifyBundle` (JS) và `dxos-witness verify-bundle` (Python) dùng chung bộ vector nhưng còn hai khác biệt đã biết: JS chỉ nhận tối đa 2 dấu `=` đệm
  trong base64 (Python nhận nhiều hơn sau một nhóm đủ), và số nguyên dài hơn 4300 chữ số cho `MALFORMED` ở Python nhưng JS vẫn chấp nhận.
  Hai khác biệt này không làm gói thật đổi kết quả.
- Gói npm `dxos-sdk-js` chưa công bố lên npm (`private: true`); ứng dụng dùng SDK qua npm workspace.

## [0.2.0] - Chưa phát hành
Mốc M2 (Tier-0 hoàn tất: workflow, niêm phong, đối soát, installer). Spec bản 1.0.3. Trưởng nhóm thay "Chưa phát hành"
bằng ngày khi gắn tag `v0.2.0`; workflow `release` từ chối mục chưa có ngày.

### Added
- Manifest 1.0.3: `policies.seal.revoke_roles`, `policies.pii.erase_roles`, `fields.<f>.label`, đánh số theo năm
  (`reset: yearly`, `{n:0W}`, `DXOS_TIMEZONE`), tham số guard; sự kiện ledger `workflow.started`, `workflow.completed`.
- Migration 003, 004: ý định và kết quả hoàn thành task, xác nhận rà PII, yêu cầu niêm phong theo ảnh chụp, tệp và
  deployment của app, khóa sửa/tải lên khi đang chạy quy trình; salt riêng của từng bản ghi (xóa được), bằng chứng xóa
  PII chỉ thêm, tuyên bố khóa.
- Bộ kiểm BPMN theo danh sách cho phép (cấm biểu thức, DTD, entity), lõi tự dựng lại BPMN trước khi deploy.
- Client REST Flowable; cầu nối quy trình: ghim phiên bản app, guard và khóa lạc quan trước Flowable, kiểm KMS trước
  task cuối (R-1), đối soát lần hoàn thành bị gián đoạn; danh mục guard chung; xác nhận rà PII (`:pii-review`).
- Niêm phong theo ảnh chụp (cam kết có salt, `SEAL_PENDING` và job thử lại, một niêm phong mỗi bản ghi), thu hồi theo
  mã lý do, `:erase-pii` (niêm phong vẫn `VALID`), tuyên bố khóa `dxos-key-statement/1` neo ở `keys/seal-key/v<n>.json`.
- API công khai `/verify/v1/seals/*`: xem niêm phong, `:check` chỉ nhận hash, gói bằng chứng ngoại tuyến;
  `dxos-witness verify-bundle` (AT-17); trang đối soát tối giản `verify-portal/minimal` (hash tính tại trình duyệt).
- Installer: nộp, diff quyền, duyệt bốn mắt (tạo realm role qua service account `dxos-installer`, deploy BPMN), vô
  hiệu hóa; `/admin/v1/health`, `/admin/v1/quarantine`; client Keycloak `dxos-cli` (device flow); `ops/keycloak_upgrade.py`.
- CLI quản trị `dxos` (wheel `dxos-cli`).
- App A "Phòng hồ sơ số" và App B "Chứng nhận số" bản 1.1.0 kèm BPMN; AT-14 quét toàn bộ mã lõi được phát hành.
- E2E mốc M2 (`tests/e2e/test_m2_*.py`), `ops/e2e/install_apps.sh` (cài app bằng CLI, bốn mắt), `ops/at13_reuse.sh`,
  overlay `deploy/compose.release.yaml` (image theo digest), image `trust-core` trên GHCR trong workflow `release`,
  `make openapi` và `docs/api/openapi.json`.
- Tài liệu: `docs/manifest-guide.md`, `docs/legal-mapping.md`, `docs/runbook-pii-erasure.md`; mục "Bản chất pháp lý
  của niêm phong" trong README.

### Changed
- `ops/e2e/run_e2e.sh` cài app bằng CLI thay cho `ops/seed_manifests.py`; `seed_manifests.py` chỉ còn dùng cho test lõi.
- Caddy: host công khai trả 404 cho `/admin`; danh sách IP của host quản trị được thực thi.
- `/admin/v1/ledger/status` chỉ còn trạng thái ledger; trạng thái thành phần chuyển sang `/admin/v1/health`.

### Chưa làm trong bản này
- E2E M2, AT-13, AT-18, AT-19, AT-20 trên stack thật và VPS: chờ chạy (danh sách việc ở `docs/evidence/README.md`).

## [0.1.0] - 2026-10-22
Mốc M1. Tag `v0.1.0` gắn trên mã cuối Plan 01 (commit `5b14e7c`) cộng commit `7247fe8` chỉ ghi ngày phát hành; không
nằm trên nhánh `main` (mã M2 đã vào `main` trước khi gắn tag).

### Lỗi đã biết (đã sửa ở 0.2.0)
- Danh sách IP của host quản trị trong Caddy (`@blocked`) không có hiệu lực; ở bản này host quản trị không giới hạn IP.
- E2E đầu-cuối của M1 chưa chạy trọn trên mã của bản này (4/5 trên Docker Desktop); đạt trên mã 0.2.0 đang phát triển
  (commit `ea96323`, 22/10/2026).

### Added
- Khung kho mã: LICENSE (Apache-2.0), NOTICE, REUSE, CI (reuse, ruff, pytest, gitleaks), mẫu issue.
- Thư viện `dxos-proof`: JSON chuẩn hóa (NFC, UTC, cấm số thực) và cây Merkle RFC 6962 (inclusion proof, consistency proof).
- Khung thư mục cho `core/`, `witness/`, `cli/`, `sdk/js/`, `apps/`, `verify-portal/`, `viewer/`, `deploy/`, `ops/`.
- Hạ tầng `deploy/`: Docker Compose với 9 mạng phân vùng theo `network-matrix.yaml`, hồ sơ p16/p8/dev-lite, Caddy (TLS, host quản trị giới hạn IP), APISIX standalone (OIDC bearer, limit-req, request-id), stub `fake-av` chỉ cho dev-lite.
- `ops/netcheck.py` (kiểm ma trận mạng, AT-01) và `ops/pin_images.py` (ghim digest image).
- Realm Keycloak `dxos` (vai trò `dxos-admin`, client `dxos-spa` PKCE S256, `apisix`, `dxos-installer`, scope audience `dxos-api`) và bản dev có người dùng mẫu; `ops/build_dev_realm.py`.
- Khung `dxos-core` (FastAPI): cấu hình `DXOS_*`, lỗi `application/problem+json`, `/healthz` và `/readyz`, worker có heartbeat; migration `001_core.sql` (schema `core`, ledger và STH chỉ-thêm bằng quyền + trigger, trigger niêm phong bản ghi, role `dxos_core` quyền tối thiểu); image `core/Dockerfile` chạy user không phải root.
- Ledger chỉ-thêm (`dxos_core.ledger`): 18 loại sự kiện (spec 12.4), chỉ số liên tục dưới khóa advisory, `actor_ref` là HMAC của `sub`, không lưu body, `verify_log` phát hiện lá bị sửa hoặc bị xóa.
- Identity: kiểm token Keycloak (chỉ RS256, `iss`/`aud`/`exp`/`nbf`, JWKS có cache), vai trò `app:<id>:<role>`, `GET /api/v1/whoami`, lỗi 401/503 dạng problem+json.
- Registry: JSON Schema manifest `dxos/v1`, validator (FLOOR_WEAKENED, NAMESPACE_VIOLATION, UNKNOWN_GUARD, SCHEMA_INVALID), kho manifest; manifest App A, App B và `test-app`.
- PDP theo manifest (admin không mặc nhiên đọc dữ liệu app), che PII (CCCD, SĐT, STK, email, họ tên), ghi `policy.denied`.
- Records API chung: cấp số văn bản, `If-Match`, chống IDOR (404), chặn sửa bản ghi đã niêm phong, NFC, phân trang keyset, nhập hàng loạt theo dòng.
- Tệp: upload → quét ClamAV trước → kiểm PDF (PDFium) → kho theo SHA-256; cách ly tệp nhiễm; hàng đợi việc trên PostgreSQL; worker.
- STH ký ed25519 qua OpenBao transit; `GET /verify/v1/sth/latest`, `/verify/v1/sth/consistency`, `/verify/v1/keys`; `deploy/openbao/init.sh`, policy `dxos-core`, `docs/runbook-openbao.md`.
- Neo STH lên repo git có bảo vệ nhánh (job `anchor_sth`, bảng `anchors`), `POST /admin/v1/anchor:run`, `GET /admin/v1/ledger/status`; CLI `dxos-witness` và mẫu repo neo; `docs/runbook-anchor.md`.
- E2E mốc M1 (`tests/e2e`, `ops/e2e/run_e2e.sh`), `ops/seed_manifests.py` (tạm thời), workflow `release` (tar.gz, SBOM CycloneDX, wheel) và `nightly` (ClamAV thật).

### Changed
- Spec 1.0.2: `so_hieu` có `public: true`; `access.update` mặc định `[owner]`.
