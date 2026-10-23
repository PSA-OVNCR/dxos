<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Tổng kết tiến độ DX-OS Trust Core — 21/10/2026

*Đội PSA_OVNCR · Kho mã: https://github.com/PSA-OVNCR/dxos (public, Apache-2.0) · Mục 1–12 cập nhật đến commit `56bac6e` (Plan 01) và Plan 02 (mục 11–12); mục 13 (Plan 03) xem bên dưới.*
*Thay cho bản 20/10 (`2026-10-20-tong-ket-tien-do.md`, giữ lại làm lịch sử).*
*Mục 13 (Plan 03, M3) cập nhật 22/10/2026 đến commit `4d7e0f1` (đợt sửa sau review cuối toàn nhánh).*
*Mục 14 (Plan 04, M4) cập nhật 23/10/2026 (commit `chore(release): 0.9.0`).*

## 1. Tóm tắt trong 30 giây
- **Cập nhật 23/10: Plan 04 (M4, v0.9.0) có mã xong ở cloud, chưa gắn tag; chưa việc nào của V37 đến V44 chạy thật.** Gồm S1 (dò PII và bản che), S2 (Viewer), S3 (trang quản trị), S4 (tag ký, tự quay lui, sao lưu AT-21) và chỗ trống PoF. Xem mục 14 (task, số test, việc V, các ruling R1 đến R28).
- **Cập nhật 22/10: Plan 03 (M3, v0.3.0) có mã xong ở cloud, chưa gắn tag; đã chạy trên stack dev ở máy trưởng nhóm** (web-build, Playwright live 10/10, vượt rào 10/10, AT-20; `docs/progress/2026-10-22-web-live.md`), chưa chạy trên VPS. Xem mục 13 (task, số test, việc V27–V36). Các gạch đầu dòng còn lại của mục này là hiện trạng cũ của Plan 01.
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
| M3 | 23/11 | v0.3.0: SDK, SPA A và B, cổng đối soát, triển khai VPS theo tag | **Mã xong (cloud)**: Plan 03 15/15 task đã qua review; review cuối toàn nhánh: 4 Important đã sửa ở `4d7e0f1`; **chưa gắn tag**; còn việc máy thật V27–V36 (mục 13) và tag `v0.3.0` sau `v0.2.0` (V33) |
| M4 | 30/11 | v0.9.0: SHOULD, chạy thử với người dùng, tài liệu + SBOM | **Mã xong (cloud)**: Plan 04 task 1 đến 15 đã qua review (task 16 thuộc M5, chưa làm); **chưa gắn tag** (trưởng nhóm gắn tag ký sau `v0.2.0`, `v0.3.0`); còn việc máy thật V37 đến V44 (mục 14) |
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
| V17 | E2E M2: **phần A xong 22/10** trên Docker Desktop (13 passed, `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`); AT-20 chạy 22/10 trên máy trưởng nhóm: phần 503 + Flowable không bị tác động **đạt**, bước mở khóa lại của test hỏng (sửa ở `40d6d64`, chạy lại đạt 22/10: V36); còn phần B trên VPS p16 (AT-19, AT-20) | VPS | Lệnh đầy đủ ở `docs/handoff/vps-checklist-plan02.md` |
| V18 | ~~Gắn tag v0.2.0~~ — trưởng nhóm gắn 23/10 trên `f111969`; workflow `release` run 39890214075 xanh (check, image, release); Release có tar.gz mã nguồn, `dxos-web-0.2.0.tar.gz`, SBOM, 4 wheel; image `ghcr.io/psa-ovncr/trust-core@sha256:96cd2c07…322e3e` | — | Xong |
| V19 | Sau lần đẩy image đầu: đặt package `trust-core` (và từ `v0.9.0` cả package `viewer`) trên GHCR là public (hoặc `docker login ghcr.io` trên VPS); ghi digest vào `LICENSES-THIRD-PARTY.md`. 23/10: image `0.2.0` đã lên GHCR nhưng package vẫn **Private** | GitHub / VPS | Hành động công khai, không đảo lại được (GitHub không cho đổi package public về private) |
| V20 | AT-13 trên VPS với image đã phát hành (`ops/at13_reuse.sh`), hai thành viên khác nhau nộp/duyệt, `DXOS_ALLOW_SELF_APPROVAL=false` | VPS | Cần image GHCR |
| V21 | `docs/legal-mapping.md`: từng thành viên đọc toàn văn từng điều và tự điền tên + ngày; điền cột "Điểm" của Điều 14 k1 và chốt thời hạn giữ backup trong `docs/runbook-pii-erasure.md` | Cả đội | Không được để agent điền thay |
| V22 | VPS phải dùng Docker Compose ≥ 2.24 (overlay phát hành dùng `!reset`) | VPS | Lỗi CI 21/10 cho thấy phụ thuộc phiên bản |
| V23 | Cổng năng suất M2: viết `docs/progress/2026-11-16.md` sau khi V17–V20 xong | Trưởng nhóm | Không ghi kết quả chưa chạy |
| V24 | Bật NTP trên VPS (lệch giờ giữa API và worker làm niêm phong bị báo "khóa hết hạn", job sẽ thử lại) | VPS | — |
| V25 | Viết runbook xử lý bản ghi bị chặn `workflow-inconsistent` (task bị xóa/hoàn thành ngoài lõi trên Flowable) | Trưởng nhóm | Cần quyết định nghiệp vụ |
| V26 | Chụp lại minh chứng trang `/apps/verify/`: tiêu đề giờ là "Hợp lệ — chưa neo công khai" cho tới khi STH được neo; kịch bản demo phải tính tới | dev-lite / VPS | Tài liệu minh chứng cũ còn tiêu đề "Hợp lệ" |
| V13 | (Từ Plan 01) Task 7 đo RAM (laptop p8 đã đo 22/10: đỉnh 5 080 MiB = 62% của 8 GB, `docs/progress/2026-10-22-p8-ram-laptop.md`; còn VPS/p16); E2E Task 17 trên VPS; ~~tag `v0.1.0`~~ (trưởng nhóm gắn 22/10 trên `5b14e7c`+`7247fe8`, Release có tar.gz, SBOM, 3 wheel); repo neo + ruleset + khóa deploy + ảnh AT-18 (repo thử `dxos-transparency-log-lab` 22/10: AT-18 đạt, AT-17 với GitHub đạt, `docs/progress/2026-10-23-anchor-lab-github.md`; còn repo chính với khóa deploy của VPS); witness độc lập; duyệt giấy phép pypdfium2; duyệt push GHCR | VPS / trưởng nhóm | Hành động công khai hoặc cần máy thật |

---

## 13. Plan 03 (M3) — cập nhật 22/10/2026

*Chạy bằng subagent trên main; 15/15 task đã qua review; review cuối toàn nhánh: 4 Important đã sửa ở `4d7e0f1`. Từng task được review (spec + chất lượng) và sửa xong mới đóng; báo cáo review cuối: `.superpowers/sdd/2026-10-22-dxos-03-tier1-m3/final-review.md`. Sổ điều phối từng quyết định: `.superpowers/sdd/2026-10-22-dxos-03-tier1-m3/progress.md`; báo cáo từng task cùng thư mục (`task-N-report.md`). Dựng ở cloud không có Docker, VPS hay Keycloak thật: mọi thứ cần chúng nằm ở bảng V-việc bên dưới, **không** tính là đã kiểm.*

### 13.1. Từng task
Cột "Review" ghi kết quả vòng đầu và số vòng sửa. "Test" là số liệu do chính task báo lúc đóng, không phải số cuối (số cuối ở 13.2).

