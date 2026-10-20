# BÀN GIAO CÔNG VIỆC — DX-OS Trust Core (OLP PMNM 2026)

*Lập 20/10/2026 22:10 (giờ VN) bởi phiên Claude đang làm dự án, để chuyển sang một tài khoản Claude khác. Trạng thái repo tại commit bàn giao: xem `git log -1` (sau `7060e56`).*

Tài liệu này viết cho **một AI hoặc người mới**: đọc hết là làm tiếp được, không cần hỏi lại lịch sử hội thoại.

---

## 0. Đọc theo thứ tự nào
1. Mục 1–3 của tài liệu này (10 phút).
2. `docs/progress/2026-10-20-tong-ket-tien-do.md`: đã làm gì, chưa làm gì.
3. `docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md` (Spec 1.0.1, **nguồn sự thật về thiết kế**).
4. `docs/superpowers/plans/2026-10-20-dxos-00-ke-hoach-tong-the.md` (Plan 00) và `...-01-nen-mong-m0-m1.md` (Plan 01, đang thực hiện).
5. `docs/handoff/ledger-plan01.md`: sổ tiến độ và mọi quyết định (ruling) đã đưa ra khi thực hiện Plan 01.
6. Nếu có quyền vào máy trưởng nhóm: thư mục `E:\PMMNM 2026\BAN-GIAO\boi-canh\` có tài liệu bối cảnh 00–05 (tóm tắt đề, giải đáp BTC G1–G13, đối thủ, ý tưởng). Ba PDF gốc của BTC nằm ở `E:\PMMNM 2026\`.

### Câu lệnh khởi động gợi ý (dán vào phiên Claude mới)
> Bạn tiếp nhận dự án DX-OS Trust Core dự thi OLP Phần mềm nguồn mở 2026 của đội PSA_OVNCR. Repo: https://github.com/PSA-OVNCR/dxos. Hãy clone repo, đọc `docs/handoff/HANDOFF.md` và làm theo mục "Cách làm việc với người dùng". Sau đó báo lại cho tôi bằng tiếng Việt: (1) bạn hiểu dự án đang ở đâu, (2) việc tiếp theo bạn đề xuất. Chưa sửa gì cho tới khi tôi đồng ý.

---

## 1. Cách làm việc với người dùng (bắt buộc giữ)
- **Ngôn ngữ:** tiếng Việt, rõ ràng, thực tế; giải thích thuật ngữ khi cần. Người dùng hay nhắn ngắn ("tiếp", "làm cho tôi đi", "xong"), đôi khi gõ telex lỗi dấu.
- **Vai trò:** cố vấn kỹ thuật + quản lý dự án + người thực thi. Khi người dùng nói "tiếp" là làm task kế tiếp theo plan, không hỏi lại.
- **Căn cứ:** khi nói về yêu cầu hoặc tiêu chí chấm, **dẫn tên tài liệu và số trang**:
  - *Đề*: "Đề thi phần mềm nguồn mở - OLP 2026", 7 trang.
  - *TL*: "Thể lệ cuộc thi phần mềm nguồn mở - OLP 2026", 3 trang.
  - *QG*: "Quick-guide-to-DXOS", 5 trang.
- **Phân loại** mọi yêu cầu: **[BB]** bắt buộc · **[TK]** tham khảo · **[ĐX]** đề xuất của cố vấn. G1–G13 là các giải đáp của BTC.
- **Trung thực:** không khẳng định "đã kiểm thử" nếu chưa chạy. Mọi tuyên bố "đạt" phải kèm lệnh đã chạy và kết quả. Mỗi lần chạy thật đều ghi minh chứng vào `docs/progress/`.
- **Git:**
  - Người dùng muốn **push thẳng lên `main`**, không cần PR hay review ("cứ up lên là được").
  - Commit theo kiểu Conventional Commits (`feat(core): …`, `fix(deploy): …`, `docs(progress): …`).
  - Mỗi tệp mã có header SPDX `SPDX-FileCopyrightText: 2026 PSA_OVNCR` và `SPDX-License-Identifier: Apache-2.0`.
- **Quyết định thay người dùng:** được tự quyết các chi tiết kỹ thuật, nhưng phải ghi lại thành `Ruling: <quyết định> — <lý do> — <cái giá nếu sai>` trong ledger và báo trong tin nhắn cuối.
- **An toàn:**
  - Không nhập mật khẩu hay mã xác thực thay người dùng; GitHub "sudo mode" phải để người dùng tự nhập.
  - Không chấp nhận điều khoản thay người dùng.
  - Không đưa bí mật thật vào repo. `.env` chỉ có giá trị `changeme…`.

## 2. Dự án trong 1 phút
- **Cuộc thi:** OLP Tin học Sinh viên – Phần mềm nguồn mở 2026, chủ đề "DX-OS Open-Core" (Đề tr.1).
- **Lịch:**
  - Nộp bài: **17:00 Chủ nhật 06/12/2026** (G12). Đề tr.6 ghi nhầm năm 2025.
  - Chấm kho mã: 07–09/12.
  - Chung kết 10/12: **chỉ trình bày và demo 15 phút** (G13).
- **Thang điểm:**
  - 50 điểm PoF (kho mã, TL tr.2–3).
  - 50 điểm sản phẩm (TL tr.3).
- **Đội PSA_OVNCR:** 3 sinh viên, Học viện An ninh nhân dân.
  - GitHub: `UI-UX-USHP` (trưởng nhóm, Owner), `Levminh` và `kirito99152` (Cao Thanh Phong), cả hai được mời làm Owner ngày 20/10, đang chờ chấp nhận.
  - **Chưa chốt** ai là TV-A, TV-B, TV-C.
- **Hướng sản phẩm đã chốt (Spec 1.0.1):**
  - **DX-OS Trust Core**: Tầng 1 headless, có Identity/SSO, Gateway, dữ liệu có cấu trúc và phi cấu trúc, Workflow, cùng lớp dịch vụ tin cậy (kiểm dịch, CAS, sổ cái Merkle + STH ký + neo GitHub + witness, niêm phong, che PII).
  - **App A "Phòng hồ sơ số"**: ứng dụng chính.
  - **App B "Chứng nhận số"**: ứng dụng nhỏ, *không phải PKI*.
  - ⚠ Tài liệu bối cảnh cũ (00–05) còn nhắc "ứng dụng Nghỉ phép" và để ngỏ ngôn ngữ. **Spec 1.0.1 thay thế:** App B là Chứng nhận số; stack là **Python 3.12/FastAPI + Vue 3** (spec 17.2).
- **Ba mệnh đề phải chứng minh:**
  - P1: hai app dùng chung lõi, **không sửa lõi**.
  - P2: không vượt chính sách.
  - P3: mọi kết quả quan trọng **kiểm chứng được**.
- **Bất biến:**
  - I1: trung gian toàn phần, phân vùng mạng.
  - I2: kiểm dịch trước khi dùng, lưu theo nội dung.
  - I3: lõi mù nghiệp vụ.
  - I4: Merkle RFC 6962 + STH ký qua OpenBao + neo repo có bảo vệ nhánh + witness.
- **Mốc:**
  - M0 26/10.
  - **M1 09/11 (v0.1.0)**.
  - M2 16/11 (v0.2.0).
  - M3 23/11 (v0.3.0).
  - M4 30/11 (v0.9.0).
  - M5 04/12 (v1.0.0).

### 2.1. Giải đáp của BTC trên Telegram (G1–G13, đã xác nhận)
| # | Nội dung | Hệ quả |
|---|---|---|
| G1 | 4 nguyên lý (Đề tr.4) chỉ **định hướng**; Tầng 2 chỉ cần **1 không gian** H/P/D/I | Không phải làm đủ HPDI |
| G2 | Phần mềm chạy độc lập như dịch vụ không tính vào giấy phép dự án (kể cả base image) | Image bên thứ ba không làm hỏng giấy phép |
| G3 | Không fork hay sửa nền tảng có giấy phép "Apache-2.0 + điều khoản bổ sung" rồi coi là OSI | Đọc kỹ LICENSE lạ |
| G4 | Thứ nhúng vào kho mã phải tương thích OSI; thứ không tương thích để ngoài kho, nạp khi chạy | Compose kéo image lúc chạy |
| G5 | Đăng ký qua trường, có giảng viên dẫn dắt | Còn treo |
| G6 | Được dùng API AI bên thứ ba | — |
| G7 | Được tích hợp dịch vụ có sẵn, miễn tuân thủ nguyên lý nguồn mở | — |
| G8 | Headless = không UI cho người dùng cuối; **vẫn phải có UI cho admin** | UI admin Tầng 1 là SHOULD, CLI là MUST (spec) |
| G9 | Tầng 1 phục vụ lập trình viên Tầng 2+; bắt buộc có cả Tầng 1 và Tầng 2 | Cần tài liệu API, SDK |
| G10 | Tầng 1 **hoàn toàn độc lập nghiệp vụ** | I3, manifest |
| G11 | Bảng 7 lớp công nghệ chỉ là ví dụ | — |
| G12 | Hạn nộp 17:00 06/12/2026 | — |
| G13 | Chung kết chỉ demo, không code tại chỗ | — |

**Chưa có giải đáp:** được commit trong thời gian chấm không; `.zip` tự sinh trong release có bị trừ điểm "định dạng không mở" không (TL tr.2); điểm trừ có dừng ở 0 không.

Bản đầy đủ (kèm phân tích đối thủ 2026 và bài học các năm trước) nằm ở `E:\PMMNM 2026\OLP2026-TONG-HOP-DU-AN.md` trên máy trưởng nhóm và trong Project claude.ai của tài khoản cũ. Đây là tài liệu nội bộ, không đưa lên repo công khai.

## 3. Trạng thái hiện tại
**Plan 01 đã xong 6/17 task**: Task 1–6. Chi tiết và bằng chứng ở `docs/progress/2026-10-20-tong-ket-tien-do.md`. Tóm tắt:

| Task | Trạng thái | Bằng chứng |
|---|---|---|
| 1–3 Khung PoF, canonical JSON, Merkle | Xong | CI xanh |
| 4 Compose 9 mạng, Caddy, APISIX, netcheck | Xong, đã chạy thật | 13/13 healthy, netcheck 30/30 (`docs/progress/2026-10-20-task4-kiem-tra-song.md`) |
| 5 Realm Keycloak `dxos` | Xong, đã chạy thật | 10/10 token, APISIX nhận token thật (`docs/progress/2026-10-20-task5-realm-keycloak.md`) |
| 6 Spike Flowable | Xong | SMOKE OK; giữ ADR-09; OSS 7.x không có console admin (`docs/spikes/flowable.md`) |
| **7 Đo RAM (AT-22)** | **Dở** | Công cụ đã có (`ops/measure.sh`, `ops/capacity_report.py`, 9 test). **Chưa có số đo.** Script `E:\PMMNM 2026\_claude-run\chay-task7b.bat` đã sẵn, chưa chạy. Đề xuất với người dùng: dời sang lúc dựng VPS. Người dùng chưa trả lời |
| 8–17 | Chưa làm | Xem Plan 01 |

**GitHub:**
- Repo `PSA-OVNCR/dxos`: public, Apache-2.0, Issues, Discussions, Private vulnerability reporting.
- Ruleset `protect-main`: chặn force-push, chặn xóa, chặn tạo nhánh mặc định; **không** bắt buộc review hay status check.
- CI `.github/workflows/ci.yml`: 4 job `reuse`, `lint`, `unit`, `secrets`.
- Ứng dụng Claude trên GitHub đã cài cho tổ chức, nhưng chỉ cấp quyền cho repo `dxos`.
  - Tài khoản Claude mới cần **tự kết nối GitHub** (claude.ai → Settings → Connectors) hoặc dùng token riêng để push.
  - Qua proxy của phiên Claude **không** được ghi cài đặt repo bằng API; phải thao tác qua trình duyệt.

## 4. Việc tiếp theo (theo thứ tự)
1. **Hỏi người dùng 3 việc còn treo:**
   - Task 7 dời sang VPS hay đo trên laptop ngay?
   - Ai là TV-A, TV-B, TV-C?
   - Khi nào có quyền vào VPS?
2. **Task 8: khung trust-core và migration** (Plan 01 dòng 443+). Gồm:
   - `core/pyproject.toml` (gói `dxos-core`).
   - `Settings` với `env_prefix="DXOS_"`, `create_app()`, `problem()` trả `application/problem+json`.
   - `apply_migrations()` có bảng `schema_migrations`.
   - `001_core.sql` theo spec 10.1: `ledger_entries.idx bigint` (không dùng bigserial), trigger `ledger_append_only`, trigger `record_seal_guard`, CHECK định dạng sha256, role `dxos_owner` và `dxos_core`; `dxos_core` **không** có UPDATE/DELETE trên ledger.
   - `core/Dockerfile` chạy bằng user không phải root.
   - Thay stub `trust-core-api` và `trust-core-worker` trong `deploy/compose.yaml`.
   - Integration test cần PostgreSQL: dùng `deploy/compose.test.yaml` (cổng `127.0.0.1:55432`, user `dxos_owner`, mật khẩu `changeme-test`) hoặc Postgres cục bộ.
3. Sau đó làm Task 9 → 17 theo Plan 01. Task 17 = E2E + **release v0.1.0** (cần `.tar.gz` trong release, TL tr.2).
4. Việc treo khác:
   - Hỏi BTC: được commit trong lúc chấm 07–09/12 không? `.zip` tự sinh của GitHub có bị trừ điểm không?
   - Đăng ký qua trường/GV (G5).
   - Repo neo STH (cần bảo vệ nhánh, chủ sở hữu là người dùng + GV) trước M1.
   - Witness độc lập trước 16/11.

### Thông số đã chốt mà Task 8 trở đi sẽ dùng
- Issuer token: `https://<DXOS_DOMAIN>/auth/realms/dxos` (localhost: `https://localhost/auth/realms/dxos`).
- JWKS nội bộ: `http://keycloak:8080/auth/realms/dxos/protocol/openid-connect/certs`. Keycloak chạy dưới `/auth` cả bên trong lẫn bên ngoài.
- Audience: `dxos-api`.
- Vai trò nằm trong `realm_access.roles`, dạng `app:<id>:<role>` và `dxos-admin` (D3). Admin không mặc nhiên đọc được dữ liệu app (D4).
- Tên service và mạng: xem `deploy/network-matrix.yaml`. Đây là nguồn sự thật; test tĩnh sẽ đỏ nếu compose lệch ma trận.
- Flowable REST: `http://flowable:8080/flowable-rest/service`, Basic auth `rest-admin` / `FLOWABLE_REST_PASSWORD`. Endpoint đã kiểm ở `docs/spikes/flowable.md`.
- Người dùng dev (chỉ hồ sơ dev-lite): `chuyen_vien1`, `truong_phong1`, `giam_doc1`, `van_thu1`, `nhan_vien1`, `can_bo_clb1`, `truong_clb1`, `owner_a1`, `owner_b1`, `admin1`; mật khẩu `dev-only-password`; client `dxos-test` cho phép direct grant.

