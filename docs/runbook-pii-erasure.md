# Runbook: xóa dữ liệu cá nhân theo yêu cầu

Áp dụng spec 25.2 (bản 1.0.3) và Luật Bảo vệ dữ liệu cá nhân 2025 (91/2025/QH15). Phần pháp lý là diễn giải kỹ thuật
của đội, không phải tư vấn pháp lý; căn cứ và giới hạn ở [`docs/legal-mapping.md`](legal-mapping.md).

Phần mềm làm được một việc: `POST …/records/{id}:erase-pii` bỏ các trường có khai `pii` khỏi bản ghi, kể cả bản ghi
đã niêm phong, trong một transaction có bằng chứng chỉ thêm. Xóa an toàn trên đĩa (Điều 14 khoản 3) và thông báo khi
không xóa được (Điều 14 khoản 5) là **việc vận hành**, ghi ở runbook này (spec 25.2).

## 1. Tiếp nhận yêu cầu

1. Ghi nhận yêu cầu: ai yêu cầu, ngày nhận, bản ghi nào (app, collection, id), trường nào. Không chép giá trị của trường
   vào phiếu, email hay issue.
2. Xác định bản ghi có trường nào khai `pii` trong manifest (App A: `nguoi_lien_he_cccd`; App B: `email`). Trường
   không khai `pii` (kể cả trường `public` đã niêm phong) không xóa được bằng API: xem mục 4.
3. Chọn `reason_code` theo bảng dưới.
4. Người thực hiện phải giữ role thuộc `policies.pii.erase_roles` của bản manifest ACTIVE (App A: `van_thu`; App B:
   `truong_clb`). Admin DX-OS (`dxos-admin`) **không** đọc được dữ liệu app nên không làm thay được.

### Mã lý do (`reason_code`)

Năm mã là các trường hợp xóa của Điều 14 khoản 1 Luật 91/2025 (spec 25.2). Spec chưa ghi mã nào ứng với điểm nào của
khoản 1, nên cột "Điểm" để trống cho tới khi thành viên đọc toàn văn Điều 14 và điền; không đoán.

| `reason_code` | Dùng khi | Điểm của Điều 14 khoản 1 |
|---|---|---|
| `data_subject_request` | chủ thể dữ liệu (người có CCCD, email trong bản ghi) yêu cầu xóa | chưa đối chiếu |
| `purpose_completed` | mục đích xử lý dữ liệu đã hoàn thành, không cần giữ trường đó nữa | chưa đối chiếu |
| `retention_expired` | hết thời hạn lưu trữ mà tổ chức đã đặt cho loại dữ liệu này | chưa đối chiếu |
| `authority_decision` | có quyết định của cơ quan có thẩm quyền yêu cầu xóa | chưa đối chiếu |
| `agreement` | xóa theo thỏa thuận giữa tổ chức và chủ thể dữ liệu | chưa đối chiếu |

Mã khác bị từ chối (422). Danh sách này trùng ràng buộc `CHECK` của bảng `core.pii_erasures`
(`core/migrations/003_workflow_seal.sql`); test `tests/repo/test_docs_m2.py` giữ hai nơi khớp nhau.

## 2. Thực hiện xóa

CLI quản trị `dxos` **không** có lệnh xóa PII: đó là công cụ của admin, mà admin không có quyền đọc dữ liệu app. Người
giữ role xóa gọi API bằng token của chính mình (giao diện SPA làm việc này ở Plan 03).

Trước khi có SPA, cách lấy token trên máy của người thực hiện (client `dxos-cli`, device flow; token lưu ở
`~/.config/dxos/token.json`, quyền 0600):

```bash
dxos login --server https://admin.<miền>
TOKEN=$(python3 -c 'import json, os; print(json.load(open(os.path.expanduser("~/.config/dxos/token.json")))["access_token"])')
```

Đọc version hiện tại của bản ghi, rồi xóa với `If-Match` đúng version đó:

```bash
BASE=https://<miền>/api/v1/apps/phong-ho-so/collections/van_ban/records
curl -sS "$BASE/<id>" -H "Authorization: Bearer $TOKEN" | python3 -c 'import json, sys; print(json.load(sys.stdin)["version"])'
curl -sS -X POST "$BASE/<id>:erase-pii" -H "Authorization: Bearer $TOKEN" -H 'If-Match: "<version>"' \
  -H 'Content-Type: application/json' \
  -d '{"fields": ["nguoi_lien_he_cccd"], "reason_code": "data_subject_request"}'
```

Các lệnh trên chưa được chạy thử trên VPS (chưa có stack VPS chạy bản M2 khi viết runbook); API đã có test integration
(Plan 02 Task 7).

Kết quả và xử lý:

| Phản hồi | Ý nghĩa | Làm gì |
|---|---|---|
| 200 | trường đã bị bỏ khỏi `data`; salt của bản ghi, ghi chú thu hồi (nếu có) đã bị xóa; tên tệp gốc đã bị thay | chạy mục 3 trong ngày |
| 404 | không đọc được bản ghi, không giữ role xóa, hoặc app không có bản ACTIVE (`app-not-active`) | app `DISABLED`: admin nộp phiên bản mới hơn rồi duyệt bốn mắt, xóa xong có thể vô hiệu hóa lại |
| 409 `record-in-workflow` | bản ghi đang trong quy trình | chờ quy trình xong rồi làm lại |
| 409 `seal-pending` | đang chờ niêm phong | chờ `SEALED` rồi làm lại |
| 409 `version-conflict`, 428 | thiếu hoặc sai `If-Match` | đọc lại version rồi gửi lại |
| 422 | trường không khai `pii`, hoặc `reason_code` sai | sửa yêu cầu; trường không xóa được thì theo mục 4 |

