# Thành phần bên thứ ba

Bảng kê giấy phép và nguồn gốc mọi mô-đun bên ngoài. Cập nhật **trong cùng commit** khi thêm phụ thuộc.

**Cột "Cách dùng":**
- **Dịch vụ độc lập:** chạy riêng, không nhúng mã, không phân phối kèm kho này.
- **Thư viện:** được import bởi mã của dự án.
- **Công cụ:** chỉ dùng khi phát triển hoặc CI, không phân phối.

**Cột "Đã kiểm chứng":**
- **Chưa:** giấy phép ghi theo hiểu biết, phải kiểm tra tệp LICENSE gốc trước khi phát hành.
- **Có (ngày):** đã đối chiếu.

## Thư viện và công cụ đang dùng
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| Python (thư viện chuẩn) | ≥ 3.12 | PSF-2.0 | Runtime | Chưa |
| pytest | ≥ 8 | MIT | Công cụ (test) | Chưa |
| pytest-asyncio | ≥ 0.24 | Apache-2.0 | Công cụ (test) | Chưa |
| respx | ≥ 0.21 | BSD-3-Clause | Công cụ (test; dùng cho test client Flowable/OpenBao, đã nằm trong `requirements-dev.txt`) | Có (21/10/2026, metadata + `LICENSE.md` của wheel 0.23.1) |
| ruff | ≥ 0.6 | MIT | Công cụ (lint) | Chưa |
| reuse | ≥ 4 | GPL-3.0-or-later | Công cụ (kiểm tra giấy phép, không phân phối) | Chưa |
| PyYAML | ≥ 6 | MIT | Thư viện (`dxos-core`; `dxos-cli`, Plan 02 Task 13, đọc `manifest.yaml` bằng `safe_load`) và công cụ (test) | Chưa |
| httpx | ≥ 0.27 | BSD-3-Clause | Thư viện (`dxos-core`, `dxos-witness`; `dxos-cli`, Plan 02 Task 13, gọi API quản trị và Keycloak) và công cụ (test) | Chưa |
| PyJWT (kèm `cryptography`) | ≥ 2.8 | MIT | Thư viện (`dxos-core`, Task 10) và công cụ (test) | Chưa |
| FastAPI | ≥ 0.115 | MIT | Thư viện (`dxos-core`) | Chưa |
| Starlette (phụ thuộc của FastAPI) | theo FastAPI | BSD-3-Clause | Thư viện | Chưa |
| Pydantic, pydantic-settings | ≥ 2.4 | MIT | Thư viện (`dxos-core`) | Chưa |
| Uvicorn (`[standard]`: uvloop, httptools, websockets, watchfiles, python-dotenv) | ≥ 0.30 | BSD-3-Clause (uvloop: MIT hoặc Apache-2.0; httptools, watchfiles: MIT; websockets, python-dotenv: BSD-3-Clause) | Thư viện (`dxos-core`) | Chưa |
| asyncpg | ≥ 0.29 | Apache-2.0 | Thư viện (`dxos-core`) | Chưa |
| jsonschema | ≥ 4.23 | MIT | Thư viện (`dxos-core`, Task 11) | Chưa |
| boto3 (botocore, s3transfer) | ≥ 1.35 | Apache-2.0 | Thư viện (`dxos-core`, Task 14) | Chưa |
| cryptography | ≥ 43 | Apache-2.0 OR BSD-3-Clause | Thư viện (`dxos-core`) | Chưa |
| pypdfium2 | ≥ 5.14, < 6 | Apache-2.0 OR BSD-3-Clause; wheel **nhúng PDFium** (BSD-3-Clause) kèm ICU (Unicode-3.0), FreeType (FTL hoặc GPL-2.0), libjpeg-turbo (IJG, BSD-3-Clause, Zlib), libpng (libpng-2.0), zlib (Zlib), OpenJPEG (BSD-2-Clause), Little-CMS (MIT), abseil (Apache-2.0), AGG 2.3, fast_float, simdutf, llvm-libc | Thư viện (`dxos-core`, kiểm PDF ở worker); cài lúc build image, không nằm trong kho mã (G4). **Trưởng nhóm đã duyệt 21/10/2026** (ngoại lệ so với danh sách MIT/BSD/Apache/PSF/ISC của Plan 01); bảng chi tiết: `docs/evidence/pypdfium2-giay-phep.md` | Có (20/10/2026, đọc `dist-info/licenses` của wheel 5.14.0) |
| python-multipart | ≥ 0.0.9 | Apache-2.0 | Thư viện (`dxos-core`, nhận multipart upload) | Có (20/10/2026, metadata PyPI) |
| defusedxml | ≥ 0.7, < 1 | PSF-2.0 | Thư viện (`dxos-core`, đọc BPMN không tin cậy, cấm DTD/entity — Plan 02 Task 3) | Có (21/10/2026, wheel 0.7.1: METADATA `License: PSFL`, `dist-info/LICENSE` là "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2") |
| `dxos-cli` (gói của dự án, wheel `cli/`) | 0.1.0 | Apache-2.0 | Công cụ dòng lệnh `dxos`, phân phối kèm bản phát hành; chỉ phụ thuộc httpx và PyYAML ở trên, không thêm dependency mới, không import `dxos-core` | Có (21/10/2026, `cli/pyproject.toml`) |
| pypdf | bất kỳ | BSD-3-Clause | Công cụ (chỉ để sinh `core/tests/fixtures/files/encrypted.pdf`) | Chưa |
| gitleaks (image Docker) | v8.18.4 | MIT | Công cụ (CI) | Chưa |
| syft (image Docker `anchore/syft`) | v1.18.1 | Apache-2.0 | Công cụ (CI, sinh SBOM khi phát hành) | Chưa |
| git, openssh-client (gói Debian trong image trust-core) | theo Debian 12 | GPL-2.0-only; BSD | Chương trình độc lập, worker gọi để đẩy STH (G2) | Chưa |
| tzdata (gói Debian trong image trust-core) | theo image nền | Public domain (IANA tz database) | Chỉ dữ liệu múi giờ, `zoneinfo` đọc cho `DXOS_TIMEZONE` | Chưa |

