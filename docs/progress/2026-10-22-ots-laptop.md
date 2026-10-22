<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# OpenTimestamps với calendar thật trên laptop trưởng nhóm (V32) — 22/10/2026

| Mục | Giá trị |
|---|---|
| Stack | p8 + `compose.e2e.yaml` (repo neo là **bare repo cục bộ** trong volume `dxos_anchor-repo`, không phải GitHub), commit `f577586` |
| Cấu hình | `DXOS_OTS_CALENDARS=https://a.pool.opentimestamps.org,https://b.pool.opentimestamps.org` (thêm vào `.env` trên laptop, đã sao lưu `.env` trước) |
| Công cụ kiểm | `opentimestamps-client` v0.7.2 (công cụ của người kiểm, cài trong container dùng một lần, không vào DX-OS) |

## Kết quả

1. Worker gọi calendar thật và commit biên nhận vào repo neo. `git log` của repo neo cục bộ có các commit `ots 602`, `ots 646`,
   `ots 651`, `ots 673`, `ots 706`, mỗi commit thêm `ots/<n 12 chữ số>.ots` (47 tệp `sth/` lúc kiểm).
2. `ots info` trên `ots/000000000602.ots` và `ots/000000000706.ots`:
   - `File sha256 hash` bằng đúng `sha256sum sth/<n>.json`:
     - STH 602: `27b0aec2…26e93b`;
     - STH 706: `d05e5dc6…c68e23`.
   - Mỗi tệp có hai nhánh pending: `alice.btc.calendar.opentimestamps.org` và `bob.btc.calendar.opentimestamps.org`. Pool `a.`/`b.` chuyển tiếp tới hai calendar này.
3. `ots upgrade` (trên bản sao) với cả hai tệp: `Got 1 attestation(s)` từ mỗi calendar, rồi `Success! Timestamp complete`.
4. `ots --no-bitcoin verify -f sth/<n>.json <n>.ots`: "check that Bitcoin block **972609** has merkleroot
   `004b31769d032519d1b661346b2723dd436e8a48924c5e8d0f58d0ec36ecab93`".
5. Đối chiếu với block explorer công khai:
   - `https://mempool.space/api/block-height/972609` → hash `00000000000000000001a4b1e376cb4869d2bc5a86b9ec9fbf844c7f2bd8dcd7`;
   - `https://mempool.space/api/block/<hash>` → `merkle_root` = `004b31769d032519d1b661346b2723dd436e8a48924c5e8d0f58d0ec36ecab93`, **khớp**. Thời điểm khối `1792667140` (2026-10-22 11:05:40 UTC).

Kết luận: chuỗi STH → biên nhận OTS → khối Bitcoin kiểm được bằng công cụ chính thức. Bước cuối dựa vào block explorer thay vì nút Bitcoin riêng (spec cho phép người kiểm tự chọn).

## Chưa làm

- Neo vào repo GitHub thật (V34, repo thử `dxos-transparency-log-lab` chưa tạo). Khi có, tệp `ots/` cũng lên GitHub.
- Trên VPS: bật như runbook mục 6 khi triển khai.
- Không chạy `DXOS_OTS_CLIENT=ots python -m pytest core/tests/test_ots.py -k official` (bước tùy chọn).

Log: `E:\PMMNM 2026\_claude-run\m3-8-ots-check.log`, `m3-9-ots-verify.log` trên máy trưởng nhóm.
