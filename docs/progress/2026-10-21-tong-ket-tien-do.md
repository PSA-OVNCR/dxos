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

## 2. Mốc thời gian
| Mốc | Ngày | Nội dung chính | Trạng thái |
|---|---|---|---|
| M0 | 26/10 | Hạ tầng chạy được, đo RAM, spike Flowable | Gần xong: thiếu đo RAM và chạy trên VPS |
| **M1** | **09/11** | Lõi Tier-0 phần 1, release **v0.1.0** | **Mã xong**; chờ E2E trên VPS + tag |
| M2 | 16/11 | v0.2.0: guard + BPMN, niêm phong, installer, App A và B cài bằng manifest, witness độc lập | Chưa bắt đầu (cần viết Plan 02) |
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
| Duyệt giấy phép **pypdfium2** (wheel nhúng PDFium, ICU, FreeType FTL/GPL-2.0, libjpeg-turbo…) | trước v0.1.0 | Cài lúc build, không nằm trong repo (G4). Phương án thay: pypdf (BSD-3) |
| Tạo repo neo, ruleset, khóa deploy, chụp ảnh AT-18 | trước 09/11 | `docs/runbook-anchor.md` |
| Tìm **witness độc lập** (người/tổ chức ngoài đội chạy `dxos-witness`) | trước 16/11 | `witness/template/` |
| Dựng VPS 16 GB; chạy Claude Code trên VPS | sớm nhất có thể | Rồi chạy Task 7 + E2E Task 17 |
| Quyết định gắn tag `v0.1.0` | sau E2E trên VPS | Plan hẹn 09/11 |
| Gửi BTC các câu còn treo (mục 6) | sớm | |
| Đăng ký qua trường, có giảng viên (G5) | | |

## 6. Câu hỏi BTC còn treo
1. `.zip` GitHub tự sinh trong release có bị trừ điểm "định dạng không mở" (TL tr.2)? G17 không nói.
2. Điểm trừ của một tiêu chí PoF có dừng ở 0 không?
3. Chấm PoF theo commit cuối trước 17:00 06/12 hay theo tag release mới nhất (G16)?
4. Release chỉ cần tag, hay cần cả trang Release có tệp đính kèm (G17)?
5. "Tổng quát nhất" có đòi nhiều tổ chức dùng chung một bản cài không (G14)?

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