## Gói npm (workspace `web`, Plan 03 Task 2–5)
Phiên bản ghim chính xác trong `package-lock.json` (đếm từ lockfile ngày 22/10/2026 sau Task 5: **186** gói bên thứ ba, gồm cả các gói nhị phân tùy chọn theo nền tảng; chỉ gói của nền tảng đang chạy được cài. Theo cờ `dev` của lockfile: **55** gói thuộc đồ thị phụ thuộc production (kể cả các gói `peer` mà npm cài kèm) và **131** gói chỉ dùng lúc phát triển). Cập nhật bảng **trong cùng commit** khi một Task sau thêm phụ thuộc (Vue Router...). Task 6 thêm Playwright (3 gói) và npm 11.6.2 bỏ 3 gói tùy chọn `@emnapi/*` khỏi lockfile nên tổng vẫn 186.

**Runtime (vào bundle trình duyệt):**
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| oidc-client-ts | 3.5.0 | Apache-2.0 | Thư viện (`sdk/js/src/auth.ts`: OIDC Authorization Code + PKCE; ứng dụng tự gói, SDK để ngoài bundle thư viện) | Có (22/10/2026, trường `license` trong `package-lock.json`) |
| jwt-decode (phụ thuộc duy nhất của oidc-client-ts) | 4.0.0 | MIT | Thư viện (gián tiếp) | Có (22/10/2026, lockfile) |
| vue | 3.5.43 | MIT | Thư viện (`sdk/js/src/vue/*.vue`; SDK để ngoài bundle thư viện, ứng dụng tự gói). Gói phụ `@vue/runtime-core`, `@vue/runtime-dom`, `@vue/reactivity`, `@vue/shared` cùng 3.5.43 (MIT) vào bundle; `@vue/compiler-*`, `@vue/server-renderer` (MIT) do `vue` kéo vào nhưng chỉ dùng lúc build/test. Một bản duy nhất nhờ `overrides` ở `package.json` gốc | Có (22/10/2026, lockfile) |
| qrcode | 1.5.4 | MIT | Thư viện (`SealQr.vue`: vẽ mã QR đối soát thành SVG, trong trình duyệt; SDK để ngoài bundle thư viện) | Có (22/10/2026, lockfile) |
| dijkstrajs (qrcode kéo vào, vào bundle trình duyệt) | 1.0.3 | MIT | Thư viện (gián tiếp) | Có (22/10/2026, lockfile) |
| pngjs, yargs, yargs-parser, cliui, y18n, wrap-ansi, string-width, strip-ansi, ansi-regex, ansi-styles, color-convert, color-name, emoji-regex, is-fullwidth-code-point, find-up, locate-path, p-locate, p-limit, p-try, path-exists, camelcase, decamelize, get-caller-file, require-directory, require-main-filename, set-blocking, which-module (qrcode kéo vào cho CLI/xuất PNG) | pngjs 5.0.0; yargs 15.4.1; còn lại theo lockfile | MIT (pngjs, yargs, string-width, strip-ansi, ansi-*, color-*, emoji-regex, find-up, locate-path, p-*, path-exists, camelcase, decamelize, require-directory, is-fullwidth-code-point); ISC (yargs-parser, cliui, y18n, get-caller-file, require-main-filename, set-blocking, which-module) | Thư viện (gián tiếp; nằm trong đồ thị production của `qrcode` nhưng không được import ở bản dựng trình duyệt, chỉ `qrcode` + `dijkstrajs` được gói) | Có (22/10/2026, lockfile) |

