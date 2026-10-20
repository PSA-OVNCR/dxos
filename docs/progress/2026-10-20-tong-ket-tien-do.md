# Tổng kết tiến độ DX-OS Trust Core — 20/10/2026

*Đội PSA_OVNCR · Kho mã: https://github.com/PSA-OVNCR/dxos (public, Apache-2.0) · Cập nhật đến commit `34d1c10`.*

> **Đã cũ.** Bản mới nhất: `2026-10-21-tong-ket-tien-do.md`.

Tài liệu này dành cho thành viên mới và người review: đọc xong biết dự án đang ở đâu, cái gì đã chứng minh được và cái gì còn phải làm.

## 1. Mốc thời gian
| Mốc | Ngày | Nội dung chính | Trạng thái |
|---|---|---|---|
| M0 | 26/10 | Hạ tầng chạy được, AT-01 bản đầu, đo RAM, spike Flowable | Gần xong (thiếu đo RAM, chạy trên VPS) |
| **M1** | **09/11** | Lõi Tier-0 phần 1, release **v0.1.0** | Đang làm: 6/17 task của Plan 01 |
| M2 | 16/11 | v0.2.0: guard + BPMN, niêm phong, installer, App A và B cài bằng manifest, witness | Chưa bắt đầu |
| M3 | 23/11 | v0.3.0: SDK, SPA A và B, cổng đối soát, triển khai VPS theo tag, hướng dẫn; toàn bộ MUST xong | Chưa bắt đầu |
| M4 | 30/11 | v0.9.0: SHOULD theo năng suất, chạy thử với người dùng, tài liệu + SBOM | Chưa bắt đầu |
| M5 | 04/12 | v1.0.0: AT-23, AT-26 trên máy sạch; đóng băng mã; checklist nộp bài | Chưa bắt đầu |
| Nộp bài | sáng 06/12 | | |
| Chung kết | 10/12 | Chỉ demo | |

## 2. Đã làm được

### 2.1. Thiết kế (đã duyệt)
- Design Spec 1.0.1: `docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`
- Plan 00 (kế hoạch tổng thể) và Plan 01 (M0 → M1): `docs/superpowers/plans/`
- Hướng sản phẩm: **DX-OS Trust Core** (Tầng 1 headless) với **App A "Phòng hồ sơ số"** (ứng dụng chính) và **App B "Chứng nhận số"** (ứng dụng nhỏ). Hai app dùng chung lõi, không sửa lõi (P1), không vượt chính sách (P2), mọi kết quả quan trọng kiểm chứng được (P3).

### 2.2. Plan 01: đã xong 6/17 task
| Task | Nội dung | Bằng chứng |
|---|---|---|
| 1 | Khung repo theo PoF: LICENSE Apache-2.0, NOTICE, SPDX/REUSE, README vi/en, BUILD, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CI 4 job | CI xanh; `reuse lint` đạt |
| 2 | `libs/dxos-proof`: canonical JSON (NFC, UTC, cấm số thực) | 9 test |
| 3 | `libs/dxos-proof`: cây Merkle RFC 6962, inclusion proof và consistency proof | 14 test, có test vector |
| 4 | Docker Compose: 13 container, **9 mạng phân vùng**; hồ sơ p16, p8, dev-lite, test; Caddy; APISIX; `fake-av`; `ops/netcheck.py`; ghim digest 10 image | Chạy thật trên Docker Desktop: **13/13 healthy, netcheck 30/30 PASS**, API không token → 401 (`docs/progress/2026-10-20-task4-kiem-tra-song.md`) |
| 5 | Realm Keycloak `dxos`: vai trò `dxos-admin`, client `dxos-spa` (PKCE S256), `apisix`, `dxos-installer`, audience `dxos-api`; bản dev có 10 người dùng | 18/18 test trên Keycloak 26.3.0; trên stack: **10/10 token đúng vai trò**, token thật đi qua APISIX (`docs/progress/2026-10-20-task5-realm-keycloak.md`) |
| 6 | Spike Flowable 7.1.0 | **SMOKE OK** trên stack; giữ ADR-09; bản OSS không có console admin (`docs/spikes/flowable.md`) |

### 2.3. GitHub
- Tổ chức `PSA-OVNCR`, repo `dxos` public; đã bật Issues, Discussions, Private vulnerability reporting.
- Ruleset `protect-main`: cấm force-push và cấm xóa `main`. Đội push thẳng vào `main`, không bắt buộc review.
- CI (`.github/workflows/ci.yml`): `reuse`, `lint` (ruff), `unit` (pytest), `secrets` (gitleaks). Tất cả xanh.

