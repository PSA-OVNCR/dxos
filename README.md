# DX-OS Trust Core

**Nền tảng lõi headless (Tầng 1) cho mô hình DX-OS Open-Core**: ứng dụng cắm vào được cung cấp SSO, lưu trữ, workflow, đồng thời **bị bắt buộc tuân thủ** các chính sách tin cậy. Mọi kết quả quan trọng đều **kiểm chứng được độc lập**.

Dự án dự thi **Olympic Tin học Sinh viên Việt Nam – Phần mềm nguồn mở 2026**, chủ đề *DX-OS Open-Core*.

> English version: [README_EN.md](README_EN.md)

## Trạng thái v0.9.0
**Mã đã xong ở cloud; chưa gắn tag** (trưởng nhóm gắn tag ký sau `v0.2.0` và `v0.3.0`). Mốc M4 gồm bốn việc SHOULD, đã qua test
đơn vị, integration và Vitest/jsdom, **chưa việc nào chạy thật** ngoài cloud:
- **S1, dò dữ liệu cá nhân trong PDF**: bộ dò CCCD, số điện thoại, số tài khoản trên lớp chữ (heuristic, không OCR), bản che chỉ chứa
  ảnh, bản gốc chỉ cho người có quyền `reveal_pii`; App A hiện số phát hiện và nút tải bản che. Chạy thật: V39 (Chromium), V44 (dữ liệu demo).
- **S2, Viewer**: dịch vụ xem từng trang PDF thành ảnh có watermark, chỉ RAM, chỉ ở hồ sơ p16. Watermark **chỉ để răn đe**, không ngăn
  được chụp màn hình. Chạy thật trong container: V40.
- **S3, trang quản trị web** `/ui/` trên host quản trị: sức khỏe, sổ cái, duyệt app bằng hai quản trị viên, tệp bị cách ly. Chạy thật với Keycloak: V41.
- **S4, vận hành**: `ops/deploy.sh` chỉ triển khai tag đã ký và tự quay lui khi health hỏng, trừ khi bản mới thêm migration (khi đó dừng và
  hướng dẫn khôi phục từ bản sao lưu hoặc sửa tiếp; V42), sao lưu mã hóa và diễn tập khôi phục
  AT-21 (V43). Viewer cũng được phát hành thành image theo digest như `trust-core`.
- Chỗ trống PoF: ghim phụ thuộc và quét giấy phép (V37), kiến trúc và trang tài liệu (V38, chưa bật), `make demo-seed` (V44).

**Thay đổi phá vỡ của SDK**: `client.download` đổi thành `client.downloadObject(sha256, variant)`; xem [CHANGELOG.md](CHANGELOG.md).
Mọi việc cần máy thật hay trưởng nhóm (V37 đến V44) và các quyết định (các ruling R trong mục 14.6): `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 14.
Từ v0.3.0 vẫn còn: `ops/deploy.sh` trên VPS (V29), biên nhận OpenTimestamps (V32), AT-26 (V31).

## Trạng thái v0.3.0
**Đã chạy trên stack dev (Docker Desktop, máy trưởng nhóm, 22/10/2026)**: `make web-build`, bộ Playwright trên trình duyệt thật 10/10 (V27),
bảng thử vượt rào 10/10 (V28), AT-20 (V36); xem `docs/progress/2026-10-22-web-live.md`. SDK, giao diện App A và App B, cổng đối soát Vue,
triển khai theo tag và hướng dẫn 30 phút nằm trong bản này. **Chưa chạy**: `ops/deploy.sh` trên VPS (V29), biên nhận OpenTimestamps (V32).
Danh sách việc: `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 13.

## Trạng thái v0.2.0
v0.2.0 (mốc M2: workflow, niêm phong, đối soát, installer) và v0.1.0 **đã gắn tag** (V18, 23/10; workflow `release` đã dựng Release và
image `trust-core`). E2E M2 đã đạt 13/13 trên Docker Desktop (22/10, AT-20 bỏ qua); phần chạy trên VPS (AT-13, AT-18, AT-19, AT-20)
chưa có. Tiến độ: `docs/progress/`.