| Task | Nội dung | Commit | Bằng chứng (test) | Review |
|---|---|---|---|---|
| 1 | Lõi: xem manifest cho client, liệt kê tệp đính kèm, `GET /admin/v1/ledger/entries`; `contract-tier2.md` | `552bbc9` | 4 unit + 21 integration mới (RED rồi GREEN) | Duyệt, không phải sửa |
| 2 | npm workspace, job CI `web`, SDK `DxosClient` (`If-Match`, không tự thử lại) | `7969a5c` | 32 test client | Duyệt, không phải sửa |
| 3 | SDK: đăng nhập OIDC PKCE, làm mới single-flight; ghim jsdom 29.1.1 | `ab2c862`, `854cc3e` | 20 test auth | Duyệt, không phải sửa |
| 4 | SDK: tự kiểm gói bằng chứng trên trình duyệt, vector dùng chung Python/JS | `c39d25c` | JS 111 test + Python (`witness/tests/test_web_vectors.py`) cùng một bộ vector | Duyệt (model mạnh), không phải sửa |
| 5 | SDK: thành phần Vue (trạng thái kiểm dịch, QR, liên kết đối soát, biểu mẫu, thông báo lỗi) | `575bc7a`, `927c324` | 224 test SDK lúc đóng; test đối chiếu `CORE_SLUGS` với mã lõi | Duyệt, không phải sửa |
| 6 | Cổng đối soát Vue `/apps/verify/` (AT-25); trang tối giản chuyển sang `/apps/verify-lite/` | `9956cf9`, `1b908dc` | 39 test cổng; Playwright (API giả) 15 passed | Vòng đầu **Critical**: lỗi repo neo hạ gói giả xuống "chưa đối chiếu"; **1 vòng sửa** (thăm dò khóa cố định trước khi rơi về không ghim; kiểm tệp khi chờ STH) rồi duyệt |
| 7 | App A: danh sách, tạo, tệp kèm có trạng thái kiểm dịch, nộp duyệt | `1797f1b`, `ed906c6`, `9839fca`, `55e65b9` | 48 test App A lúc đóng | Vòng đầu **Important**: trang trắng khi không bắt đầu được đăng nhập; **1 vòng sửa** rồi duyệt |
| 8 | App A: hộp việc, rà soát và xóa PII, niêm phong có QR, thu hồi, Sổ đăng ký văn bản đi | `fd2803d` | 109 test App A | Duyệt, không phải sửa |
| 9 | App B: nhập CSV (BOM, CP1258, UTF-16, `;`), duyệt lô, giấy chứng nhận, trang in; chuyển phần dùng chung vào SDK | `c73200f`, `7f91890`, `1c9853e` | App B 101 test, SDK 249, App A 100 | Duyệt (model mạnh), không phải sửa |
| 10 | `build_web.sh`, `make web-build`, CSP cho `/apps/*`, bộ Playwright live (mặc định bỏ qua) | `eb41734` | 13 + 8 + 8 test script/Caddy; 1 test Caddy 2.10.0 thật; `test:live` bỏ qua 10 test khi không có stack | Duyệt, không phải sửa |
| 11 | `ops/vuot_rao.py` (10 kịch bản) và ma trận `docs/acceptance.md` | `ac17a26`, `9f09d9a` | 54 test `vuot_rao`; `test_at_matrix.py` | Vòng đầu **Important**: nhận mọi 404 là "bị chặn" (✅ giả); **1 vòng sửa** (đòi đúng slug, V8 chờ thì ⚠️) rồi duyệt |
| 12 | `ops/deploy.sh`, `docs/runbook-deploy.md`, tar SPA trong release | `c387591`, `7866088` | 51 test với `git`/`docker`/`curl` giả | Duyệt (không có Critical/Important); **1 vòng sửa** do điều phối quyết định: thiếu `compose pull` (spec 16.3) và biến môi trường kế thừa lấn digest |
| 13 | Hướng dẫn 30 phút, `examples/so-muon-sach`, `docs/at26-checklist.md` | `15c489d`, `aa2ae6c` | 10 test ví dụ; `test_tutorial_docs.py`; tutorial + `tests/apps` 34 passed | Vòng đầu **Important**: lệnh `dxos` thiếu `--ca-file`; **1 vòng sửa** rồi duyệt |
| 14 | Biên nhận OpenTimestamps cho STH đã neo (mặc định tắt) | `1fe265f`, `eeb8af6`, `59758be` | 36 passed + 1 skipped (`core/tests/test_ots.py`), 10 integration, witness 146 | Vòng đầu 2 **Important** (không có hạn tổng với calendar; bộ đọc lỏng hơn bản chính thức); **2 vòng sửa** rồi duyệt |
| 15 | Tài liệu: README (VI, EN), BUILD.md, CHANGELOG `[0.3.0]`, `sdk/js/README.md`, mục này, `tests/repo/test_docs_m3.py` | commit `docs(m3)` ngay sau `59758be` | `test_docs_m3.py` (RED rồi GREEN) | Sạch sau 1 vòng sửa |

### 13.2. Số test cuối (do Task 15 chạy trên commit này, 22/10/2026, cloud không Docker)
- `make check PYTHON=python`: **1511 passed, 6 skipped, 483 deselected** (mã thoát 0; ruff sạch; 5 test Caddy sống bỏ qua vì không có binary `caddy`, 1 test `ots` chính thức bỏ qua).
- `npm run check`: mã thoát 0. SDK **251**, cổng đối soát **39**, App A **100**, App B **101**, ví dụ `so-muon-sach` **10** test (tổng 501); typecheck và build cả 5 workspace đạt.
- `reuse lint`: mã thoát 0, 565/565 tệp có bản quyền và giấy phép.
- Integration (PostgreSQL 16 chạy tại chỗ, `DXOS_TEST_REQUIRE_DB=1 python -m pytest -m integration core/tests/integration`): **445 passed, 1 skipped** (bỏ qua: test trình duyệt cần `DXOS_TEST_BROWSER=1`). Bộ này không gồm test cần Docker (`-m infra`, `-m e2e`).
- Playwright của cổng đối soát (API giả, chạy ở Task 6 với `PW_CHROMIUM` trỏ Chromium có sẵn): 15 passed. Task 15 không chạy lại.
- **Đợt sửa sau review cuối (`4d7e0f1`, 22/10, cloud không Docker; có `shellcheck` 0.11.0 cài tạm trong `.venv`, không ghi vào requirements)**: `make check PYTHON=python` **1531 passed, 6 skipped, 485 deselected** (mã thoát 0); `npm run check` mã thoát 0 (SDK 251, cổng 39, App A 100, App B **106**, `so-muon-sach` 10); `reuse lint` mã thoát 0, 566/566 tệp; integration (PostgreSQL 16, OpenBao, SeaweedFS, Flowable 7.1.0 chạy tại chỗ, `DXOS_TEST_REQUIRE_DB=1 python -m pytest -m integration core/tests/integration`) **447 passed, 1 skipped**.
- **Sau `4d7e0f1`**: `cc1c20f` chặn mặc định mọi tệp `.env*` (kể cả `.env.example`, `.env.bak`, `.env.vps`) khi `ops/web_build_docker.sh` và `ops/web_live.sh` chép nguồn vào container npm (CI run 39703255338 xanh sau khi chạy lại một lần bước cài Playwright bị lỗi); commit kế tiếp cho `ops/build_web.sh` từ chối `<out_dir>` có thành phần `.`/`..` (trừ `.` trần) trước mọi chuẩn hóa, và từ chối thư mục không đọc được (re-review I4).
- **CI**: run `ci` **39701368613** ở commit `4d7e0f1` xanh mọi job (`lint`, `secrets`, `web`, `reuse`, `unit`, `caddy-live`, `integration`). Trước đó job `unit` đỏ từ `c387591` tới `65e67af` vì `shellcheck` mới trên runner báo SC2329 (info) ở `ops/deploy.sh` (review cuối, I1).
- **Chạy trên máy trưởng nhóm 22/10 (Docker Desktop, Git Bash; `docs/progress/2026-10-22-web-live.md`)**: `bash ops/web_build_docker.sh` exit 0; `bash ops/web_live.sh` **10 passed**; `ops/vuot_rao.py` **10/10**, exit 0; E2E trên mã M3 13 passed + AT-20 14 passed. Bốn lỗi chỉ lộ khi chạy thật đã sửa: `15d65b0`, `6d13a0e`, `3056d53`, `395a90b`.
- **Chưa chạy ở bất kỳ nơi nào**: `ops/deploy.sh`, `release.yml` bước dựng SPA, gọi calendar OpenTimestamps thật, test đối chiếu `ots` chính thức (`DXOS_OTS_CLIENT=ots`).

