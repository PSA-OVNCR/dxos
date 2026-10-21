# docs/evidence/: minh chứng kiểm thử thủ công

Ảnh chụp và log cho các AT kiểm thủ công, ví dụ AT-18 (force-push vào repo neo bị từ chối). Tên tệp: `at<NN>-<mô-tả>.png`.

| AT | Tệp | Trạng thái |
|---|---|---|
| AT-18 (deploy key không force-push được nhánh `main` của repo neo) | `at18-force-push-rejected.png` | Chưa có: repo neo và ruleset đã tạo 21/10; chờ deploy key trên VPS (`docs/runbook-anchor.md`) |
| Witness độc lập (spec 11.4) | ghi tên người chạy, link repo witness, ngày bắt đầu | Chưa có: repo mẫu https://github.com/PSA-OVNCR/dxos-witness-kit đã tạo 21/10 |
| Trang đối soát tối giản (Plan 02 Task 10) | `verify-page-live-check.md`, `verify-page-1..8-*.png` | Có: chạy 21/10 trên Caddy 2.10.0 + API thật (không qua Docker, xem tệp); cần chụp lại trên dev-lite khi có Docker |

Mỗi minh chứng ghi kèm: ngày giờ, commit của `dxos`, lệnh đã chạy và kết quả.