## Thành phần
| Thành phần | Trạng thái |
|---|---|
| `libs/dxos-proof`: JSON chuẩn hóa + cây Merkle RFC 6962 | Có, kèm test vector |
| `deploy/`: Docker Compose 9 mạng phân vùng, Caddy, APISIX, Keycloak, Flowable, OpenBao, SeaweedFS, ClamAV; overlay `compose.release.yaml` chạy image phát hành theo digest | Có; stack đã chạy trên Docker Desktop (M1) |
| `core/`: identity, manifest + validator, PDP + che PII, Records API, kiểm dịch → CAS, ledger Merkle, STH, neo git, API xác minh và quản trị | Có, kèm unit + integration test |
| `core/`: cầu nối Flowable (guard, bốn mắt, khóa lạc quan), niêm phong theo ảnh chụp, thu hồi, `:erase-pii`, tuyên bố khóa, cổng đối soát công khai và gói bằng chứng, installer bốn mắt | Có, kèm unit + integration test (Plan 02) |
| `witness/`: CLI `dxos-witness` (`sync`, `verify-bundle`) + mẫu repo neo | Có |
| `cli/`: CLI quản trị `dxos` | Có, kèm test |
| `verify-portal/minimal`: trang đối soát tối giản (hash tính tại trình duyệt) | Có; đã kiểm trên Caddy + API thật, chưa qua Docker |
| `apps/phong-ho-so`, `apps/chung-nhan` (Tầng 2) | Manifest 1.1.0 + BPMN, kèm giao diện Vue (Plan 03); đã chạy trên Chromium thật với stack dev 22/10 (V27) |
| E2E mốc M2 (`tests/e2e`), `ops/at13_reuse.sh` | E2E đã chạy trên Docker Desktop 22/10: 13 passed, 1 skipped (AT-20 cần khóa OpenBao do trưởng nhóm nhập), [docs/progress/2026-10-22-e2e-m2-docker-desktop.md](docs/progress/2026-10-22-e2e-m2-docker-desktop.md); chưa chạy trên VPS. `ops/at13_reuse.sh` chưa chạy (cần tag `v0.2.0`) |
| `sdk/js`: SDK TypeScript (client, OIDC PKCE, tự kiểm gói bằng chứng, thành phần Vue) | Có, kèm test (Plan 03); [sdk/js/README.md](sdk/js/README.md) |
| `verify-portal/app`: cổng đối soát Vue `/apps/verify/` (trang tối giản cũ ở `/apps/verify-lite/`) | Có, kèm Playwright với API giả trong CI; đã kiểm trên stack dev 22/10 (V27) |
| `ops/`: `deploy.sh` (triển khai theo tag đã ký, tự quay lui), `vuot_rao.py` (bảng thử vượt rào), `build_web.sh` | Có; `vuot_rao.py` đã chạy trên stack dev 22/10 (V28: 10/10); `deploy.sh` chưa chạy trên VPS (V29, V42) |
| `viewer/`: Secure Viewer (S2), ảnh PNG từng trang có watermark chỉ để răn đe, chỉ p16; image phát hành theo digest | Có, kèm test; chưa chạy trong container (V40), [viewer/README.md](viewer/README.md) |
| `admin-ui/`: trang quản trị web `/ui/` (S3) trên host quản trị | Có, kèm Vitest và Caddy thật không Keycloak; chưa chạy với Keycloak thật (V41) |
| `ops/`: `backup.sh`, `restore.sh`, `at21_drill.sh` (S4), `demo_seed.py`, `license_scan.py`, `pin_actions.py` | Có, kiểm bằng lệnh giả; chưa chạy thật (V43, V44, V37) |
| `examples/so-muon-sach` + hướng dẫn 30 phút | Có; AT-26 (người ngoài đội làm thử) chưa tổ chức (V31) |