`dxos-sdk-js` (gói của dự án, Apache-2.0) phụ thuộc runtime vào `oidc-client-ts`, `vue` và `qrcode` (cùng các gói gián tiếp ở trên). `vue-router` sẽ được thêm ở Task sau.

**Công cụ build/test (chỉ dùng lúc build/test, không vào bundle):**
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| TypeScript | 5.9.3 | Apache-2.0 | Công cụ (kiểm kiểu) | Có (22/10/2026, trường `license` trong `package-lock.json`) |
| vue-tsc | 3.3.12 | MIT | Công cụ (kiểm kiểu `.ts`/`.vue`) | Có (22/10/2026, lockfile) |
| Vite (kèm Rolldown 1.1.5, PostCSS 8.5.31, lightningcss 1.33.0) | 8.1.6 | MIT (Rolldown, PostCSS: MIT; lightningcss: **MPL-2.0**) | Công cụ (build thư viện/ứng dụng) | Có (22/10/2026, lockfile) |
| Vitest | 5.0.3 | MIT | Công cụ (test đơn vị) | Có (22/10/2026, lockfile) |
| jsdom (môi trường DOM giả cho test cần `sessionStorage`/`location`) | 29.1.1 | MIT | Công cụ (test đơn vị; ghim 29.1.1 vì 30.x đòi Node >=22.22.2; các gói gián tiếp kèm theo đều `dev` trong lockfile) | Có (22/10/2026, lockfile) |
| @vitejs/plugin-vue | 6.0.9 | MIT | Công cụ (biên dịch `.vue` cho Vite/Vitest) | Có (22/10/2026, lockfile) |
| @vue/test-utils (kéo js-beautify 2.0.3, config-chain, editorconfig, @one-ini/wasm, js-cookie, commander, glob 13, minimatch, minipass, path-scurry, brace-expansion, balanced-match, ini, proto-list, semver, abbrev, nopt, vue-component-type-helpers) | 2.5.1 | MIT (js-beautify, config-chain, editorconfig, @one-ini/wasm, js-cookie, commander, brace-expansion, balanced-match, vue-component-type-helpers: MIT; ini, proto-list, semver, abbrev, nopt: ISC; glob, minimatch, minipass, path-scurry: **BlueOak-1.0.0**) | Công cụ (test thành phần Vue; tất cả đều `dev` trong lockfile). `nopt` bị `overrides` ghim 9.0.0 vì `js-beautify` 2.0.3 đòi nopt 10.0.1, mà nopt 10.0.1 đòi Node >=22.22.2 (môi trường dùng 22.22.0, `engine-strict`); `js-beautify` chỉ dùng hàm định dạng HTML, không dùng phần dòng lệnh của nopt | Có (22/10/2026, lockfile) |
| @playwright/test (kéo playwright, playwright-core) | 1.63.0 | Apache-2.0 | Công cụ (AT-25 trên trình duyệt thật cho `verify-portal/app`, Plan 03 Task 6; `dev` trong lockfile, không vào bundle; trình duyệt Chromium do `npx playwright install` tải, không phân phối kèm kho này) | Có (22/10/2026, lockfile) |
| @types/qrcode (kèm @types/node, undici-types) | 1.5.5 | MIT | Công cụ (kiểu TypeScript cho `qrcode`) | Có (22/10/2026, lockfile) |