### 13.3. Việc cần máy thật hoặc trưởng nhóm (gom từ Plan 03)
| # | Việc | Ở đâu | Ghi chú |
|---|---|---|---|
| V27 | ~~Chạy `make web-build` và bộ Playwright live cho App A, App B và cổng đối soát; chụp ảnh minh chứng~~ — đã chạy 22/10 trên máy trưởng nhóm: build exit 0, live **10 passed** (`docs/progress/2026-10-22-web-live.md`, ảnh ở `docs/evidence/web-live-2026-10-22/`) | — | Xong trên Windows; chưa chạy trên Linux/VPS. `ignoreHTTPSErrors` đã thay bằng ghim SPKI ở Plan 04 Task 14 (chạy thật: V39) |
| V28 | ~~Chạy `python ops/vuot_rao.py` trên stack dev~~ — đã chạy 22/10 trên máy trưởng nhóm: **10/10 bị chặn đúng**, exit 0 (`docs/progress/2026-10-22-web-live.md`) | — | Xong |
| V29 | Chạy `ops/deploy.sh v0.3.0` (từ `v0.9.0`: `ops/deploy.sh v0.9.0`, kèm digest Viewer) trên VPS sau khi có tag và image GHCR | VPS | Cần Docker Compose ≥ 2.24 (V22), NTP (V24), package GHCR công khai (V19). `docs/runbook-deploy.md` |
| V30 | ~~Xác nhận giấy phép MPL-2.0 (lightningcss, `certifi`), BlueOak-1.0.0, MIT-0, CC0-1.0 (`mdn-data`), 0BSD (`tslib`)~~ — trưởng nhóm duyệt 23/10/2026; ghi ở bảng "Ngoại lệ đã duyệt" của `LICENSES-THIRD-PARTY.md` | — | Xong |
| V31 | Tổ chức AT-26 theo `docs/at26-checklist.md` (người ngoài đội làm hướng dẫn 30 phút) | Trưởng nhóm | Mọi lệnh trong hướng dẫn chưa chạy thật, ghi "chưa kiểm ở cloud — kiểm trong AT-26" |
| V32 | OpenTimestamps: **đã chạy 22/10 trên laptop** với calendar thật và repo neo cục bộ; `ots upgrade` xong, khối Bitcoin 972609, merkle root khớp mempool.space (`docs/progress/2026-10-22-ots-laptop.md`). Còn: bật trên VPS và với repo neo GitHub | VPS | `docs/runbook-anchor.md` mục 6 |
| V33 | Gắn tag `v0.3.0` sau `v0.2.0` (xem 13.4). 23/10: đã nâng 4 gói lên `0.3.0`, `make openapi`, ghi ngày `[0.3.0]` trong CHANGELOG; còn trưởng nhóm gắn tag khi CI xanh ở commit `chore(release): 0.3.0` | Trưởng nhóm | Hành động công khai |
| V34 | Đặt `VITE_ANCHOR_RAW_BASE` (lúc build) và `DXOS_ANCHOR_RAW_ORIGIN` (`.env`, hai giá trị phải khớp) theo repo neo thật khi repo đó có trên GitHub. Laptop 22–23/10 với repo thử: cổng hiện "Hợp lệ — đã đối chiếu repo neo" cho niêm phong App B; niêm phong vừa ban hành mà STH chưa neo bị báo "Không hợp lệ" (lỗi sản phẩm, sửa ở Plan 04 Task 14; `docs/progress/2026-10-23-anchor-lab-github.md`) | VPS | Chưa đặt thì cổng đối soát nói rõ là chưa đối chiếu repo neo |
| V35 | ~~Chạy `make pin-images` trên máy có Docker để ghim digest `NODE_IMAGE` và `PLAYWRIGHT_IMAGE`~~ — đã chạy 22/10 trên máy trưởng nhóm (`ops/pin_images.py`, exit 0); digest commit từ cloud | — | Xong |
| V36 | ~~Chạy lại AT-20 sau bản sửa `40d6d64`~~ — đã chạy 22/10 trên máy trưởng nhóm: **14 passed** gồm AT-20; OpenBao mở khóa lại (`sealed: false`) (`docs/progress/2026-10-22-web-live.md`) | — | Xong |

Các việc V1–V26 của mục 12 vẫn còn hiệu lực (ví dụ V18 tag `v0.2.0`, V21, V22, V24).

### 13.4. Thủ tục gắn tag (việc của trưởng nhóm; Task 15 không gắn và không đổi phiên bản)
Thứ tự: `v0.2.0` (V18) rồi `v0.3.0` (V33). Mỗi tag:
1. `make pin-images` (V35) và commit nếu chưa ghim; image Node phải ghim trước khi chạy `ops/deploy.sh` (V29), vì script dựng SPA bằng Docker. (`release.yml` dựng tar SPA bằng Node trên Actions, không dùng image ghim.)
2. Nâng phiên bản 4 gói Python và 3 tệp `__init__.py` (22/10 đã nâng lên `0.2.0` cho tag `v0.2.0`, 23/10 lên `0.3.0` cho `v0.3.0`; danh sách ở `BUILD.md` mục "Phát hành"), chạy `make openapi`. Các gói web (`package.json` gốc và các workspace) đã ghi `0.3.0` từ Plan 03; workflow không kiểm chúng, nên khi gắn `v0.2.0` chúng vẫn là `0.3.0` (không ảnh hưởng release).
3. Đổi `## [X.Y.Z] - Chưa phát hành` trong `CHANGELOG.md` thành ngày thật (mục `[0.3.0]` đã viết sẵn, mục `[Unreleased]` để trống).
4. `make check PYTHON=python && npm run check && reuse lint` (kiểm bằng mã thoát), commit, push lên `main`.
5. CI xanh ở commit gắn tag (`gh run list -R PSA-OVNCR/dxos --limit 5`; mọi job của run `ci` ở đúng commit đó là `success`).
   Chưa xanh thì không gắn tag: máy cloud và máy trưởng nhóm không có `shellcheck`, CI thì có (review cuối Plan 03, I1).
6. `git tag -a vX.Y.Z -m "…"`, `git push origin vX.Y.Z`.
7. Sau khi Release có: V29 (`ops/deploy.sh vX.Y.Z` trên VPS).

