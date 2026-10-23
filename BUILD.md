# Hướng dẫn build từ mã nguồn

> Tài liệu này được cập nhật theo từng mốc (bản này: M3, Plan 03). Phần web (Node) ở các mục "Công cụ web" và "Dựng SPA Tầng 2" bên dưới; những bước chưa chạy trên máy thật được đánh dấu rõ.

## Yêu cầu
| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | ≥ 3.12 | CI chạy 3.12 |
| GNU Make | bất kỳ | |
| Git | bất kỳ | |
| Docker + Docker Compose v2 (≥ 2.24) | Docker Desktop hoặc Docker Engine | Cần cho `make up`; Windows nên chạy lệnh trong WSL2 |
| Node.js 22 LTS | `>=22 <23` (CI dùng 22; đã thử 22.22.0) | Cần cho SDK, cổng đối soát và ứng dụng Tầng 2; không cần để chạy lõi hay `make check` |
| npm | **đúng 11.6.2** (`npm@11.6.2`) | npm 10.9 (đi kèm Node 22) không cài được bộ phụ thuộc này; `engine-strict` bật nên phiên bản khác bị từ chối |

Toàn bộ công cụ build đều là phần mềm nguồn mở.

## Build và kiểm thử phần đã có
```bash
git clone <địa-chỉ-repo> dxos && cd dxos
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
make dev-install
make check
```
Kết quả mong đợi: `ruff` không báo lỗi; `reuse lint` in dòng `Congratulations!`; toàn bộ test đơn vị đạt.

Integration test của `core/` (cần PostgreSQL; mỗi test tự tạo rồi xóa một database riêng):
```bash
make test-db-up            # PostgreSQL :55432, SeaweedFS :58333, OpenBao dev :58200 (deploy/compose.test.yaml)
make test-integration
```
Dùng PostgreSQL có sẵn: đặt `DXOS_TEST_OWNER_DSN=postgresql://<role có quyền tạo DB>:<mật khẩu>@<host>:<cổng>/<db>`.

## Công cụ web (SDK, cổng đối soát, App A và B)
Mã web nằm trong một npm workspace ở thư mục gốc (`package.json`: `sdk/js`, `verify-portal/app`, `apps/phong-ho-so/web`,
`apps/chung-nhan/web`, `examples/so-muon-sach/web`). Cần Node.js 22 và `npm@11.6.2`; `.npmrc` bật `engine-strict` nên Node
hoặc npm sai phiên bản thì `npm ci` dừng ngay:
```bash
node --version                       # v22.x
npm install -g npm@11.6.2            # nếu npm --version khác 11.6.2
npm ci                               # cài đúng theo package-lock.json (không dùng npm install)
make web-check                       # = npm run check: typecheck + test + build của mọi workspace
```
`make web-check` không cần Docker hay mạng sau `npm ci`; kết quả mong đợi là mã thoát 0. Chạy một workspace:
`npm run test -w dxos-sdk-js` (đổi tên gói cho workspace khác), `npm run typecheck -w dxos-verify-portal`.

Phiên bản ghim chính xác (không `^`, `~`; `tests/repo/test_web_hygiene.py` kiểm). Hai ghi chú vì Node 22.22.0:
- `jsdom` ghim **29.1.1**: jsdom 30.x đòi Node `>=22.22.2`.
- `overrides` trong `package.json` gốc: `@vue/*` ghim 3.5.43 (cho `vue-tsc` không kéo bản 3.5.44) và `nopt` 9.0.0 (cho
  `js-beautify` của `@vue/test-utils`, vì nopt 10.0.1 đòi Node `>=22.22.2`). Nâng Vue hay Node thì rà lại các `overrides` này.
Công cụ chỉ dùng lúc build/test (Vite, Vitest, jsdom, Playwright...) và giấy phép của chúng: `LICENSES-THIRD-PARTY.md`.

Test trình duyệt của cổng đối soát (AT-25) dùng Playwright với API giả: `npx playwright install --with-deps chromium`
rồi `npx -w dxos-verify-portal playwright test` (đây là bước của job `web` trong CI). Bộ Playwright "live" trên stack thật
là bộ khác, xem mục "Dựng SPA Tầng 2".

