<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Tổng kết tiến độ DX-OS Trust Core — 21/10/2026

*Đội PSA_OVNCR · Kho mã: https://github.com/PSA-OVNCR/dxos (public, Apache-2.0) · Cập nhật đến commit `56bac6e`.*
*Thay cho bản 20/10 (`2026-10-20-tong-ket-tien-do.md`, giữ lại làm lịch sử).*

## 1. Tóm tắt trong 30 giây
- **Plan 01 (M0 → M1): xong phần mã của cả 17 task.** Task 1–6 và 8–16 đã xong; Task 7 (đo RAM) dời sang VPS;
  Task 17 còn chạy lại E2E trên VPS và gắn tag `v0.1.0`.
- Lõi Tầng 1 đã có: SSO/JWT, kho manifest, PDP + che PII, Records API, tải tệp → kiểm dịch → kho theo nội dung,
  sổ cái Merkle, STH ký qua OpenBao, neo lên repo git, công cụ witness độc lập.
- Test ở cloud (`56bac6e`): **258** test đơn vị, **178** integration (PostgreSQL 16, SeaweedFS, OpenBao 2.2.0 thật), **18** witness.
  CI 5 job xanh.
- Chạy thật trên Docker Desktop: Task 8 đạt; E2E Task 17 đạt **4/5**, test luồng chính chưa chạy được vì Windows Defender
  (`docs/progress/2026-10-20-task17-e2e.md`).
- **22/10, máy trưởng nhóm (Docker Desktop, p16 + `compose.e2e.yaml`, commit `ea96323`): E2E M1 + M2 đạt 13/13, AT-20 bỏ qua**,
  gồm cả luồng chính M1 (EICAR → neo → witness) (`docs/progress/2026-10-22-e2e-m2-docker-desktop.md`).

## 2. Mốc thời gian
| Mốc | Ngày | Nội dung chính | Trạng thái |
|---|---|---|---|
| M0 | 26/10 | Hạ tầng chạy được, đo RAM, spike Flowable | Gần xong: thiếu đo RAM và chạy trên VPS |
| **M1** | **09/11** | Lõi Tier-0 phần 1, release **v0.1.0** | **Đã phát hành v0.1.0 (22/10)**; còn E2E trên VPS |
| M2 | 16/11 | v0.2.0: guard + BPMN, niêm phong, installer, App A và B cài bằng manifest, witness độc lập | **Mã xong (cloud)**: Plan 02 15/15 task + review toàn nhánh; còn việc VPS và tag v0.2.0 (mục 12) |
| M3 | 23/11 | v0.3.0: SDK, SPA A và B, cổng đối soát, triển khai VPS theo tag | Chưa bắt đầu |
| M4 | 30/11 | v0.9.0: SHOULD, chạy thử với người dùng, tài liệu + SBOM | Chưa bắt đầu |
| M5 | 04/12 | v1.0.0, máy sạch, đóng băng mã | Chưa bắt đầu |
| Nộp bài | 17:00 06/12 | Điểm PoF chấm theo hiện trạng kho lúc gửi (G16) | |
| Chung kết | 10/12 | Chỉ demo 15 phút (Đề tr.7) | |

