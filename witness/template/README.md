# Repo neo `dxos-transparency-log` và witness

Repo này nhận các Signed Tree Head (STH) mà DX-OS ký bằng OpenBao: mỗi STH là một tệp `sth/<tree_size 12 chữ số>.json`.
Cùng commit với STH còn có khóa công khai `keys/seal-key/v<n>.pub`, `keys/sth-key/v<n>.pub` (base64 khóa ed25519 + xuống
dòng) và tuyên bố khóa `keys/seal-key/v<n>.json` (tên tổ chức, thời hạn hiệu lực của khóa niêm phong; spec 25.3).
Nhánh `main` được bảo vệ (cấm force-push, cấm xóa, lịch sử tuyến tính), nên bên vận hành DX-OS **không** viết lại được
lịch sử đã neo, kể cả khi có quyền root trên VPS (spec 11.3, mô hình X3).

## Chạy witness độc lập trên máy của bạn (khuyến nghị: người ngoài đội)
Theo spec 11.4, cần **ít nhất một witness chạy ngoài tài khoản và tổ chức GitHub của đội** (chống X4).
```bash
git clone https://github.com/<chủ-repo>/dxos-transparency-log
python -m pip install "dxos-proof @ git+https://github.com/PSA-OVNCR/dxos@v0.1.0#subdirectory=libs/dxos-proof" \
                      "dxos-witness @ git+https://github.com/PSA-OVNCR/dxos@v0.1.0#subdirectory=witness"
dxos-witness sync --server https://<DXOS_DOMAIN> --anchor-dir dxos-transparency-log --state-dir ~/.dxos-witness
```
Đặt lệnh trên chạy theo lịch (cron, Task Scheduler). Mã thoát `0`: bình thường; `2`: bất thường, hãy báo cho đội và
giữ lại thư mục `--state-dir` làm bằng chứng.

| Kết quả | Ý nghĩa |
|---|---|
| `FIRST_RUN` / `OK` | STH mới nhất có chữ ký đúng, khớp repo neo, nhất quán với lần kiểm trước |
| `BAD_SIGNATURE` | Chữ ký sai, hoặc khóa công khai của cùng phiên bản bị thay (`key_mismatch_anchor`: khóa máy chủ đưa khác `keys/…/v<n>.pub` trong repo neo) |
| `ANCHOR_MISMATCH` | STH máy chủ trả khác tệp trong repo neo |
| `REWRITE_DETECTED` | Cùng kích thước mà root khác, hoặc cây nhỏ đi |
| `INCONSISTENT` | Consistency proof từ lần trước tới nay không hợp lệ: lịch sử đã bị viết lại |

## Kiểm gói bằng chứng niêm phong ngoại tuyến (`verify-bundle`)
Trên trang đối soát, bấm tải **gói bằng chứng** (`dxos-seal-<id>.json`). Gói chứa payload đã ký, lá ledger, inclusion
proof, STH và consistency proof tới STH đã neo, đủ để kiểm **không cần mạng** (spec 11.5; AT-17).
```bash
git -C dxos-transparency-log pull          # verify-bundle không tự pull: cập nhật repo neo trước
dxos-witness verify-bundle dxos-seal-<id>.json --anchor-dir dxos-transparency-log --file quyet-dinh.pdf
```
- `--anchor-dir`: khóa `seal-key`/`sth-key` và tuyên bố khóa **chỉ** lấy từ repo neo; khóa đi kèm gói chỉ là gợi ý,
  khác khóa đã neo thì gói `INVALID KEY_MISMATCH`. STH đã neo phải phủ niêm phong và trùng từng byte với
  `sth/<tree_size>.json`.
- `--file`: SHA-256 của tệp được tính **ngay trên máy bạn**; tệp không được gửi đi đâu. Hash phải thuộc niêm phong.
- Kết quả in `VALID …` hoặc `INVALID <MÃ>: …`, kèm dòng `Niêm phong bởi: <tên tổ chức> (<mã định danh>)` khi hợp lệ.

| Mã thoát | Ý nghĩa |
|---|---|
| `0` | `VALID` và **đã ghim** khóa từ repo neo |
| `3` | `VALID` nhưng **chưa ghim** (không có `--anchor-dir`) |
| `2` | `INVALID`, hoặc không đọc được gói/tệp |

**"Chưa ghim"** (unpinned): khóa lấy từ chính gói, nên kết quả chỉ cho thấy gói tự nhất quán. Ai làm giả cả gói lẫn
khóa đi kèm vẫn có thể đạt mã 3. Chỉ mã 0 (khóa từ repo neo có bảo vệ nhánh) mới chứng minh niêm phong do đúng tổ chức
phát hành. Không có `--anchor-dir`, gói chưa có STH đã neo phủ niêm phong vẫn có thể `VALID` mã 3, kèm ghi chú
"chưa neo"; có `--anchor-dir` thì gói đó là `INVALID NOT_ANCHORED` (tải lại gói sau lần neo kế tiếp).

**"Trạng thái thu hồi chưa biết khi ngoại tuyến"** (`revocation: unknown_offline`): gói không ký trạng thái thu hồi;
trường `status` trong gói bị bỏ qua. Niêm phong có thể đã bị thu hồi sau khi tải gói, nên luôn tra trực tuyến
`GET https://<DXOS_DOMAIN>/verify/v1/seals/<id>` (hoặc trang đối soát) để biết `VALID`/`REVOKED`.

Mã lỗi thường gặp: `SIGNATURE` (payload bị sửa), `LEAF_LINK`/`INCLUSION` (lá ledger hoặc proof bị sửa),
`STH_SIGNATURE`, `CONSISTENCY`, `NOT_ANCHORED`, `KEY_NOT_ANCHORED`, `KEY_MISMATCH`, `KEY_STATEMENT`,
`KEY_STATEMENT_NOT_ANCHORED`, `KEY_NOT_VALID_AT_ISSUE` (niêm phong ngoài thời hạn của khóa), `FILE_NOT_IN_SEAL`.

## Witness tự động trong repo neo
Chép `.github/workflows/witness.yml` vào repo neo và đặt biến `DXOS_SERVER`. Workflow chạy 6 giờ một lần; thất bại thì
đỏ công khai. Vì nằm trong repo của đội, witness này **không** được tính là độc lập trước X4.