### 13.5. Điểm kỹ thuật còn mở (ghi từ review từng task, chưa sửa; review toàn nhánh Plan 03 đã xem, các mục chịu lực đã sửa ở `4d7e0f1`)
- **Sổ đăng ký (Task 8)**: năm của sổ lấy từ `issued_at` còn bộ đếm `so_hieu` theo năm tạo bản ghi; cần ghi vào runbook.
- **Ma trận AT (Task 11)**: `2026-10-22-e2e-m2-docker-desktop.md` tự mâu thuẫn về AT-19 (bảng ghi PASSED, mục "Chưa làm" ghi chưa); ma trận ghi cả hai, trưởng nhóm cần xác nhận.
- **OpenTimestamps (Task 14)**: thứ tự nhánh khi nhiều biên nhận cùng nút là tất định nhưng không cam kết trùng từng byte với `ots` chính thức (không ảnh hưởng tính hợp lệ).
- Cổng đối soát: nếu GitHub trả được `v1.pub` nhưng lỗi tạm thời ở tệp khác, người dùng thấy "Không hợp lệ" thay vì "chưa đối chiếu" (đánh đổi đã chấp nhận ở Task 6).
- Bộ live đã chuyển `ignoreHTTPSErrors` sang ghim SPKI (Plan 04 Task 14), nhưng `tests/deploy/browser/verify_page_checks.js` (bộ riêng của trang đối soát tối giản) vẫn dùng `ignoreHTTPSErrors`; việc tiếp theo, xem 14.5.
- Ảnh minh chứng trong `docs/evidence/verify-page-*.png` chụp từ trang tối giản; ảnh của cổng Vue (Chromium thật) ở `docs/evidence/web-live-2026-10-22/` (V27).

## 14. Plan 04 (M4–M5)

*Chạy bằng subagent trên `main` (quyết định của trưởng nhóm: push thẳng `main`); task 1 đến 15 đã qua review (spec + chất lượng) và sửa xong mới đóng. Sổ điều phối từng quyết định: `.superpowers/sdd/2026-10-22-dxos-04-should-release/progress.md`; báo cáo từng task cùng thư mục (`task-N-report.md`). Thư mục `.superpowers/` nằm trong `.gitignore` nên không có trên GitHub: mọi quyết định (ruling) được chép đủ ở mục 14.6. Dựng ở cloud không có Docker, VPS hay Keycloak thật: mọi thứ cần chúng nằm ở bảng V (mục 14.3), **không** tính là đã kiểm.*

### 14.1. Từng task
Cột "Review" ghi kết quả vòng đầu và số vòng sửa. Task 16 (M5) chưa làm.

| Task | Nội dung | Commit | Bằng chứng (test) | Review |
|---|---|---|---|---|
| 1 | Ghim phụ thuộc Python (`constraints.txt`), quét giấy phép (`ops/license_scan.py`, job CI `licenses`), ghim `uses:` theo SHA (`ops/pin_actions.py`) | `329e4fc`, `00d438c`, `432283c`, `548921d`, `0f2a7a6` | `test_license_scan.py`, `test_pin_actions.py`, `test_constraints.py`; CI run 39894576708 xanh ở `548921d` | Vòng đầu **Important**: quét giấy phép thoát 0 sau khi quét 0 gói; **1 vòng sửa** (sau 1 lượt sửa theo R6 đến R10) rồi duyệt |
| 2 | `ARCHITECTURE.md`, trang tài liệu, `docs/capacity.md`, `make build/sbom/release-check`, `ops/release_check.py`, nhãn repo | `bfc9d29` (`f8ec5a8` chỉ ghi duyệt V30) | `test_pof_m4.py` 15 passed (RED 14 failed) | Duyệt, không phải sửa; Pages và chủ đề repo bị proxy chặn: V38 |
| 3 | Bộ dò CCCD, SĐT, STK trên lớp chữ PDF | `b203339`, `de80271` | `test_pii_detect.py` 61 test lúc đóng | Vòng đầu 2 **Important** (số hợp lệ cạnh số thứ tự bị bỏ sót; mã số thuế bị gán thành SĐT); **1 vòng sửa** (R14, R15) rồi duyệt |
| 4 | Việc nền `pii_detect`, bảng `pii_scans`, guard chờ quét (migration 006) | `7d9178e`, `dfa7731` | `test_pii_extract.py`, `test_pii_job.py` (10 integration), guard tests | Vòng đầu **Important**: guard có thể chặn vĩnh viễn; **1 vòng sửa** (R16) rồi duyệt |
| 5 | Bản che chỉ-ảnh, `variant=redacted`, bản gốc khóa bằng `reveal_pii` (migration 007 đến 009) | `ae36aa1`, `0d0861c`, `e42c579` | bộ nhớ PDF nhiễu +1305 MB thành +107 MB; tests redact/job/router | Vòng đầu 3 **Important** (RAM theo số trang, liên kết bản che chèn-một-lần, quét khóa theo sha); **2 vòng sửa** (R18, R19, R20) rồi duyệt |
| 6 | App A: panel PII, tải bản che, `client.downloadObject` (breaking) | `794c572` | SDK 290, App A 120, App B 106 lúc đóng; 105 integration passed; `app-a.spec.ts` chỉ qua `typecheck:live` (V39) | Duyệt, không phải sửa |
| 7 | Dịch vụ `dxos-viewer`: trang PDF thành PNG có watermark, chỉ RAM | `e2a7d71`, `7e7e125` | 98 test viewer lúc đóng | Vòng đầu **Important**: chú thích đục che watermark; **1 vòng sửa** (R26, R27) rồi duyệt |
| 8 | Nối Viewer vào p16, APISIX, ma trận mạng, App A | `02081e7` | RED 11 failed (infra, deploy, netcheck) rồi GREEN; Vitest `viewer.test.ts`; ma trận mạng có `profile_only`; `make check` 1982 passed lúc đóng | Duyệt; **Important** ghi nhận (release dựng Viewer từ nguồn) chuyển cho task 15 (R28), đã xong ở đây |
| 9 | Trang quản trị: khung, đăng nhập, Sức khỏe, Sổ cái; client `dxos-admin-ui` | `1fcc0b0`, `790d44f` | admin-ui 22 test lúc đóng; realm và `keycloak_upgrade` | Vòng đầu **Important**: redirect `admin.${DXOS_DOMAIN}` lệch `DXOS_ADMIN_HOST`; **1 vòng sửa** (R22) rồi duyệt |
| 10 | Trang quản trị: Ứng dụng (diff, duyệt bốn mắt, vô hiệu hóa), Cách ly, Caddy `/ui/` | `b2048ef`, `97924bf`, `b5bbf38` | admin-ui 43 test; Caddy 2.10.0 thật 7 passed | Duyệt có minor; **2 vòng sửa** (R24: không duyệt bản chưa xem diff) |
| 11 | `ops/deploy.sh`: chỉ tag ký SSH, tự quay lui, mã thoát 0/2/3/4/5 | `068141a`, `b1cecb1` | `test_deploy_sh.py` 78 passed lúc đóng (git, docker, curl giả); thử `git cat-file` / `rev-parse` thật, chưa `verify-tag` thật | Vòng đầu **Important**: tag ký đẩy lại dưới tên khác qua được `verify-tag`; **1 vòng sửa** (6 mục) rồi duyệt |
| 12 | `ops/backup.sh`, `restore.sh`, `at21_drill.sh`, `docs/runbook-backup.md` | `388499a`, `f232015` | `test_backup_restore.py` 62 passed lúc đóng (`openssl` thật) | Vòng đầu 2 **Important** (diễn tập không đọc lại SeaweedFS/OpenBao; TMPDIR trong thư mục đích); **1 vòng sửa** (R25) rồi duyệt |
| 13 | `make demo-seed`: dữ liệu demo hư cấu cho App A và App B | `eecc5e7`, `19114e7` | `test_demo_seed.py` 15 passed | Vòng đầu **Important**: seed App B bắt buộc, xung đột kịch bản demo; **1 vòng sửa** rồi duyệt |
| 14 | Ghim SPKI CA Caddy ở bộ live; JS khớp Python; cổng "Hợp lệ — chưa neo công khai" (R11) | `f2a25f6`, `b5e32c6` | vector `b64-three-pad`, `int-4301-digits`, `b64/validate.json` (112 ca) | Duyệt, không phải sửa (rà soát bảo mật không thấy đường để gói giả hiện "Hợp lệ") |
| 15 | Phát hành 0.9.0: phiên bản, CHANGELOG, README, tài liệu này, Viewer vào `release.yml` / `compose.release.yaml` / `deploy.sh` / `release_check` | `chore(release): 0.9.0` | `tests/repo/test_docs_m4.py` (RED 35 failed, 12 passed; GREEN sau khi sửa); test mới cho digest Viewer của `deploy.sh`, overlay compose và `release.yml` (đột biến một điều kiện của `deploy.sh` làm test đỏ) | Do điều phối review |
| 16 | M5: máy sạch, bộ demo, nộp bài, chuẩn bị v1.0.0 | — | — | Chưa làm |

