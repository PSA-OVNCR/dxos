# Runbook neo STH lên GitHub (Plan 01 Task 16, bước thiết lập thủ công)

Các bước dưới đây cần **chủ tổ chức GitHub** làm trên trình duyệt (cần 2FA, "sudo mode"). Phiên Claude có thể thao tác thay
trên trình duyệt đã đăng nhập sẵn, nhưng không nhập mật khẩu hay mã 2FA.

## 1. Tạo repo neo
1. Tạo repo **công khai** `dxos-transparency-log`. Chủ sở hữu: trưởng nhóm và giảng viên hướng dẫn, cả hai bật 2FA
   (spec 11.7). Quyền admin repo **không** đặt trên VPS.
2. Chép nội dung `witness/template/` của repo `dxos` vào repo neo (README và `.github/workflows/witness.yml`).
   Bản đã tạo: https://github.com/PSA-OVNCR/dxos-transparency-log (workflow chỉ chạy khi có biến `DXOS_SERVER`).
3. Settings → Rules → Rulesets → New branch ruleset cho `main`: bật *Restrict deletions*, *Block force pushes*,
   *Require linear history*. Không thêm ai vào danh sách bypass.

**Trạng thái 21/10/2026: bước 1–3 đã xong.**
- Repo https://github.com/PSA-OVNCR/dxos-transparency-log (Public, trong tổ chức `PSA-OVNCR`), commit đầu `dd66478`.
- Ruleset `protect-main` (id 25495143): Active, áp cho nhánh mặc định `main`, bật *Restrict deletions*, *Require linear
  history*, *Block force pushes*; danh sách bypass trống (kiểm qua API `repos/PSA-OVNCR/dxos-transparency-log/rulesets/25495143`).
- Lệch so với spec 11.7: repo nằm trong tổ chức của đội (3 owner là thành viên đội) chứ chưa phải trưởng nhóm + giảng viên.
  Rủi ro X4 được bù bằng witness độc lập (mục 5). Nên mời giảng viên làm admin repo khi có thể.
- Còn lại: bước 2 (deploy key, cần VPS), bước 4 (AT-18), mục 5 (witness).

## 2. Deploy key cho VPS
```bash
ssh-keygen -t ed25519 -N "" -C dxos-anchor -f .secrets/anchor-deploy-key   # .secrets/ đã có trong .gitignore
```
Repo neo → Settings → Deploy keys → Add: dán `.secrets/anchor-deploy-key.pub`, **tích "Allow write access"**.
Khóa riêng chỉ nằm trên VPS (Docker secret).

**Quyền đọc khóa trong container.** Compose (không Swarm) gắn secret dạng `file:` bằng bind mount, giữ nguyên chủ sở hữu
và quyền của tệp trên máy chủ. Worker chạy bằng uid 10001, còn `ssh` từ chối khóa riêng mà người khác đọc được, nên trên VPS Linux:
```bash
sudo chown 10001:10001 .secrets/anchor-deploy-key
sudo chmod 0400 .secrets/anchor-deploy-key
```
Nếu bỏ bước này, việc neo báo `PUSH_FAILED` (Permission denied hoặc "UNPROTECTED PRIVATE KEY FILE") và thử lại mãi.
Trên Docker Desktop (Windows/macOS) quyền của bind mount được giả lập, chỉ dùng để thử; neo thật chạy trên VPS.

## 3. Bật neo trong stack
Thêm vào `.env`:
```
DXOS_ANCHOR_REMOTE=git@github.com:<chủ-repo>/dxos-transparency-log.git
```
và chạy kèm overlay `deploy/compose.anchor.yaml`:
```bash
docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.p16.yaml -f deploy/compose.anchor.yaml up -d
```
Kiểm: `POST /admin/v1/anchor:run` (token `dxos-admin`) rồi xem `GET /admin/v1/ledger/status` → `last_anchor.commit_sha`
trùng commit mới nhất trên repo neo.