### 2.4. Lỗi thật phát hiện nhờ chạy sống (đã sửa, có test chặn tái phát)
1. Caddy cắt tiền tố `/auth` làm Keycloak trả `token_endpoint` sai. Sửa: Keycloak chạy dưới `/auth` cả trong lẫn ngoài.
2. Image APISIX không có `curl`, image Flowable không có `bash`, nên healthcheck báo hỏng dù dịch vụ chạy. Sửa: dùng công cụ có sẵn trong từng image.
3. Realm khai báo `clientScopes` thì Keycloak bỏ scope mặc định, token thiếu vai trò và `sub`. Sửa: khai báo tường minh các scope chuẩn.

## 3. Chưa làm được

### 3.1. Đang dở
- **Task 7, đo RAM (AT-22):** công cụ đã có (`ops/measure.sh`, `ops/capacity_report.py`). Chưa có số đo thật, đang chạy `chay-task7b.bat` trên máy trưởng nhóm. Khi xong sẽ có `docs/capacity.md`.

### 3.2. Còn lại của Plan 01 (trước M1, 09/11)
| Task | Nội dung | Hạn |
|---|---|---|
| 8 | Khung trust-core (FastAPI api + worker) và migration DB; thay image stub | 29/10 |
| 9 | Ledger (chỉ số liên tục, khóa advisory) | 30/10 |
| 10 | Identity: kiểm JWT, ánh xạ vai trò `app:<id>:<role>` | 29/10 |
| 11 | Schema manifest, validator, kho manifest | 31/10 |
| 12 | PDP và che PII | 03/11 |
| 13 | Records API | 06/11 |
| 14 | Upload → kiểm dịch → CAS, hàng đợi, worker | 07/11 |
| 15 | STH ký qua OpenBao transit, endpoint xác minh | 04/11 |
| 16 | Neo GitHub, `dxos-witness`, endpoint quản trị neo | 07/11 |
| 17 | E2E M1 và **release v0.1.0** | 09/11 |

### 3.3. Chưa có (sau M1, thuộc Plan 02–04)
- Workflow bridge, danh mục guard, BPMN; niêm phong (`SEAL_PENDING`), thu hồi, cổng đối soát.
- Installer và CLI `dxos`; UI admin Tầng 1.
- SDK JS; SPA App A và App B; viewer.
- Bộ AT tự động AT-01..26; hướng dẫn "Viết app DX-OS trong 30 phút".
- Triển khai VPS theo tag; release v1.0.0.

### 3.4. Việc chưa kiểm chứng hoặc còn mở
- Mới đo trên Docker Desktop của trưởng nhóm. **Chưa chạy trên VPS** (tiêu chí M0).
- Test sống bằng pytest (`make test-infra`) chưa chạy trên Linux/WSL. Trên Windows mới chạy script PowerShell làm việc tương đương.
- Hồ sơ p8/p16 với ClamAV thật: chờ kết quả Task 7.
- Repo neo cho STH (có bảo vệ nhánh) và **witness độc lập**: phải có trước 16/11.
- Hỏi BTC: được commit trong thời gian chấm không, có cần nộp `.zip` không; đăng ký qua trường/GV.

## 4. Thành viên
| GitHub | Vai trò trong tổ chức | Ghi chú |
|---|---|---|
| UI-UX-USHP | Owner | Trưởng nhóm |
| Levminh | Owner (đã mời 20/10, chờ chấp nhận) | Toàn quyền tổ chức và repo |
| kirito99152 (Cao Thanh Phong) | Owner (đã mời 20/10, chờ chấp nhận) | Toàn quyền tổ chức và repo |

Phân chia theo Plan 00: TV-A hạ tầng/lõi, TV-B ledger/kiểm dịch/PDP, TV-C workflow/nền tảng/Tầng 2. **Cần chốt ai là TV-A/B/C.**

## 5. Bắt đầu nhanh cho thành viên mới
```bash
git clone https://github.com/PSA-OVNCR/dxos && cd dxos
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
make dev-install && make check                    # lint + REUSE + test đơn vị
cp .env.example .env
make up PROFILE=dev-lite                          # Docker Desktop / Docker Engine
make netcheck                                     # phân vùng mạng: 30/30 PASS
```
Người dùng dev: `chuyen_vien1`…`admin1`, mật khẩu `dev-only-password` (chỉ ở hồ sơ dev-lite). Chi tiết: `BUILD.md`.