### 14.2. Số test cuối (do Task 15 chạy trên commit này, 23/10/2026, cloud không Docker daemon)
- `make check PYTHON=python`: **2086 passed, 9 skipped, 533 deselected** (mã thoát 0; ruff sạch, `reuse lint` nằm trong lệnh; 9 bỏ qua: 7 test Caddy sống cần binary `caddy`, 1 test thư mục không đọc được vì chạy bằng root, 1 test `ots` chính thức cần `DXOS_OTS_CLIENT=ots`).
- `npm run check`: mã thoát 0. SDK **320**, cổng đối soát **50**, `admin-ui` **47**, App A **138**, App B **106**, ví dụ `so-muon-sach` **10** test (tổng 671); typecheck và build cả 6 workspace đạt.
- `reuse lint`: mã thoát 0, 679/679 tệp có bản quyền và giấy phép.
- Integration (PostgreSQL 16, OpenBao, SeaweedFS, Flowable 7.1.0 chạy tại chỗ, `DXOS_TEST_REQUIRE_DB=1 python -m pytest -m integration core/tests/integration`): **495 passed, 1 skipped** (bỏ qua: test trình duyệt cần `DXOS_TEST_BROWSER=1`). Task 15 không đổi mã lõi; chạy để chắc việc nâng phiên bản không làm gì vỡ. Không gồm test cần Docker (`-m infra`, `-m e2e`).
- `shellcheck -S warning ops/deploy.sh`: mã thoát 0 (shellcheck cài trong `.venv`, không ghi vào requirements).
- `make release-check VERSION=0.9.0`: chỉ thoát 0 sau khi commit đã được đẩy (nó so `HEAD` với `origin/main`); trưởng nhóm chạy lại trước khi gắn tag (14.4).
- **CI**: trưởng nhóm kiểm bằng `gh run list -R PSA-OVNCR/dxos --limit 5` rằng mọi job của run `ci` ở đúng commit `chore(release): 0.9.0` là `success` trước khi gắn tag (14.4); số run của lần đẩy này ghi ở báo cáo điều phối của Task 15 (`.superpowers/`, không có trên GitHub).
- **Chưa chạy ở bất kỳ nơi nào**: mọi việc V37 đến V44 (mục 14.3), job `image-viewer` của `release.yml` (chỉ chạy được khi trưởng nhóm đẩy tag), đường `viewer-image-X.Y.Z.txt` của `ops/deploy.sh` ngoài lệnh giả.

