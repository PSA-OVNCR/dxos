<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Tổng kết tiến độ DX-OS Trust Core — 21/10/2026

*Đội PSA_OVNCR · Kho mã: https://github.com/PSA-OVNCR/dxos (public, Apache-2.0) · Mục 1–12 cập nhật đến commit `56bac6e` (Plan 01) và Plan 02 (mục 11–12); mục 13 (Plan 03) xem bên dưới.*
*Thay cho bản 20/10 (`2026-10-20-tong-ket-tien-do.md`, giữ lại làm lịch sử).*
*Mục 13 (Plan 03, M3) cập nhật 22/10/2026 đến commit `4d7e0f1` (đợt sửa sau review cuối toàn nhánh).*

## 1. Tóm tắt trong 30 giây
- **Cập nhật 22/10: Plan 03 (M3, v0.3.0) có mã xong ở cloud, chưa gắn tag, chưa chạy trên stack thật.** Xem mục 13 (task, số test, việc V27–V36). Các gạch đầu dòng còn lại của mục này là hiện trạng cũ của Plan 01.
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
- **CI**: run `ci` **39701368613** ở commit `4d7e0f1` xanh mọi job (`lint`, `secrets`, `web`, `reuse`, `unit`, `caddy-live`, `integration`). Trước đó job `unit` đỏ từ `c387591` tới `65e67af` vì `shellcheck` mới trên runner báo SC2329 (info) ở `ops/deploy.sh` (review cuối, I1).
- **Chưa chạy ở bất kỳ nơi nào**: bộ Playwright live (`make web-live`), `make web-build`, `ops/vuot_rao.py`, `ops/deploy.sh`, `release.yml` bước dựng SPA, gọi calendar OpenTimestamps thật, test đối chiếu `ots` chính thức (`DXOS_OTS_CLIENT=ots`).

### 13.3. Việc cần máy thật hoặc trưởng nhóm (gom từ Plan 03)
| # | Việc | Ở đâu | Ghi chú |
|---|---|---|---|
| V27 | Chạy `make web-build` và bộ Playwright live (`make web-live` hoặc `ops/web_live.sh`) cho App A, App B và cổng đối soát; chụp ảnh minh chứng; ghi `docs/progress/<ngày>-web-live.md` | Máy trưởng nhóm / VPS | Cần V35 trước. Bộ live chưa từng chạy; giả định về realm dev, `ignoreHTTPSErrors` và host-resolver-rules chưa kiểm. Lệnh Windows: `docs/evidence/README.md` |
| V28 | Chạy `python ops/vuot_rao.py` (hoặc `make vuot-rao`) trên stack dev; dán bảng kết quả vào `docs/progress/` | Máy trưởng nhóm | Kịch bản V5 (ban hành đủ luồng niêm phong) dễ lỗi nhất; mã thoát 2 = bước chuẩn bị hỏng, không phải "bị chặn" |
| V29 | Chạy `ops/deploy.sh v0.3.0` trên VPS sau khi có tag và image GHCR | VPS | Cần Docker Compose ≥ 2.24 (V22), NTP (V24), package GHCR công khai (V19). `docs/runbook-deploy.md` |
| V30 | Xác nhận công cụ build/test có giấy phép MPL-2.0 (lightningcss), BlueOak-1.0.0, MIT-0, CC0-1.0 (`mdn-data`) chỉ nằm ngoài bundle | Trưởng nhóm | `LICENSES-THIRD-PARTY.md`. Không chấp nhận thì phải bỏ jsdom và đổi cách test |
| V31 | Tổ chức AT-26 theo `docs/at26-checklist.md` (người ngoài đội làm hướng dẫn 30 phút) | Trưởng nhóm | Mọi lệnh trong hướng dẫn chưa chạy thật, ghi "chưa kiểm ở cloud — kiểm trong AT-26" |
| V32 | Bật `DXOS_OTS_CALENDARS` trên VPS; sau vài giờ `ots upgrade` rồi `ots verify` tệp `ots/<n>.ots`; tùy chọn chạy `DXOS_OTS_CLIENT=ots python -m pytest core/tests/test_ots.py -k official` | VPS | `docs/runbook-anchor.md` mục 6. Mặc định tắt; cắt được nếu thiếu thời gian |
| V33 | Gắn tag `v0.3.0` sau `v0.2.0` (xem 13.4) | Trưởng nhóm | Hành động công khai |
| V34 | Đặt `VITE_ANCHOR_RAW_BASE` (lúc build) và `DXOS_ANCHOR_RAW_ORIGIN` (`.env`, hai giá trị phải khớp) theo repo neo thật khi repo đó có trên GitHub | VPS | Chưa đặt thì cổng đối soát nói rõ là chưa đối chiếu repo neo |
| V35 | Chạy `make pin-images` trên máy có Docker để ghim digest `NODE_IMAGE` (`ops/web_build_docker.sh`) và `PLAYWRIGHT_IMAGE` (`ops/web_live.sh`), rồi commit | Máy có Docker | Registry bị chặn (403) khi viết; tới lúc đó cả hai script thoát mã 3 và `deploy.sh` dừng ở bước dựng SPA. **Làm trước V27, V29, V33** |
| V36 | Chạy lại AT-20 trên máy trưởng nhóm sau bản sửa bước mở khóa OpenBao của test (`40d6d64`) | Máy trưởng nhóm | Thay phần "chưa chạy lại" của V17; AT-20 cần `docker` ngoài container |