## Cấu hình
Mọi cấu hình đặt qua biến môi trường (xem `.env.example`). Không cần sửa mã nguồn để cấu hình.

## Chạy toàn bộ hệ thống
```bash
cp .env.example .env          # giá trị mẫu chạy được trên localhost; đổi mật khẩu khi lên VPS
make pin-images               # lần đầu: ghim digest image (cần mạng tới Docker Hub, quay.io)
make up PROFILE=dev-lite      # laptop; máy 8 GB dùng PROFILE=p8; máy chủ dùng p16 (mặc định)
make ps                       # chờ các container "healthy"
make netcheck                 # kiểm ma trận mạng (AT-01): mọi dòng phải PASS
make test-infra               # test sống: AT-01, AT-02 phía gateway
```

Không có `make` (Windows thuần): thay `make up PROFILE=dev-lite` bằng
`docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.dev-lite.yaml up -d --build`
và `make netcheck` bằng `python ops/netcheck.py`.

| Hồ sơ | Dùng khi | Khác biệt |
|---|---|---|
| `p16` | máy chủ 16 GB | heap JVM 1 GB, ClamAV mặc định |
| `p8` | máy 8 GB, laptop demo dự phòng | heap 512 MB, ClamAV 1 luồng, không nạp chữ ký song song |
| `dev-lite` | phát triển trên laptop | **ClamAV thay bằng `fake-av` (chỉ nhận EICAR)**; không dùng để nghiệm thu |

Người dùng dev (chỉ hồ sơ dev-lite, mật khẩu `dev-only-password`): `chuyen_vien1`, `chuyen_vien_tp1` (chuyên viên kiêm trưởng phòng, cho AT-07), `truong_phong1`, `giam_doc1`, `van_thu1`, `nhan_vien1`, `can_bo_clb1`, `truong_clb1`, `owner_a1`, `owner_b1`, `admin1`, `admin2` (admin thứ hai để duyệt app theo bốn mắt).
Realm chỉ được nạp lần đầu (`--import-realm` bỏ qua realm đã có). Stack đã chạy từ trước thì sau mỗi lần kéo mã mới chạy
`python ops/keycloak_upgrade.py` (p8/p16) hoặc `python ops/keycloak_upgrade.py --profile dev-lite`: script idempotent, thêm
client `dxos-cli`, quyền `manage-realm` cho service account `dxos-installer`, người dùng dev còn thiếu; mã thoát 2 nghĩa là
còn lệch phải xử lý tay (đã in ra). Muốn nạp lại từ đầu thì xóa volume `dxos_kc-db-data`.

`trust-core-api` tự chạy migration khi khởi động (role `dxos_owner`) rồi mới phục vụ bằng role `dxos_core`. Đã có `.env` từ trước Task 8 thì thêm 2 dòng `DXOS_ACTOR_HMAC_KEY` và `OPENBAO_CORE_TOKEN` từ `.env.example`.

Truy cập: `https://localhost/auth/` (Keycloak), `https://localhost/api/v1/...` (qua APISIX).
Trình duyệt sẽ cảnh báo chứng chỉ vì Caddy dùng CA nội bộ cho `localhost`.