### 14.3. Việc cần máy thật hoặc trưởng nhóm (gom từ Plan 04)
| # | Việc | Ở đâu | Ghi chú |
|---|---|---|---|
| V37 | ~~Ghim `uses:` của `.github/workflows/*.yml` theo SHA (`python ops/pin_actions.py`)~~ — đã chạy 23/10 từ cloud: mọi `git ls-remote` phân giải được, 24 dòng `uses:` (checkout v4, setup-python v5, setup-node v4) đã thành `@<sha40> # vN`; chạy lại là no-op (CI xanh ở `548921d`, run 39894576708, nên các SHA phân giải được trên GitHub). **Còn lại**: chạy `make pin-images` để ghim digest `anchore/syft` và `zricethezav/gitleaks` trong workflow; commit kết quả | Máy trưởng nhóm | Cần Docker buildx. Sau khi ghim, kiểm CI xanh |
| V38 | Hai thiết lập repo bị proxy của phiên cloud chặn (HTTP 403 "not permitted through this proxy", 23/10, Plan 04 Task 2), chưa thử đường khác. Trưởng nhóm chạy trên máy có quyền ghi (hoặc làm trên web: Settings, About, Topics; Settings, Pages): (1) chủ đề repo: `gh api -X PUT repos/PSA-OVNCR/dxos/topics -f 'names[]=dx-os' -f 'names[]=open-source' -f 'names[]=trust-core'`; (2) bật Pages từ `main` thư mục `/docs`: `gh api -X POST repos/PSA-OVNCR/dxos/pages -f 'source[branch]=main' -f 'source[path]=/docs'`. Sau khi bật, mở `https://psa-ovncr.github.io/dxos/` kiểm trang chủ và các liên kết (`docs/index.md`, `docs/_config.yml`; chưa dựng thử Jekyll). Các nhãn `area:core`, `area:web`, `area:ops`, `area:docs`, `pof`, `security` đã tạo xong ngay 23/10 (`good first issue` đã có sẵn) | Máy trưởng nhóm / web GitHub | Chưa làm thì README trỏ tới một trang chưa tồn tại |
| V39 | Chạy thật `tests/web/live/app-a.spec.ts` đã cập nhật ở Plan 04 Task 6 (chưa chạy ở cloud, chỉ qua `npm run typecheck:live`): chuyên viên tải `pii-fictional.pdf`, thấy "Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)", tải bản che (tên tệp `-che.pdf`, bắt đầu `%PDF-`), bấm "Tải bản gốc" thì nhận lỗi của máy chủ; văn thư thấy "Tệp 1: Phát hiện 3 ...", xác nhận rà rồi mở được bản gốc; ban hành và đối soát bằng đúng tệp đó. Lệnh: `make web-live` trên stack dev (`docs/progress/2026-10-22-web-live.md`) | Máy trưởng nhóm | Chưa chạy thì các câu chữ và selector (`.dx-pii-file`, `.dx-pii-files`, `.dx-files-section`) của luồng dò PII chỉ được kiểm bằng Vitest/jsdom. **Kiểm thêm khi chạy (Plan 04 Task 14)**: (1) `ops/web_live.sh` tính SPKI của CA gốc và CA trung gian Caddy bằng `openssl` và Chromium đăng nhập được với `--ignore-certificate-errors-spki-list` thay cho `ignoreHTTPSErrors` (Caddy chỉ gửi chứng chỉ lá và CA trung gian; nếu Chromium vẫn báo lỗi chứng chỉ thì xem chuỗi `openssl s_client -connect localhost:443 -showcerts` và ghim đúng chứng chỉ có trong chuỗi); (2) với cổng dựng có `VITE_ANCHOR_RAW_BASE` (V34), niêm phong App A vừa ban hành mà STH chưa lên repo neo hiện "Hợp lệ — chưa neo công khai" (không phải "Không hợp lệ"), và sau khi worker neo + CDN cập nhật thì hiện "Hợp lệ — đã đối chiếu repo neo" |
| V40 | Chạy thật Viewer ở p16 (Plan 04 Tasks 7–8, S2; mới kiểm bằng test đơn vị, `docker compose config`, ASGI giả và `strace` trên uvicorn thật ở cloud, chưa dựng image vì cloud không có Docker daemon): trên laptop `make up` (p16, `.env` có `COMPOSE_PROFILES=viewer`) rồi (1) `docker compose -p dxos ps` thấy `viewer` khỏe (healthcheck urllib; kiểm image dựng được, `docker run --read-only` không lỗi ghi, tiến trình uid 10001); (2) `make netcheck` đạt, gồm hàng `net-app` → `apisix:9080` mở và `core-db`, `seaweedfs`, `openbao`, `flowable`, `clamav` đóng; thử thêm từ trong container: `docker compose -p dxos exec viewer python -c "import socket; socket.create_connection(('core-db',5432),2)"` phải lỗi; (3) `curl -k https://localhost/view/v1/healthz` không token phải 401, có token 200; (4) đăng nhập App A, mở một văn bản có tệp PDF đã kiểm dịch, bấm "Xem": thấy trang có watermark `DX-OS <8 ký tự đầu của sub> <ngày giờ> ICT`, chuyển trang, đóng (tab Network: ảnh là `blob:`, CSP không báo vi phạm trong Console); chụp ảnh từng bước; (5) PDF nhiều trang và PDF 200+ trang (phải 422), một tệp có chú thích đè (watermark vẫn thấy); (6) đo RAM thật của container khi xem 3 người cùng lúc (`docker stats`) so với trần 768 MiB và thời gian dựng trang để chỉnh `timeout.read` 30 giây của route `view`; (7) `make PROFILE=p8 up` và `PROFILE=dev-lite`: không có container `viewer`, App A không hiện nút "Xem". **Đã xử lý ở Task 15 (R28), chưa chạy thật**: `release.yml` có job `image-viewer` (image `ghcr.io/psa-ovncr/viewer:X.Y.Z`, tệp `viewer-image-X.Y.Z.txt`), `compose.release.yaml` thay `build:` bằng `DXOS_VIEWER_DIGEST`, `ops/deploy.sh` đọc tệp đó (thoát 3 nếu thiếu); còn lại: Release `v0.9.0` thật phải có hai tệp image, package GHCR `viewer` đặt công khai (V19), rồi `ops/deploy.sh v0.9.0` trên VPS p16 phải kéo đúng image Viewer theo digest (`docker inspect` phải ra `ghcr.io/psa-ovncr/viewer@sha256:...`) và `docker compose ... config` không còn `build:` cho `viewer` | Laptop trưởng nhóm, rồi VPS p16 | Chưa chạy thì giới hạn RAM/CPU, `read_only` thật và watermark trên trình duyệt thật chưa được kiểm chứng |
| V41 | Chạy thật trang quản trị web (Plan 04 Tasks 9–10, mới kiểm bằng Vitest/jsdom và Caddy thật không có Keycloak): trên laptop đăng nhập `https://<DXOS_ADMIN_HOST>/ui/` bằng tài khoản `dxos-admin`, xem Sức khỏe hệ thống và Sổ cái, rồi nộp `examples/so-muon-sach` và **duyệt bằng hai quản trị viên khác nhau**: người nộp bấm "Duyệt phiên bản này" phải nhận câu "Người duyệt phải khác người nộp (nguyên tắc bốn mắt)", quản trị viên thứ hai duyệt được, bản chuyển "Đang hoạt động"; thử "Vô hiệu hóa" (phải gõ đúng mã ứng dụng) và màn hình Cách ly (tải tệp EICAR ở App A rồi mở lại). Chụp ảnh từng bước. **Chuẩn bị với stack đã dựng từ trước**: (1) thêm `DXOS_ADMIN_HOST` vào `.env` (compose bắt buộc); (2) tạo lại container keycloak để nhận biến mới (`docker compose up -d --force-recreate keycloak`); (3) chạy lại `python ops/keycloak_upgrade.py` (tạo client `dxos-admin-ui`; script báo lệch và nêu tên biến nếu `DXOS_ADMIN_HOST` thiếu hoặc rỗng); (4) nếu client `dxos-admin-ui` đã tạo tay từ trước mà redirect khác `https://<DXOS_ADMIN_HOST>/ui/*`, sửa tay trong Keycloak (Clients, dxos-admin-ui, Valid redirect URIs và Web origins `https://<DXOS_ADMIN_HOST>`); (5) chạy `make web-build` để bản dựng `admin-ui` vào volume `apps-static`. **Kiểm thêm**: lời gọi lấy token OIDC từ host admin phải chạy được (`KC_HOSTNAME` là host công khai nên `issuer` trong token là host công khai, còn trang gọi `/auth/realms/dxos` cùng origin ở host admin: kiểm trong tab Network rằng `.well-known/openid-configuration` và `token` trả 200 và đăng nhập không bị lỗi lệch issuer/redirect); `/ui/` trên host công khai phải 404 | Laptop trưởng nhóm (hoặc VPS) | Chưa chạy thì việc đăng nhập thật với Keycloak, redirect/issuer từ host admin và luồng hai quản trị viên chỉ được kiểm bằng giả lập |
| V42 | Tạo khóa SSH ký tag phát hành và đưa khóa công khai vào `deploy/allowed_signers` (Plan 04 Task 11, S4). Hiện tệp chỉ có dòng chú thích nên `ops/deploy.sh` từ chối mọi tag (đóng mặc định). Trưởng nhóm: `ssh-keygen -t ed25519 -f ~/.ssh/dxos-release -C "truong-nhom"`, thêm dòng `<email> namespaces="git" <nội dung .pub>` vào `deploy/allowed_signers`, commit; rồi `git config gpg.format ssh`, `git config user.signingkey ~/.ssh/dxos-release.pub`, ký mọi tag bằng `git tag -s vX.Y.Z -m ...` và kiểm `git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/vX.Y.Z` (phải in `for <principal>`). Chi tiết: `docs/runbook-deploy.md` mục 2. Cũng chạy thật `ops/deploy.sh` với tag ký trên VPS, kể cả một lần ép health hỏng để xem tự quay lui (mới kiểm bằng `git`, `docker`, `curl` giả) | Máy trưởng nhóm / VPS | Chưa có khóa thì không triển khai được nếu không dùng `--allow-unsigned` (ghi `signed=no`, chỉ để cấp cứu). Khóa riêng không bao giờ vào repo |
| V43 | Diễn tập AT-21 thật (Plan 04 Task 12, S4): laptop p8 (Git Bash) rồi VPS. Chuẩn bị: tạo `.secrets/backup-passphrase` (`openssl rand -base64 32`, `chmod 600`, giữ bản sao ngoài máy chủ); có unseal key OpenBao của stack đang chạy trong một tệp; chọn **trước** một niêm phong đã ban hành (mã trên trang đối soát; App A cần thêm `--file` là tệp gốc) và clone repo neo. Chạy lúc stack không có ghi: `ops/at21_drill.sh --seal-id <mã> --anchor-dir <repo neo> --unseal-key-file <tệp> [--file <tệp gốc>]`; mong đợi `AT-21 ĐẠT` (`tree_size` và `root_hash` của STH mới nhất và STH trong gói khớp trước/sau, hai lần `verify-bundle` đạt). Chưa kiểm ở cloud (không có Docker daemon): các điểm chỉ thật mới lộ ra gồm `pg_restore --exit-on-error` trên PostgreSQL 17 trong container (role `dxos_core` được tạo trước; chưa thử đủ), tar volume bằng busybox (`--volumes-from ...:ro`, quyền sở hữu tệp), mở khóa OpenBao bằng `docker exec -e`, `docker compose up --wait` chỉ vài dịch vụ, RAM khi chạy hai stack cùng lúc ở p8, và thời gian/kích thước gói. Khoảng trống đã biết: khôi phục thật vào project `dxos` khi mất máy chủ chưa có script (`restore.sh` cố ý từ chối), runbook mục 4.2 chỉ là [ĐX]. Ghi kết quả vào `docs/progress/<ngày>-at21-<nơi>.md`, rồi sửa dòng AT-21 trong `docs/acceptance.md` dẫn tài liệu đó | Laptop trưởng nhóm, rồi VPS | Chưa chạy thì sao lưu/khôi phục chưa được kiểm chứng thật; lịch systemd (`docs/runbook-backup.md` mục 3.1) chưa bật và thời hạn giữ gói chờ V21 |
| V44 | Chạy thật `make demo-seed` (Plan 04 Task 13; mới kiểm bằng stack giả `httpx.MockTransport` ở cloud, chưa chạy với Keycloak, lõi, ClamAV thật): trên laptop có stack dev-lite đang chạy và App A đã cài: (1) `make demo-seed ARGS="--only a --ca-file <caddy-root.crt>"` phải thoát mã 0 và in "App A: 3 văn bản mới"; chạy lần hai phải in "3 đã có từ trước" mà không tạo thêm bản ghi nào; (2) khi App B chưa cài, `make demo-seed` không cờ phải in "bỏ qua App B" và thoát mã 0; (3) cài và duyệt App B như kịch bản demo (bước cài phải thực sự chạy, không phải no-op), rồi `--only b` phải in "App B: 12 chứng nhận mới" (lần hai: "12 đã có từ trước"). Kiểm thêm: có `HTTPS_PROXY` trong môi trường thì seed vẫn tới được `https://localhost`. Rồi đăng nhập kiểm: `chuyen_vien1` thấy 3 văn bản `[DEMO] ...`, văn bản 1 là nháp, văn bản 2 và 3 chờ duyệt; mỗi văn bản hiện số phát hiện PII (CCCD, SĐT; văn bản 2 thêm STK) và tải được bản che; `truong_phong1` thấy 2 việc chờ duyệt; `can_bo_clb1` thấy 12 chứng nhận (8 chờ duyệt, 4 nháp), `truong_clb1` thấy 8 việc phê duyệt. Điểm chưa kiểm ở cloud: `limit=200` và phân trang của danh sách, tên tệp tải lên, thời gian chờ tệp CLEAN với ClamAV thật, bản che 150 dpi của PDF mẫu | Laptop trưởng nhóm | Chưa chạy thì seed chưa được kiểm chứng với stack thật; dữ liệu demo nằm lại trên stack (sổ cái chỉ-thêm), muốn làm lại từ đầu phải dựng lại stack dev |

