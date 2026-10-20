# Repo neo `dxos-transparency-log` và witness

Repo này nhận các Signed Tree Head (STH) mà DX-OS ký bằng OpenBao: mỗi STH là một tệp `sth/<tree_size 12 chữ số>.json`.
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
| `BAD_SIGNATURE` | Chữ ký sai, hoặc khóa công khai của cùng phiên bản bị thay |
| `ANCHOR_MISMATCH` | STH máy chủ trả khác tệp trong repo neo |
| `REWRITE_DETECTED` | Cùng kích thước mà root khác, hoặc cây nhỏ đi |
| `INCONSISTENT` | Consistency proof từ lần trước tới nay không hợp lệ: lịch sử đã bị viết lại |

## Witness tự động trong repo neo
Chép `.github/workflows/witness.yml` vào repo neo và đặt biến `DXOS_SERVER`. Workflow chạy 6 giờ một lần; thất bại thì
đỏ công khai. Vì nằm trong repo của đội, witness này **không** được tính là độc lập trước X4.
