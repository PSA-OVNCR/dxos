# Runbook OpenBao (khóa ký STH và niêm phong)

Áp dụng cho stack `deploy/compose.yaml` (dịch vụ `openbao`, chỉ nằm trong mạng `net-data`).
Căn cứ: Design Spec mục 11.6 (quản lý khóa, mô hình admin bị xâm phạm) và 16.4 (dự phòng demo).

| Khóa | Dùng cho | Kiểu | Xuất được? |
|---|---|---|---|
| `sth-key` | Ký Signed Tree Head của ledger | ed25519, có phiên bản | Không (`exportable=false`) |
| `seal-key` | Ký niêm phong bản ghi (Plan 02) | ed25519, có phiên bản | Không |

Token của trust-core mang policy `dxos-core` (`deploy/openbao/dxos-core-policy.hcl`): chỉ **ký** bằng 2 khóa trên,
**đọc khóa công khai**, tự gia hạn và tự xem thông tin token. Không xuất, không xoay, không xóa khóa, không đọc cấu hình.

## 1. Khởi tạo lần đầu (một lần cho mỗi volume `openbao-data`)
```bash
docker compose -p dxos exec openbao bao operator init -key-shares=1 -key-threshold=1 -format=json > openbao-init.json
```
- **Cấu hình demo: Shamir 1 phần**, trưởng nhóm giữ. Cấu hình đề xuất cho thực tế là **3-of-5** (spec 11.6).
- `openbao-init.json` chứa unseal key và root token: **không** để trên VPS và **không** commit. Chép ra USB hoặc
  trình quản lý mật khẩu của trưởng nhóm, rồi xóa khỏi máy chủ.

## 2. Mở khóa (sau mỗi lần OpenBao khởi động lại)
```bash
docker compose -p dxos exec openbao bao operator unseal <unseal-key>
docker compose -p dxos exec openbao bao status          # Sealed: false
```
Khi OpenBao còn khóa, lõi **từ chối** lập STH và niêm phong (fail-closed, F8): `/verify/v1/keys` trả 503
`kms-unavailable`, việc neo STH được thử lại sau.

## 3. Bật transit, tạo khóa, cấp token cho trust-core (một lần)
```bash
docker compose -p dxos exec -e BAO_TOKEN=<root-token> openbao sh /openbao/dxos/init.sh
```
Dòng cuối là **token của trust-core**. `init.sh` thu hồi root token khi xong (tạo lại bằng `bao operator generate-root`
nếu cần quản trị). Ghi token vào `.env`:
```
OPENBAO_CORE_TOKEN=<token vừa in ra>
```
rồi tạo lại container lõi để nạp Docker secret mới:
```bash
docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.p16.yaml up -d --force-recreate trust-core-api trust-core-worker
```
Kiểm: `curl -k https://<DXOS_DOMAIN>/verify/v1/keys` trả `{"seal-key": {"1": "..."}, "sth-key": {"1": "..."}}`.

Token là token *period* 768 giờ: lõi gia hạn được (`auth/token/renew-self`). Nếu để quá hạn, chạy lại bước 3 với root
token tạo lại.

## 4. Xoay khóa
```bash
docker compose -p dxos exec -e BAO_TOKEN=<root-token> openbao bao write -f transit/keys/sth-key/rotate
```
STH mới ký bằng phiên bản mới nhất; STH cũ vẫn kiểm được bằng phiên bản cũ (`/verify/v1/keys` trả mọi phiên bản).
Sau khi xoay, công bố khóa công khai mới vào repo neo (Task 16) để witness cập nhật.

## 5. Checklist 60 phút trước demo (spec 16.4)
- [ ] `bao status`: `Sealed: false`.
- [ ] `/readyz` của trust-core-api trả 200; `docker compose ps` tất cả `healthy`.
- [ ] `/verify/v1/keys` trả đủ 2 khóa.
- [ ] Đã chạy `POST /admin/v1/anchor:run`; STH mới nhất đã có trên repo neo; witness `OK`.
- [ ] Mạng ra Internet của `trust-core-worker` hoạt động (để đẩy STH lên GitHub).

## 6. Khi nghi bị xâm phạm (spec 11.6)
| Mức | Việc cần làm ngay |
|---|---|
| X1. Lộ quyền SQL | Chạy `verify_log` / witness: sửa dữ liệu làm lệch root so với STH đã ký. Khôi phục DB từ backup. |
| X2. Lộ tài khoản admin DX-OS | Thu hồi tài khoản trong Keycloak; rà ledger `app.installed`, `policy.denied`. |
| X3. Lộ root VPS (có mọi khóa) | `bao operator seal` ngay; xoay `sth-key`, `seal-key`; công bố thời điểm xâm phạm. Lịch sử **đã neo** vẫn được bảo vệ nhờ consistency proof với repo neo và witness. |
| X4. Lộ cả root VPS và admin repo neo | Chỉ còn witness độc lập giữ STH cũ; liên hệ người chạy witness để đối chiếu. |