**Gói gián tiếp (theo trường `license` trong lockfile, 22/10/2026; tổng 186 gói, gồm cả các gói trực tiếp ở trên):**
| Giấy phép | Số gói | Ghi chú |
|---|---|---|
| MIT | 138 | `@babel/*`, `@rolldown/*`, `@vue/*`, `@vitejs/plugin-vue`, `@volar/*`, `@asamuzakjp/*`, `qrcode` và phụ thuộc của nó, `vue`, `jsdom` và phần lớn phụ thuộc của nó (`parse5`, `whatwg-url`, `undici`, `css-tree`, `decimal.js`...), `@vue/test-utils` và `js-beautify`, `chai`, `postcss`, `rolldown`, `jwt-decode`... |
| Apache-2.0 | 8 | `typescript`, `detect-libc`, `expect-type`, `oidc-client-ts`, `xml-name-validator`, `@playwright/test`, `playwright`, `playwright-core` |
| MPL-2.0 | 12 | `lightningcss` và 11 gói nhị phân theo nền tảng của nó (do Vite kéo vào) |
| BSD-2-Clause | 3 | `entities` (hai phiên bản), `webidl-conversions` |
| BSD-3-Clause | 2 | `source-map-js`, `tough-cookie` |
| ISC | 14 | `picocolors`, `saxes`, `semver`, `ini`, `nopt`, `abbrev`, `proto-list` (test) và `yargs-parser`, `cliui`, `y18n`, `get-caller-file`, `require-main-filename`, `set-blocking`, `which-module` (qrcode) |
| MIT-0 | 2 | `@csstools/color-helpers`, `@csstools/css-syntax-patches-for-csstree` (jsdom kéo vào; chỉ test) |
| BlueOak-1.0.0 | 5 | `lru-cache` (jsdom kéo vào), `glob`, `minimatch`, `minipass`, `path-scurry` (js-beautify của `@vue/test-utils` kéo vào); tất cả chỉ test |
| CC0-1.0 | 1 | `mdn-data` (do `css-tree` của jsdom kéo vào; chỉ test) |
| 0BSD | 1 | `tslib` (tùy chọn) |