## 4. AT-18: deploy key không force-push được
Trên VPS, trong một bản clone dùng deploy key:
```bash
git commit --amend -m "thử viết lại" && git push --force origin main
```
Kết quả mong đợi: GitHub từ chối (`protected branch` / `Cannot force-push`). Chụp màn hình lưu vào
`docs/evidence/at18-force-push-rejected.png`, kèm lệnh đã chạy.

## 5. Witness độc lập (trước 16/11)
Nhờ một người ngoài đội (ví dụ thành viên CLB) làm witness. Cách dễ nhất: repo mẫu
[`PSA-OVNCR/dxos-witness-kit`](https://github.com/PSA-OVNCR/dxos-witness-kit) (GitHub Actions, không cần máy riêng).
- Người đó bấm **Use this template** để tạo repo **trong tài khoản của chính họ**, đặt biến `DXOS_SERVER`, rồi chạy workflow lần đầu.
- Nếu chỉ thêm họ làm cộng tác viên vào repo trong tổ chức `PSA-OVNCR` thì workflow vẫn chạy, nhưng owner tổ chức (đội)
  sửa được `state/`, nên witness đó **không** được tính là độc lập trước X4 (spec 11.4, 11.7).
- Hoặc chạy `dxos-witness` theo lịch trên máy riêng, theo `witness/template/README.md`.
- Workflow cần tag `v0.1.0` (hoặc đặt biến `DXOS_REF`) và DX-OS đã chạy công khai trên VPS.

Ghi tên người chạy, link repo witness và ngày bắt đầu vào `docs/evidence/README.md`.

## 6. OpenTimestamps (Đ2, mặc định tắt)
Neo thêm STH đã neo vào Bitcoin qua calendar OpenTimestamps (Plan 03 Task 14, P3-D10). Tính năng **cắt được**:
không bật thì lõi không gửi request nào và mọi thứ ở trên vẫn như cũ. Lõi chỉ gửi digest STH và lưu biên nhận; nâng
cấp lên Bitcoin và kiểm chứng do **người kiểm** tự làm bằng công cụ chính thức `ots` (opentimestamps-client, không
nằm trong DX-OS).

**Bật.** Neo STH phải đang chạy (mục 3). Thêm vào `.env` rồi khởi động lại `trust-core-worker` (worker đã ở `net-egress`):
```
DXOS_OTS_CALENDARS=https://a.pool.opentimestamps.org,https://b.pool.opentimestamps.org
```
Chỉ nhận URL `https://`, không trùng nhau; sai thì worker không khởi động. Tắt: để trống (việc đã xếp sẽ xong mà không
gửi request).

**Lõi làm gì.**
- Mỗi lần neo **mới** thành công, worker xếp việc `ots_stamp`. Việc này `POST <calendar>/digest` với thân là
  32 byte `SHA-256(canonical(STH))`, cũng là SHA-256 của tệp `sth/<n>.json` trong repo neo. Timeout 10 giây.
- Phản hồi được kiểm định dạng, lưu nguyên văn vào bảng chỉ-thêm `ots_receipts`, rồi commit
  `ots/<n 12 chữ số>.ots` vào repo neo. Tệp này dựng lại tất định từ bảng, ghi một lần, không ghi đè.
- Mỗi lời gọi calendar có hạn **tổng** 10 giây và phản hồi tối đa 10000 byte, đọc dòng và cắt ngay khi quá. Phản hồi
  phải đọc được bằng trình đọc chính thức: thông điệp qua mỗi op ≤ 4096 byte, URI pending ≤ 1000 ký tự
  `[A-Za-z0-9._/:-]`, không thừa byte. Tối đa 8 calendar.
- Tệp `ots/<n>.ots` đã commit ở clone của worker nhưng chưa đẩy được: lượt sau không hỏi calendar nữa, chỉ đẩy lại.
- Calendar lỗi: ghi log, thử lại sau 10 phút, tối đa 6 lượt. Sau lượt cuối, có biên nhận nào thì commit với biên
  nhận đó. Không có biên nhận nào thì việc `FAILED`. Việc neo STH **không bao giờ** bị chặn hay hỏng vì calendar.
- Gói bằng chứng có thêm `"timestamps": [{"type": "opentimestamps", "tree_size": n, "ots": "<base64>"}]` cho STH
  đã neo, khi đã có biên nhận. `dxos-witness verify-bundle` và cổng đối soát trên trình duyệt **không** đổi
  kết quả hay mã thoát vì khóa này. Witness chỉ ghi chú "OTS: … đang chờ xác nhận trên Bitcoin — kiểm bằng
  `ots upgrade` rồi `ots verify`". Phần đầu tệp `.ots` không khớp `anchored.sth` thì witness ghi chú "bỏ qua".
- `timestamps` trong gói được dựng lại từ bảng `ots_receipts` mỗi lần tải gói, bỏ qua hàng không còn đọc được. Khi
  việc `ots_stamp` còn đang thử lại calendar thiếu, gói có thể có **ít nhánh hơn** tệp `ots/<n>.ots` sẽ commit sau.
  Cả hai đều hợp lệ (mỗi nhánh tự kiểm được). Bản chuẩn để kiểm là tệp trong repo neo.

**Người kiểm làm gì** (trên máy có Internet, trong bản clone repo neo):
```bash
python -m venv ~/ots && ~/ots/bin/pip install opentimestamps-client     # công cụ của người kiểm
cp ots/000000000042.ots /tmp/42.ots                                      # upgrade sửa tệp: làm trên bản sao
~/ots/bin/ots info /tmp/42.ots                                            # xem digest và calendar (ngoại tuyến)
~/ots/bin/ots upgrade /tmp/42.ots                                         # lấy đường dẫn tới khối Bitcoin
~/ots/bin/ots verify -f sth/000000000042.json /tmp/42.ots                 # kiểm với khối Bitcoin
```
`ots verify` cần một nút Bitcoin để đối chiếu header khối. Cách cấu hình tùy phiên bản client, xem
`ots verify --help`.

**Giới hạn.**
- Biên nhận lúc đầu chỉ là "pending" (lời hứa của calendar). Calendar gom digest và đưa vào khối Bitcoin sau vài giờ;
  trước đó `ots upgrade` báo chưa xong.
- Tệp trong repo neo giữ nguyên dạng pending. Bản đã nâng cấp nằm ở máy người kiểm.
- Calendar là bên thứ ba. Mất calendar trước khi nâng cấp thì mất biên nhận đó, nên dùng ít nhất hai calendar.

**Việc V32 (trên VPS; cloud không ra được Internet nên chưa gọi calendar thật lần nào).**
1. Bật như trên, `docker compose ... up -d trust-core-worker`.
2. `POST /admin/v1/anchor:run`, đợi việc neo xong. Kiểm `SELECT tree_size, calendar, octet_length(reply) FROM
   ots_receipts` có hai hàng, và repo neo có commit `ots <n>` chứa `ots/<n>.ots`.
3. `ots info` trên tệp đó phải hiện digest bằng `sha256sum sth/<n>.json` và hai calendar. Vài giờ sau chạy
   `ots upgrade` rồi `ots verify -f sth/<n>.json`. Chụp kết quả lưu vào `docs/evidence/`.
4. (Tùy chọn) Test đối chiếu với client chính thức. Test này dùng calendar giả trên `127.0.0.1`, không cần Internet:
   ```bash
   . .venv/bin/activate && pip install opentimestamps-client     # chỉ trong venv thử, không vào phụ thuộc của lõi
   DXOS_OTS_CLIENT=ots python -m pytest core/tests/test_ots.py -k official -v
   ```
   Test so phần đầu tệp (magic, phiên bản, op sha256, digest) với tệp do `ots stamp` sinh. Sau đó cho `ots info`
   đọc tệp `.ots` do lõi dựng.
