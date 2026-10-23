<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Neo vào repo GitHub thật (repo thử) trên laptop trưởng nhóm: AT-18, AT-17, V34 — 22–23/10/2026

| Mục | Giá trị |
|---|---|
| Repo neo | `PSA-OVNCR/dxos-transparency-log-lab`, công khai, **repo thử**: tách khỏi repo chính `dxos-transparency-log`, để lịch sử laptop không lẫn vào lịch sử VPS |
| Bảo vệ nhánh | Ruleset `protect-main` (Active, nhánh mặc định): Restrict deletions, Block force pushes, Require linear history; danh sách bypass trống |
| Khóa deploy | `dxos-anchor-lab`, quyền ghi, vân tay `SHA256:0tGGFLCZ14DPHp2M/EZOJMecfOc8vwu9t26lB54llg0`. Khóa riêng chỉ nằm trên laptop, trong thư mục đã gitignore, gắn vào worker bằng Docker secret |
| Stack | p8 + `deploy/compose.anchor.yaml` + overlay cục bộ (đặt `DXOS_ANCHOR_REPO_DIR=/var/lib/dxos/anchor-lab`, `DXOS_ANCHOR_GIT_SSH_COMMAND` đọc khóa từ secret), commit `db7d56c` |
| `.env` | `DXOS_ANCHOR_REMOTE=git@github.com:PSA-OVNCR/dxos-transparency-log-lab.git`, `DXOS_ANCHOR_RAW_ORIGIN=https://raw.githubusercontent.com`, `VITE_ANCHOR_RAW_BASE=https://raw.githubusercontent.com/PSA-OVNCR/dxos-transparency-log-lab/main` (đã sao lưu `.env` trước khi sửa) |

## AT-18: khóa deploy không force-push được (Đạt)

Trong container dùng một lần: clone bằng khóa deploy, `git commit --amend`, rồi `git push --force origin main`.
GitHub từ chối: `GH013: Repository rule violations … Cannot force-push to this branch`, `! [remote rejected] main -> main`.
Lịch sử trên GitHub sau lần thử vẫn là `5d364b8 Initial commit`. Log: `docs/evidence/anchor-lab-2026-10-23/at18-force-push.log`.

Clone SSH bằng cùng khóa chạy được, nên lần từ chối là do ruleset chứ không phải do khóa sai.

## Worker neo lên GitHub (Đạt)

Worker chỉ neo khi sổ cái có lá mới (`maybe_schedule`). Vì vậy trong 10 phút chờ đầu tiên chưa có commit nào. Lần neo đầu
xảy ra khi bộ kiểm trình duyệt tạo niêm phong:

| Commit | Giờ (UTC) | Nội dung |
|---|---|---|
| `1a1af36` | 2026-10-22 17:27:20 | `sth 721` (lần đẩy đầu, kèm `keys/sth-key/v1.pub`, `keys/seal-key/v1.pub`, `keys/seal-key/v1.json`) |
| `02cfa66` | 17:27:34 | `ots 721` |
| `273aa2d`, `1d6d45e` | 17:27:56, 17:28:09 | `sth 753`, `ots 753` |
| `4ee7056`, `421ea2c` | 17:28:18, 17:28:32 | `sth 710`, `ots 710` |
| `572b843`, `952f3b2` | 17:32:57, 17:33:11 | `sth 754`, `ots 754` (do `POST /admin/v1/anchor:run`) |

`GET /admin/v1/ledger/status` sau `anchor:run`: `last_anchor.commit_sha = 572b84360faf2e0cac3568621b20217bad66c2d0`, trùng commit
`sth 754` trên GitHub. STH 710 được đẩy sau STH 753 vì các việc neo chạy song song; mỗi STH là một tệp riêng nên thứ tự đẩy không
ảnh hưởng việc kiểm.

## AT-17 với repo GitHub thật (Đạt)

Gói bằng chứng của niêm phong `ZW7SM467PVY66YKNHGMRSQIJOE` (App B) lấy từ `GET /verify/v1/seals/<id>/bundle`. Repo neo được
clone qua https công khai, rồi chạy `dxos-witness verify-bundle /tmp/bundle.json --anchor-dir /tmp/anchor`:

```
VALID OK; khóa đã ghim từ repo neo; đã neo: sth/000000000754.json; OTS: biên nhận OpenTimestamps cho sth/000000000754.json đang chờ xác nhận trên Bitcoin …
(witness exit 0)
```

Log: `docs/evidence/anchor-lab-2026-10-23/at17-verify-bundle-github.log`.

## Cổng đối soát chế độ ghim (V34)

**Lần 1 (22/10, 17:27 UTC): 8 passed, 1 failed, 1 did not run.** Test hỏng là App A, bước "mở verify_url, chọn đúng tệp PDF
và thấy Hợp lệ": cổng hiện `Không hợp lệ`; trace ghi `keys/seal-key/v1.pub` trả 404. Test chạy cùng phút với lần neo đầu
(17:27:20 UTC), lúc đó khóa chưa có trên GitHub hoặc CDN của raw.githubusercontent.com còn giữ câu trả lời 404.

Ruling: giữ nguyên "thiếu khóa niêm phong trong repo neo → Không hợp lệ (`KEY_NOT_ANCHORED`)" — coi 404 là "chưa đối chiếu"
thì máy chủ bị chiếm chỉ cần dùng khóa chưa neo để né việc ghim — cái giá nếu sai: vài phút đầu sau khi nối repo neo mới,
người xem thấy "Không hợp lệ"; runbook yêu cầu chạy `anchor:run` và chờ CDN trước khi phát niêm phong.

**Lần 2 (23/10, sau khi laptop khởi động lại, `chay-m3-13-lab-web.bat`): 8 passed, 1 failed, 1 did not run.**
- Lần chạy trước đó cùng ngày hỏng 3 test vì OpenBao khóa sau khi máy khởi động lại (lõi chặn bước duyệt cuối khi KMS khóa,
  đúng thiết kế R-1). Script nay tự mở khóa bằng `m2-5-unseal.ps1` nếu thấy `"sealed": true`.
- Cả bốn tệp khóa trên GitHub trả 200.
- **Cổng đối soát với niêm phong App B: "Hợp lệ — đã đối chiếu repo neo"**, repo đối chiếu
  `https://raw.githubusercontent.com/PSA-OVNCR/dxos-transparency-log-lab/main` (ảnh
  `docs/evidence/anchor-lab-2026-10-23/verify-github-pinned-app-b.png`). Test này chờ (tải lại trang) cho tới khi STH phủ
  niêm phong được neo.
- Test App A vẫn hỏng, lần này vì lý do khác: `NOT_ANCHORED: STH đã neo (cỡ 754) chưa phủ lá 791`. Niêm phong vừa ban hành,
  STH phủ nó chưa được đẩy lên repo neo, và test không chờ. Ở chế độ ghim, bộ kiểm JS (giống `dxos-witness --anchor-dir`,
  ruling C8 của Plan 02) coi "chưa neo" là hỏng, nên cổng hiện **"Không hợp lệ"** cho một niêm phong thật vừa phát.

Đây là lỗi sản phẩm, không chỉ là lỗi test: ngay sau khi ban hành (đúng lúc demo), cổng ở chế độ ghim nói văn bản thật là
"Không hợp lệ". Đã đưa vào Plan 04 Task 14: khi khóa đã đối chiếu repo neo mà STH phủ niêm phong chưa được neo, cổng báo
"Hợp lệ — chưa neo công khai" (như khi không ghim), không báo "Không hợp lệ"; `dxos-witness --anchor-dir` giữ kiểm chặt.

## Chưa làm

- Sửa cổng cho niêm phong chưa neo (Plan 04 Task 14), rồi chạy lại bộ trình duyệt với repo neo GitHub.
- Trên VPS: dùng repo chính `dxos-transparency-log` với khóa deploy riêng của VPS, `DXOS_ANCHOR_REPO_DIR` mới (runbook mục 3).
- Witness độc lập theo dõi repo neo chính.

Log gốc trên máy trưởng nhóm: `E:\PMMNM 2026\_claude-run\m3-10-lab-anchor.log`, `m3-11-anchor-verify.log`, `m3-13-lab-web.log`.