## Cấu hình niêm phong, tổ chức và cài app (Plan 02)
Đặt trong `.env` (mẫu và chú thích ở `.env.example`); `trust-core-api` và `trust-core-worker` đọc khi khởi động.

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `DXOS_ORG_NAME` | Tên tổ chức vận hành, ghi **vĩnh viễn** vào tuyên bố khóa `seal-key` ở lần niêm phong đầu (bảng chỉ-thêm, đã neo). Rỗng, giá trị mặc định của lõi hoặc bắt đầu bằng `changeme` thì lõi **không niêm phong**: task cuối trả 503 `org-not-configured`, bản ghi đã duyệt nằm ở `SEAL_PENDING`, và `dxos health` báo `org: down: not configured` | rỗng (= chưa đặt) |
| `DXOS_ORG_ID` | Mã định danh tổ chức (ví dụ mã số doanh nghiệp), vào tuyên bố khóa; rỗng = `null` | rỗng |
| `DXOS_SEAL_KEY_VALIDITY_DAYS` | Thời hạn tuyên bố khóa, 1..3650 ngày (khung tham khảo: NĐ 23/2025 Điều 7 khoản 4). Hết hạn thì niêm phong bị từ chối (503 `seal-key-expired`) cho tới khi xoay khóa | 3650 |
| `DXOS_SEAL_PURPOSE` | Mục đích của khóa, vào tuyên bố khóa; rỗng = câu mặc định của lõi | rỗng |
| `DXOS_KEY_POLICY_URL` | URL chính sách khóa công khai; rỗng = `null` | rỗng |
| `DXOS_TIMEZONE` | Múi giờ IANA tính năm cho số văn bản đánh lại theo năm (`reset: yearly`) | `Asia/Ho_Chi_Minh` |
| `DXOS_ALLOW_SELF_APPROVAL` | `true` cho phép một admin tự duyệt app mình nộp. **Chỉ** cho demo một người; không bật khi lấy minh chứng | `false` |
| `DXOS_INSTALLER_CLIENT_SECRET` | Secret của client `dxos-installer` (service account tạo realm role `app:<id>:<role>` khi duyệt app). Phải trùng giá trị Keycloak đã nạp lúc tạo realm; đổi `.env` không xoay secret trong Keycloak | `changeme-installer` |
| `DXOS_TRUST_CORE_DIGEST` | Digest image `trust-core` đã phát hành (64 hex), chỉ dùng với `deploy/compose.release.yaml` | không có |
| `DXOS_VIEWER_DIGEST` | Digest image `viewer` đã phát hành (64 hex), chỉ dùng với `deploy/compose.release.yaml` khi hồ sơ `viewer` bật (Plan 04 Task 15) | không có |
| `COMPOSE_PROFILES` | `viewer` bật dịch vụ Viewer (chỉ hồ sơ p16; p8 và dev-lite bỏ qua). Xóa dòng hoặc để trống để tắt | `viewer` trong `.env.example` |
| `DXOS_ADMIN_HOST` | Host của trang quản trị (`/ui/`) và API quản trị; Caddy phục vụ site quản trị ở host này, Keycloak đặt redirect của client `dxos-admin-ui` theo nó (Plan 04 Task 9) | `admin.localhost` |

Đặt tên tổ chức **trước** lần niêm phong đầu: tên đã vào tuyên bố khóa thì không sửa được. Tổ chức hư cấu của demo
theo spec là "Công ty TNHH Sao Mai"; tên dùng trên VPS do trưởng nhóm quyết định.

Flowable phải giữ history level từ `audit` trở lên (mặc định của Flowable; compose không đổi): lõi đọc lịch sử task và
biến của Flowable để đối soát lần hoàn thành task bị gián đoạn. Hạ xuống `activity` hoặc `none` làm đối soát báo
`workflow-inconsistent`.

## Chạy bằng image đã phát hành (máy chủ)
Máy chủ không build `trust-core` từ mã nguồn: dùng image trên GHCR theo digest ghi ở trang GitHub Release của tag.
```bash
# .env: DXOS_TRUST_CORE_DIGEST=<64 hex từ trang Release>
docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.p16.yaml \
  -f deploy/compose.anchor.yaml -f deploy/compose.release.yaml up -d
docker inspect -f '{{.Config.Image}}' dxos-trust-core-api-1   # phải là ghcr.io/psa-ovncr/trust-core@sha256:<digest>
```
Viewer (hồ sơ p16 có `COMPOSE_PROFILES=viewer`) cũng chạy image đã phát hành, không dựng trên máy chủ: đặt thêm
`DXOS_VIEWER_DIGEST=<64 hex từ trang Release>` (tệp `viewer-image-X.Y.Z.txt`); `ops/deploy.sh` tự đọc cả hai digest.
Thiếu digest Viewer mà hồ sơ bật nó thì `deploy.sh` thoát 3 trước khi gọi compose.
Không dùng `make up` ở chế độ này (`make up` build từ mã nguồn).

