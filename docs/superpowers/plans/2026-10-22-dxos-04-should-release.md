# Plan 04 — SHOULD S1–S4, gia cố, chạy thử, phát hành v0.9.0 → v1.0.0 (M4–M5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Làm cả bốn SHOULD (S1 PII trong tài liệu, S2 Viewer watermark, S3 trang admin web, S4 tag ký + tự quay lui + backup), lấp chỗ trống PoF, chuẩn bị chạy thử và bộ demo, rồi phát hành **v0.9.0 (M4, 30/11/2026)** và **v1.0.0 (M5, 04/12/2026)**.

**Architecture:**
- Như Plan 00–03. Lõi chỉ thêm endpoint/việc **chung** (không định danh app, AT-14 xanh).
- S1 nằm trong lõi:
  - worker dò PII trên lớp chữ PDF (regex, không thư viện mới);
  - dựng **bản che dạng ảnh** bằng pypdfium2;
  - lưu thành object `redacted`.
- S2 là dịch vụ Tầng 2 dùng chung `viewer/`:
  - chỉ ở `net-app`, chỉ gọi API bằng token của người xem;
  - render trang trên RAM kèm watermark;
  - chỉ bật ở hồ sơ p16.
- S3 là SPA Vue ở `https://admin.<miền>/ui/`, gọi Admin API sẵn có.
- S4 nằm ở `ops/` (deploy, backup, restore, diễn tập).

**Tech Stack:**
- Như Plan 03. **Không thêm phụ thuộc mới** nào, Python hay npm (quyết định của trưởng nhóm 22/10: không Pillow, không vipii, không MkDocs).
- Viewer dùng lại `pypdfium2` (đã có trong lõi, giấy phép đã ghi ở `LICENSES-THIRD-PARTY.md`), `fastapi`, `uvicorn`, `httpx`.

**Spec:** `docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md` bản **1.0.3**. Các mục liên quan:
- 7, 9.4, 12 (`object_refs`, `pii_findings`, `variant=redacted`);
- 15 (giới hạn công bố);
- 16.1–16.4 (p8/p16, GitOps, backup, demo);
- 18 (S1–S4, thứ tự cắt);
- 19 (AT-21, 22, 23, 26);
- 20.2 (PoF);
- 22 (M4, M5, M6);
- 25 (lời pháp lý).