## Kiến trúc tóm tắt
- **Tầng 1, DX-OS Trust Core:**
  - Dịch vụ nguồn mở chạy độc lập: Keycloak (SSO), Apache APISIX (gateway), PostgreSQL, SeaweedFS, Flowable, ClamAV, OpenBao.
  - Phần đội tự viết: `trust-core` (Records API, kiểm dịch tệp, PDP, ledger Merkle, niêm phong) và thư viện `dxos-proof`.
- **Tầng 2:** App A "Phòng hồ sơ số" và App B "Chứng nhận số". Cả hai được cài bằng manifest, **không sửa mã lõi**. Viewer (xem trang PDF
  có watermark chỉ để răn đe) là dịch vụ riêng ở hồ sơ p16, chỉ đi vào lõi qua APISIX.
- **Kiến trúc trong vài phút đọc:** [ARCHITECTURE.md](ARCHITECTURE.md). Mục lục tài liệu trên trang GitHub Pages: <https://psa-ovncr.github.io/dxos/> (**chưa bật**, việc V38; nguồn trang là `docs/index.md`).
- **Thiết kế chi tiết:** [`docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`](docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md).

## Tầng 2: SDK, ứng dụng và cổng đối soát
Giao diện là SPA Vue 3 tĩnh, dựng bằng Vite và Caddy phục vụ từ volume `apps-static`; mọi quyết định bảo mật vẫn nằm ở lõi
(SPA chỉ là client của API).

| Đường dẫn | Là gì | Mã nguồn |
|---|---|---|
| `/apps/phong-ho-so/` | App A "Phòng hồ sơ số": văn bản, tệp kèm có trạng thái kiểm dịch, hộp việc, rà soát và xóa PII, niêm phong có mã QR, thu hồi, Sổ đăng ký văn bản đi | `apps/phong-ho-so/web` |
| `/apps/chung-nhan/` | App B "Chứng nhận số": nhập CSV (kể cả CSV Excel UTF-8 BOM, CP1258, UTF-16), duyệt theo lô, giấy chứng nhận và trang in | `apps/chung-nhan/web` |
| `/apps/verify/` | Cổng đối soát: băm tệp và tự kiểm gói bằng chứng ngay trên trình duyệt (tệp không rời máy); đối chiếu repo neo khi build có `VITE_ANCHOR_RAW_BASE` | `verify-portal/app` |
| `/apps/verify-lite/` | Trang đối soát tối giản (HTML tĩnh, không cần build), giữ làm dự phòng | `verify-portal/minimal` |
| `/apps/so-muon-sach/` | Ví dụ của hướng dẫn 30 phút | `examples/so-muon-sach` |

Dựng và kiểm:
```bash
npm ci && make web-check     # cần Node 22 và npm 11.6.2 (BUILD.md)
make web-build               # dựng bằng container Node dùng một lần, ghi vào volume apps-static
```
`make web-build` cần Docker và image Node ghim digest; digest đã ghim ngày 22/10/2026 bằng `make pin-images` trên máy trưởng nhóm (V35); lệnh dựng đã chạy trên máy đó 22/10 (V27).
Cổng đối soát chỉ đối chiếu repo neo khi build có `VITE_ANCHOR_RAW_BASE` và `.env` có `DXOS_ANCHOR_RAW_ORIGIN` khớp
(cần repo neo thật, V34); không thì cổng nói rõ là chưa đối chiếu. Triển khai lên VPS theo tag: [docs/runbook-deploy.md](docs/runbook-deploy.md).
SDK cho lập trình viên Tầng 2: [sdk/js/README.md](sdk/js/README.md). Ma trận nghiệm thu AT-01..AT-28: [docs/acceptance.md](docs/acceptance.md).

