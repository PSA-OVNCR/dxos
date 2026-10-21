# Runbook: triển khai VPS theo tag

Áp dụng spec S9.2 và R-3 (Plan 03 Task 12). Một lệnh đưa VPS lên đúng một bản đã phát hành:

```bash
cd /đường/dẫn/tới/dxos          # bản sao repo trên VPS, nhánh/tag bất kỳ, cây làm việc sạch
ops/deploy.sh v0.3.0            # hồ sơ mặc định p16
ops/deploy.sh v0.3.0 --profile p8
```

Chạy thật trên VPS là việc V29 (chưa chạy khi viết tài liệu này; script mới được kiểm bằng `git`, `docker`, `curl`
giả, xem `tests/ops/test_deploy_sh.py`).

## 1. Điều kiện

| Điều kiện | Chi tiết |
|---|---|
| Docker Compose ≥ **2.24** (V22) | Overlay `deploy/compose.release.yaml` dùng `!reset`; bản cũ hơn sẽ build từ mã nguồn thay vì dùng image đã phát hành. Kiểm: `docker compose version`. |
| NTP bật (V24) | Lệch giờ giữa API và worker làm niêm phong bị báo "khóa hết hạn". Kiểm: `timedatectl show -p NTPSynchronized`. |
| Package GHCR `trust-core` **công khai** (V19) | VPS kéo image theo digest mà không cần đăng nhập. Nếu để riêng tư thì `docker login ghcr.io` trên VPS trước. |
| `.env` đủ | Sao từ `.env.example`; bắt buộc có `DXOS_DOMAIN` (script thoát 2 nếu thiếu). `DXOS_ANCHOR_REMOTE` khác rỗng thì script tự thêm `deploy/compose.anchor.yaml` (cần `.secrets/anchor-deploy-key`, xem `docs/runbook-anchor.md`). |
| Image Node đã ghim digest | `make pin-images` rồi commit trước khi gắn tag. Chưa ghim thì `ops/web_build_docker.sh` thoát 3 và `deploy.sh` dừng, chưa gọi compose. |
| Release của tag đã có tệp `trust-core-image-<X.Y.Z>.txt` | Do workflow `release` sinh; script tải từ `https://github.com/PSA-OVNCR/dxos/releases/download/<tag>/`. Repo khác: `--repo-url`. |
| Cây làm việc sạch | `git status --porcelain` rỗng. `.env`, `deploy/release.env`, `deploy/deployments.log` đã nằm trong `.gitignore`. |

## 2. Script làm gì

Theo đúng thứ tự, dừng ở bước đầu tiên hỏng:

1. Kiểm tag `^v[0-9]+\.[0-9]+\.[0-9]+$`, profile `p16`/`p8`, `.env`. Sai: thoát 2, chưa làm gì.
2. Kiểm cây sạch. Không sạch: thoát 2.
3. Ghi nhớ bản đang chạy tốt (dòng `OK` cuối của `deploy/deployments.log`, hoặc `none`).
4. `git fetch origin refs/tags/<tag>:refs/tags/<tag>` **không** `--force`: nếu tag cục bộ khác tag trên remote, git từ chối
   và script thoát 1 (tag đã bị di chuyển; điều tra trước khi làm gì tiếp).
5. `git checkout --detach <tag>`.
6. Tải `trust-core-image-<X.Y.Z>.txt`, lấy digest. `release.yml` ghi hai dòng: `ghcr.io/psa-ovncr/trust-core:<X.Y.Z>`
   và `ghcr.io/psa-ovncr/trust-core@sha256:<64 hex>`; script lấy phần sau `@sha256:` (cũng nhận tệp chỉ có 64 hex).
   Digest phải khớp `^[0-9a-f]{64}$`, nếu không thoát 1 **trước** khi gọi compose. Ghi `deploy/release.env`.
