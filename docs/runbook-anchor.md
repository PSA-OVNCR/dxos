# Runbook neo STH lên GitHub (Plan 01 Task 16, bước thiết lập thủ công)

Các bước dưới đây cần **chủ tổ chức GitHub** làm trên trình duyệt (cần 2FA, "sudo mode"); phiên Claude không làm thay.

## 1. Tạo repo neo
1. Tạo repo **công khai** `dxos-transparency-log`. Chủ sở hữu: trưởng nhóm và giảng viên hướng dẫn, cả hai bật 2FA
   (spec 11.7). Quyền admin repo **không** đặt trên VPS.
2. Chép nội dung `witness/template/` của repo `dxos` vào repo neo (README và `.github/workflows/witness.yml`).
3. Settings → Rules → Rulesets → New branch ruleset cho `main`: bật *Restrict deletions*, *Block force pushes*,
   *Require linear history*. Không thêm ai vào danh sách bypass.

## 2. Deploy key cho VPS
```bash
ssh-keygen -t ed25519 -N "" -C dxos-anchor -f .secrets/anchor-deploy-key   # .secrets/ đã có trong .gitignore
```
Repo neo → Settings → Deploy keys → Add: dán `.secrets/anchor-deploy-key.pub`, **tích "Allow write access"**.
Khóa riêng chỉ nằm trên VPS (Docker secret).

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
Nhờ một người ngoài đội (ví dụ thành viên CLB) chạy `dxos-witness` theo lịch trên máy riêng, theo
`witness/template/README.md`. Ghi tên người chạy và ngày bắt đầu vào `docs/evidence/README.md`.