## Bản chất pháp lý của niêm phong
> Niêm phong số là chữ ký điện tử chuyên dùng do tổ chức vận hành tạo lập (Điều 22 khoản 1 điểm a Luật Giao dịch điện tử 2023). Trong nội bộ tổ chức, niêm phong dùng để xác nhận văn bản đã được duyệt và chưa bị sửa. Niêm phong **chưa** được chứng nhận "bảo đảm an toàn", nên **không** tương đương chữ ký tay (Điều 23 khoản 2) và **không phải** chữ ký số. Muốn dùng niêm phong để giao dịch với tổ chức, cá nhân bên ngoài với giá trị pháp lý, tổ chức phải đăng ký chứng nhận (Điều 25 khoản 3). Với người ngoài, cổng đối soát là công cụ **kiểm tra toàn vẹn về kỹ thuật**.

Ánh xạ cơ chế ↔ điều khoản, những gì **không** đạt và giới hạn về dữ liệu cá nhân: [docs/legal-mapping.md](docs/legal-mapping.md)
(diễn giải kỹ thuật của đội, không phải tư vấn pháp lý). Phạm vi của App B (spec mục 14):

> Chứng nhận số là hệ thống **quản lý và xác minh giấy chứng nhận điện tử** (chứng nhận tham gia sự kiện). Đây **không phải** hệ thống cấp chứng thư số PKI, **không phải** chữ ký số hay dịch vụ chứng thực chữ ký số, và **không** cấp văn bằng, chứng chỉ thuộc hệ thống giáo dục quốc dân. "Niêm phong số" là chữ ký điện tử chuyên dùng của tổ chức vận hành, **chưa** được chứng nhận bảo đảm an toàn (mục 25.1); với người ngoài, đối soát là kiểm tra toàn vẹn về kỹ thuật.

## Bắt đầu nhanh (phát triển)
```bash
make dev-install   # cài công cụ và gói Python ở chế độ editable
make check         # lint + kiểm tra giấy phép REUSE + test đơn vị
```
Hướng dẫn build đầy đủ: [BUILD.md](BUILD.md).

**Viết một app mới trong 30 phút, không sửa `core/`:** [docs/tutorial-app-30-phut.md](docs/tutorial-app-30-phut.md) (ví dụ chạy được: [examples/so-muon-sach/](examples/so-muon-sach/); checklist cho người thử ngoài đội: [docs/at26-checklist.md](docs/at26-checklist.md)).

## Giấy phép
Mã nguồn của dự án phát hành theo **Giấy phép Apache 2.0** (xem [LICENSE](LICENSE)). Bạn được tự do sử dụng, sửa đổi và phân phối lại, kể cả cho mục đích thương mại, với điều kiện giữ nguyên thông báo bản quyền và giấy phép.

Mỗi tệp mã đều có header `SPDX-License-Identifier`; kiểm tra bằng `reuse lint`.

Các thành phần bên ngoài (Keycloak, APISIX, Flowable, PostgreSQL, SeaweedFS, ClamAV, OpenBao, Caddy…) chạy như dịch vụ độc lập, **không** được phân phối kèm trong kho mã này, và tuân theo giấy phép riêng của từng dự án. Danh sách: [LICENSES-THIRD-PARTY.md](LICENSES-THIRD-PARTY.md).

Image `trust-core` cài thư viện pypdfium2 lúc build; thư viện này nhúng PDFium và các thành phần bên thứ ba, trong đó có
phần mềm của **The FreeType Project** (www.freetype.org) và phần mềm dựa một phần trên công trình của
**Independent JPEG Group**. Chi tiết: [docs/evidence/pypdfium2-giay-phep.md](docs/evidence/pypdfium2-giay-phep.md).

## Đóng góp và báo lỗi
- Báo lỗi và đề xuất tính năng: mục **Issues** của kho mã.
- Cách đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md).
- Báo lỗ hổng bảo mật: [SECURITY.md](SECURITY.md).