## 3. Plan 01: từng task
| Task | Nội dung | Commit | Bằng chứng |
|---|---|---|---|
| 1–3 | Khung PoF; canonical JSON; Merkle RFC 6962 | `65130b4`…`07bdd38` | CI xanh |
| 4 | Compose 9 mạng, Caddy, APISIX, netcheck | …`f07815e` | 13/13 healthy, netcheck 30/30 (`task4-kiem-tra-song.md`) |
| 5 | Realm Keycloak `dxos` | …`79016d0` | 10/10 token (`task5-realm-keycloak.md`) |
| 6 | Spike Flowable | …`9d98631` | SMOKE OK (`docs/spikes/flowable.md`) |
| **7** | **Đo RAM (AT-22)** | `34d1c10` (công cụ) | **Dời sang VPS** (Ruling của người dùng, 20/10) |
| 8 | Khung trust-core (FastAPI + worker), migration, 2 role DB, trigger chỉ-thêm | `ee72b95`, `82d97c2` | Chạy thật trên Docker Desktop (`task8-trust-core.md`) |
| 9 | Ghi ledger: chỉ số liên tục dưới khóa advisory, kiểm cả chuỗi | `aad846d` | 50 lượt ghi song song đúng `0..49` (`task9-ledger.md`) |
| 10 | Identity: kiểm JWT chỉ RS256, ánh xạ `app:<id>:<role>`, `/api/v1/whoami` | `9982fed` | Test đơn vị + integration |
| 11 | Schema manifest, validator (sàn an toàn, không gian tên), kho manifest | `19406fb` | Test; spec lên 1.0.2 |
| 12 | PDP (`decide`/`enforce`), che PII, từ chối được ghi ledger | `68beb4a` | Test |
| 13 | Records API (tạo, đọc, sửa, liệt kê, số hiệu tự tăng) | `37004ff` | Test |
| 14 | Tải tệp → ClamAV trước, kiểm PDF sau → kho theo nội dung hoặc cách ly; hàng đợi việc trên PostgreSQL | `61e95f0` | Test với SeaweedFS thật |
| 15 | STH ký ed25519 qua OpenBao transit; `/verify/v1/sth/*`, `/keys` | `26f34de` | Test với OpenBao 2.2.0 thật |
| 16 | Neo STH lên repo git có bảo vệ nhánh; gói `dxos-witness`; API quản trị neo | `90eb048` | 18 test witness |
| 17 | E2E M1, `release.yml`, `nightly.yml`, nạp manifest tạm | `a4175b8` | E2E 4/5 (xem mục 1) |
| — | Sửa 10 lỗi từ rà soát độc lập | `28b114b` | Test mới đỏ trên mã cũ, xanh sau sửa |
| — | Ghi giải đáp BTC G14–G17; runbook neo | `56bac6e` | — |

### 3.1. 10 lỗi tìm được khi rà soát toàn bộ (đã sửa ở `28b114b`)
1. Witness bỏ sót trường hợp server viết lại phần lịch sử **đã neo** → giờ kiểm cả chuỗi STH đã neo.
2. Tệp tạm bị xóa trước khi DB commit, lần thử lại sẽ kẹt → chỉ xóa sau commit.
3. Tạo/sửa bản ghi có thể trả PII rõ mà không ghi ledger → tạo luôn che; sửa chỉ hiện rõ qua đường có ghi `field.revealed`.
4. Khai `pii` trên trường không phải chuỗi thì không che được → validator chặn; ngày kiểm regex chặt.
5. Token OpenBao của lõi không được gia hạn → worker gia hạn mỗi giờ.
6. Mỗi lần đẩy neo lỗi lại ký một STH mới → lưu `tree_size` vào việc, thử lại dùng đúng STH cũ.
7. Lệnh git không có timeout → 120 s, kèm tùy chọn ssh.
8. Tải tệp giữ kết nối DB suốt lúc nhận dữ liệu → nhả kết nối; thiếu Content-Length trả 411; APISIX giới hạn 20 MB.
9. Quyền đọc khóa deploy trong container → bước `chown 10001` + `chmod 0400` trong `docs/runbook-anchor.md`.
10. Vòng lặp worker thoát khi DB lỗi → bắt lỗi trong từng vòng.

## 4. Chưa xong hoặc chưa kiểm chứng
- **E2E luồng chính** (tải EICAR + PDF sạch → cách ly/CAS → ledger → STH → neo → witness): chưa chạy đầu-cuối. Chạy trên VPS.
- **Hồ sơ p16 với ClamAV thật**: chưa chạy trên stack (CI ban đêm `nightly.yml` sẽ chạy integration với ClamAV thật, chưa thấy lượt nào).
- **`pytest -m infra tests/infra` (AT-01)**: mới chạy bằng script PowerShell tương đương, chưa chạy bằng pytest trên Linux.
- **Đo RAM (AT-22)**: chưa có số.
- **Repo neo thật** `dxos-transparency-log` + ruleset + khóa deploy + ảnh minh chứng AT-18: chưa tạo (việc của trưởng nhóm, `docs/runbook-anchor.md`).
- **Tag `v0.1.0`**: chưa gắn. Gắn tag là hành động công khai, cần trưởng nhóm đồng ý; nên gắn sau khi E2E trên VPS đạt.

## 5. Việc chỉ trưởng nhóm làm được
| Việc | Hạn đề xuất | Ghi chú |
|---|---|---|
| Tạo repo neo, ruleset, khóa deploy, chụp ảnh AT-18 | trước 09/11 | `docs/runbook-anchor.md` |
| Tìm **witness độc lập** (người/tổ chức ngoài đội chạy `dxos-witness`) | trước 16/11 | `witness/template/` |
| Dựng VPS 16 GB; chạy Claude Code trên VPS | sớm nhất có thể | Rồi chạy Task 7 + E2E Task 17 |
| Quyết định gắn tag `v0.1.0` | sau E2E trên VPS | Plan hẹn 09/11 |
| Đăng ký qua trường, có giảng viên (G5) | | |