Khi plan và spec lệch nhau, **spec thắng**.
**Kế hoạch tổng thể:** `docs/superpowers/plans/2026-10-20-dxos-00-ke-hoach-tong-the.md` (E10 S10.1–S10.4, §5, §7, §8, §10).
**Plan trước:** Plan 03 (mã ở `main`, `f577586`). Mọi giao diện "Consumes" lấy theo mã thật ở `f577586`.
**Đầu vào đã gom:** việc còn mở ở `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 13 (V-bảng). Cổng năng suất (Plan 00 §8): M3 xong mã ngày 22/10, sớm khoảng một tháng, đạt ≥ 90%, nên làm đủ S1–S4. Trưởng nhóm đã duyệt ngày 22/10.

## Quyết định của plan (P4-Dn)

| # | Quyết định | Lý do | Cái giá nếu sai |
|---|---|---|---|
| P4-D1 | Không thêm phụ thuộc. Dò PII bằng regex tự viết; ô che và watermark vẽ bằng pypdfium2; PNG tự mã hóa bằng `zlib` của thư viện chuẩn | Trưởng nhóm chốt 22/10. Pillow (HPND) nằm ngoài danh sách giấy phép; vipii đang Alpha | Bỏ sót PII ngoài 3 loại; mã vẽ tự viết dài hơn |
| P4-D2 | `pii_findings.value_hmac` để **NULL**. Không lưu giá trị, kể cả dạng băm | I5. CCCD chỉ có 12 chữ số, băm dò ngược được | Không khử trùng lặp được phát hiện giữa các tệp |
| P4-D3 | Thêm bảng `pii_scans(sha256 PK)`, ghi kết quả dò của từng object. Guard `pii_reviewed` báo `pii_scan_pending` (409) khi collection có `document_detect` mà còn tệp CLEAN chưa có hàng `pii_scans` | Dò chạy nền sau CLEAN; nếu không chặn, người duyệt xác nhận trước khi dò xong | Thêm một lượt chờ ngắn trong luồng duyệt |
| P4-D4 | Tệp có ≥ 1 phát hiện: tải `variant=original` cần quyền `reveal_pii` của collection, thiếu thì 404 và ghi `policy.denied`. `variant=redacted` chỉ cần quyền `read` | Mục đích của S1 là không phát tán bản gốc chứa PII | Người tải lên (không có `reveal_pii`) không tải lại được bản gốc của chính mình |
| P4-D5 | Bản che là PDF **chỉ có ảnh**, 150 dpi, ô đen phủ bbox nở thêm 2 pt. Lưu như object CLEAN, `scanner_version='dxos-redact/1'`, `object_refs.role='redacted'` | Không còn lớp chữ, nên không chép lại được số bị che | Tệp lớn hơn bản gốc |
| P4-D6 | Viewer không giữ trạng thái, không ghi đĩa, không có bí mật. Lấy tệp qua APISIX bằng token người xem; lấy định danh người xem từ `GET /api/v1/whoami` (8 ký tự đầu của `sub`) | I1: viewer chỉ gọi API; lõi không trả tên đăng nhập | Mỗi trang tải lại tệp (chấp nhận được cho demo) |
| P4-D7 | Watermark chỉ ASCII: `DX-OS <8 ký tự đầu của sub> <YYYY-MM-DD HH:MM> ICT`, lặp chéo, xám 35% | Phông chuẩn của PDF (Helvetica) không có dấu tiếng Việt | Watermark không dấu |
| P4-D8 | Tag ký bằng **SSH signing** của git; khóa công khai ở `deploy/allowed_signers`. `deploy.sh` từ chối tag không ký trừ khi có `--allow-unsigned` (ghi cảnh báo vào `deploy/deployments.log`) | Spec 16.3 (`git tag -v`). SSH dễ hơn GPG cho trưởng nhóm | Laptop lab phải thêm cờ |
| P4-D9 | Backup mã hóa bằng `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt`, mật khẩu ở `.secrets/backup-passphrase`. Diễn tập khôi phục chạy ở **compose project riêng** `dxos-restore`, không bao giờ đụng project `dxos` | openssl có sẵn trên VPS Linux; tách project nên diễn tập không làm mất dữ liệu thật | Không có xác thực MAC riêng (bù bằng sha256 của gói ghi kèm) |
| P4-D10 | Trang tài liệu: GitHub Pages dựng sẵn Jekyll từ `/docs` của `main` (không công cụ trong repo); `docs/_config.yml` loại `superpowers/`, `handoff/`, `spikes/` | PoF "trang tài liệu", không thêm công cụ | Giao diện đơn giản |
| P4-D11 | Ghim phụ thuộc Python bằng `constraints.txt` (đúng phiên bản, sinh từ môi trường CI đã xanh); `core/Dockerfile` cài với `-c`. Actions ghim theo SHA bằng `ops/pin_actions.py` chạy trên máy có mạng (việc V) | Image và SBOM dựng lại được | Phải cập nhật constraints khi nâng phụ thuộc |
| P4-D12 | Mọi thiết lập repo qua API (topic `dx-os`, nhãn, Pages) do Claude làm (trưởng nhóm đồng ý 22/10). API bị chặn thì ghi thành việc V | PoF | — |

## Global Constraints

Toàn bộ Global Constraints của Plan 00, 01, 02 và 03 áp dụng nguyên văn (Plan 03 mục "Global Constraints", trừ dòng jsdom: phiên bản **thật** là `29.1.1`). Plan này thêm:

- **Không thêm phụ thuộc** Python hay npm (P4-D1). Cần thêm thì **dừng lại hỏi trưởng nhóm**.
- Lõi: chỉ endpoint, việc nền, bảng **chung**. Test lõi chỉ dùng `test-app`/`test-flow`. AT-14 phải xanh.
- `pii_findings`, `pii_scans` và ledger **không bao giờ** chứa giá trị PII hay mã băm của nó (I5, P4-D2). Sự kiện `pii.detected` chỉ có `sha256`, đếm theo loại và `detector`.
- Viewer:
  - chỉ ở `net-app`, không tới kho, Flowable, OpenBao (I1, AT-01);
  - chỉ bật ở p16 (spec 16.1);
  - không ghi đĩa (`tempfile`, `open(..., 'w')` bị cấm trong `viewer/src`; có test tĩnh).
- Giới hạn tài nguyên khi render (cả lõi lẫn viewer):
  - ≤ **200** trang mỗi tệp;
  - ảnh ≤ **4000×4000** px mỗi trang;
  - 150 dpi cho bản che, 110 dpi cho viewer.
- SPA mới (admin) theo đúng luật SPA của Plan 03:
  - không `v-html`;
  - router hash;
  - token trong `sessionStorage`;
  - `If-Match` có nháy;
  - mọi lỗi hiển thị qua `ProblemMessage`;
  - CSP riêng, không `unsafe-inline`.
- Script `ops/*.sh` mới:
  - `set -euo pipefail`;
  - `shellcheck -S warning` sạch (CI có shellcheck);
  - không bao giờ `rm -rf` trên đường dẫn do người dùng truyền mà chưa qua kiểm như `ops/build_web.sh` (từ chối `/`, `.`, `..`, `$HOME`, repo).
- Lời pháp lý (spec 25.1):
  - không bao giờ viết niêm phong "có giá trị pháp lý";
  - không bao giờ viết App A "tuân thủ Nghị định 30";
  - không bao giờ viết Trust Core "sẵn sàng để được chứng nhận".
  
  Tài liệu mới về watermark phải nói "chỉ để răn đe" (spec 15).
- Dữ liệu demo hư cấu ("Công ty TNHH Sao Mai", "Sự kiện CLB"). Số CCCD, SĐT, STK trong fixture **tự bịa**, có chú thích "hư cấu".
- Kiểm trước khi push bằng mã thoát: `make check PYTHON=python && npm run check && reuse lint`. Tag chỉ gắn khi CI xanh ở **đúng** commit đó. Trưởng nhóm tự gõ lệnh tag.
- Việc cần máy thật, VPS hay người ngoài: ghi vào bảng V (`docs/progress/2026-10-21-tong-ket-tien-do.md` mục 14 mới, đánh số tiếp từ V37) rồi làm tiếp.

## Review Focus

Năm loại đầu vào mà spec ngầm yêu cầu, chưa có test tự nhiên. Mỗi mục có test ở task sở hữu.

1. **Số PII trong PDF thật hiếm khi gọn gàng.** Các dạng gặp:
   - `079 203 012 345`;
   - `079.203.012.345`;
   - `0912-345-678`;
   - `+84 912 345 678`;
   - số nằm trong ô bảng;
   - số vắt qua hai dòng;
   - trang xoay 90°;
   - chữ số toàn chiều rộng.

   Kỳ vọng:
   - dò được các dạng có dấu cách, chấm, gạch nối;
   - bbox đúng trang, kể cả trang xoay;
   - không báo nhầm dãy số khác độ dài (mã số thuế 10/13 số, số hợp đồng).

   Test ở Task 3, 4.
2. **Tệp lớn, nhiều trang, trang khổng lồ.** Kỳ vọng:
   - quá 200 trang thì `pii_scans.status='TOO_LARGE'` và không dựng bản che; bản gốc vẫn bị khóa theo P4-D4, coi như có phát hiện;
   - trang vượt 4000×4000 px ở dpi đã chọn thì hạ dpi, không cấp phát RAM vô hạn.

   Test ở Task 4, 7.
3. **Quyền tải.** Kỳ vọng:
   - người không có `reveal_pii` tải `original` của tệp có phát hiện thì nhận 404 và ledger có `policy.denied`;
   - người đó tải được `redacted`;
   - tệp không phát hiện gì thì vẫn tải `original` như cũ;
   - `variant` lạ thì 404.

   Test ở Task 5.
4. **Viewer gặp token hỏng hoặc tệp không quyền.** Kỳ vọng:
   - không token thì 401;
   - API trả 404 thì viewer trả 404, không ảnh;
   - số trang ngoài phạm vi thì 404;
   - API chậm quá 10 giây thì 504;
   - viewer không bao giờ trả ảnh khi API chưa trả 200.

   Test ở Task 7.
5. **Triển khai và khôi phục gặp sự cố.** Kỳ vọng:
   - tag không ký thì `deploy.sh` thoát 2 **trước** mọi thay đổi;
   - health hỏng sau khi lên tag mới thì tự quay về tag tốt gần nhất và thoát 4;
   - lần triển khai đầu (chưa có tag tốt) thì dừng, in hướng dẫn;
   - khôi phục với mật khẩu sai hoặc gói bị sửa thì dừng **trước khi** tạo volume.

   Test ở Task 11, 12.

---

## Cấu trúc tệp

| Tệp | Trách nhiệm | Task |
|---|---|---|
| `constraints.txt`, `ops/pin_actions.py`, `ops/license_scan.py`, `.github/workflows/ci.yml` | Ghim phụ thuộc, quét giấy phép | 1 |
| `ARCHITECTURE.md`, `docs/index.md`, `docs/_config.yml`, `.github/ISSUE_TEMPLATE/config.yml`, `Makefile` (build, sbom, release-check), `docs/capacity.md` | PoF | 2 |
| `core/src/dxos_core/pii/detect.py` | Dò PII trên văn bản + toạ độ ký tự (thuần, không I/O) | 3 |
| `core/migrations/006_pii_scans.sql`, `core/src/dxos_core/pii/job.py`, `objects/ingest.py`, `workflow/guards.py` | Việc nền `pii_detect`, bảng `pii_scans`, guard | 4 |
| `core/src/dxos_core/pii/redact.py`, `pii/png.py`, `objects/router.py`, `objects/service` (danh sách tệp) | Bản che, `variant=redacted`, khóa bản gốc | 5 |
| `apps/phong-ho-so/web/src/...`, `sdk/js/src/client.ts` | UI phát hiện và bản che | 6 |
| `viewer/` (gói `dxos_viewer`) | Dịch vụ Viewer | 7 |
| `deploy/compose.p16.yaml`, `deploy/apisix/apisix.yaml`, `deploy/network-matrix.yaml`, `apps/phong-ho-so/web/...` | Nối Viewer | 8 |
| `admin-ui/`, `sdk/js/src/auth.ts`, `deploy/keycloak/*.json`, `ops/keycloak_upgrade.py` | SPA quản trị phần 1 | 9 |
| `admin-ui/src/views/*`, `deploy/caddy/Caddyfile`, `ops/build_web.sh` | SPA quản trị phần 2 + phục vụ | 10 |
| `ops/deploy.sh`, `deploy/allowed_signers`, `docs/runbook-deploy.md` | Tag ký + tự quay lui | 11 |
| `ops/backup.sh`, `ops/restore.sh`, `ops/at21_drill.sh`, `docs/runbook-backup.md` | Backup, khôi phục, AT-21 | 12 |
| `ops/demo_seed.py`, `demo/` (fixture hư cấu), `Makefile demo-seed` | Dữ liệu demo | 13 |
| `tests/web/live/*`, `sdk/js/src/proof/*` | Ghim SPKI CA Caddy; khớp JS–Python | 14 |
| `CHANGELOG.md`, `README*.md`, `docs/acceptance.md`, tiến độ, phiên bản | Chuẩn bị v0.9.0 | 15 |
| `BUILD.md` (máy sạch), `ops/doctor.sh`, `ops/demo_preflight.sh`, `docs/demo/`, `docs/nop-bai.md` | M5: máy sạch, bộ demo, nộp bài, chuẩn bị v1.0.0 | 16 |

---

### Task 1: Ghim phụ thuộc Python, Actions theo SHA, quét giấy phép trong CI

**Files:**
- Create: `constraints.txt`, `ops/pin_actions.py`, `ops/license_scan.py`, `tests/ops/test_license_scan.py`, `tests/ops/test_pin_actions.py`, `tests/repo/test_constraints.py`
- Modify: `core/Dockerfile`, `Makefile` (`dev-install` dùng `-c constraints.txt`), `.github/workflows/ci.yml` (job `licenses`), `LICENSES-THIRD-PARTY.md`

**Interfaces:**
- Produces:
  - `python ops/license_scan.py [--npm-lock package-lock.json] [--allow-file LICENSES-THIRD-PARTY.md]`, thoát 0 nếu sạch, 1 nếu vi phạm;
  - `python ops/pin_actions.py [--dry-run]`;
  - `make licenses`.

- [ ] **Step 1: Test cho `license_scan`.**
  - Test `test_python_dists_outside_allowlist_fail`: một dist giả có `License-Expression: GPL-3.0-only` thì thoát 1, kèm tên gói.
  - Test `test_build_only_npm_exceptions_pass`: gói `dev: true` trong lockfile có `MPL-2.0`/`BlueOak-1.0.0`/`MIT-0`/`CC0-1.0` thì đạt **chỉ khi** tên gói có trong bảng ngoại lệ của `LICENSES-THIRD-PARTY.md`.
  - Test `test_runtime_npm_must_be_permissive`: gói không `dev` có `MPL-2.0` thì thoát 1.
  - Test `test_pypdfium2_compound_licence_is_allowed_by_name`: `pypdfium2` được nhận vì có tên trong danh sách cho phép của `LICENSES-THIRD-PARTY.md`.
  - Danh sách cho phép (Plan 01): `MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, PSF-2.0, ISC`, cộng ngoại lệ có tên.
- [ ] **Step 2:** Chạy `python -m pytest tests/ops/test_license_scan.py -q`. Kỳ vọng FAIL (chưa có script).
- [ ] **Step 3:** Viết `ops/license_scan.py`.
  - Đọc giấy phép bằng `importlib.metadata` (`License-Expression`, rồi `License`, rồi classifier `License ::`) cho các dist cài trong venv hiện tại, trừ gói của đội.
  - Đọc khóa `packages.*.license` và `dev` trong `package-lock.json`.
  - Bảng ngoại lệ lấy từ phần "Ngoại lệ đã duyệt" của `LICENSES-THIRD-PARTY.md`. Thêm phần đó nếu chưa có, liệt kê đúng các gói đã ghi ở V30.
- [ ] **Step 4: `constraints.txt`.**
  - Sinh từ venv CI đã xanh: `pip freeze --exclude-editable`, chỉ giữ phụ thuộc runtime của 4 gói Python. Đầu tệp có SPDX và một dòng cách sinh lại.
  - `core/Dockerfile` đổi thành `pip install -c /src/constraints.txt ...`.
  - Test `tests/repo/test_constraints.py`:
    - mọi dòng có dạng `name==x.y.z`;
    - mọi phụ thuộc trong 4 `pyproject.toml` có mặt;
    - `core/Dockerfile` có `-c`.
- [ ] **Step 5: `ops/pin_actions.py`.**
  - Đổi `uses: owner/repo@vN` trong `.github/workflows/*.yml` thành `@<sha40> # vN`, hỏi SHA qua `git ls-remote https://github.com/owner/repo refs/tags/vN`.
  - Test bằng hàm phân giải giả: `test_rewrites_tag_to_sha_with_comment`, `test_already_pinned_untouched`, `test_dry_run_writes_nothing`.
  - Cloud không ra GitHub được, nên **chạy thật là việc V37** (máy trưởng nhóm, như `pin_images.py`).
  - Image `anchore/syft` và `zricethezav/gitleaks` trong workflow cũng thêm vào `ops/pin_images.py` (mẫu `*.yml` trong `.github/workflows`), có test.
- [ ] **Step 6:** Thêm job `licenses` vào `ci.yml`: `pip install -e ... -c constraints.txt`, `npm ci`, `python ops/license_scan.py`. Thêm `make licenses`.
- [ ] **Step 7:** Chạy cổng kiểm (mã thoát). Chạy `python ops/license_scan.py` trong venv cloud; thoát 0. Ghi số gói đã quét vào báo cáo.
- [ ] **Step 8:** Commit `build: pin Python deps, add licence scan job, action pinning tool`.

### Task 2: Chỗ trống PoF — ARCHITECTURE, trang tài liệu, Makefile, thiết lập repo

**Files:**
- Create: `ARCHITECTURE.md`, `docs/index.md`, `docs/_config.yml`, `.github/ISSUE_TEMPLATE/config.yml`, `docs/capacity.md`, `tests/repo/test_pof_m4.py`
- Modify: `Makefile`, `README.md`, `README_EN.md`, `CONTRIBUTING.md` (mục "Thành viên đóng góp")

**Interfaces:**
- Produces:
  - `make build` (`docker compose build`);
  - `make sbom VERSION=x` (syft trong Docker theo digest ghim, ra `dist/sbom-x.cdx.json`);
  - `make release-check VERSION=x` (kiểm phiên bản 4 gói + 3 `__init__`, mục CHANGELOG có ngày, cây sạch, `HEAD` là `origin/main`; không gắn tag).

- [ ] **Step 1: Test `tests/repo/test_pof_m4.py`.**
  - `ARCHITECTURE.md` có các mục `## Ba tầng`, `## Mạng`, `## Luồng tải tệp`, `## Niêm phong và sổ cái`, `## Ranh giới tin cậy` và trỏ tới spec.
  - `docs/_config.yml` loại `superpowers`, `handoff`, `spikes`.
  - `Makefile` có target `build`, `sbom`, `release-check`.
  - `config.yml` có `blank_issues_enabled: false` và link Discussions.
  - `docs/capacity.md` có bảng p8 và p16, cột `Nguồn đo`, và **không** có số nào không kèm nguồn.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL.
- [ ] **Step 3:** Viết các tệp.
  - `ARCHITECTURE.md` tóm tắt spec mục 4–6, 9, 11; dưới 250 dòng; có sơ đồ mermaid ba tầng.
  - `docs/capacity.md`:
    - hàng p8 lấy số đo thật trên laptop ngày 22/10 (log `E:\PMMNM 2026\_claude-run\m3-7-p8-ots.log`, có trong `docs/progress/` khi đã ghi);
    - hàng p16 ghi "chưa đo (V13)".
  - `make release-check` chỉ đọc, không gắn tag.
- [ ] **Step 4: Thiết lập repo qua API.** Trưởng nhóm đồng ý; dùng endpoint gắn với repo:
  - `gh api -X PUT repos/PSA-OVNCR/dxos/topics -f names[]=dx-os -f names[]=open-source -f names[]=trust-core`;
  - tạo nhãn `area:core`, `area:web`, `area:ops`, `area:docs`, `pof`, `security`, `good first issue` (đã có thì bỏ qua) bằng `gh api repos/PSA-OVNCR/dxos/labels`;
  - bật Pages: `gh api -X POST repos/PSA-OVNCR/dxos/pages -f source[branch]=main -f source[path]=/docs`.

  Lệnh nào bị proxy chặn (403) thì ghi thành V38 kèm đúng lệnh, **không** thử đường khác.
- [ ] **Step 5:** Chạy cổng kiểm. Commit `docs: architecture, docs site, capacity, PoF targets`.

### Task 3: Bộ dò PII trên văn bản có toạ độ (S1, thuần)

**Files:**
- Create: `core/src/dxos_core/pii/__init__.py`, `core/src/dxos_core/pii/detect.py`, `core/tests/test_pii_detect.py`

**Interfaces:**
- Produces:
  ```python
  PiiType = Literal["CCCD", "PHONE", "BANK_ACCOUNT"]

  @dataclass(frozen=True)
  class Box:            # đơn vị PDF point, gốc dưới-trái của trang
      page: int
      left: float
      bottom: float
      right: float
      top: float

  @dataclass(frozen=True)
  class Finding:
      type: PiiType
      page: int
      boxes: tuple[Box, ...]

  def detect_text(text: str, char_boxes: Sequence[Box | None], types: Collection[PiiType]) -> list[Finding]
  ```
  `char_boxes[i]` là hộp của `text[i]`, hoặc `None` với ký tự sinh thêm (xuống dòng do PDFium chèn). Finding **không** chứa giá trị.

- [ ] **Step 1: Test.** Giá trị đều hư cấu.
  - `test_cccd_forms`: phải dò được các dạng sau, đúng 1 phát hiện CCCD mỗi chuỗi.
    - `"CCCD: 079203012345"`;
    - `"079 203 012 345"`;
    - `"079.203.012.345"`;
    - `"０７９２０３０１２３４５"` (toàn chiều rộng, chuẩn hóa NFKC chỉ để so khớp).
  - `test_cccd_rejects_bad_province_and_length`: không phát hiện với các chuỗi sau.
    - `"099203012345"` (mã tỉnh ≥ 097 không hợp lệ);
    - `"79203012345"` (11 số);
    - `"0792030123456"` (13 số);
    - mã số thuế `"0312345678-001"`.
  - `test_phone_forms`: dò được `"0912345678"`, `"0912-345-678"`, `"+84 912 345 678"`, `"(+84) 912.345.678"`. Không dò `"0212345678"`: đầu số 02x là cố định, ngoài phạm vi; ghi rõ đây là giới hạn.
  - `test_bank_account_needs_keyword`:
    - `"STK: 1234 5678 9012"` dò được;
    - `"Số tài khoản 0123456789012"` dò được;
    - `"Mã hợp đồng 1234567890"` không;
    - từ khóa cách số quá 30 ký tự thì không.
  - `test_number_split_across_lines_is_found_once`: `"079 203\n012 345"` → 1 phát hiện, 2 hộp.
  - `test_only_requested_types`: `types={"PHONE"}` thì bỏ qua CCCD.
  - `test_finding_has_no_value`: `dataclasses.asdict(f)` không chứa chữ số nào của đầu vào (chỉ `type`, `page`, `boxes`).
- [ ] **Step 2:** Chạy `python -m pytest core/tests/test_pii_detect.py -q`. Kỳ vọng FAIL.
- [ ] **Step 3:** Viết `detect.py`.
  - Chuẩn hóa NFKC, nhưng giữ bảng ánh xạ chỉ số về chuỗi gốc để lấy hộp.
  - Dấu phân cách cho phép giữa nhóm chữ số: dấu cách, `.`, `-`, xuống dòng, tối đa 1 ký tự liên tiếp.
  - Ranh giới: không chữ số hay chữ cái liền trước hoặc liền sau.
  - Mã tỉnh CCCD hợp lệ: `001–096` (danh sách theo Thông tư 07/2016/TT-BCA). Ghi nguồn trong docstring.
  - Đầu số di động: `03x, 05x, 07x, 08x, 09x`.
  - STK: 8–19 chữ số, có từ khóa `stk|so tai khoan|tai khoan` (bỏ dấu, không phân biệt hoa thường) trong 30 ký tự ngay trước.
- [ ] **Step 4:** Chạy test, PASS. Chạy `make check`.
- [ ] **Step 5:** Commit `feat(pii): text-layer detector for CCCD, phone and bank account numbers`.

### Task 4: Việc nền `pii_detect`, bảng `pii_scans`, guard chờ dò xong (S1)

**Files:**
- Create: `core/migrations/006_pii_scans.sql`, `core/src/dxos_core/pii/job.py`, `core/tests/integration/test_pii_job.py`, `core/tests/fixtures/files/pii-fictional.pdf` (+ `.license` nếu REUSE cần), `core/tests/helpers/make_pii_pdf.py`
- Modify: `core/src/dxos_core/objects/ingest.py` (đưa việc vào hàng đợi trong transaction CLEAN), `core/src/dxos_core/worker.py` (đăng ký handler), `core/src/dxos_core/workflow/guards.py`, `core/src/dxos_core/ledger/events.py` (đã có `pii.detected`), `docs/api/contract-tier2.md`

**Interfaces:**
- Consumes: `detect_text`, `Box`, `Finding` (Task 3).
- Produces:
  - migration `006_pii_scans.sql`:
    ```sql
    CREATE TABLE pii_scans (sha256 sha256_hex PRIMARY KEY REFERENCES objects(sha256),
      status text NOT NULL CHECK (status IN ('DONE','TOO_LARGE','FAILED')),
      findings integer NOT NULL CHECK (findings >= 0), detector text NOT NULL,
      scanned_at timestamptz NOT NULL DEFAULT now());
    GRANT SELECT, INSERT ON pii_scans TO dxos_core;
    ```
  - `PII_JOB = "pii_detect"`; payload `{"sha256": ..., "types": [...]}`;
  - `async def process_pii_job(ctx: WorkerContext, job: Job) -> None`;
  - `def extract(data: bytes, max_pages: int = 200) -> tuple[str, list[Box|None]] | None` (`None` khi quá số trang). Lấy văn bản và hộp từng ký tự bằng `PdfTextPage.get_text_range` + `get_charbox`, có tính trang xoay.
  - Guard `pii_reviewed` thêm lý do `pii_scan_pending` (409).

- [ ] **Step 1: Fixture.** `make_pii_pdf.py` dựng PDF 2 trang bằng pypdfium2 (phông chuẩn Helvetica, nội dung không dấu):
  - trang 1 có CCCD và SĐT hư cấu;
  - trang 2 **xoay 90°** có STK hư cấu kèm "STK".

  Commit tệp sinh ra. Test `test_fixture_is_reproducible` dựng lại và so sha256.
- [ ] **Step 2: Test integration.** Dùng `test-app` có `document_detect: [CCCD, PHONE, BANK_ACCOUNT]`.
  - `test_clean_upload_enqueues_pii_job_only_when_manifest_asks`: manifest không có `document_detect` thì không có việc `pii_detect`.
  - `test_findings_rows_have_no_values`:
    - 3 hàng `pii_findings` đúng `type`/`page`;
    - `value_hmac IS NULL`;
    - `bbox` là list hộp số thực;
    - ledger có `pii.detected` với body `{"sha256", "counts": {"CCCD":1,"PHONE":1,"BANK_ACCOUNT":1}, "detector": "dxos-pii/1"}` và **không** chuỗi chữ số dài ≥ 8 nào.
  - `test_rotated_page_box_is_inside_page`: hộp của STK nằm trong mediabox trang 2.
  - `test_too_many_pages`: PDF 201 trang dựng trong test → `pii_scans.status='TOO_LARGE'`, `findings=0`.
  - `test_guard_waits_for_scan`: tệp CLEAN chưa có `pii_scans` thì `:pii-review` vẫn ghi nhận, nhưng guard `pii_reviewed` báo `pii_scan_pending` 409. Sau khi dò xong và rà lại thì đạt.
  - `test_job_is_idempotent`: chạy việc 2 lần → không nhân đôi hàng (`ON CONFLICT` theo `pii_scans`).
- [ ] **Step 3:** Chạy `DXOS_TEST_REQUIRE_DB=1 python -m pytest -m integration core/tests/integration/test_pii_job.py -q`. Kỳ vọng FAIL.
- [ ] **Step 4:** Hiện thực.
  - Đưa việc vào hàng đợi trong cùng transaction với `object.clean`, chỉ khi manifest đang hoạt động của app có `policies.pii.document_detect` khác rỗng.
  - Việc nền:
    1. đọc object từ kho;
    2. chạy `extract` rồi `detect_text` trong `asyncio.to_thread` (khóa `_LOCK` của pdfcheck dùng chung);
    3. trong một transaction: INSERT `pii_findings` + `pii_scans` + ledger `pii.detected`.

    Lỗi PDFium thì `pii_scans.status='FAILED'`; guard coi `FAILED` như "có phát hiện", cần rà.
  - Cập nhật `contract-tier2.md` (lý do mới `pii_scan_pending`).
- [ ] **Step 5:** Chạy test, PASS. Chạy cổng kiểm và integration toàn bộ `core/tests/integration`.
- [ ] **Step 6:** Commit `feat(pii): background detection job, pii_scans table, guard waits for scan`.

### Task 5: Bản che dạng ảnh, `variant=redacted`, khóa bản gốc (S1)

**Files:**
- Create: `core/src/dxos_core/pii/png.py`, `core/src/dxos_core/pii/redact.py`, `core/tests/test_pii_png.py`, `core/tests/test_pii_redact.py`, `core/tests/integration/test_pii_download.py`
- Modify: `core/src/dxos_core/pii/job.py`, `core/src/dxos_core/objects/router.py` (`get_object`, `list_attachments`), `docs/api/contract-tier2.md`, `docs/api/openapi.json` (`make openapi`)

**Interfaces:**
- Produces:
  - `def encode_png(width: int, height: int, rgb: bytes) -> bytes` (dùng zlib; viewer dùng lại bằng cách chép mã, vì viewer là gói riêng; test giống hệt ở cả hai nơi);
  - `def redact_pdf(data: bytes, findings: Sequence[Finding], dpi: int = 150, pad_pt: float = 2.0, max_px: int = 4000) -> bytes` trả về PDF chỉ có ảnh;
  - `GET /api/v1/objects/{sha256}?variant=redacted`;
  - phần tử danh sách tệp thêm `"pii": {"status": "PENDING"|"DONE"|"TOO_LARGE"|"FAILED", "findings": int, "redacted": bool}`.

- [ ] **Step 1: Test thuần.**
  - `test_png_roundtrip_header_and_crc`: chữ ký PNG, IHDR đúng kích thước, CRC mọi chunk đúng (`zlib.crc32`), IDAT giải nén đúng độ dài `(1+3w)*h`.
  - `test_redacted_pdf_has_no_text_layer`: trang nào của PDF ra cũng có `get_text_range().strip()==""`.
  - `test_redacted_pixels_black_under_box`: render lại trang 1 của bản che; mọi điểm ảnh trong hộp CCCD là đen (`<16`).
  - `test_huge_page_lowers_dpi`: trang 5000×5000 pt → ảnh ≤ 4000 px mỗi chiều.
- [ ] **Step 2: Test integration.** Hai người dùng trên `test-app`: `reader` chỉ `read`; `reviewer` có thêm `reveal_pii`.
  - `test_reader_gets_redacted_not_original`:
    - `original` → 404, ledger có `policy.denied` với `reason="pii_original"`;
    - `redacted` → 200, `application/pdf`, không lớp chữ.
  - `test_reviewer_gets_both`.
  - `test_no_findings_original_unchanged`: tệp không phát hiện gì thì `reader` tải `original` 200; `redacted` → 404.
  - `test_unknown_variant_404`.
  - `test_attachment_list_shows_pii_state`: trước khi dò `PENDING`, sau đó `DONE`/`findings=3`/`redacted=true`.
- [ ] **Step 3:** Chạy test. Kỳ vọng FAIL.
- [ ] **Step 4:** Hiện thực.
  - Việc `pii_detect`: findings > 0 thì gọi `redact_pdf`, ghi object mới (sha256 của bản che) vào kho, `objects` (CLEAN, `scanner_version='dxos-redact/1'`) và `object_refs(role='redacted')` cho **mọi** bản ghi tham chiếu bản gốc, trong cùng transaction với `pii_scans`.
  - `get_object`: theo P4-D4. `reason` mới `pii_original` thêm vào danh sách lý do của PDP.
- [ ] **Step 5:** Chạy test, PASS. `make openapi`. Chạy cổng kiểm và integration toàn bộ.
- [ ] **Step 6:** Commit `feat(pii): image-only redacted copy, variant=redacted, original gated by reveal_pii`.

### Task 6: App A hiện phát hiện PII và tải bản che (S1)

**Files:**
- Modify: `sdk/js/src/client.ts` (`downloadObject(sha256, variant: 'original'|'redacted')`), `sdk/js/src/types.ts`, `sdk/js/test/client.test.ts`, `apps/phong-ho-so/web/src/components/AttachmentList.vue` (hoặc tệp tương đương đang hiển thị `QuarantineStatus`), `apps/phong-ho-so/web/src/components/PiiPanel.vue` (SDK, dùng chung), test tương ứng

**Interfaces:**
- Consumes: trường `pii` của danh sách tệp (Task 5).
- Produces: `client.downloadObject(sha256: string, variant?: 'original'|'redacted'): Promise<Blob>`.

- [ ] **Step 1: Test Vitest.**
  - `shows 'Đang dò dữ liệu cá nhân' while PENDING and polls until DONE` (dùng lại cách thăm dò chịu lỗi tạm của `QuarantineStatus`).
  - `DONE with 3 findings shows 'Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)' and a 'Tải bản che' button`.
  - `original download 404 shows ProblemMessage, never a blank`.
  - `PiiPanel lists per-file counts and blocks confirm text until scans are DONE`: chỉ là văn bản hướng dẫn; quyết định vẫn ở máy chủ.
  - Test SDK: `downloadObject` gửi `?variant=redacted`; không tự thử lại.
- [ ] **Step 2:** Chạy `npm -w <workspace> test`. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Chạy `npm run check`. Cập nhật một test live `tests/web/live/app-a.spec.ts`: chuyên viên tải `pii-fictional.pdf`, thấy "Phát hiện 3", tải bản che. Chạy thật là việc V39 (máy trưởng nhóm).
- [ ] **Step 4:** Commit `feat(app-a): show document PII findings and redacted download`.

### Task 7: Dịch vụ Viewer (S2)

**Files:**
- Create: `viewer/pyproject.toml` (gói `dxos-viewer` 0.9.0, chỉ phụ thuộc `fastapi`, `uvicorn[standard]`, `httpx`, `pypdfium2`, ràng theo `constraints.txt`), `viewer/Dockerfile` (`python:3.12-slim@sha256:` cùng digest với lõi), `viewer/src/dxos_viewer/{__init__,app,render,png,settings}.py`, `viewer/tests/test_render.py`, `viewer/tests/test_app.py`, `viewer/tests/test_no_disk.py`
- Modify: `viewer/README.md`, `Makefile` (`check` chạy test viewer), CI `unit`

**Interfaces:**
- Produces (đặt sau APISIX, tiền tố `/view`):
  - `GET /view/v1/healthz` → `{"status":"ok"}`;
  - `GET /view/v1/objects/{sha256}/info?variant=` → `{"pages": n}`;
  - `GET /view/v1/objects/{sha256}/pages/{n}.png?variant=` → `image/png`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.

  Biến môi trường `DXOS_VIEWER_API_BASE` (mặc định `http://apisix:9080`), `DXOS_VIEWER_TIMEOUT_S=10`.
- Consumes: `GET /api/v1/objects/{sha}?variant=`, `GET /api/v1/whoami` (`sub`).

- [ ] **Step 1: Test.** Dùng `httpx.MockTransport` làm API giả.
  - `test_no_token_401`: không header `Authorization` → 401, **không** gọi API.
  - `test_api_404_passthrough`: API 404 → viewer 404, thân problem+json, không ảnh.
  - `test_api_timeout_504`.
  - `test_page_out_of_range_404`.
  - `test_png_has_watermark_pixels`:
    - render trang có nền trắng;
    - vùng giữa ảnh có điểm ảnh xám (watermark);
    - chuỗi watermark đúng mẫu P4-D7 (kiểm qua hàm `watermark_text(sub: str, now: datetime) -> str`, có `now` cố định; `watermark_text('0f1e2d3c-…', 2026-12-10T09:05+07) == 'DX-OS 0f1e2d3c 2026-12-10 09:05 ICT'`).
  - `test_huge_page_capped`: ảnh ≤ 4000 px.
  - `test_no_disk_writes`: test tĩnh quét `viewer/src`, cấm `tempfile`, `open(` với chế độ ghi, `.write_bytes`, `.write_text`. Test chạy: `monkeypatch` `builtins.open` để fail nếu mở ghi trong một lần render.
  - `test_token_forwarded_unchanged`: API giả nhận đúng header `Authorization`.
- [ ] **Step 2:** Chạy `python -m pytest viewer/tests -q`. Kỳ vọng FAIL.
- [ ] **Step 3:** Hiện thực.
  - Watermark: chèn text object (phông chuẩn `Helvetica`, cỡ 18, xoay 30°, lặp lưới 3×4, màu xám 35%) vào bản sao trang trong bộ nhớ rồi mới render.
  - PNG mã hóa bằng `png.py` (chép từ lõi kèm cùng test).
  - Khóa PDFium dùng chung một `threading.Lock` trong tiến trình.
- [ ] **Step 4:** Chạy test, PASS. Chạy `reuse lint`, cổng kiểm.
- [ ] **Step 5:** Commit `feat(viewer): stateless RAM-only page renderer with watermark`.

### Task 8: Nối Viewer vào stack p16 và App A (S2)

**Files:**
- Modify:
  - `deploy/compose.yaml` (service `viewer` có `profiles: ["viewer"]`, chỉ `net-app`, `read_only: true`, `tmpfs` không có, `cap_drop: [ALL]`);
  - `deploy/compose.p16.yaml` (bật profile qua `COMPOSE_PROFILES` trong `.env.example` cho p16);
  - `deploy/apisix/apisix.yaml` (route `/view/*` bật, cần JWT như `/api/*`);
  - `deploy/network-matrix.yaml` + `ops/netcheck.py` (hàng của viewer);
  - `apps/phong-ho-so/web/src/components/ViewerDialog.vue` (mới);
  - Caddyfile (CSP `/apps/*` thêm `img-src blob:`);
  - test tương ứng.

**Interfaces:**
- Consumes: endpoint của Task 7.
- Produces: nút "Xem" trong App A, chỉ hiện khi `GET /view/v1/healthz` trả 200.

- [ ] **Step 1: Test.**
  - `tests/infra`/`tests/repo`: service `viewer` chỉ ở `net-app`, không `ports`, `profiles: [viewer]`.
  - Ma trận mạng có `viewer → apisix` mở; `viewer → core-db/seaweedfs/openbao/flowable/clamav` đóng.
  - Route APISIX `/view/*` có plugin JWT giống `/api/*`.
  - Vitest:
    - `ViewerDialog fetches pages as blobs with bearer token and revokes object URLs on close`;
    - `hidden when healthz fails`;
    - `page error shows ProblemMessage`.
  - Test tĩnh CSP: `/apps/*` có `img-src 'self' data: blob:`, vẫn không `unsafe-inline`.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Chạy cổng kiểm. Chạy thật (p16 + `make netcheck` + xem trang có watermark, chụp ảnh) là việc V40.
- [ ] **Step 4:** Commit `feat(viewer): wire viewer into p16 profile, gateway and App A`.

### Task 9: Trang admin web — khung, đăng nhập, Health, Sổ cái (S3)

**Files:**
- Create: `admin-ui/` (workspace `dxos-admin-ui`, cấu trúc như `verify-portal/app`: `package.json` 0.9.0, `vite.config.ts` với `base: '/ui/'`, `src/main.ts`, `src/router.ts`, `src/views/HealthView.vue`, `src/views/LedgerView.vue`, `test/*.test.ts`)
- Modify:
  - `package.json` gốc (`workspaces`), `package-lock.json`;
  - `sdk/js/src/auth.ts` (`createAuth({ clientId?: string = 'dxos-spa', ... })`);
  - `sdk/js/test/auth.test.ts`;
  - `deploy/keycloak/realm-dxos.json`, `realm-dxos-dev.json` (client công khai `dxos-admin-ui`, PKCE S256, redirect `https://admin.${DXOS_DOMAIN}/ui/*`, web origin cùng host);
  - `ops/keycloak_upgrade.py` (tạo client khi thiếu) và test.

**Interfaces:**
- Consumes: Admin API `GET /admin/v1/health`, `GET /admin/v1/ledger/status`, `GET /admin/v1/ledger/entries`, `POST /admin/v1/anchor:run`.
- Produces: SPA ở `/ui/` (hash router, các route `#/health`, `#/ledger`, `#/apps`, `#/quarantine`). Base URL Admin API là cùng origin `/admin/v1`.

- [ ] **Step 1: Test.**
  - SDK: `createAuth uses given clientId and keeps sessionStorage`.
  - Keycloak: `test_realm_has_admin_ui_client_pkce` (cả hai realm), `test_upgrade_creates_admin_ui_client_once`.
  - Vitest:
    - `HealthView shows each dependency with status text, not colour only`;
    - `LedgerView shows tree size, last STH time in Asia/Ho_Chi_Minh, last anchor commit; 'Neo ngay' posts anchor:run once and disables while pending`;
    - `403 from admin API shows 'Tài khoản này không có quyền quản trị'`.
  - `tests/repo/test_web_hygiene.py` tự quét workspace mới. Thêm `admin-ui` vào danh sách nếu test liệt kê cứng.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Chạy `npm run check`, cổng kiểm.
- [ ] **Step 4:** Commit `feat(admin-ui): admin SPA shell with health and ledger views`.

### Task 10: Trang admin web — duyệt app, kiểm dịch, phục vụ qua Caddy (S3)

**Files:**
- Create: `admin-ui/src/views/AppsView.vue`, `admin-ui/src/views/AppDiffView.vue`, `admin-ui/src/views/QuarantineView.vue`, test tương ứng
- Modify: `deploy/caddy/Caddyfile` (khối host admin: `handle_path /ui/*` từ `/srv/apps/admin-ui`, CSP riêng `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`), `ops/build_web.sh` (`DIST_MAP` thêm `admin-ui:admin-ui/dist`), `tests/ops/test_build_web_sh.py`, test Caddy

**Interfaces:**
- Consumes: `GET /admin/v1/apps`, `GET /admin/v1/apps/{id}/versions/{v}/diff`, `POST /admin/v1/apps/{id}:approve` (`{"version"}`), `POST /admin/v1/apps/{id}:disable`, `GET /admin/v1/quarantine`.

- [ ] **Step 1: Test.**
  - `AppsView lists active and pending versions`.
  - `AppDiffView renders diff lines as text (no v-html) and highlights floor changes`.
  - `approve by the submitter shows the server's four-eyes problem message`: máy chủ quyết định; SPA không tự chặn.
  - `disable asks for confirmation with the app id typed`.
  - `QuarantineView lists items newest first with VN time`.
  - Caddy: `/ui/*` chỉ trên host admin và nằm sau danh sách IP admin sẵn có; host công khai `/ui/` → 404 (test cấu hình sống như các test Caddy hiện có).
  - `build_web.sh` chép `admin-ui`.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Chạy cổng kiểm. Chạy thật trên laptop (đăng nhập admin, duyệt `examples/so-muon-sach` bằng hai admin, chụp ảnh) là việc V41.
- [ ] **Step 4:** Commit `feat(admin-ui): app review, quarantine view, served on the admin host`.

### Task 11: Triển khai chỉ nhận tag ký và tự quay lui (S4)

**Files:**
- Create: `deploy/allowed_signers` (ban đầu chỉ có dòng chú thích; khóa thật là việc V42)
- Modify: `ops/deploy.sh`, `tests/ops/test_deploy_sh.py`, `docs/runbook-deploy.md`

**Interfaces:**
- Produces:
  - `ops/deploy.sh <tag> [--allow-unsigned]`.
  - Mã thoát:
    - 0: đạt;
    - 2: từ chối trước khi đổi gì (tag không ký/khóa lạ, cây bẩn, tham số sai);
    - 3: thiếu điều kiện (digest, compose);
    - 4: health hỏng đã quay lui về tag tốt;
    - 5: health hỏng và **không** quay lui được.
  - `deploy/deployments.log` thêm cột `result` (`ok|rolled-back|failed`) và `signed` (`yes|no`).

- [ ] **Step 1: Test** (dùng `git`/`docker`/`curl` giả sẵn có của bộ test).
  - `test_unsigned_tag_refused_before_any_change`: thoát 2, không lời gọi `docker`, không `checkout`.
  - `test_signed_tag_verified_with_allowed_signers`: lệnh `git` được gọi với `-c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag <tag>`.
  - `test_allow_unsigned_logs_warning`: dòng log có `signed=no`.
  - `test_health_fail_rolls_back_to_last_ok`: log có tag tốt trước đó `v0.9.0` → triển khai `v1.0.0` health hỏng → tự gọi lại chuỗi triển khai cho `v0.9.0`, thoát 4, log `rolled-back`.
  - `test_first_deploy_health_fail_no_previous`: không có dòng `ok` nào → thoát 5, in hướng dẫn khôi phục tay.
  - `test_rollback_also_fails_exit_5`.
  - `shellcheck -S warning` sạch.
- [ ] **Step 2:** Chạy `python -m pytest tests/ops/test_deploy_sh.py -q`. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Cập nhật runbook: cách ký tag bằng SSH (`git config gpg.format ssh`, `user.signingkey`, `git tag -s`), thêm khóa vào `deploy/allowed_signers`.
- [ ] **Step 4:** Chạy cổng kiểm. Commit `feat(ops): deploy only signed tags and roll back on failed health`.

### Task 12: Backup mã hóa, khôi phục, diễn tập AT-21 (S4)

**Files:**
- Create: `ops/backup.sh`, `ops/restore.sh`, `ops/at21_drill.sh`, `docs/runbook-backup.md`, `tests/ops/test_backup_restore.py`
- Modify: `docs/acceptance.md` (AT-21 → test và thủ công), `docs/runbook-pii-erasure.md` (thời hạn giữ backup **để trống** cho V21, không điền thay)

**Interfaces:**
- Produces:
  - `ops/backup.sh <thư mục ra>`: tạo `dxos-backup-<UTC>.tar.enc` và `.sha256`. Nội dung: `pg_dump -Fc` của `core-db`, `kc-db`, `flowable-db`; tar volume SeaweedFS và storage OpenBao, lấy qua container `busybox` đã ghim, `--volumes-from`, chỉ đọc. Thoát 0/2/3.
  - `ops/restore.sh <tệp.tar.enc> --project dxos-restore`: kiểm sha256 rồi giải mã **trước**, tạo volume và DB mới **chỉ** dưới project đã cho. Từ chối `--project dxos`.
  - `ops/at21_drill.sh`: backup → restore vào `dxos-restore` → dựng stack restore ở cổng khác (`DXOS_DOMAIN=restore.localhost`) → `dxos-witness verify-bundle` một niêm phong đã chọn **trước** khi backup → so `tree_size` và root.

- [ ] **Step 1: Test** (docker giả ghi lại lời gọi, như `test_deploy_sh.py`).
  - `test_backup_encrypts_and_writes_checksum`: lệnh `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:` trỏ `.secrets/backup-passphrase`; không ghi tệp chưa mã hóa ra thư mục đích.
  - `test_backup_refuses_missing_passphrase_exit_3`.
  - `test_restore_refuses_project_dxos_exit_2`.
  - `test_restore_bad_checksum_stops_before_any_docker_call`.
  - `test_restore_wrong_passphrase_stops_before_volume_create`.
  - `test_drill_compares_tree_size_and_root`.
  - `shellcheck -S warning` sạch cả ba script.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Viết runbook: lịch hằng đêm bằng systemd timer (mẫu trong runbook, không bật mặc định), nơi giữ mật khẩu, cách khôi phục.
- [ ] **Step 4:** Chạy cổng kiểm. Commit `feat(ops): encrypted backup, guarded restore, AT-21 drill script`.
- [ ] **Step 5:** Diễn tập thật trên laptop (p8) và trên VPS là việc V43. Laptop chạy được qua Git Bash; ghi kết quả vào `docs/progress/`.

### Task 13: `make demo-seed` — dữ liệu demo hư cấu

**Files:**
- Create: `ops/demo_seed.py`, `demo/README.md`, `demo/sao-mai/*.pdf` (3 tệp sinh bằng `core/tests/helpers/make_pii_pdf.py`, có CCCD, SĐT hư cấu), `demo/su-kien-clb.csv` (UTF-8 BOM, 12 dòng hư cấu), `tests/ops/test_demo_seed.py`
- Modify: `Makefile` (`demo-seed`), `BUILD.md`

**Interfaces:**
- Consumes: SDK hành vi như E2E (`ops/e2e/run_e2e.sh` lấy token dev bằng `dxos-test`); API Records, tải tệp, `workflow:start`, `:bulk` của App B.
- Produces: `python ops/demo_seed.py [--base https://localhost] [--ca-file F] [--allow-remote]`. Mật khẩu dev chỉ qua `DXOS_E2E_PASSWORD`. Khác `localhost` thì phải `--allow-remote` (như `vuot_rao.py`).

- [ ] **Step 1: Test** (stack giả như `test_vuot_rao.py`).
  - `test_idempotent_by_marker`: lần 2 không tạo trùng; bản ghi có tiêu đề bắt đầu `[DEMO] `.
  - `test_refuses_remote_without_flag`.
  - `test_password_never_on_argv_or_stdout`.
  - `test_csv_is_fictional_marked`: dòng đầu tệp CSV là chú thích hư cấu, hoặc README nói rõ.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Chạy cổng kiểm. Chạy thật trên laptop là việc V44.
- [ ] **Step 4:** Commit `feat(ops): make demo-seed with fictional Sao Mai documents and CLB event`.

### Task 14: Gia cố còn mở từ Plan 03 — ghim SPKI trong bộ live, khớp JS–Python

**Files:**
- Modify: `tests/web/live/helpers.ts`, `tests/web/live/playwright.config.ts`, `ops/web_live.sh`, `sdk/js/src/proof/*.ts`, `sdk/js/test/vectors/*`, `witness/tests/test_web_vectors.py`, `sdk/js/README.md`, `CHANGELOG.md`, `docs/progress/...` mục 13.5

- [ ] **Step 1: Test.**
  - Test tĩnh: `helpers.ts` **không** còn `ignoreHTTPSErrors: true`. `playwright.config.ts` có `--ignore-certificate-errors-spki-list=${DXOS_CADDY_SPKI}`. `web_live.sh` tính SPKI bằng `openssl x509 -pubkey | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64` và truyền `-e DXOS_CADDY_SPKI`. Thiếu biến thì bộ live dừng với lỗi rõ.
  - Vector mới, dùng chung Python và JS:
    - `b64-three-pad`: base64 có 3 dấu `=` sau nhóm đủ, Python nhận thế nào thì JS y vậy;
    - `int-4301-digits`: Python `MALFORMED` thì JS cũng `MALFORMED`.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL (vector mới lệch). Sửa JS cho khớp Python. Chạy lại, PASS.
- [ ] **Step 3:** Bỏ mục "khác biệt đã biết" ở `sdk/js/README.md`, CHANGELOG và 13.5. Chạy cổng kiểm. Chạy bộ live thật là việc V39.
- [ ] **Step 4:** Commit `fix(web): pin Caddy CA SPKI in live suite; close JS/Python verifier gaps`.

### Task 15: Chuẩn bị v0.9.0 (M4)

**Files:**
- Modify: 4 `pyproject.toml` + 3 `__init__.py` + `viewer/pyproject.toml` + `viewer/src/dxos_viewer/__init__.py` (`0.9.0`), `package.json` gốc và mọi workspace (`0.9.0`), `CHANGELOG.md` (mục `[0.9.0] - 2026-MM-DD` gom S1–S4, PoF; ngày = ngày commit), `README.md`, `README_EN.md`, `docs/acceptance.md`, `docs/progress/2026-10-21-tong-ket-tien-do.md` (mục 14: Plan 04), `.github/workflows/release.yml` (đưa wheel `dxos-viewer` và image `viewer` vào release, cùng cách với `trust-core`), `tests/repo/test_docs_m4.py`

- [ ] **Step 1: Test `test_docs_m4.py`.**
  - Mọi phiên bản bằng `0.9.0`.
  - CHANGELOG có mục `[0.9.0]` có ngày, nằm trên `[0.3.0]`.
  - README nêu S1–S4 kèm việc V chưa chạy.
  - Không câu cấm nào của spec 25.1.
  - `docs/acceptance.md` có AT-21 trỏ test thật.
  - `release.yml` có bước cho `viewer`.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Sửa. Chạy lại, PASS. `make openapi`, `make release-check VERSION=0.9.0` (thoát 0 sau khi push).
- [ ] **Step 3:** Chạy cổng kiểm. Commit `chore(release): 0.9.0`. Push, chờ CI xanh, ghi số run.
- [ ] **Step 4:** Đưa trưởng nhóm lệnh tag **ký** (`git tag -s v0.9.0 <sha> -m ...`, `git push origin v0.9.0`). Điều kiện: V18, V33 (v0.2.0, v0.3.0) đã gắn trước.

### Task 16: M5 — máy sạch, bộ demo, nộp bài, chuẩn bị v1.0.0

**Files:**
- Create: `ops/doctor.sh` (kiểm điều kiện máy: Docker ≥ 24, Compose ≥ 2.24, RAM, cổng 443 trống, Node 22 và npm 11.6.2 nếu dựng web), `ops/demo_preflight.sh` (checklist 60 phút của Plan 00 §10: OpenBao unsealed, health xanh, STH mới nhất đã neo, mạng, dữ liệu demo có), `docs/demo/kich-ban.md` (kịch bản 15 phút theo spec 22 và danh sách video V1–V6), `docs/nop-bai.md` (mẫu email theo Đề tr.6, checklist PoF cuối, ghi rõ hạn 17:00 06/12/2026), `tests/ops/test_doctor_sh.py`, `tests/ops/test_demo_preflight_sh.py`, `tests/repo/test_docs_m5.py`
- Modify: `BUILD.md` (mục "Máy Ubuntu 24.04 sạch, từng lệnh"), `docs/at26-checklist.md`, phiên bản `1.0.0`, `CHANGELOG.md` `[1.0.0]`

- [ ] **Step 1: Test.**
  - `doctor.sh` với lệnh giả:
    - Compose 2.23 → thoát 3, nêu rõ;
    - đủ hết → 0;
    - không in bí mật.
  - `demo_preflight.sh`:
    - OpenBao sealed → thoát 1 kèm lệnh mở khóa trong runbook (không tự mở khóa);
    - STH mới nhất chưa neo → cảnh báo.
  - `test_docs_m5.py`:
    - email mẫu đúng tiêu đề `BÀI THI PMNM 2026 - [Tên Đội] - [Tên Trường]` và địa chỉ của Đề tr.6;
    - checklist có dòng "tag v1.0.0 trước khi gửi email";
    - kịch bản demo không câu cấm 25.1 và có câu thống nhất 25.1 nguyên văn.
- [ ] **Step 2:** Chạy test. Kỳ vọng FAIL. Hiện thực. Chạy lại, PASS.
- [ ] **Step 3:** Ghi việc V cho M5:
  - V45 AT-23: người ngoài đội dựng trên máy sạch theo `BUILD.md`;
  - V46 AT-26: người ngoài đội theo `docs/tutorial-app-30-phut.md` (thay V31);
  - V47: quay 6 video;
  - V48: tập demo 5 lần;
  - V49: hai thành viên còn lại commit đều (tiêu chí SCM của spec 20.2; agent **không** thể làm thay);
  - V50: tag ký `v1.0.0` trước 04/12, gửi email sáng 06/12.
- [ ] **Step 4:** Nâng phiên bản `1.0.0`, CHANGELOG `[1.0.0]` (đóng băng mã: chỉ sửa lỗi sau commit này). Chạy cổng kiểm. Commit `chore(release): 1.0.0`, chờ CI xanh, đưa trưởng nhóm lệnh tag ký.

---

## Việc ngoài mã (gom vào bảng V khi tới task)

| V | Việc | Ở đâu |
|---|---|---|
| V37 | `python ops/pin_actions.py` rồi `make pin-images` (thêm syft, gitleaks), commit | Máy trưởng nhóm |
| V38 | Thiết lập repo nếu API bị chặn (topic, nhãn, Pages) | Trưởng nhóm |
| V39 | Bộ live có ca PII và SPKI | Máy trưởng nhóm |
| V40 | Viewer trên p16, `make netcheck`, ảnh watermark | Máy p16 (laptop đủ RAM hoặc VPS) |
| V41 | Admin UI: đăng nhập, duyệt app bằng hai admin, ảnh | Laptop |
| V42 | Khóa SSH ký tag của trưởng nhóm vào `deploy/allowed_signers` | Trưởng nhóm |
| V43 | Diễn tập AT-21 thật | Laptop rồi VPS |
| V44 | `make demo-seed` thật | Laptop |
| V45–V50 | Như Task 16 Step 3 | Người ngoài đội, cả đội |
| (V13 cũ) | Witness độc lập ngoài GitHub của đội (MUST, spec 11.4) — vẫn thiếu người | Trưởng nhóm tìm người |

## Thứ tự và cắt giảm

- Thứ tự thực hiện: 1 → 2 → 3 → 4 → 5 → 6 → 9 → 10 → 11 → 12 → 7 → 8 → 13 → 14 → 15 → 16.
  - S2 xếp sau S3, S4 vì p8 không có Viewer và rủi ro tài nguyên cao nhất.
- Thiếu thời gian thì cắt theo spec 18.3:
  1. S2 (Task 7–8);
  2. S4 phần backup (Task 12);
  3. S3 phần duyệt app (Task 10).

  S1 giữ, vì đây là ưu tiên 1. Task 15–16 không cắt.
