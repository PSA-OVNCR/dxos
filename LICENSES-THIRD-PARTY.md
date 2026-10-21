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

## Gói npm (workspace `web`, Plan 03 Task 2–3)
Phiên bản ghim chính xác trong `package-lock.json` (đếm từ lockfile ngày 22/10/2026 sau Task 3: 119 gói bên thứ ba, gồm cả các gói nhị phân tùy chọn theo nền tảng; chỉ gói của nền tảng đang chạy được cài). Cập nhật bảng **trong cùng commit** khi một Task sau thêm phụ thuộc (Vue, Vue Router, qrcode, @vue/test-utils, Playwright...).

**Runtime (vào bundle trình duyệt):**
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| oidc-client-ts | 3.5.0 | Apache-2.0 | Thư viện (`sdk/js/src/auth.ts`: OIDC Authorization Code + PKCE; ứng dụng tự gói, SDK để ngoài bundle thư viện) | Có (22/10/2026, trường `license` trong `package-lock.json`) |
| jwt-decode (phụ thuộc duy nhất của oidc-client-ts) | 4.0.0 | MIT | Thư viện (gián tiếp) | Có (22/10/2026, lockfile) |

`dxos-sdk-js` (gói của dự án, Apache-2.0) chỉ phụ thuộc runtime vào hai gói trên. Task 5 sẽ thêm `qrcode`, `vue`, `vue-router` vào bảng này.

**Công cụ build/test (chỉ dùng lúc build/test, không vào bundle):**
| Thành phần | Phiên bản | Giấy phép | Cách dùng | Đã kiểm chứng |
|---|---|---|---|---|
| TypeScript | 5.9.3 | Apache-2.0 | Công cụ (kiểm kiểu) | Có (22/10/2026, trường `license` trong `package-lock.json`) |
| vue-tsc | 3.3.12 | MIT | Công cụ (kiểm kiểu `.ts`/`.vue`) | Có (22/10/2026, lockfile) |
| Vite (kèm Rolldown 1.1.5, PostCSS 8.5.31, lightningcss 1.33.0) | 8.1.6 | MIT (Rolldown, PostCSS: MIT; lightningcss: **MPL-2.0**) | Công cụ (build thư viện/ứng dụng) | Có (22/10/2026, lockfile) |
| Vitest | 5.0.3 | MIT | Công cụ (test đơn vị) | Có (22/10/2026, lockfile) |
| jsdom (môi trường DOM giả cho test cần `sessionStorage`/`location`) | 30.1.2 | MIT | Công cụ (test đơn vị; các gói gián tiếp kèm theo đều `dev` trong lockfile) | Có (22/10/2026, lockfile) |

**Gói gián tiếp (theo trường `license` trong lockfile, 22/10/2026; tổng 119 gói, gồm cả các gói trực tiếp ở trên):**
| Giấy phép | Số gói | Ghi chú |
|---|---|---|
| MIT | 90 | `@babel/*`, `@rolldown/*`, `@vue/*`, `@volar/*`, `@asamuzakjp/*`, `jsdom` và phần lớn phụ thuộc của nó (`parse5`, `whatwg-url`, `undici`, `css-tree`, `decimal.js`...), `chai`, `postcss`, `rolldown`, `jwt-decode`... |
| Apache-2.0 | 5 | `typescript`, `detect-libc`, `expect-type`, `oidc-client-ts`, `xml-name-validator` |
| MPL-2.0 | 12 | `lightningcss` và 11 gói nhị phân theo nền tảng của nó (do Vite kéo vào) |
| BSD-2-Clause | 3 | `entities` (hai phiên bản), `webidl-conversions` |
| BSD-3-Clause | 2 | `source-map-js`, `tough-cookie` |
| ISC | 2 | `picocolors`, `saxes` |
| MIT-0 | 2 | `@csstools/color-helpers`, `@csstools/css-syntax-patches-for-csstree` (jsdom kéo vào; chỉ test) |
| BlueOak-1.0.0 | 1 | `lru-cache` (jsdom kéo vào; chỉ test) |
| CC0-1.0 | 1 | `mdn-data` (do `css-tree` của jsdom kéo vào; chỉ test) |
| 0BSD | 1 | `tslib` (tùy chọn) |

- **MPL-2.0 (lightningcss):** chỉ dùng lúc build/test, không vào bundle và không được phân phối kèm kho này; dự án không sửa mã của nó, nên không phát sinh nghĩa vụ chia sẻ mã nguồn. Cùng nhóm với OpenBao (MPL-2.0) ở bảng dịch vụ.
- **BlueOak-1.0.0, MIT-0, CC0-1.0 (đã xuất hiện từ Task 3 do thêm jsdom):** cả bốn gói (`lru-cache`, hai gói `@csstools/*`, `mdn-data`) đều đánh dấu `dev` trong lockfile: chỉ dùng lúc test, không vào bundle và không phân phối. BlueOak-1.0.0 và MIT-0 là giấy phép cho phép (permissive). **CC0-1.0 (`mdn-data`) cần trưởng nhóm xác nhận (V30)**; nếu không chấp nhận, cách gỡ là bỏ jsdom và chạy test auth trong môi trường node với `sessionStorage` giả. Các gói `glob`, `minimatch`, `minipass`, `path-scurry` dự kiến ở bản trước chưa xuất hiện (sẽ kiểm lại khi thêm công cụ test ở Task sau).

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