## Cài ứng dụng bằng CLI
Ứng dụng được cài qua installer bằng CLI `dxos`, một admin nộp, một admin **khác** duyệt (bốn mắt):
```bash
dxos login --server https://admin.<miền>                 # mỗi admin trên máy của mình
DXOS_SERVER=https://admin.<miền> sh ops/e2e/install_apps.sh apps/phong-ho-so   # admin A: nộp, in lệnh duyệt
dxos --server https://admin.<miền> app approve phong-ho-so 1.1.0              # admin B
```
Chi tiết manifest, guard, BPMN, luật nâng phiên bản: [docs/manifest-guide.md](docs/manifest-guide.md).
`ops/seed_manifests.py` ghi thẳng manifest vào DB, bỏ qua installer: **chỉ dùng cho test lõi**.

## E2E (stack dev-lite đang chạy)
> E2E dùng client `dxos-test` và người dùng dev có mật khẩu đã biết, chỉ có ở realm dev. Chạy trên VPS (kể cả bước
> e2e của AT-13) cần thêm tạm chúng vào realm production: quyết định của trưởng nhóm; lệnh thêm và gỡ ở
> `docs/evidence/README.md`, mục "Người dùng dev tạm trên VPS".

1. `.env`: đặt `DXOS_ORG_NAME` thật (ví dụ `Công ty TNHH Sao Mai`), rồi
   `docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.dev-lite.yaml -f deploy/compose.e2e.yaml up -d --build`
2. Init và unseal OpenBao, chạy `init.sh`, ghi `OPENBAO_CORE_TOKEN` (`docs/runbook-openbao.md`).
3. Stack có từ trước: `python ops/keycloak_upgrade.py --profile dev-lite` (thêm `admin2`, `chuyen_vien_tp1`, client `dxos-cli`).
4. Lấy CA của Caddy: `docker compose -p dxos cp caddy:/data/caddy/pki/authorities/local/root.crt <thư mục kết quả>/caddy-root.crt`.
5. Chạy `ops/e2e/run_e2e.sh` trong container `python:3.12-slim` (lệnh `docker run` ở đầu tệp, thêm
   `-e DXOS_ORG_NAME="<như .env>"`). Script cài App A, App B bằng CLI (`ops/e2e/install_apps.sh`: admin1 nộp, admin2
   duyệt) rồi chạy cả E2E M1 và M2; kết quả ở `<thư mục kết quả>/e2e-junit.xml`.
6. AT-20 (khóa OpenBao) cần `docker` nên chạy trên máy chủ, ngoài container: xem đầu tệp `tests/e2e/test_m2_attacks.py`.

## Dữ liệu demo hư cấu (`make demo-seed`)
Nạp sẵn dữ liệu cho buổi demo vào stack dev đang chạy (cùng điều kiện với E2E: realm dev, App A và App B đã cài):
```bash
make demo-seed ARGS="--only a"                    # trước buổi demo: chỉ App A (https://localhost)
make demo-seed ARGS="--only b"                    # sau khi cài và duyệt App B trên sân khấu
make demo-seed                                    # diễn tập: cả hai; App B chưa cài thì bỏ qua (mã 0)
make demo-seed ARGS="--only a --ca-file <caddy-root.crt>"   # nếu Python chưa tin CA của Caddy (hoặc đặt SSL_CERT_FILE)
```
Kịch bản demo cài App B ngay trên sân khấu; nạp App B trước thì bước cài thành no-op (`install_apps.sh` bỏ qua bản đang hoạt
động), nên diễn thật phải nạp A trước và `--only b` sau (`demo/README.md`, "Thứ tự khi diễn thật"). Địa chỉ `localhost` không đi
qua `HTTP(S)_PROXY` của môi trường; địa chỉ khác (cần `--allow-remote`) vẫn theo biến đó.
Tạo 3 văn bản "Công ty TNHH Sao Mai" kèm PDF có CCCD, số điện thoại hư cấu (App A) và 12 chứng nhận "Sự kiện CLB" từ
`demo/su-kien-clb.csv` (App B), toàn bộ qua API thật. Mọi dữ liệu là **hư cấu** và có tên bắt đầu bằng `[DEMO] `. Chạy lại
không tạo trùng. Seed không duyệt, không niêm phong: trạng thái từng mục (nháp, chờ duyệt) ở `demo/README.md`. Mật khẩu dev
chỉ qua biến `DXOS_E2E_PASSWORD` (mặc định `dev-only-password`), không có tham số dòng lệnh cho mật khẩu; khác `localhost`
phải thêm `--allow-remote`. Chạy thật trên laptop là việc V44.