## 6. Điểm chưa rõ với BTC: không hỏi thêm, đã chốt cách làm
- `.zip` tự sinh có bị trừ "định dạng không mở" (TL tr.2)? → luôn đính kèm `.tar.gz`.
- Điểm trừ PoF có dừng ở 0? → coi như không; rà đủ checklist PoF trước hạn.
- Chấm theo commit cuối hay theo tag (G16)? → gắn tag `v1.0.0` trước khi gửi email, ghi tag trong email; PoF xong trước 17:00 06/12.
- Release chỉ cần tag hay cả trang Release (G17)? → làm cả hai (tag + tar.gz, SBOM, wheel).
- "Tổng quát nhất" có đòi đa thuê bao (G14)? → mỗi tổ chức một bản cài; đa thuê bao là hướng phát triển.

## 7. Quyết định cần trưởng nhóm xem lại (trích ledger, đầy đủ ở `docs/handoff/ledger-plan01.md`)
- Spec 1.0.2: `so_hieu` có `public: true`; `access.update` mặc định `[owner]` khi manifest không khai.
- `tree_heads` không có cột `anchor_commit`; neo ghi vào bảng riêng `anchors` (chỉ-thêm).
- Migration chạy lúc trust-core-api khởi động, rồi xóa thông tin đăng nhập owner khỏi tiến trình
  (vẫn thấy được qua `docker inspect`; trên VPS có thể tách thành job chạy một lần).
- Tệp bị từ chối (không phải PDF, có mật khẩu, không có lớp chữ) cũng chuyển vào kho cách ly, không xóa.
- Neo là tùy chọn qua `DXOS_ANCHOR_REMOTE`; không cấu hình thì STH vẫn được ký nhưng không neo.
- Witness ghim khóa theo từng phiên bản; đổi khóa cùng phiên bản bị coi là chữ ký sai.

## 8. Việc tiếp theo
1. **Viết Plan 02 (M2, hạn 16/11)**: workflow bridge + BPMN, danh mục guard, niêm phong, installer + CLI `dxos`, App A và B cài bằng manifest.
   Có thể làm ngay ở cloud, không cần VPS.
2. Khi có VPS: Task 7 (đo RAM), E2E Task 17 trên p16, rồi gắn tag `v0.1.0`.
3. Cổng năng suất M1 (Plan 00 mục 8) ghi vào `docs/progress/2026-11-09.md`.

## 9. Thành viên
| GitHub | Vai trò trong tổ chức |
|---|---|
| UI-UX-USHP | Owner, trưởng nhóm |
| Levminh | Owner (mời 20/10) |
| kirito99152 (Cao Thanh Phong) | Owner (mời 20/10) |

Không chia vai TV-A/B/C: cả đội làm chung (người dùng quyết 20/10).

## 10. Bắt đầu nhanh
```bash
git clone https://github.com/PSA-OVNCR/dxos && cd dxos
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
make dev-install && make check                    # ruff + REUSE + 258 test đơn vị
make test-db-up && DXOS_TEST_REQUIRE_DB=1 make test-integration
cp .env.example .env && make up PROFILE=dev-lite
```
Chi tiết: `BUILD.md`, `docs/runbook-openbao.md`, `docs/runbook-anchor.md`.

---

## 11. Plan 02 (M2) — cập nhật 21/10/2026 23:00

*Chạy bằng subagent, mỗi task qua review (spec + chất lượng) và sửa xong mới đóng. Mọi commit đã push lên main.*