- **MPL-2.0 (lightningcss):** chỉ dùng lúc build/test, không vào bundle và không được phân phối kèm kho này; dự án không sửa mã của nó, nên không phát sinh nghĩa vụ chia sẻ mã nguồn. Cùng nhóm với OpenBao (MPL-2.0) ở bảng dịch vụ.
- **BlueOak-1.0.0, MIT-0, CC0-1.0 (BlueOak-1.0.0 và MIT-0 là giấy phép cho phép; xuất hiện từ Task 3 do thêm jsdom, nay thêm `glob`, `minimatch`, `minipass`, `path-scurry` do `@vue/test-utils` ở Task 5):** cả chín gói (`lru-cache`, `glob`, `minimatch`, `minipass`, `path-scurry`, hai gói `@csstools/*`, `mdn-data`) đều đánh dấu `dev` trong lockfile: chỉ dùng lúc test, không vào bundle và không phân phối. **CC0-1.0 (`mdn-data`)** không nằm trong danh sách OSI, nhưng là dữ liệu chỉ dùng lúc test, do `npm ci` tải về, không có trong kho mã và không vào bundle; theo giải đáp G4 của BTC, chỉ thứ nhúng vào kho mã mới phải tương thích OSI. Trưởng nhóm duyệt ngày 23/10/2026 (V30).

## Ngoại lệ đã duyệt
`make licenses` (`ops/license_scan.py`, job `licenses` của CI, Plan 04 Task 1) chỉ cho qua giấy phép **MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, PSF-2.0, ISC** (biểu thức `OR` đạt khi một nhánh đạt, `AND` đạt khi mọi nhánh đạt). Gói nào khác phải có tên trong bảng dưới đây; **máy quét đọc đúng bảng này**, nên thêm một dòng là trưởng nhóm đã duyệt gói đó.
- Hệ `python`: miễn theo tên gói. **Phạm vi quét Python là bao đóng phụ thuộc runtime của bốn gói `dxos-*`** (đúng thứ nằm trong image và trên máy người dùng), còn công cụ phát triển như `reuse` (GPL-3.0-or-later) nằm ngoài phạm vi.
- Hệ `npm`: miễn theo tên gói **và** đúng giấy phép ghi trong bảng, chỉ cho mục `dev` của `package-lock.json` (chỉ build/test, không vào bundle). Gói chạy thật phải thuộc danh sách cho phép; đổi giấy phép của một gói đã duyệt là phải duyệt lại.

| Hệ | Gói | Giấy phép | Phạm vi | Lý do |
|---|---|---|---|---|
| python | `pypdfium2` | Giấy phép ghép (BSD-3-Clause hoặc Apache-2.0, kèm PDFium và các thành phần nhúng) | runtime | Trưởng nhóm đã duyệt 21/10/2026; bảng chi tiết ở `docs/evidence/pypdfium2-giay-phep.md` |
| npm | `lightningcss` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-android-arm64` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-darwin-arm64` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-darwin-x64` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-freebsd-x64` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-linux-arm-gnueabihf` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-linux-arm64-gnu` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-linux-arm64-musl` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-linux-x64-gnu` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-linux-x64-musl` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-win32-arm64-msvc` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `lightningcss-win32-x64-msvc` | MPL-2.0 | dev | build/test, không vào bundle, không sửa mã (V30) |
| npm | `glob` | BlueOak-1.0.0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `lru-cache` | BlueOak-1.0.0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `minimatch` | BlueOak-1.0.0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `minipass` | BlueOak-1.0.0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `path-scurry` | BlueOak-1.0.0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `@csstools/color-helpers` | MIT-0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `@csstools/css-syntax-patches-for-csstree` | MIT-0 | dev | giấy phép cho phép; chỉ test (V30) |
| npm | `mdn-data` | CC0-1.0 | dev | chỉ test, không trong kho mã, không vào bundle (G4); trưởng nhóm duyệt 23/10/2026 (V30) |
| python | `certifi` | MPL-2.0 | runtime (httpx kéo vào; chỉ chứa gói chứng chỉ CA, dùng nguyên bản, không sửa mã) | Trưởng nhóm duyệt 23/10/2026 (V30). MPL-2.0 là giấy phép OSI, copyleft theo từng tệp; dùng nguyên bản, không sửa, không chép vào kho mã nên tương thích Apache-2.0 (MPL-2.0 mục 3.3); cùng nhóm với lightningcss và OpenBao |
| python | `cffi` | MIT-0 | runtime (cryptography kéo vào) | MIT-0 là giấy phép OSI, cho phép hơn MIT; điều phối viên duyệt 23/10/2026 |
| npm | `tslib` | 0BSD | dev (tùy chọn) | 0BSD là giấy phép OSI, cho phép hơn MIT; chỉ build/test; điều phối viên duyệt 23/10/2026 |

