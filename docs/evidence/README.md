# docs/evidence/: minh chứng kiểm thử thủ công

Ảnh chụp và log cho các AT kiểm thủ công, ví dụ AT-18 (force-push vào repo neo bị từ chối). Tên tệp: `at<NN>-<mô-tả>.png`.

| AT | Tệp | Trạng thái |
|---|---|---|
| AT-18 (deploy key không force-push được nhánh `main` của repo neo) | `anchor-lab-2026-10-23/at18-force-push.log` (repo thử); `at18-force-push-rejected.png` (repo chính, VPS) | Có trên repo thử `dxos-transparency-log-lab`: 22/10 GitHub từ chối force-push bằng khóa deploy (`GH013 … Cannot force-push`), ghi ở `docs/progress/2026-10-23-anchor-lab-github.md`. Repo chính: chờ deploy key trên VPS (`docs/runbook-anchor.md`) |
| AT-17 với repo neo GitHub thật; cổng đối soát chế độ ghim (V34) | `anchor-lab-2026-10-23/at17-verify-bundle-github.log`, `anchor-lab-2026-10-23/verify-github-pinned-app-b.png` | Có trên repo thử: `dxos-witness verify-bundle --anchor-dir` → `VALID OK`, 22/10 (`docs/progress/2026-10-23-anchor-lab-github.md`) |
| Witness độc lập (spec 11.4) | ghi tên người chạy, link repo witness, ngày bắt đầu | Chưa có: repo mẫu https://github.com/PSA-OVNCR/dxos-witness-kit đã tạo 21/10 |
| Trang đối soát tối giản (Plan 02 Task 10) | `verify-page-live-check.md`, `verify-page-1..8-*.png` | Có: chạy 21/10 trên Caddy 2.10.0 + API thật (không qua Docker, xem tệp); cần chụp lại trên dev-lite khi có Docker |
| E2E mốc M2 (Plan 02 Task 15): AT-05, 07, 08, 11, 12, 17, 19, 27, 28 | `docs/progress/2026-11-xx-m2-e2e.md` (theo mẫu `docs/progress/2026-10-20-task17-e2e.md`) + `e2e-junit.xml` | Có (Docker Desktop, chưa phải VPS): 22/10 chạy `pytest -m e2e tests/e2e` trên máy trưởng nhóm, 13 passed, 1 skipped (AT-20), ghi ở `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`; chưa chạy trên VPS |
| AT-13 (cài App B trên image đã phát hành, diff `core/` và gateway rỗng) | `at13-reuse.txt` (do `ops/at13_reuse.sh` ghi) | Chưa có: cần tag `v0.2.0` và image trên GHCR trước |
| AT-19 (40 request đồng thời + `X-Forwarded-For` giả → 429) | trong `e2e-junit.xml` của E2E M2 | Có: PASSED trên Docker Desktop 22/10 (`docs/progress/2026-10-22-e2e-m2-docker-desktop.md`, chạy lại trên mã M3 ở `docs/progress/2026-10-22-web-live.md`); VPS chưa |
| AT-20 (OpenBao khóa trước task cuối → 503, task còn ở Flowable; mở khóa → `SEALED`) | trong kết quả pytest chạy trên máy chủ | Có: PASSED trên Docker Desktop 22/10 sau bản sửa `40d6d64` (V36, `docs/progress/2026-10-22-web-live.md`). Giới hạn: trường hợp OpenBao hỏng **sau** khi Flowable đã hoàn thành chỉ chứng minh ở integration test (Plan 02 Task 7, `FlakySigner`) |
| Kiểm trình duyệt thật App A, App B, cổng đối soát (Plan 03 Task 10, V27) | `docs/progress/<ngày>-web-live.md` + `web-live-junit.xml` + `shots/*.png` | Có: 10 passed trên Docker Desktop 22/10 (`docs/progress/2026-10-22-web-live.md`, ảnh và junit ở `docs/evidence/web-live-2026-10-22/`) |
| Cổng năng suất M2 | `docs/progress/2026-11-16.md` | Chưa có: trưởng nhóm ghi sau khi chạy xong các mục trên |

Mỗi minh chứng ghi kèm: ngày giờ, commit của `dxos`, lệnh đã chạy và kết quả.

## Việc chờ chạy (Plan 02 Task 15)

Lệnh đầy đủ ở `BUILD.md` (mục E2E, "Chạy bằng image đã phát hành") và ở đầu từng script. Tóm tắt thứ tự:
1. dev-lite: `ops/e2e/run_e2e.sh` trong container (BUILD.md, mục E2E).
2. VPS, hồ sơ p16 (ClamAV thật): E2E M1 + M2, rồi AT-20 trên máy chủ (`tests/e2e/test_m2_attacks.py`).
3. Trưởng nhóm đổi phiên bản, ghi ngày vào CHANGELOG, gắn tag `v0.2.0` (BUILD.md, mục Phát hành); workflow `release`
   đẩy image lên GHCR và ghi digest.