## 5. Quy trình thực thi đang dùng
- Dùng skill **superpowers:executing-plans** (thực thi tuần tự, TDD, review toàn nhánh ở cuối).
- **Ledger** ở `.superpowers/sdd/2026-10-20-dxos-01-nen-mong-m0-m1/progress.md`. Thư mục này nằm trong `.gitignore` nên **không có trong repo**. Bản sao lúc bàn giao: `docs/handoff/ledger-plan01.md`.
  - Phiên mới: chép bản sao này về đúng đường dẫn trên rồi tiếp tục.
  - Mỗi task xong ghi `Task N: complete (commits a..b, tests: <lệnh> → <kết quả>)`.
- Mỗi task:
  1. Đọc brief trong plan.
  2. Viết test trước, chạy cho đỏ.
  3. Cài đặt, chạy cho xanh.
  4. `make check` (ruff + REUSE + pytest).
  5. Commit, push, xem CI.
  6. Ghi ledger.
- `make check` phải xanh trước khi push. Nhớ xóa `__pycache__` nếu `reuse lint` báo tệp `.pyc` (Makefile đã đặt `PYTHONDONTWRITEBYTECODE=1`, nhưng chạy pytest ngoài make vẫn sinh `.pyc`).

## 6. Môi trường và cách đã chạy thử (rất quan trọng)