## Dựng SPA Tầng 2 và kiểm trên trình duyệt thật
Bốn SPA (App A `/apps/phong-ho-so/`, App B `/apps/chung-nhan/`, cổng đối soát `/apps/verify/` và ví dụ của hướng dẫn 30 phút `/apps/so-muon-sach/`) nằm trong volume `apps-static`
(`dxos_apps-static`, Caddy mount chỉ đọc ở `/srv/apps`). Stack không có dịch vụ build; `make web-build` chạy MỘT
container Node dùng một lần (image ghim digest ở đầu `ops/web_build_docker.sh`, ghim bằng `make pin-images`).

> **Đã ghim, đã chạy trên máy Windows.** `NODE_IMAGE` (`ops/web_build_docker.sh`) và `PLAYWRIGHT_IMAGE` (`ops/web_live.sh`) đã ghim
> digest ngày 22/10/2026 bằng `make pin-images` trên máy trưởng nhóm (V35; nếu digest bị xóa, hai script thoát mã 3 cho tới khi
> ghim lại). Cùng ngày, trên máy đó (Git Bash + Docker Desktop), `bash ops/web_build_docker.sh` thoát 0 và `bash ops/web_live.sh`
> cho 10 passed (V27, `docs/progress/2026-10-22-web-live.md`). Chưa chạy trên Linux hay VPS. `make web-check` và
> `sh ops/build_web.sh <thư mục>` (Node 22, npm 11.6.2) không cần Docker.


```bash
make up                 # lần đầu: tạo volume apps-static
make web-build          # npm ci + npm run build --workspaces, chép dist vào volume, ghi BUILD-INFO.json
```
- `ops/build_web.sh <out_dir>` dựng vào `<out_dir>.tmp` rồi mới thay `<out_dir>`: build lỗi thì thoát khác 0 và bản đang
  chạy còn nguyên. Danh sách thư mục chép cố định ở đầu tệp. Chạy trực tiếp không cần Docker: `sh ops/build_web.sh /tmp/apps`
  (cần Node 22, npm 11.6.2; mã commit lấy từ git hoặc `DXOS_BUILD_COMMIT`).
  Script từ chối (mã 2) `<out_dir>` có thành phần `.` hoặc `..` (trừ `.` trần), là `/`, repo, thư mục cha của repo, `$HOME`,
  một tệp, thư mục không đọc được, hay thư mục không rỗng không có `BUILD-INFO.json`, vì bước thay xóa nội dung cũ.
  `make web-build` không chép tệp `.env*`, `.secrets/`, `deploy/release.env` vào container Node.
- Cổng đối soát tự đối chiếu repo neo khi build có `VITE_ANCHOR_RAW_BASE` (môi trường hoặc `.env`) và `.env` có
  `DXOS_ANCHOR_RAW_ORIGIN` khớp (CSP của Caddy); để trống thì cổng nói rõ là chưa đối chiếu repo neo.
- Header cho `/apps/*`: CSP `default-src 'self'` (không `unsafe-inline`), `nosniff`, `Referrer-Policy: no-referrer`;
  HTML `no-cache`, `assets/` cache một năm (`immutable`). `/apps/verify/` và `/apps/verify-lite/` giữ CSP chặt hơn của riêng chúng.