Sau khi xóa: niêm phong vẫn `VALID`, gói bằng chứng vẫn kiểm được (chữ ký phủ `record_digest` có salt, không phủ
`data`). Ledger ghi `pii.erased {collection, fields, reason_code, version}`: tên trường, không có giá trị.

## 3. Xóa trên đĩa: `VACUUM`

PostgreSQL giữ bản cũ của hàng (trước khi xóa) trên đĩa cho tới khi `VACUUM` dọn. Chạy bằng role `dxos_owner` (chủ
của schema `core`; role `dxos_core` của ứng dụng không có quyền này).

Ngay sau mỗi lần xóa, và theo lịch hằng đêm:

```bash
docker exec dxos-core-db-1 psql -U dxos_owner -d dxos -c 'VACUUM (ANALYZE) core.records, core.record_salts, core.uploads;'
```

Lịch hằng đêm trên VPS (`crontab -e` của người dùng chạy Docker), 03:17 giờ máy chủ:

```
17 3 * * * docker exec dxos-core-db-1 psql -U dxos_owner -d dxos -c 'VACUUM (ANALYZE) core.records, core.record_salts, core.uploads;' >> /var/log/dxos-vacuum.log 2>&1
```

Giới hạn cần biết:
- `VACUUM` thường đánh dấu chỗ trống để dùng lại; byte cũ có thể còn trong trang dữ liệu tới khi bị ghi đè. Muốn
  ghi lại toàn bộ bảng thì dùng `VACUUM FULL` trong giờ bảo trì (khóa bảng trong lúc chạy). [ĐX]
- Ghi chú thu hồi bị xóa nằm ở bảng `core.seal_revocation_notes`; thêm bảng này vào lệnh `VACUUM` khi bản ghi từng bị
  thu hồi có ghi chú. [ĐX]
- WAL của PostgreSQL cũng chứa dữ liệu cũ tới khi được tái sử dụng.

## 4. Trường hợp không xóa và thông báo cho chủ thể

Không xóa bằng `:erase-pii` được (spec 25.2, phần "Không thuộc" của I5):

- **Trường `public` đã niêm phong** (ví dụ họ tên trên chứng nhận App B): đã chép vào `seal_requests` và
  `seals.payload` đã ký, là công bố có chủ đích. Chỉ **thu hồi** được niêm phong (`:revoke`), không xóa được nội dung.
- **Tệp PDF đã ban hành**: là bản gốc văn bản, lưu theo nội dung và có thể dùng chung nhiều bản ghi.
- `sub` của nhân viên trong các bảng quy trình: định danh giả danh do Keycloak cấp; ledger chỉ giữ HMAC.

Khi không xóa được, tổ chức **tự** thông báo cho chủ thể dữ liệu, nêu căn cứ Điều 14 khoản 2 và Điều 19 Luật Bảo vệ
dữ liệu cá nhân 2025 (spec 25.2). Mẫu (đối chiếu toàn văn hai điều này trước khi gửi):

> Kính gửi Ông/Bà ……,
>
> Ngày …/…/……, [tên tổ chức] nhận được yêu cầu xóa dữ liệu cá nhân của Ông/Bà trong [tên văn bản / chứng nhận, số
> hiệu]. [Tên tổ chức] đã xóa: [các trường đã xóa, nếu có]. [Tên tổ chức] không xóa được: [trường / tệp], vì
> [đây là nội dung đã công bố trong văn bản được niêm phong / đây là bản gốc của văn bản đã ban hành], căn cứ
> Điều 14 khoản 2 và Điều 19 Luật Bảo vệ dữ liệu cá nhân 2025. [Biện pháp thay thế đã làm, ví dụ: thu hồi niêm
> phong ngày …/…/……]. Mọi thắc mắc xin liên hệ [đầu mối, email].
>
> [Nơi gửi], ngày …/…/……  [Người đại diện, chức vụ]

## 5. Backup

Hiện stack **chưa có backup tự động**: spec 16.3 xếp `pg_dump` hằng đêm và snapshot volume là SHOULD (hạng mục S4).
Khi bật backup, dữ liệu đã xóa còn trong các bản backup cũ tới khi bản đó hết hạn và bị hủy. Vì vậy:

- Thời hạn giữ backup: trưởng nhóm chốt khi bật backup; [ĐX] tối đa 30 ngày. Đã chốt: ……… ngày (người chốt, ngày).
- Khi khôi phục từ backup cũ hơn một lần xóa, chạy lại các lần xóa có ngày sau thời điểm của bản backup trước khi mở
  hệ thống cho người dùng. Lấy danh sách từ sổ tiếp nhận (mục 1), **không** từ `core.pii_erasures`: bảng đó nằm trong
  chính DB vừa khôi phục nên đã mất các lần xóa sau backup.
- Thông báo cho chủ thể (mục 4) nêu thời hạn giữ backup đã chốt.