### 6.1. Máy trưởng nhóm (Windows)
- Docker Desktop 28.4 / Compose v2.39, 16 CPU, ~16 GB RAM cho Docker.
- Thư mục làm việc: `E:\PMMNM 2026\`.
  - Repo: `E:\PMMNM 2026\dxos` (nhánh `main`, có `.env` sinh từ `.env.example`, toàn giá trị `changeme`).
  - Script chạy thử: `E:\PMMNM 2026\_claude-run\` (`task4.ps1` … `task7b.ps1`, tệp `.bat` tương ứng, log).
- **Stack dev-lite đang chạy** trên máy này (project `dxos`). Tắt bằng Docker Desktop → Stop nhóm `dxos`.
- Cách phiên Claude cũ chạy thử trên máy này:
  1. Viết script **PowerShell 5.1, chỉ dùng ký tự ASCII**, kèm tệp `.bat` gọi `powershell -ExecutionPolicy Bypass -File`.
  2. Chép vào `_claude-run` (qua shell Linux trên máy, hoặc qua công cụ chép tệp).
  3. Mở File Explorer bằng computer use (chỉ được quyền **click**, không gõ phím được) và bấm đúp tệp `.bat`.
  4. Đọc log qua thư mục được kết nối.
- Bẫy đã gặp:
  - Tên hàm PowerShell trùng alias sẽ bị alias "ăn mất". Ví dụ `Measure` thành `Measure-Object`. Đặt tên dạng `Invoke-DxosXxx`.
  - `Tee-Object` ghi UTF-16; dùng `Out-File -Encoding ascii`.
  - Công cụ chép tệp có thể giữ bản cache cũ. Đổi tên tệp mới (ví dụ `task7b.ps1`) rồi kiểm lại nội dung trước khi chạy.
  - Cửa sổ Zalo, Cốc Cốc, ChatGPT/Codex hay chiếm màn hình nên computer use không click được. Khi đó nhờ người dùng tự bấm đúp `.bat`.
  - Quyền computer use hết hạn sau 30 phút không dùng; phải xin lại.
  - Shell Linux trên máy người dùng đôi khi không khởi động được; khi đó dùng công cụ chép tệp thay thế.
- Image không có công cụ quen thuộc:
  - APISIX (Debian): không có curl hay wget; có bash.
  - Flowable (Alpine): không có bash; có `nc` và `wget`.
  - Keycloak: không có curl; có bash.

### 6.2. Môi trường cloud của phiên Claude
- **Không kéo được image Docker** (Docker Hub, quay.io, ghcr đều bị chặn). Vì vậy:
  - Digest image được lấy trên máy người dùng (`docker buildx imagetools inspect`) rồi ghim bằng `ops/pin_images.py`.
  - Muốn test một dịch vụ Java thì **tải bản phát hành từ GitHub** và chạy bằng Java 21 có sẵn:
    - Keycloak 26.3.0: `bin/kc.sh start-dev --import-realm --http-relative-path=/auth`.
    - Flowable 7.1.0: `java -jar flowable-rest.war`. Biến môi trường có dấu gạch nối phải đặt bằng `env 'FLOWABLE_REST_APP_ADMIN_USER-ID=…'`.
- PyPI dùng được (`pip install --break-system-packages`). Tài khoản mới có thể có môi trường khác; hãy kiểm lại.

## 7. Các quyết định quan trọng đã đưa ra (tóm tắt ledger)
- Chạy Keycloak với `KC_HTTP_RELATIVE_PATH=/auth`, Caddy **không** cắt tiền tố. Nếu cắt, `token_endpoint` mất `/auth` (lỗi thật đã gặp).
- Realm khai báo `clientScopes` thì phải khai báo tường minh `basic/profile/roles/web-origins/acr`; nếu không, token thiếu `realm_access` và `sub` (lỗi thật đã gặp).
- `realm-dxos-dev.json` **sinh tự động** từ `realm-dxos.json` + `dev-overlay.json` bằng `ops/build_dev_realm.py`. Test tĩnh sẽ đỏ nếu sửa tay.
- Gateway (APISIX) chỉ xác thực token; **trust-core** kiểm vai trò `dxos-admin` (Task 10/12).
- `compose.test.yaml` dùng `fake-av` thay ClamAV để chạy nhanh. Nghiệm thu chính thức chạy ClamAV thật ở hồ sơ p8/p16.
- Hồ sơ dev-lite thay `clamav` bằng `fake-av` (nhãn `dxos.dev-only`). CI kiểm tra p8/p16 không chứa dịch vụ dev-only (AT-24).
- Chuỗi EICAR chỉ lưu dạng base64, không commit nguyên văn, để Windows Defender không cách ly tệp.
- Mọi image ghim `@sha256`, ghi trong `LICENSES-THIRD-PARTY.md`.
- Code of Conduct do đội tự viết, không chép Contributor Covenant.

Danh sách đầy đủ kèm "cái giá nếu sai": `docs/handoff/ledger-plan01.md`.

### Điểm nhỏ để sau (từ review)
- `canonical_bytes` ném `UnicodeEncodeError` (không phải `CanonicalError`) khi gặp surrogate lẻ. Records API (Task 13) phải kiểm đầu vào.
- `rfc3339_utc` cắt phần lẻ dưới giây.
- Merkle tính lại cây con nhiều lần (O(n log n)); đủ cho quy mô demo.
- Nâng `setuptools>=77` khi sửa đóng gói.
- `REUSE.toml` gán Apache-2.0 cho mọi `**/fixtures/**`; xem lại khi thêm tệp mẫu của bên thứ ba.
- Swagger của Flowable (`/flowable-rest/docs/`) mở không cần xác thực, nhưng chỉ trong `net-wf`; đưa vào mô hình đe dọa.

## 8. Lệnh nhanh
```bash
git clone https://github.com/PSA-OVNCR/dxos && cd dxos
python -m venv .venv && . .venv/bin/activate
make dev-install && make check            # ruff + REUSE + 82 test
python -m pytest -m infra tests/infra     # test sống, cần stack đang chạy
make up PROFILE=dev-lite                  # cần .env (cp .env.example .env)
make netcheck                             # 30/30 PASS
python ops/build_dev_realm.py --check     # realm dev khớp production + overlay
python ops/pin_images.py --dry-run        # liệt kê image chưa ghim
```