| Task | Nội dung | Commit cuối | Trạng thái |
|---|---|---|---|
| 1 | Manifest 1.0.3: revoke_roles, tham số guard, nhãn, đánh số theo năm | `15003fa` | Xong |
| 2 | Migration 003+004: bảng workflow/niêm phong, salt theo bản ghi, bằng chứng xóa PII, chống bảng tạm che bảng thật | `c57e006` | Xong |
| 3 | Bộ kiểm BPMN theo danh sách cho phép, lõi tự dựng lại BPMN rồi mới deploy | `4e37fb5` | Xong |
| 4 | Client Flowable (kiểm với Flowable 7.1.0 thật) | `2e81007` | Xong |
| 5 | Danh mục guard | `762d42a` | Xong |
| 6 | Cầu nối workflow: ý định + đối soát, khóa theo bản ghi, bất biến chống lệch Flowable/DB | `2ac5789` | Xong |
| 7 | Niêm phong (ảnh chụp), thu hồi, xóa PII, tuyên bố khóa | `d25bd40` | Xong |
| 8 | API kiểm tra công khai, gói bằng chứng, khóa công khai + tuyên bố khóa lên repo neo | `cdb8f21` | Xong |
| 9 | `dxos-witness verify-bundle` (AT-17, AT-28) | `d7e06b2` | Xong |
| 10 | Trang kiểm tra tối giản (WebCrypto, CSP chặt); sửa lỗi Plan 01: danh sách IP admin không có hiệu lực | `fbf074c` | Xong |
| 11 | Keycloak: service account installer, client `dxos-cli`, script nâng cấp realm | `3b2c0e6` | Xong |
| 12 | Installer, duyệt bốn mắt, health, quarantine; chặn `/admin` trên host công khai | `2666311` | Xong |
| 13 | CLI `dxos` (device flow, refresh token gắn server) | `616a95b` | Xong |
| 14 | BPMN + manifest 1.1.0 App A/B, AT-14 quét toàn bộ image lõi | `cb8e2a2` | Xong |
| 15 | E2E M2 (viết sẵn, chạy trên VPS), AT-13 script, release GHCR, OpenAPI, tài liệu pháp lý/manifest/runbook xóa PII | `d17c755` | Xong phần cloud |
| — | Review toàn nhánh (model mạnh nhất) + 1 vòng sửa (treo pool kết nối; nâng cấp sau disable lọt luật P2-D14; 10 lỗi nhỏ) | `2b78542` | Xong |

Test gần nhất (`2b78542`): `make check` 1125 passed (không cảnh báo), integration 409 passed, witness 86, CLI 145; CI GitHub xanh. Sổ quyết định đầy đủ: `docs/handoff/plan02/ledger.md` — chạy ở cloud không có Docker (PostgreSQL 16, OpenBao 2.2.0, SeaweedFS, Flowable 7.1.0, Keycloak 26.3.0, Caddy 2.10.0 chạy trực tiếp).

## 12. Việc cần VPS / trưởng nhóm làm sau (gom từ Plan 02)