4. VPS chạy image theo digest (`deploy/compose.release.yaml`), cài App A, rồi `ops/at13_reuse.sh` (người duyệt App B
   khác người nộp; `DXOS_ALLOW_SELF_APPROVAL=false`).
5. Ghi kết quả vào các tệp ở bảng trên; điền bảng "Thành viên đã đọc toàn văn" trong `docs/legal-mapping.md`.

## Người dùng dev tạm trên VPS (quyết định của trưởng nhóm)

> **Cảnh báo:** E2E M2 và bước e2e App B của AT-13 lấy token bằng client `dxos-test` và người dùng dev có **mật khẩu
> đã biết** (`dev-only-password`, gồm hai tài khoản `dxos-admin`). Realm production trên VPS không có chúng. Thêm tạm
> là quyết định của trưởng nhóm; gỡ ngay sau khi chạy xong. Các lệnh dưới đây chưa được chạy thử.

Thêm (sau `git pull`, trên VPS):
```bash
python ops/keycloak_upgrade.py --profile dev-lite
```
Gỡ người dùng dev và client `dxos-test`:
```bash
read -rs KC_CLI_PASSWORD && export KC_CLI_PASSWORD      # KEYCLOAK_ADMIN_PASSWORD trong .env
KC="docker exec -e KC_CLI_PASSWORD dxos-keycloak-1 /opt/keycloak/bin/kcadm.sh"
$KC config credentials --config /tmp/kc.cfg --server http://localhost:8080/auth --realm master --user admin
for u in chuyen_vien1 chuyen_vien_tp1 truong_phong1 giam_doc1 van_thu1 nhan_vien1 can_bo_clb1 truong_clb1 owner_a1 owner_b1 admin1 admin2; do
  id=$($KC get users --config /tmp/kc.cfg -r dxos -q username=$u -q exact=true --fields id --format csv --noquotes)
  [ -n "$id" ] && $KC delete users/$id --config /tmp/kc.cfg -r dxos
done
cid=$($KC get clients --config /tmp/kc.cfg -r dxos -q clientId=dxos-test --fields id --format csv --noquotes)
[ -n "$cid" ] && $KC delete clients/$cid --config /tmp/kc.cfg -r dxos
docker exec dxos-keycloak-1 rm -f /tmp/kc.cfg
unset KC_CLI_PASSWORD
```
Kiểm đã gỡ: `python ops/keycloak_upgrade.py` (hồ sơ p16) không còn báo người dùng thừa, và password grant của
`dxos-test` trả lỗi `invalid_client`.

## Kiểm trình duyệt thật (V27, Plan 03 Task 10)

Việc của máy trưởng nhóm (Windows + Docker Desktop). Đã chạy 22/10/2026 bằng `bash ops/web_build_docker.sh` rồi `bash ops/web_live.sh` trong Git Bash (kết quả: `docs/progress/2026-10-22-web-live.md`); tệp `.bat` mẫu dưới đây chưa chạy nguyên văn.
Điều kiện: stack dev-lite đang chạy cùng overlay e2e, Keycloak đã nạp người dùng dev, App A và App B đã cài (BUILD.md, mục E2E).

1. Ghim digest hai image mới (một lần, rồi commit `ops/web_build_docker.sh` và `ops/web_live.sh`):
   `python ops/pin_images.py`
2. Dựng SPA vào volume và chạy bộ kiểm. Tệp mẫu `web-live.bat` (đặt ngoài repo, ví dụ `E:\PMMNM 2026\web-live.bat`; sửa `REPO`):
```bat
@echo off
rem Dung SPA roi chay bo kiem trinh duyet that. Can Docker Desktop dang chay, stack dev-lite dang chay, Git for Windows.
set REPO=E:\PMMNM 2026\dxos
set BASH="C:\Program Files\Git\bin\bash.exe"
set CHERE_INVOKING=1
set MSYS_NO_PATHCONV=1
cd /d "%REPO%" || exit /b 1
%BASH% -l ops/web_build_docker.sh || exit /b 1
%BASH% -l ops/web_live.sh
echo Ket qua: %REPO%\test-results\web-live  (web-live-junit.xml, shots\*.png)
pause
```
3. Ghi `docs/progress/<ngày>-web-live.md`: ngày giờ, commit, kết quả `web-live-junit.xml`, ảnh trong `shots/`
   (kể cả `verify-1-app-b.png`), mọi test đỏ kèm trace ở `artifacts/`.

Rủi ro đã biết khi chạy lần đầu: (a) Chromium trong container phải ép `localhost` về máy chủ Docker bằng
`--host-resolver-rules` (đã cấu hình, chưa thử); (b) CA nội bộ của Caddy được bỏ qua ở phía trình duyệt bằng
`ignoreHTTPSErrors` (chỉ Node dùng `NODE_EXTRA_CA_CERTS`); (c) bộ kiểm báo đỏ nếu console có vi phạm CSP của `/apps/*`,
kể cả do một thư viện chèn style nội tuyến; (d) cổng đối soát chờ worker công bố STH nên có thể mất vài phút.
