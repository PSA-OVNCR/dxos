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