| # | Việc | Ở đâu | Vì sao chưa làm ở cloud |
|---|---|---|---|
| V1 | Chạy `python ops/keycloak_upgrade.py` (prod) và `--profile dev-lite` (dev stack); chạy 2 lần, lần 2 phải "không thay đổi gì" | VPS + dev stack | Keycloak bỏ qua import khi realm đã có; nhánh `docker exec` chỉ mới unit test |
| V2 | Lấy secret client `dxos-installer` trong Keycloak → đặt vào `.env` (`DXOS_INSTALLER_CLIENT_SECRET`) → tạo lại `trust-core-api` | VPS + dev stack | Secret thật không được vào repo |
| V3 | Nếu mật khẩu bootstrap admin đã đổi: chạy script với `--admin-user` | VPS | — |
| V4 | Đặt `DXOS_ORG_NAME` (tên thật của tổ chức) và `DXOS_ORG_ID`; lõi **từ chối niêm phong** khi tên trống/mặc định/bắt đầu bằng `changeme` | VPS | Tên ghi vĩnh viễn vào tuyên bố khóa (chỉ thêm, đã neo) |
| V5 | Kiểm `trust-core-api` gọi được `http://keycloak:8080/auth/admin/realms/dxos` khi bật `KC_HOSTNAME*` của prod | VPS | Cloud không có Docker |
| V6 | Kiểm APISIX định tuyến đúng `…/seals/{id}:check` và `:bundle` (dấu `:` trong đường dẫn) | dev-lite/VPS | Chỉ kiểm qua Caddy → uvicorn |
| V7 | Kiểm `remote_ip` của Caddy thấy IP thật sau Docker (danh sách IP admin vừa được sửa để có hiệu lực) | VPS | — |
| V8 | Chụp lại ảnh + `curl` trang `/apps/verify/` trên dev-lite/VPS (ảnh hiện có lấy từ Caddy + uvicorn không Docker) | dev-lite/VPS | — |
| V9 | ~~Xem lần chạy CI đầu của job `caddy-live`~~ — đã xanh trên GitHub (21/10) | — | Xong |
| V10 | Flowable phải giữ history level ≥ `audit` (mặc định); bất biến chống lệch dựa vào lịch sử Flowable | VPS | — |
| V11 | Task bị xóa thẳng trên console Flowable sẽ làm bản ghi bị chặn (`workflow-inconsistent`) — cần người xử lý tay; đừng thao tác trên console Flowable | VPS | Chủ ý an toàn |
| V12 | Đồng bộ `witness/template/README.md` sang repo `PSA-OVNCR/dxos-witness-kit` | GitHub | Repo riêng, chưa gắn vào phiên |
| V14 | Kiểm `dxos login` (device flow) và tự làm mới token với Keycloak thật | VPS / dev-lite | Chỉ test bằng server giả |
| V15 | Quyết định: E2E trên VPS cần tạm thêm user dev (mật khẩu đã biết, có 2 admin) + client `dxos-test`; lệnh thêm/gỡ ở `docs/evidence/README.md` (lệnh gỡ chưa chạy thử) | Trưởng nhóm | Rủi ro bảo mật trên host công khai |
| V16 | ~~Chạy lại `ops/keycloak_upgrade.py --profile dev-lite` trên dev stack~~ — đã chạy 22/10 trên máy trưởng nhóm, lần 2 "không thay đổi gì" | — | Xong |
| V17 | E2E M2: **phần A xong 22/10** trên Docker Desktop (13 passed, `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`); AT-20 chạy 22/10 trên máy trưởng nhóm: phần 503 + Flowable không bị tác động **đạt**, bước mở khóa lại của test hỏng (sửa ở `40d6d64`, chưa chạy lại); còn phần B trên VPS p16 (AT-19, AT-20) | VPS | Lệnh đầy đủ ở `docs/handoff/vps-checklist-plan02.md` |
| V18 | Gắn tag v0.2.0: nâng version 4 gói lên 0.2.0, `make openapi`, điền ngày CHANGELOG, rồi tag (job `check` chặn nếu thiếu) | Trưởng nhóm | Hành động công khai; sau v0.1.0 |
| V19 | Sau lần đẩy image đầu: đặt package `trust-core` trên GHCR là public (hoặc `docker login ghcr.io` trên VPS); ghi digest vào `LICENSES-THIRD-PARTY.md` | GitHub / VPS | Hành động công khai |
| V20 | AT-13 trên VPS với image đã phát hành (`ops/at13_reuse.sh`), hai thành viên khác nhau nộp/duyệt, `DXOS_ALLOW_SELF_APPROVAL=false` | VPS | Cần image GHCR |
| V21 | `docs/legal-mapping.md`: từng thành viên đọc toàn văn từng điều và tự điền tên + ngày; điền cột "Điểm" của Điều 14 k1 và chốt thời hạn giữ backup trong `docs/runbook-pii-erasure.md` | Cả đội | Không được để agent điền thay |
| V22 | VPS phải dùng Docker Compose ≥ 2.24 (overlay phát hành dùng `!reset`) | VPS | Lỗi CI 21/10 cho thấy phụ thuộc phiên bản |
| V23 | Cổng năng suất M2: viết `docs/progress/2026-11-16.md` sau khi V17–V20 xong | Trưởng nhóm | Không ghi kết quả chưa chạy |
| V24 | Bật NTP trên VPS (lệch giờ giữa API và worker làm niêm phong bị báo "khóa hết hạn", job sẽ thử lại) | VPS | — |
| V25 | Viết runbook xử lý bản ghi bị chặn `workflow-inconsistent` (task bị xóa/hoàn thành ngoài lõi trên Flowable) | Trưởng nhóm | Cần quyết định nghiệp vụ |
| V26 | Chụp lại minh chứng trang `/apps/verify/`: tiêu đề giờ là "Hợp lệ — chưa neo công khai" cho tới khi STH được neo; kịch bản demo phải tính tới | dev-lite / VPS | Tài liệu minh chứng cũ còn tiêu đề "Hợp lệ" |
| V13 | (Từ Plan 01) Task 7 đo RAM; E2E Task 17 trên VPS; ~~tag `v0.1.0`~~ (trưởng nhóm gắn 22/10 trên `5b14e7c`+`7247fe8`, Release có tar.gz, SBOM, 3 wheel); repo neo + ruleset + khóa deploy + ảnh AT-18; witness độc lập; duyệt giấy phép pypdfium2; duyệt push GHCR | VPS / trưởng nhóm | Hành động công khai hoặc cần máy thật |
