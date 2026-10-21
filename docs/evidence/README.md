# docs/evidence/: minh chứng kiểm thử thủ công

Ảnh chụp và log cho các AT kiểm thủ công, ví dụ AT-18 (force-push vào repo neo bị từ chối). Tên tệp: `at<NN>-<mô-tả>.png`.

| AT | Tệp | Trạng thái |
|---|---|---|
| AT-18 (deploy key không force-push được nhánh `main` của repo neo) | `at18-force-push-rejected.png` | Chưa có: repo neo và ruleset đã tạo 21/10; chờ deploy key trên VPS (`docs/runbook-anchor.md`) |
| Witness độc lập (spec 11.4) | ghi tên người chạy, link repo witness, ngày bắt đầu | Chưa có: repo mẫu https://github.com/PSA-OVNCR/dxos-witness-kit đã tạo 21/10 |
| Trang đối soát tối giản (Plan 02 Task 10) | `verify-page-live-check.md`, `verify-page-1..8-*.png` | Có: chạy 21/10 trên Caddy 2.10.0 + API thật (không qua Docker, xem tệp); cần chụp lại trên dev-lite khi có Docker |
| E2E mốc M2 (Plan 02 Task 15): AT-05, 07, 08, 11, 12, 17, 19, 27, 28 | `docs/progress/2026-11-xx-m2-e2e.md` (theo mẫu `docs/progress/2026-10-20-task17-e2e.md`) + `e2e-junit.xml` | Chưa có: test đã viết (`tests/e2e/test_m2_*.py`), chưa chạy trên dev-lite hay VPS |
| AT-13 (cài App B trên image đã phát hành, diff `core/` và gateway rỗng) | `at13-reuse.txt` (do `ops/at13_reuse.sh` ghi) | Chưa có: cần tag `v0.2.0` và image trên GHCR trước |
| AT-19 (40 request đồng thời + `X-Forwarded-For` giả → 429) | trong `e2e-junit.xml` của E2E M2 | Chưa có |
| AT-20 (OpenBao khóa trước task cuối → 503, task còn ở Flowable; mở khóa → `SEALED`) | trong kết quả pytest chạy trên máy chủ | Chưa có. Giới hạn: trường hợp OpenBao hỏng **sau** khi Flowable đã hoàn thành chỉ chứng minh ở integration test (Plan 02 Task 7, `FlakySigner`) |
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