Kiểm trên Chromium thật (`tests/web/live`: App A đủ vòng đời, App B nhập CSV và duyệt lô, cổng đối soát), cần Docker và
stack dev-lite đang chạy cùng overlay e2e, App A/B đã cài (xem mục E2E), đã `make web-build`:
```bash
make web-live           # container mcr.microsoft.com/playwright (ghim digest ở đầu ops/web_live.sh)
```
Kết quả ở `test-results/web-live/` (`web-live-junit.xml`, `shots/*.png`, `artifacts/`). Bộ này chỉ chạy khi
`DXOS_WEB_LIVE=1` (script tự đặt); `npm run test:live` ngoài container thì bỏ qua mọi test, `npm run typecheck:live` kiểm
kiểu. Chromium không tắt kiểm chứng chỉ: `ops/web_live.sh` cần `openssl`, tính SPKI của CA gốc và CA trung gian Caddy rồi truyền `DXOS_CADDY_SPKI` (cấu hình Playwright dừng với lỗi rõ nếu thiếu biến khi chạy thật). Mật khẩu người dùng dev đọc từ `DXOS_E2E_PASSWORD` (mặc định `dev-only-password`, chỉ có ở realm dev). Lệnh cho
Windows: `docs/evidence/README.md`, mục "Kiểm trình duyệt thật (V27)".

## Tài liệu API (OpenAPI)
`docs/api/openapi.json` sinh từ ứng dụng FastAPI, không cần dịch vụ nào: `make openapi`. Test
`tests/ops/test_openapi.py` đỏ nếu tệp đã commit khác bản sinh lại, nên sau khi đổi route hay đổi phiên bản gói thì chạy
`make openapi` rồi commit.

## CLI quản trị `dxos`
`make dev-install` cài sẵn `dxos-cli` ở chế độ editable (lệnh `dxos`); wheel riêng, chỉ cần `httpx` và `PyYAML`, không import `dxos-core`.
Build wheel: `python -m pip install build && python -m build --wheel --outdir dist cli`.
Test (không cần dịch vụ, dùng respx): `python -m pytest cli -q`. Cách dùng: `cli/README.md`.

## Phát hành
Chỉ trưởng nhóm gắn tag (hành động công khai). Trước khi gắn tag `vX.Y.Z` (thứ tự: `v0.2.0`, `v0.3.0`, rồi `v0.9.0`):
1. Đổi phiên bản trong `libs/dxos-proof/pyproject.toml`, `core/pyproject.toml`, `witness/pyproject.toml`,
   `cli/pyproject.toml`, `viewer/pyproject.toml` và `__version__` của `core/src/dxos_core/__init__.py`,
   `witness/src/dxos_witness/__init__.py`, `cli/src/dxos_cli/__init__.py`, `viewer/src/dxos_viewer/__init__.py`; chạy
   `make openapi`. Các gói web (`package.json` gốc, `sdk/js`, `verify-portal/app`, `apps/*/web`, `examples/*/web`,
   `admin-ui`) và `package-lock.json` cùng số phiên bản (từ `0.9.0`; bản kiểm của workflow không đọc chúng, nhưng
   `tests/repo/test_docs_m4.py` bắt buộc khớp). `make release-check VERSION=X.Y.Z` kiểm 5 gói Python (kể cả `viewer`).
2. Đổi tiêu đề `## [X.Y.Z] - Chưa phát hành` trong `CHANGELOG.md` thành `## [X.Y.Z] - YYYY-MM-DD`.
3. `make check`, commit, rồi `git tag -a vX.Y.Z -m "…"` và `git push origin vX.Y.Z`.

Workflow `release` dừng ngay nếu phiên bản gói (5 gói Python) khác tag hoặc mục CHANGELOG chưa có ngày. Nếu đạt, nó build
image `trust-core` và image `viewer` từ commit của tag, đẩy lên `ghcr.io/psa-ovncr/trust-core:X.Y.Z` và
`ghcr.io/psa-ovncr/viewer:X.Y.Z` (bằng `GITHUB_TOKEN`, hai job riêng), rồi tạo Release đính kèm `dxos-X.Y.Z.tar.gz`,
`sbom-X.Y.Z.cdx.json`, `trust-core-image-X.Y.Z.txt`, `viewer-image-X.Y.Z.txt`, `dxos-web-X.Y.Z.tar.gz` (các SPA do
`ops/build_web.sh` dựng) và wheel của `dxos-proof`, `dxos-core`, `dxos-witness`, `dxos-cli`, `dxos-viewer`; hai digest
image ghi trong mô tả Release. Sau lần đẩy image Viewer đầu tiên, package `viewer` trên GHCR cũng phải đặt công khai (V19).

Triển khai lên VPS theo tag: `ops/deploy.sh vX.Y.Z` (`docs/runbook-deploy.md`).