Các việc V1–V26 của mục 12 vẫn còn hiệu lực (ví dụ V18 tag `v0.2.0`, V21, V22, V24).

### 13.4. Thủ tục gắn tag (việc của trưởng nhóm; Task 15 không gắn và không đổi phiên bản)
Thứ tự: `v0.2.0` (V18) rồi `v0.3.0` (V33). Mỗi tag:
1. `make pin-images` (V35) và commit nếu chưa ghim; image Node phải ghim trước khi chạy `ops/deploy.sh` (V29), vì script dựng SPA bằng Docker. (`release.yml` dựng tar SPA bằng Node trên Actions, không dùng image ghim.)
2. Nâng phiên bản 4 gói Python và 3 tệp `__init__.py` (hiện vẫn `0.1.0`, danh sách ở `BUILD.md` mục "Phát hành"), chạy `make openapi`. Các gói web (`package.json` gốc và các workspace) đã ghi `0.3.0` từ Plan 03; workflow không kiểm chúng, nên khi gắn `v0.2.0` chúng vẫn là `0.3.0` (không ảnh hưởng release).
3. Đổi `## [X.Y.Z] - Chưa phát hành` trong `CHANGELOG.md` thành ngày thật (mục `[0.3.0]` đã viết sẵn, mục `[Unreleased]` để trống).
4. `make check PYTHON=python && npm run check && reuse lint` (kiểm bằng mã thoát), commit, push lên `main`.
5. CI xanh ở commit gắn tag (`gh run list -R PSA-OVNCR/dxos --limit 5`; mọi job của run `ci` ở đúng commit đó là `success`).
   Chưa xanh thì không gắn tag: máy cloud và máy trưởng nhóm không có `shellcheck`, CI thì có (review cuối Plan 03, I1).
6. `git tag -a vX.Y.Z -m "…"`, `git push origin vX.Y.Z`.
7. Sau khi Release có: V29 (`ops/deploy.sh vX.Y.Z` trên VPS).

### 13.5. Điểm kỹ thuật còn mở (ghi từ review từng task, chưa sửa; review toàn nhánh Plan 03 đã xem, các mục chịu lực đã sửa ở `4d7e0f1`)
- **Bộ Playwright live (Task 10)**: dùng `ignoreHTTPSErrors`; nên ghim SPKI của CA Caddy (dời sang Plan 04, làm cùng V27).
- **Sổ đăng ký (Task 8)**: năm của sổ lấy từ `issued_at` còn bộ đếm `so_hieu` theo năm tạo bản ghi; cần ghi vào runbook.
- **Ma trận AT (Task 11)**: `2026-10-22-e2e-m2-docker-desktop.md` tự mâu thuẫn về AT-19 (bảng ghi PASSED, mục "Chưa làm" ghi chưa); ma trận ghi cả hai, trưởng nhóm cần xác nhận.
- **OpenTimestamps (Task 14)**: thứ tự nhánh khi nhiều biên nhận cùng nút là tất định nhưng không cam kết trùng từng byte với `ots` chính thức (không ảnh hưởng tính hợp lệ).
- **Khác biệt đã biết giữa bộ kiểm JS và Python** (Task 4, chưa sửa, không đổi kết quả hợp lệ/không hợp lệ của gói thật): `b64decodePy` chỉ chấp nhận tối đa 2 dấu `=` đệm trong khi Python chấp nhận nhiều hơn sau một nhóm đủ; số nguyên dài hơn 4300 chữ số cho `MALFORMED` ở Python nhưng JS vẫn chấp nhận (ở trường không được ký). Vì vậy không được nói hai bên "cùng mã lỗi" tuyệt đối.
- Cổng đối soát: nếu GitHub trả được `v1.pub` nhưng lỗi tạm thời ở tệp khác, người dùng thấy "Không hợp lệ" thay vì "chưa đối chiếu" (đánh đổi đã chấp nhận ở Task 6).
- Trên stack dev đang chạy, `/apps/verify/` trả 404 cho tới khi `make web-build` (trang cũ ở `/apps/verify-lite/`).
- Ảnh minh chứng trong `docs/evidence/verify-page-*.png` chụp từ trang tối giản; ảnh của cổng Vue chưa có (nằm trong V27).
