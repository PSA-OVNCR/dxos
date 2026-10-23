# Changelog

Mọi thay đổi đáng kể được ghi tại đây, theo định dạng [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/) và [Semantic Versioning](https://semver.org/lang/vi/).

## [Unreleased]

## [0.9.0] - 2026-10-23
Mốc M4: các việc SHOULD S1 (phát hiện PII và bản che), S2 (Viewer có watermark), S3 (trang quản trị web), S4 (tag ký, tự quay
lui, sao lưu mã hóa và diễn tập khôi phục) và các chỗ trống PoF (ghim phụ thuộc, quét giấy phép, kiến trúc, dữ liệu demo).
Mã đã qua test đơn vị và integration ở cloud (không có Docker, VPS hay Keycloak thật); **không việc nào ở mục "Known
limitations" đã chạy thật** (V37 đến V44). Gắn tag `v0.9.0` sau `v0.2.0` (V18) và `v0.3.0` (V33). Có một thay đổi phá vỡ
tương thích của SDK (mục Changed, "BREAKING").

### Added
- **S1: dò dữ liệu cá nhân trong PDF (Plan 04 Tasks 3 đến 5)**. `dxos_core.pii.detect` (không thêm phụ thuộc, P4-D1) dò CCCD
  (12 chữ số, ba số đầu 001 đến 096), số điện thoại (`0[35789]` cộng 8 chữ số, hoặc `+84`) và số tài khoản (8 đến 19 chữ số, phải có
  từ khóa "STK", "số tài khoản" trong 30 ký tự trước), bỏ qua mã số thuế; chỉ đọc lớp chữ của PDF (không OCR) và là heuristic: dải
  001 đến 096 chưa đối chiếu với danh mục tỉnh của Thông tư 07/2016/TT-BCA. Việc nền `pii_detect` chạy sau khi tệp qua kiểm dịch
  (CLEAN), tối đa 200 trang mỗi tệp, ghi `pii_scans` và `pii_findings` (migration 006: vị trí và loại, **không** giá trị và **không** hash,
  I5) và lá ledger `pii.detected` (chỉ `sha256`, số lượng theo loại, `detector`). Guard `pii_reviewed` chờ quét xong
  (409 `pii_scan_pending`); `:pii-review` tự xếp việc quét cho tệp CLEAN chưa có kết quả, quét hỏng thì ghi `FAILED` để người rà tay.
- **S1: bản che và kiểm soát bản gốc**. Việc nền dựng bản che là PDF chỉ chứa ảnh (150 dpi, tối đa 4000 × 4000 px mỗi trang; không còn
  chữ, chú thích hay siêu dữ liệu), ghi từng trang bằng zlib của thư viện chuẩn nên RAM bị chặn bởi trần dưới đây, không tăng theo số trang. Trần dung lượng
  bản che **100 MiB**: vượt thì dừng chắc chắn, đánh dấu không có bản che (migration 009) và bản gốc vẫn khóa. `GET
  /api/v1/objects/{sha}?variant=redacted` trả bản che; `variant=original` chỉ cho người có `reveal_pii`, trừ khi tệp đã quét xong
  và không có phát hiện nào (quét chưa xong, hỏng, quá lớn hay có phát hiện đều khóa). Migration 007 (cột `pii_scans.redacted_sha256`),
  008 (chuyển liên kết sang bảng chỉ-thêm `pii_redactions`, bỏ cột đó, thêm việc `pii_redact` thử lại khi dựng bản che hỏng), 009
  (`pii_redaction_skips`). Danh sách tệp đính kèm
  có thêm `pii` (trạng thái, số phát hiện, số theo loại CCCD, SĐT, STK; chỉ số, không giá trị).
- **S1: giao diện App A**: panel PII (trong SDK) hiện "Phát hiện N dữ liệu cá nhân (CCCD n, SĐT n, STK n)", nút tải bản che và
  bản gốc (chỉ người có quyền), và danh sách trạng thái từng tệp trong bước rà soát.
- **S2: dịch vụ Viewer `dxos-viewer` (Plan 04 Task 7)**: gói Python riêng (FastAPI, PDFium qua pypdfium2; không phụ thuộc
  `dxos-core`), không trạng thái, chỉ RAM, không ghi đĩa (test tĩnh cấm `tempfile` và `open(..., "w")` trong `viewer/src`). Lấy
  PDF qua API bằng chính token của người gọi, dựng **một trang** thành PNG 110 dpi (tối đa 4000 × 4000 px, 200 trang, tệp
  `DXOS_VIEWER_MAX_BYTES` mặc định 64 MiB), đóng watermark (chú thích của PDF được dán phẳng vào nội dung trước nên không che được
  nó) rồi trả ảnh với `Cache-Control: no-store`. Điểm vào `/view/v1/healthz`, `/view/v1/objects/{sha}/info`,
  `/view/v1/objects/{sha}/pages/{n}.png`; lỗi dạng `problem+json` (401 giữ 401; API 5xx hoặc không nối được là 502, quá hạn là 504,
  mọi lỗi 4xx khác là 404, không bao giờ có ảnh nếu API không trả 200). Watermark `DX-OS <8 ký tự đầu của sub> <ngày giờ> ICT`
  **chỉ để răn đe**: không ngăn chụp màn hình. `viewer/Dockerfile` chạy user không phải root, ghim bằng `constraints.txt`.
- **Nối Viewer vào p16 và App A (S2, Plan 04 Task 8)**: dịch vụ `viewer` trong compose (profile `viewer`, bật bằng
  `COMPOSE_PROFILES=viewer` trong `.env.example`; p8 và dev-lite không bao giờ dựng), chỉ `net-app`, không cổng, `read_only`
  không tmpfs/volume, `cap_drop: [ALL]`, `no-new-privileges`, giới hạn 768 MiB RAM không swap, 1 CPU, 128 tiến trình
  (PDFium không hủy được giữa chừng); route APISIX `/view/*` bật với cùng chuỗi OIDC bearer và `limit-req` như `/api/v1/*`,
  cắt sau 30 giây; ma trận mạng thêm `viewer` và `profile_only`. App A có nút "Xem" (chỉ hiện khi `GET /view/v1/healthz`
  trả 200) và `ViewerDialog` (ảnh PNG qua blob: URL, thu hồi khi đổi trang/đóng); SDK thêm `viewerAvailable`, `viewInfo`,
  `viewPage`; CSP của `/apps/*` thêm `blob:` vào `img-src`, vẫn không `unsafe-inline`. Watermark chỉ để răn đe.
  Chưa chạy thật trong container (V40).
- `ops/deploy.sh` chỉ triển khai **tag đã ký SSH** (`git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers
  verify-tag`, kiểm trước mọi lệnh `docker` và trước `checkout`; `--allow-unsigned` cho cấp cứu, ghi `signed=no`) và **tự quay
  lui** về bản tốt gần nhất khi health hỏng (S4); tên trong thân tag ký phải khớp tên ref (chặn đổi tên tag ký cũ), checkout theo OID
  đã giải, `compose pull` chạy trước bước dựng SPA. Mã thoát 0/2/3/4/5; `deploy/deployments.log` thêm cột `result`
  (`ok|rolled-back|failed`) và `signed`, dòng kiểu cũ vẫn đọc được. `deploy/allowed_signers` mới chỉ có chú thích, khóa thật
  là việc V42 nên cho tới đó mọi tag bị từ chối nếu không dùng `--allow-unsigned`. Mới kiểm bằng `git`, `docker`, `curl` giả.
- **Sao lưu mã hóa, khôi phục có chốt chặn, diễn tập AT-21 (S4, P4-D9)**: `ops/backup.sh <thư mục ra>` (`pg_dump -Fc` ba DB, tar hai
  volume qua busybox ghim digest chỉ đọc, mã hóa `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt` với `.secrets/backup-passphrase`,
  ghi kèm `.sha256`; không có tệp chưa mã hóa ở thư mục ra), `ops/restore.sh <gói> --project <tên>` (kiểm sha256, giải mã và kiểm
  gói trước mọi lệnh docker; từ chối `--project dxos`; chỉ tạo tài nguyên của project được chỉ định) và `ops/at21_drill.sh`
  (sao lưu, khôi phục vào `dxos-restore`, dựng lõi ở `restore.localhost`, `dxos-witness verify-bundle` rồi so `tree_size` và root).
  Container seaweedfs được `docker pause` đúng lúc tar volume của nó (unpause bằng bẫy EXIT); `TMPDIR` phải nằm ngoài thư mục ra;
  diễn tập đọc lại khóa công khai (`/verify/v1/keys`) và tệp đính kèm từ OpenBao/SeaweedFS đã khôi phục.
  `docs/runbook-backup.md` có mẫu systemd timer (không bật mặc định). Không có xác thực MAC riêng (sha256 ghi kèm bù một phần);
  thời hạn giữ gói chờ V21; mới kiểm bằng `docker` và `dxos-witness` giả với `openssl` thật, diễn tập thật là V43.
- `ARCHITECTURE.md` (tóm tắt kiến trúc, trỏ về spec), trang tài liệu GitHub Pages (`docs/index.md`, `docs/_config.yml`; chưa bật, V38),
  `docs/capacity.md` (chỉ số có nguồn đo), `.github/ISSUE_TEMPLATE/config.yml` (tắt issue trống, trỏ Discussions), mục
  "Thành viên đóng góp" trong `CONTRIBUTING.md`.
- `make build`, `make sbom VERSION=x` (syft cùng image với workflow release, ra `dist/sbom-x.cdx.json`) và
  `make release-check VERSION=x` (`ops/release_check.py`, chỉ đọc, không gắn tag).
- **S3: trang quản trị web `/ui/` (Plan 04 Tasks 9 và 10)**: workspace `admin-ui` (Vue 3, đăng nhập OIDC PKCE qua client Keycloak mới
  `dxos-admin-ui`, token trong `sessionStorage`, CSP riêng không `unsafe-inline`, không `v-html`) do Caddy phục vụ **chỉ trên host
  quản trị** (`DXOS_ADMIN_HOST`, giới hạn IP như API quản trị; `/ui/` trên host công khai trả 404). Màn hình: Sức khỏe hệ thống,
  Sổ cái (xem lá, "Neo ngay"), Ứng dụng (danh sách, diff quyền giữa phiên bản chờ duyệt và đang chạy kèm đánh dấu thay đổi sàn
  chính sách, duyệt bốn mắt: người nộp bấm duyệt nhận câu giải thích; vô hiệu hóa phải gõ đúng mã ứng dụng) và Cách ly (tệp bị từ
  chối hoặc nhiễm mã độc). Chỉ gọi API quản trị hiện có; không thêm endpoint lõi.
- **S4: chỉ triển khai tag đã ký, tự quay lui (Plan 04 Task 11)**. `ops/deploy.sh` chỉ triển khai **tag đã ký SSH** (`git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers
  verify-tag`, kiểm trước mọi lệnh `docker` và trước `checkout`; `--allow-unsigned` cho cấp cứu, ghi `signed=no`) và **tự quay
  lui** về bản tốt gần nhất khi health hỏng; tên trong thân tag ký phải khớp tên ref (chặn đổi tên tag ký cũ), checkout theo OID
  đã giải, `compose pull` chạy trước bước dựng SPA. Mã thoát 0/2/3/4/5; `deploy/deployments.log` thêm cột `result`
  (`ok|rolled-back|failed`) và `signed`, dòng kiểu cũ vẫn đọc được. `deploy/allowed_signers` mới chỉ có chú thích, khóa thật
  là việc V42 nên cho tới đó mọi tag bị từ chối nếu không dùng `--allow-unsigned`. Mới kiểm bằng `git`, `docker`, `curl` giả.
- **Sao lưu mã hóa, khôi phục có chốt chặn, diễn tập AT-21 (S4, P4-D9)**: `ops/backup.sh <thư mục ra>` (`pg_dump -Fc` ba DB, tar hai
  volume qua busybox ghim digest chỉ đọc, mã hóa `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt` với `.secrets/backup-passphrase`,
  ghi kèm `.sha256`; không có tệp chưa mã hóa ở thư mục ra), `ops/restore.sh <gói> --project <tên>` (kiểm sha256, giải mã và kiểm
  gói trước mọi lệnh docker; từ chối `--project dxos`; chỉ tạo tài nguyên của project được chỉ định) và `ops/at21_drill.sh`
  (sao lưu, khôi phục vào `dxos-restore`, dựng lõi ở `restore.localhost`, `dxos-witness verify-bundle` rồi so `tree_size` và root).
  Container seaweedfs được `docker pause` đúng lúc tar volume của nó (unpause bằng bẫy EXIT); `TMPDIR` phải nằm ngoài thư mục ra;
  diễn tập đọc lại khóa công khai (`/verify/v1/keys`) và tệp đính kèm từ OpenBao/SeaweedFS đã khôi phục.
  `docs/runbook-backup.md` có mẫu systemd timer (không bật mặc định). Không có xác thực MAC riêng (sha256 ghi kèm bù một phần);
  thời hạn giữ gói chờ V21; mới kiểm bằng `docker` và `dxos-witness` giả với `openssl` thật, diễn tập thật là V43.
- **Phát hành Viewer cùng cách với `trust-core` (Plan 04 Task 15, ruling R28)**: workflow `release` có job `image-viewer` (dựng
  `viewer/Dockerfile`, đẩy `ghcr.io/psa-ovncr/viewer:X.Y.Z`, digest ghi vào mô tả Release và tệp `viewer-image-X.Y.Z.txt`), thêm
  wheel `dxos-viewer`, và bước `check` kiểm cả `viewer/pyproject.toml` lẫn `dxos_viewer/__init__.py`. `deploy/compose.release.yaml`
  thay `build:` của `viewer` bằng image theo digest (`DXOS_VIEWER_DIGEST`; để mặc định là chuỗi không phải digest nên p8 và dev-lite
  không phải đặt một digest không dùng, còn p16 thiếu digest thì không có `build` để rơi về). `ops/deploy.sh` đọc
  `viewer-image-X.Y.Z.txt` từ Release như digest lõi, chỉ khi hồ sơ p16 bật `viewer` và overlay của tag có `DXOS_VIEWER_DIGEST` (tag
  cũ không có Viewer vẫn quay lui được); thiếu hoặc sai digest thì thoát 3 trước khi gọi compose. `ops/release_check.py` và
  `make release-check` kiểm 5 gói Python. Chưa chạy một Release thật có Viewer (V40, V29).
- **PoF: ghim phụ thuộc và quét giấy phép (Plan 04 Task 1)**: `constraints.txt` ghim 44 phụ thuộc Python chạy thật (Dockerfile của lõi
  và Viewer, `make dev-install` và CI cài theo nó); `ops/license_scan.py` (`make licenses`, job CI `licenses`) quét giấy phép của
  closure runtime và lockfile npm, đối chiếu "Ngoại lệ đã duyệt" trong `LICENSES-THIRD-PARTY.md` (MPL-2.0 như `certifi` và
  `lightningcss`, BlueOak-1.0.0, MIT-0, CC0-1.0, 0BSD; trưởng nhóm duyệt 23/10, V30); `ops/pin_actions.py` (`make pin-actions`) ghim
  `uses:` của workflow theo SHA commit (24 dòng đã ghim, CI xanh).
- **PoF: dữ liệu demo hư cấu (Plan 04 Task 13)**: `make demo-seed` tạo ba văn bản `[DEMO]` của "Công ty TNHH Sao Mai" với PDF
  hư cấu có CCCD, SĐT, STK (mỗi số ghi "hư cấu") cho App A và 12 chứng nhận `[DEMO] Sự kiện CLB` cho App B (`demo/`, UTF-8 BOM);
  chạy lại không tạo trùng (khóa theo tiền tố `[DEMO] `), không duyệt hay niêm phong, từ chối máy chủ ngoài localhost nếu không có
  `--allow-remote`, mật khẩu chỉ từ `DXOS_E2E_PASSWORD`. App B chưa cài thì bỏ qua (`--only a|b`).
- `ARCHITECTURE.md` (tóm tắt kiến trúc, trỏ về spec), trang tài liệu GitHub Pages (`docs/index.md`, `docs/_config.yml`; chưa bật, V38),
  `docs/capacity.md` (chỉ số có nguồn đo), `.github/ISSUE_TEMPLATE/config.yml` (tắt issue trống, trỏ Discussions), mục
  "Thành viên đóng góp" trong `CONTRIBUTING.md`.
- `make build`, `make sbom VERSION=x` (syft cùng image với workflow release, ra `dist/sbom-x.cdx.json`) và
  `make release-check VERSION=x` (`ops/release_check.py`, chỉ đọc, không gắn tag).

### Changed
- **BREAKING (SDK `dxos-sdk-js`, Plan 04 Task 6)**: `client.download(...)` đã bị **bỏ**, thay bằng
  `client.downloadObject(sha256, variant = 'original')` trả `Blob`; `variant` là `'original'` hoặc `'redacted'`. Gọi
  `client.download` sẽ lỗi `TypeError`. Mã Tầng 2 ngoài kho phải đổi lời gọi. SDK còn thêm `viewerAvailable()`, `viewInfo()` và
  `viewPage()` cho Viewer. Gói vẫn `private: true` (chưa công bố lên npm).
- `variant=original` của tệp đính kèm giờ bị khóa bằng `reveal_pii` ở bộ sưu tập có dò PII (xem mục S1 ở trên); trước Plan 04
  không có cổng này, người đọc được bản ghi tải được bản gốc.
- Migration `006_pii_scans.sql`, `007_pii_redacted.sql`, `008_pii_redactions.sql`, `009_pii_redaction_skips.sql` (đều chạy tự động khi
  `trust-core-api` khởi động, role `dxos_owner`; `dxos_core` chỉ có SELECT và INSERT trên các bảng mới). Chưa kiểm trên CSDL đã có dữ liệu thật.
- Biến môi trường mới hoặc đổi nghĩa: `DXOS_ADMIN_HOST` (bắt buộc; Caddy, Keycloak và trang quản trị dùng cùng một host, nên **được
  truyền cho Keycloak** để redirect của client `dxos-admin-ui` khớp; stack dựng từ trước cần thêm biến, tạo lại container keycloak
  và chạy lại `python ops/keycloak_upgrade.py`, xem V41); `COMPOSE_PROFILES=viewer` trong `.env.example` (bật Viewer ở p16; p8 và
  dev-lite luôn bỏ qua); `DXOS_VIEWER_API_BASE`, `DXOS_VIEWER_TIMEOUT_S`, `DXOS_VIEWER_MAX_BYTES` (cấu hình của container Viewer, đặt
  sẵn trong compose); `DXOS_VIEWER_DIGEST` (chỉ cho `deploy/compose.release.yaml`, mục Added).
- Cổng đối soát và `verifyBundle` khớp hơn với `dxos-witness` (mục Fixed).
- Phiên bản mọi gói lên `0.9.0`: 5 gói Python (`dxos-proof`, `dxos-core`, `dxos-witness`, `dxos-cli`, `dxos-viewer`), `package.json`
  gốc và mọi workspace (`sdk/js`, `verify-portal/app`, `apps/*/web`, `examples/*/web`, `admin-ui`), `package-lock.json`, `docs/api/openapi.json`.

### Fixed
- **Cổng đối soát không còn báo "Không hợp lệ" cho niêm phong vừa ban hành (Plan 04 Task 14, R11)**: ở chế độ ghim
  (`VITE_ANCHOR_RAW_BASE`), niêm phong mà STH phủ nó chưa lên repo neo bị báo `NOT_ANCHORED: STH đã neo (cỡ 754) chưa phủ lá 791`
  (laptop trưởng nhóm 23/10, `docs/progress/2026-10-23-anchor-lab-github.md`). `verifyBundle` có tùy chọn
  `allowPendingAnchor` (mặc định tắt, nên vẫn chặt như `dxos-witness verify-bundle --anchor-dir`, ruling C8) trả
  `ok: true, pinned: true, pendingAnchor: true` cho ba trường hợp "chưa neo kịp" (gói không có `anchored`, STH đã neo chưa phủ lá,
  repo neo chưa có `sth/<n>.json`); cổng bật tùy chọn này và hiện "Hợp lệ — chưa neo công khai" kèm lời nhắc kiểm lại sau vài phút.
  Khóa phải khớp repo neo; chữ ký, inclusion, consistency vẫn kiểm đủ; `sth/<n>.json` đã có trong repo mà khác gói vẫn là
  "Không hợp lệ". Test App A trên trình duyệt thật chấp nhận nhãn này (chạy thật: V39).
- **Bộ Playwright live ghim SPKI của CA Caddy thay cho `ignoreHTTPSErrors`**: `ops/web_live.sh` tính SPKI của CA gốc và CA trung
  gian bằng `openssl`, truyền `DXOS_CADDY_SPKI`; cấu hình đưa vào `--ignore-certificate-errors-spki-list` và dừng với lỗi rõ khi
  thiếu biến. Chạy thật trên Chromium là V39.
- **`verifyBundle` (JS) khớp `dxos-witness verify-bundle` (Python) ở hai chỗ còn lệch**: base64 nhận nhiều dấu `=` thừa sau nhóm
  đủ như `b64decode(validate=True)` (vector `b64-three-pad`, `b64/validate.json`) và số nguyên dài hơn 4300 chữ số làm gói
  `MALFORMED` (vector `int-4301-digits`).
- **Phát hiện PII bỏ sót số nằm cạnh số thứ tự hoặc ngày**: các nhóm chữ số nối bằng `.` hoặc `-` là một khối, còn nhóm cách bằng
  khoảng trắng hoặc xuống dòng có thể tách, nên CCCD trong bảng có cột STT vẫn được thấy (hướng sai là che thừa, không phải sót);
  mã số thuế đứng sau "MST" không bị gán thành SĐT hay CCCD.
- Quét PII và bản che không còn làm worker hết bộ nhớ: bản che ghi từng trang (RAM tăng 107 MB thay vì 1,3 GB khi thử với PDF 200
  trang nhiễu), tệp hỏng được đánh dấu `FAILED` thay vì thử mãi, mọi loại PII đều được quét bất kể manifest xin loại nào (một app
  xin ít loại hơn không còn mở bản gốc cho người không có quyền), và `MemoryError` không bị nuốt.
- `ops/deploy.sh` không chấp nhận tag ký của bản cũ đẩy lại dưới tên mới; `ops/at21_drill.sh` thật sự đọc lại khóa và tệp từ OpenBao và
  SeaweedFS đã khôi phục (không chỉ so `tree_size`); `make demo-seed --only a|b` coi App B chưa cài là bỏ qua.
- Trang quản trị: nút duyệt luôn ở đúng phiên bản đang xem diff (không duyệt bản chưa xem), mọi lỗi 403 đi qua `ProblemMessage`.

### Security
- Giá trị PII và hash của chúng **không bao giờ** vào `pii_findings`, `pii_scans` hay sổ cái (I5, P4-D2): lá `pii.detected` chỉ có
  `sha256`, số lượng theo loại và tên bộ dò; bản che là ảnh nên không còn lớp chữ để trích ngược.
- Viewer chỉ ở `net-app`, đi vào lõi duy nhất qua APISIX bằng token của người gọi, không thấy kho dữ liệu, Flowable, OpenBao (ma
  trận mạng và `make netcheck`); container `read_only` không tmpfs, `cap_drop: [ALL]`, `no-new-privileges`, 768 MiB RAM không swap.
  Watermark chỉ để răn đe, không phải biện pháp chống rò rỉ.
- Triển khai chỉ nhận tag đã ký bằng khóa trong `deploy/allowed_signers`, tên trong thân tag phải khớp ref; sao lưu mã hóa AES-256-CBC
  (PBKDF2 600000 vòng) kèm sha256, `ops/restore.sh` từ chối project `dxos` và kiểm gói trước mọi lệnh docker. Chữ ký tag **không phủ**
  digest image (lấy từ GitHub Release); giới hạn đã ghi ở `docs/runbook-deploy.md` mục 2.
- Trang quản trị có CSP riêng không `unsafe-inline`, chỉ phục vụ trên host quản trị có IP allow-list; ghim `uses:` của workflow theo SHA.

### Known limitations
**Chưa chạy ở bất kỳ nơi nào ngoài cloud** (mã chỉ được kiểm bằng test đơn vị, integration, Vitest/jsdom, `docker compose config`,
và các lệnh giả). Việc cần làm ghi ở `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 14.
- **V37**: `make pin-images` cho `anchore/syft` và `zricethezav/gitleaks` trong workflow (cần Docker buildx); ghim `uses:` theo SHA đã xong.
- **V38**: chủ đề repo và GitHub Pages bị proxy cloud chặn (403), trang `https://psa-ovncr.github.io/dxos/` chưa tồn tại; chưa dựng thử Jekyll.
- **V39**: bộ Playwright live có ca PII và ghim SPKI của CA Caddy chưa chạy trên Chromium thật.
- **V40**: Viewer chưa chạy trong container (chưa dựng image, `read_only` thật, `make netcheck`, ảnh watermark, đo RAM); chưa có Release
  nào kèm image Viewer nên đường `viewer-image-X.Y.Z.txt` của `ops/deploy.sh` chưa chạy thật.
- **V41**: trang quản trị chưa chạy với Keycloak thật (đăng nhập từ host quản trị, lệch issuer, luồng duyệt bằng hai quản trị viên).
- **V42**: chưa có khóa SSH ký tag trong `deploy/allowed_signers`, nên `ops/deploy.sh` từ chối mọi tag (trừ `--allow-unsigned`); chưa
  chạy với tag ký thật hay ép health hỏng để xem tự quay lui trên VPS.
- **V43**: diễn tập AT-21 (`ops/at21_drill.sh`) chưa chạy trên Docker thật; khôi phục thật vào project `dxos` khi mất máy chủ chưa có
  script (`ops/restore.sh` từ chối cố ý), thời hạn giữ gói chờ V21, lịch systemd chưa bật.
- **V44**: `make demo-seed` chưa chạy với Keycloak, lõi và ClamAV thật.
- Các việc của bản 0.3.0 vẫn còn: `ops/deploy.sh` trên VPS (V29), OpenTimestamps trên VPS (V32), AT-26 (V31), repo neo thật cho cổng
  đối soát (V34), package GHCR (`trust-core`, `viewer`) còn Private (V19).
- Bộ dò PII là heuristic trên lớp chữ của PDF: không OCR (PDF quét ảnh không có phát hiện nào), không dò số cố định `02x`, số `84...`
  không có dấu `+`, hay số dính liền chữ cái; có thể che thừa. Bản che có trần 100 MiB (PDF nhiều ảnh màu lớn có thể không có bản che,
  khi đó chỉ người có `reveal_pii` mở được bản gốc). Sự cố kéo dài qua hết số lần thử của việc quét đánh dấu tệp `FAILED` vĩnh
  viễn (rà tay, ghi chú vận hành chưa viết).
- Viewer chưa có giới hạn thời gian dựng trang riêng (chỉ giới hạn của container và `timeout.read` 30 giây của route APISIX); mọi lời gọi từ
  Viewer vào APISIX dùng chung một bucket `limit-req` (khóa theo `X-Forwarded-For`).
- Sao lưu: tar SeaweedFS được `docker pause` để đồng nhất, tar OpenBao là bản sao nóng; không có xác thực MAC riêng cho gói.
- `tests/deploy/browser/verify_page_checks.js` (bộ Playwright riêng của trang đối soát tối giản) vẫn dùng `ignoreHTTPSErrors`; việc tiếp theo.
- Gói npm `dxos-sdk-js` chưa công bố lên npm (`private: true`).

## [0.3.0] - 2026-10-23
Mốc M3 (Tầng 1 hoàn tất cho client: SDK, hai ứng dụng Tầng 2 có giao diện, cổng đối soát Vue, triển khai theo tag).
Mã đã qua test đơn vị, integration và Playwright với API giả ở cloud, và đã chạy trên stack dev ở máy trưởng nhóm
(Docker Desktop); **chưa chạy trên VPS** (mục "Known limitations"). Gắn tag `v0.3.0` sau `v0.2.0` (V18 rồi V33).

### Added
- **Ba endpoint chung cho client Tầng 2** (không chứa định danh app nào): `GET /api/v1/apps/{app}/manifest` (phần
  manifest an toàn cho client, kèm giá trị `decision` của từng task đọc từ BPMN đã triển khai; người không có vai trò
  của app nhận 404 và lá `policy.denied`), `GET .../records/{rid}/attachments` (liệt kê tệp đính kèm, quyền như đọc
  bản ghi, không ghi `field.revealed`) và `GET /admin/v1/ledger/entries` (các lá ledger mới nhất, chỉ `dxos-admin`).
  `docs/api/contract-tier2.md`: hợp đồng HTTP của lõi đối chiếu theo mã, cập nhật cho ba endpoint này.
- **SDK `dxos-sdk-js`** (`sdk/js/`, npm workspace; chưa công bố lên npm): client HTTP `DxosClient` (`If-Match` luôn
  lấy từ một lần GET ngay trước, không tự thử lại yêu cầu ghi), đăng nhập OIDC Authorization Code + PKCE `createAuth`
  (token chỉ nằm trong `sessionStorage`, làm mới single-flight), bộ kiểm gói bằng chứng trên trình duyệt `verifyBundle`
  (dịch từng bước `dxos-witness verify-bundle`, hai bên chạy chung một bộ vector), thành phần Vue
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

### Fixed
- Lỗi chỉ lộ khi chạy thật trên Docker Desktop + Git Bash (22/10): `ops/web_build_docker.sh` lấy commit build bằng
  `git rev-parse` trong repo; `ops/web_live.sh` cài phụ thuộc test dù image Playwright kèm Node 24
  (`npm_config_engine_strict=false`); hai test live của App A chờ đúng URL văn bản và chọn tệp PDF trước khi đòi "Hợp lệ".
- Neo: worker từ chối đẩy STH qua bản clone đang trỏ remote khác `DXOS_ANCHOR_REMOTE` (`PUSH_FAILED`), thay vì lặng lẽ
  đẩy vào repo neo cũ; đổi repo neo thì đặt `DXOS_ANCHOR_REPO_DIR` mới (`docs/runbook-anchor.md`).
- `NODE_IMAGE` và `PLAYWRIGHT_IMAGE` ghim theo digest (V35).

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
Đã chạy trên stack dev (Docker Desktop, máy trưởng nhóm, 22–23/10/2026): `make web-build`, bộ Playwright live 10/10
(V27), `ops/vuot_rao.py` 10/10 (V28), AT-20 (V36), E2E M1 + M2 13 passed trên mã M3 (`docs/progress/2026-10-22-web-live.md`);
hồ sơ p8 đỉnh 5 080 MiB (`docs/progress/2026-10-22-p8-ram-laptop.md`); biên nhận OpenTimestamps với calendar thật, `ots verify`
tới khối Bitcoin 972609 (`docs/progress/2026-10-22-ots-laptop.md`); neo lên repo GitHub thử, AT-18 và AT-17 đạt
(`docs/progress/2026-10-23-anchor-lab-github.md`). Workflow `release` đã dựng `dxos-web-X.Y.Z.tar.gz` trên Actions khi gắn
`v0.2.0`. Các mục dưới đây **chưa chạy**; việc cần làm ghi ở `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 13.
- `ops/deploy.sh` mới được kiểm bằng `git`, `docker`, `curl` giả, chưa chạy trên VPS (V29).
- Biên nhận OpenTimestamps: chưa bật trên VPS (V32). Test đối chiếu với client chính thức (`DXOS_OTS_CLIENT=ots`) chưa chạy.
- Cổng đối soát chỉ đối chiếu repo neo khi build có `VITE_ANCHOR_RAW_BASE` và `.env` có `DXOS_ANCHOR_RAW_ORIGIN` khớp nhau. Với
  repo neo GitHub thử, bộ trình duyệt mới đạt 8/10 vì chạy cùng phút với lần neo đầu; chưa chạy lại, repo neo chính trên VPS
  chưa nối (V34). AT-26 (người ngoài đội làm theo hướng dẫn) chưa tổ chức (V31).
- Phần mềm build có giấy phép MPL-2.0, BlueOak-1.0.0,
  MIT-0, CC0-1.0 (`mdn-data`) chỉ nằm trong công cụ build, không vào bundle; chờ trưởng nhóm xác nhận (V30).
- Gói npm `dxos-sdk-js` chưa công bố lên npm (`private: true`); ứng dụng dùng SDK qua npm workspace.

## [0.2.0] - 2026-10-22
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
