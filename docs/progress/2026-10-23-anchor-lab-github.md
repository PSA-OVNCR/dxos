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

## Cổng đối soát chế độ ghim (V34): chưa đạt, cần chạy lại

Lần build cổng có `VITE_ANCHOR_RAW_BASE` rồi chạy bộ trình duyệt thật (`ops/web_live.sh`): 8 passed, 1 failed, 1 did not run.
Test hỏng là App A, bước "mở verify_url, chọn đúng tệp PDF và thấy Hợp lệ": cổng hiện `Không hợp lệ`. Trace ghi
`GET https://raw.githubusercontent.com/PSA-OVNCR/dxos-transparency-log-lab/main/keys/seal-key/v1.pub` trả 404.

Nguyên nhân, nhiều khả năng: test chạy trong cùng phút với lần neo đầu (17:27:20 UTC). Lúc test hỏi, `keys/seal-key/v1.pub` chưa
có trên GitHub, hoặc CDN của raw.githubusercontent.com còn giữ câu trả lời 404 (bộ đệm khoảng 5 phút). Từ 17:33 UTC repo đã đủ
`keys/` và `sth/`, và AT-17 ở trên đạt với chính các tệp đó.

Ruling: giữ nguyên hành vi "thiếu khóa niêm phong trong repo neo → Không hợp lệ (`KEY_NOT_ANCHORED`)" — nếu coi 404 là "chưa đối
chiếu" thì máy chủ bị chiếm chỉ cần dùng một khóa chưa neo để né việc ghim; lời giải thích trên cổng đã nói rõ "khóa niêm phong
chưa có trong repo neo" — cái giá nếu sai: người xem thấy "Không hợp lệ" trong vài phút đầu sau khi đổi repo neo, nên runbook
yêu cầu chạy `anchor:run` và chờ CDN trước khi phát niêm phong.

Chưa chạy lại được bộ trình duyệt: lúc định chạy lại, laptop đã khóa màn hình, các tệp `.bat` không khởi động. Việc còn lại:
chạy `chay-m3-12-web-lab2.bat` (thư mục `_claude-run`), kỳ vọng 10 passed và cổng hiện "Hợp lệ" kèm "đã đối chiếu repo neo".

## Chưa làm

- Chạy lại bộ trình duyệt với repo neo GitHub (trên).
- Trên VPS: dùng repo chính `dxos-transparency-log` với khóa deploy riêng của VPS, `DXOS_ANCHOR_REPO_DIR` mới (runbook mục 3).
- Witness độc lập theo dõi repo neo chính.

Log gốc trên máy trưởng nhóm: `E:\PMMNM 2026\_claude-run\m3-10-lab-anchor.log`, `m3-11-anchor-verify.log`.