7. `ops/web_build_docker.sh`: dựng SPA từ mã nguồn của tag vào volume `apps-static`.
8. Với cùng một bộ tệp: `docker compose -p dxos --env-file .env --env-file deploy/release.env -f deploy/compose.yaml
   -f deploy/compose.<profile>.yaml [-f deploy/compose.anchor.yaml] -f deploy/compose.release.yaml` rồi chạy lần lượt
   `pull --ignore-buildable` và `up -d --wait --wait-timeout 600` (spec 16.3: `compose pull && up -d`). Script bỏ
   `DXOS_TRUST_CORE_DIGEST` và `DXOS_RELEASE_TAG` khỏi môi trường của tiến trình ngay từ đầu: compose ưu tiên biến môi
   trường hơn `--env-file`, nên giá trị đã `export` trong shell sẽ lấn digest đã kiểm.
9. Kiểm sức khỏe: `/readyz` của `trust-core-api` (trong container) in `200`, và `https://$DXOS_DOMAIN/verify/v1/keys`
   trả 200 (`curl -k`: chấp nhận CA nội bộ của Caddy).
10. Ghi dòng kết quả vào `deploy/deployments.log`.

`deploy.sh` đọc `.env` bằng `sed`, không `source`, và không in giá trị bí mật. Lõi chạy đúng image theo digest của Release
(không build trên VPS); SPA được dựng từ mã nguồn của tag. Script của bản đang chạy là script thực hiện việc triển khai
(bash đã đọc xong tệp trước khi `git checkout` thay nó), nên muốn dùng script mới hơn hãy `git checkout` nó trước.

## 3. Đọc `deploy/deployments.log`

Mỗi lần chạy (từ bước 4 trở đi) thêm một dòng, các cột cách nhau bằng tab:

```
<UTC>	<tag>	<commit>	<digest>	OK|FAIL
2026-10-22T03:14:07Z	v0.3.0	0123…cdef	aaaa…aaaa	OK
```

- `commit` và `digest` là `-` nếu script hỏng trước khi biết được (ví dụ `git fetch` bị từ chối, hay tệp digest sai).
- Xem bản đang chạy tốt: `awk -F'\t' '$5=="OK"{t=$0} END{print t}' deploy/deployments.log`.
- Dòng `FAIL` không có nghĩa stack đã dừng: compose có thể đã chạy một phần. Xem `docker compose -p dxos ps` và log
  của dịch vụ không khỏe trước khi quyết định.

## 4. Quay lại bản trước

Không có tự quay lui (đó là S4, Plan 04). Khi hỏng, script in đúng:

```
Triển khai <tag> hỏng. Quay lại bằng: ops/deploy.sh <tag trước>
```

Chạy lệnh đó. Nó đi lại cả mười bước với tag cũ (digest lấy từ Release của tag cũ, SPA dựng lại từ mã nguồn tag cũ).
Nếu `<tag trước>` là `none` thì chưa có bản nào từng chạy tốt qua script này. Lưu ý: migration cơ sở dữ liệu của bản mới
không tự hoàn tác; chỉ quay lại bản có lược đồ tương thích (xem ghi chú nâng cấp trong CHANGELOG).

## 5. Timer systemd tùy chọn (không bật mặc định)

Không có timer nào được cài sẵn: triển khai là hành động có chủ đích của người vận hành. Nếu muốn một lịch kiểm sức khỏe
(không triển khai) tự chạy, ví dụ mỗi 15 phút, có thể tạo thủ công:

```ini
# /etc/systemd/system/dxos-health.service
[Service]
Type=oneshot
WorkingDirectory=/đường/dẫn/tới/dxos
ExecStart=/usr/bin/docker compose -p dxos exec -T trust-core-api python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status)"

# /etc/systemd/system/dxos-health.timer
[Timer]
OnCalendar=*:0/15
Persistent=true
[Install]
WantedBy=timers.target
```

`sudo systemctl enable --now dxos-health.timer` mới bật nó. Đừng đặt `ops/deploy.sh` vào timer: nó đổi mã đang chạy và
cần người đọc kết quả.