### 14.4. Thủ tục gắn tag `v0.9.0` (việc của trưởng nhóm; Task 15 không gắn tag)
Điều kiện trước: `v0.2.0` (V18) và `v0.3.0` (V33) đã gắn; có khóa SSH ký tag (V42; khóa riêng không vào repo).
1. `git pull`, rồi `make release-check VERSION=0.9.0` phải thoát 0 (kiểm 5 gói Python kể cả `viewer`, CHANGELOG có ngày, cây sạch, `HEAD` = `origin/main`).
2. CI xanh ở đúng commit `chore(release): 0.9.0` (`gh run list -R PSA-OVNCR/dxos --limit 5`; mọi job của run `ci` ở commit đó là `success`).
3. `git tag -s v0.9.0 <sha của commit đó> -m "v0.9.0: M4 (S1 đến S4, PoF)"`, kiểm `git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/v0.9.0` (cần dòng khóa trong `deploy/allowed_signers`, V42), rồi `git push origin v0.9.0`.
4. Workflow `release` chạy: job `check` (phiên bản 5 gói, CHANGELOG có ngày), hai job `image` và `image-viewer`, rồi job `release` (tar.gz mã nguồn, SBOM, `trust-core-image-0.9.0.txt`, `viewer-image-0.9.0.txt`, `dxos-web-0.9.0.tar.gz`, 5 wheel). Chưa chạy lần nào với Viewer (V40): xem Release có đủ hai tệp image.
5. Đặt package GHCR `trust-core` và `viewer` công khai (V19), rồi V29 (`ops/deploy.sh v0.9.0` trên VPS).

### 14.5. Điểm kỹ thuật còn mở (ghi từ review từng task, chưa sửa)
- **Bộ riêng của trang tối giản (Task 14)**: `tests/deploy/browser/verify_page_checks.js` vẫn dùng `ignoreHTTPSErrors: true`; chưa chuyển sang ghim SPKI. Nhãn "Hợp lệ — chưa neo công khai" dùng chung tiêu đề với khẳng định chỉ-máy-chủ của `UNSUPPORTED_CRYPTO` và không cảnh báo tuổi; SPKI của CA trung gian Caddy tính lại mỗi lần chạy.
- **App A (Task 6)**: nút "Tải bản PDF đã ban hành" của hồ sơ đã niêm phong luôn xin bản gốc nên người không có `reveal_pii` nhận 404 (bản che chỉ tới được từ danh sách tệp); nên sửa trước buổi demo.
- **Dò PII (Task 3, 4, 5)**: dải 001 đến 096 của CCCD chưa đối chiếu với Thông tư 07/2016/TT-BCA; `pii_scans` khóa theo sha nên các app dùng chung kết quả; quét `FAILED` và `TOO_LARGE` không ghi lá ledger; sự cố kéo dài qua hết số lần thử đánh dấu `FAILED` vĩnh viễn (cần ghi chú vận hành); trần bản che 100 MiB không phải cài đặt, và dấu "không có bản che" (migration 009) vĩnh viễn nếu sau này nâng trần.
- **Viewer (Task 7, 8)**: không giới hạn thời gian dựng trang riêng; lời gọi từ Viewer vào APISIX dùng chung một bucket `limit-req`; hộp xem chưa có bẫy tiêu điểm; cờ chú thích NoView/Invisible không giống PDFium gốc (không ảnh hưởng watermark).
- **Trang quản trị (Task 9, 10)**: lời gọi lấy token OIDC từ host quản trị trong khi `KC_HOSTNAME` là host công khai (kiểm ở V41); client `dxos-admin-ui` đã tạo tay từ trước không được `ops/keycloak_upgrade.py` cập nhật; bấm duyệt hai lần khi rời trang rồi quay lại giữa lúc POST (máy chủ chặn bằng bốn mắt và kiểm trạng thái).
- **Triển khai (Task 11, 15)**: chữ ký tag không phủ digest image (lấy từ GitHub Release); `deploy/release.env` được ghi trước `compose pull` nên thoát 3 để lại digest mới; chưa thử `verify-tag` thật; tag cũ trước `v0.9.0` không có Viewer nên quay lui về chúng bỏ Viewer.
- **Sao lưu (Task 12)**: chưa có script khôi phục thật vào project `dxos`; tar OpenBao là bản sao nóng, SeaweedFS tạm dừng chỉ vài giây; gói không có MAC riêng.
- **Dữ liệu demo (Task 13)**: lời nhắn bỏ qua App B nói "chưa cài" cả khi đã cài nhưng chưa duyệt.
- **Trang tài liệu (Task 2)**: Jekyll có thể hiểu `${{…}}` hay `{% %}` trong `docs/progress` là Liquid; kiểm trước khi bật Pages (V38).