## Dịch vụ (image Docker, chạy độc lập, không nhúng mã)
Digest được ghim trong `deploy/` bằng `make pin-images`; cột "Digest" cập nhật cùng commit ghim.

| Thành phần | Image | Giấy phép | Cách dùng | Digest | Đã kiểm chứng |
|---|---|---|---|---|---|
| Caddy | `caddy:2.10` | Apache-2.0 | Dịch vụ độc lập | `sha256:c3d7ee5d2b11f9dc54f947f68a734c84e9c9666c92c88a7f30b9cba5da182adb` | Chưa |
| Apache APISIX | `apache/apisix:3.12.0-debian` | Apache-2.0 | Dịch vụ độc lập | `sha256:83e70a2a1aff751c17cbf7f876e53fd37fbfcd4f0bc13748effc2cd8c86802ab` | Chưa |
| Keycloak | `quay.io/keycloak/keycloak:26.3` | Apache-2.0 | Dịch vụ độc lập | `sha256:357829ec7c4693397533035092ad13b0644bcc95ded311f33a3738c4d9e9bdba` | Chưa |
| Flowable REST | `flowable/flowable-rest:7.1.0` | Apache-2.0 | Dịch vụ độc lập (spike Task 6 xác nhận image OSS) | `sha256:b7ae287502cd5c243b577a0ca2894172e1c18cd75aea4fd67dc7d58f1b40db44` | Chưa |
| PostgreSQL | `postgres:17-alpine` | PostgreSQL | Dịch vụ độc lập (core-db, kc-db, flowable-db) | `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24` | Chưa |
| SeaweedFS | `chrislusf/seaweedfs:3.80` | Apache-2.0 | Dịch vụ độc lập | `sha256:1055999e08eed1789b0ae45d235126e4495e23d3fb9d6396293fd42539b1ae6a` | Chưa |
| ClamAV | `clamav/clamav:1.4` | GPL-2.0-only | Dịch vụ độc lập, nói chuyện qua socket clamd (G2) | `sha256:3bba6dd5ac6663d55b80f86a3126e146612d93b593cc2617188d13f637d91260` | Chưa |
| OpenBao | `openbao/openbao:2.2.0` | MPL-2.0 | Dịch vụ độc lập | `sha256:19612d67a4a95d05a7b77c6ebc6c2ac5dac67a8712d8df2e4c31ad28bee7edaa` | Chưa |
| BusyBox | `busybox:1.37` | GPL-2.0-only | Công cụ (probe mạng, AT-01) | `sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e` | Chưa |
| Python | `python:3.12-slim` | PSF-2.0 (+ Debian) | Image nền: `core/Dockerfile` (trust-core-api, trust-core-worker), `fake-av` | `sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1` | Chưa |

## Image của dự án (phát hành trên GHCR)
Image do workflow `release` build từ `core/Dockerfile` ở commit của tag và đẩy lên GHCR (Plan 02 Task 15). Image nền và
gói bên trong đã liệt kê ở hai bảng trên (Python `python:3.12-slim`, git, openssh-client, tzdata, các thư viện của
`dxos-core`, pypdfium2). Digest lấy từ trang GitHub Release của tag; cập nhật cột "Digest" trong cùng commit ghi nhận
bản phát hành.

| Thành phần | Image | Giấy phép | Cách dùng | Digest |
|---|---|---|---|---|
| trust-core (`trust-core-api`, `trust-core-worker`) | `ghcr.io/psa-ovncr/trust-core:0.2.0` | Apache-2.0 (mã của dự án) | Chạy trên máy chủ theo digest qua `deploy/compose.release.yaml` (AT-13) | Chưa phát hành: chưa có tag `v0.2.0` |