### 14.6. Rulings của điều phối (R1 đến R28) và chi phí nếu sai
Mọi quyết định mà điều phối phải đưa ra khi plan, spec hoặc repo không đủ rõ, chép từ sổ điều phối (`progress.md`, dòng `Ruling:`). Cột cuối là chi phí nếu quyết định sai; trưởng nhóm có thể mở lại bất kỳ ruling nào.

| # | Task | Quyết định | Nếu sai |
|---|---|---|---|
| R1 | 3 | `Box.page` và `pii_findings.page` đánh số từ 1 (giống giao diện "trang 1"); ràng buộc `>= 0` cũ vẫn đúng | Lệch một trang ở giao diện hoặc bản che; các test đọc lại phát hiện bắt được |
| R2 | 6 | Sửa `PiiPanel` ở SDK (`sdk/js/src/vue/PiiPanel.vue`), không tạo bản sao ở App A | Không ảnh hưởng chức năng; App B và ví dụ nhận cùng câu chữ |
| R3 | 11 | `deploy.sh` giữ mã 2 cho "từ chối trước khi đổi gì", mã 3 cho "thiếu điều kiện trước khi chuyển", theo bảng mã của plan | Phải sửa runbook và test về mã thoát |
| R4 | 16 | V49 ghi "trưởng nhóm quyết 22/10: không cần" thay vì việc còn mở | Tiêu chí SCM (commit của mọi thành viên, spec 20.2) không được nêu; trưởng nhóm mở lại được |
| R5 | 1 | `constraints.txt` sinh từ venv cloud; job CI `licenses` cài theo nó nên CI chứng minh các pin phân giải được | Một pin lệch khỏi lần xanh gần nhất; CI đỏ và pin được sửa |
| R6 | 1 | `cffi` (MIT-0) và `tslib` (0BSD) vào "Ngoại lệ đã duyệt" | Không đáng kể (cả hai đều đã được OSI duyệt và dễ dãi hơn MIT) |
| R7 | 1 | `certifi` (MPL-2.0, runtime qua httpx) vào "Ngoại lệ đã duyệt", ghi "chờ trưởng nhóm xác nhận cùng V30" để CI xanh; trưởng nhóm đã duyệt 23/10 | Nếu bị từ chối thì phải thay `certifi` (khó nếu không thêm phụ thuộc) |
| R8 | 1 | Phạm vi quét giấy phép là closure runtime của các gói `dxos-*`; công cụ dev (như `reuse`, GPL) không tính vì không được phân phối | Một công cụ GPL bị đóng gói mà không ai biết; image chỉ cài phụ thuộc runtime nên rủi ro thấp |
| R9 | 1 | Dòng `Co-Authored-By` của commit subagent ghi model thật sự viết commit (Opus hay Sonnet) | Chỉ hình thức |
| R10 | 1 | Chạy `ops/pin_actions.py` thật từ cloud (đã chạy được); `pin_images` cho syft và gitleaks để máy có Docker (V37) | Thêm một việc V |
| R11 | 14 | Ở chế độ ghim, khi khóa khớp nhưng STH đã neo chưa phủ niêm phong (hay chưa có tệp), cổng hiện "Hợp lệ — chưa neo công khai" thay vì "Không hợp lệ"; tệp sth có mặt nhưng khác gói vẫn là lỗi cứng; `dxos-witness --anchor-dir` vẫn chặt | Cổng báo sai "không hợp lệ" cho niêm phong mới trong buổi demo |
| R12 | 2 | `make sbom` dùng đúng image syft của `release.yml` (một chỗ ghim) | Image SBOM chưa ghim digest tới khi V37 xong |
| R13 | 3 | Commit đã đẩy giữ nguyên dòng đồng tác giả; không sửa lịch sử hay force-push chỉ vì đồng tác giả | Chỉ hình thức |
| R14 | 3 | Nhóm số nối bằng `.` hoặc `-` là một khối; nhóm cách bằng khoảng trắng hoặc xuống dòng được tách, lấy dãy hợp lệ dài nhất | Che thừa trên danh sách số cách nhau bằng khoảng trắng (phía an toàn) |
| R15 | 3 | Từ khóa phủ định `MST` / `mã số thuế` (30 ký tự trước) loại số khỏi SĐT và CCCD | SĐT thật viết ngay sau "MST" bị bỏ sót (hiếm) |
| R16 | 4 | `:pii-review` xếp việc quét cho tệp CLEAN chưa có `pii_scans`; lần thử cuối của việc quét hỏng ghi `FAILED` để rà tay | Thêm một cú bấm xác nhận sau khi quét xong |
| R17 | 5 | `variant=original` bị khóa bằng `reveal_pii` trừ khi quét xong và 0 phát hiện, cả khi chưa quét, quá lớn hay hỏng | Người tải lên chờ vài giây cho quét xong mới tải lại được tệp của mình |
| R18 | 5 | Ghi PDF bản che từng trang bằng zlib; liên kết bản che ở bảng chỉ-thêm `pii_redactions`; việc `pii_redact` thử lại; không nuốt `MemoryError` (migration 008, không sửa 007) | CSDL dev đã có dữ liệu cũ phải qua 008 (có test chuyển liên kết 007 sang 008) |
| R19 | 5 | Việc nền luôn quét cả ba loại; `document_detect` của manifest chỉ quyết định có chờ quét hay không | App xin ít loại thấy thêm loại khác và bản gốc bị khóa nhiều hơn (phía an toàn) |
| R20 | 5 | Trần bản che cố định 100 MiB, kiểm khi thêm từng trang; vượt thì không có bản che, không thử lại (migration 009) | PDF quét ảnh màu lớn không có bản che; chỉ người có `reveal_pii` chia sẻ được |
| R21 | 6 | Danh sách tệp đính kèm trả thêm `pii.counts` theo loại (số lượng, không giá trị) | Thêm một trường ở lõi; I5 không bị ảnh hưởng |
| R22 | 9 | Redirect của client `dxos-admin-ui` theo `DXOS_ADMIN_HOST` (host mà Caddy phục vụ site quản trị), truyền biến này cho Keycloak | Thêm một biến môi trường ở Keycloak |
| R23 | 9 | "Neo ngay" bị tắt khi còn việc neo đang chờ (`pending_anchor_jobs > 0`) | Quản trị viên chờ việc neo hiện có xong |
| R24 | 10 | Lỗi "duyệt phiên bản chưa xem diff" lên mức vòng sửa riêng | Thêm một vòng sửa nhỏ |
| R25 | 12 | Sao lưu `docker pause` SeaweedFS chỉ trong lúc tar volume của nó (mở lại bằng bẫy EXIT); tar OpenBao nóng là giới hạn có ghi | Tải lên bị treo vài giây trong lúc sao lưu đêm |
| R26 | 7 | Viewer: 401 giữ 401; API 5xx hoặc không nối được là 502; quá hạn là 504; mọi lỗi khác không phải 200 là 404; không bao giờ có ảnh nếu API không trả 200 | Client thấy 502 chỗ lẽ ra 404 |
| R27 | 7 | Watermark xám 128 với độ đục 45% (đọc "xám 35%" của plan theo ý "xám nhìn thấy được") | Watermark nổi hơn một chút |
| R28 | 8 | Khoảng trống phát hành Viewer (dựng từ nguồn trên máy chủ) chuyển cho Task 15 thành yêu cầu cứng: image lên GHCR, overlay thay `build:` bằng digest, `deploy.sh` đọc digest, `release_check` kiểm Viewer | Thêm một vòng phát hành với Viewer dựng từ nguồn nếu Task 15 trễ; đã làm xong ở Task 15 (chưa chạy thật, V40) |
