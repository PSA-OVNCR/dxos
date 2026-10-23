# Runbook: triển khai VPS theo tag

Áp dụng spec S9.2 và R-3 (Plan 03 Task 12) và S4 (Plan 04 Task 11: chỉ nhận tag đã ký, tự quay lui khi health hỏng).
Một lệnh đưa VPS lên đúng một bản đã phát hành:

```bash
cd /đường/dẫn/tới/dxos          # bản sao repo trên VPS, nhánh/tag bất kỳ, cây làm việc sạch
ops/deploy.sh v0.3.0            # hồ sơ mặc định p16
ops/deploy.sh v0.3.0 --profile p8
ops/deploy.sh v0.3.0 --allow-unsigned   # chỉ cấp cứu, xem mục 2.3
```

Chạy thật trên VPS là việc V29 (chưa chạy khi viết tài liệu này; script mới được kiểm bằng `git`, `docker`, `curl`
giả, xem `tests/ops/test_deploy_sh.py`).

## 1. Điều kiện

| Điều kiện | Chi tiết |
|---|---|
| Docker Compose ≥ **2.24** (V22) | Overlay `deploy/compose.release.yaml` dùng `!reset`; bản cũ hơn sẽ build từ mã nguồn thay vì dùng image đã phát hành. Kiểm: `docker compose version`. |
| NTP bật (V24) | Lệch giờ giữa API và worker làm niêm phong bị báo "khóa hết hạn". Kiểm: `timedatectl show -p NTPSynchronized`. |
| Package GHCR `trust-core` và `viewer` **công khai** (V19) | VPS kéo image theo digest mà không cần đăng nhập. Nếu để riêng tư thì `docker login ghcr.io` trên VPS trước. |
| `.env` đủ | Sao từ `.env.example`; bắt buộc có `DXOS_DOMAIN` (script thoát 2 nếu thiếu). `DXOS_ANCHOR_REMOTE` khác rỗng thì script tự thêm `deploy/compose.anchor.yaml` (cần `.secrets/anchor-deploy-key`, xem `docs/runbook-anchor.md`). |
| Image Node đã ghim digest | `make pin-images` rồi commit trước khi gắn tag. Chưa ghim thì `ops/web_build_docker.sh` thoát 3 và `deploy.sh` dừng, chưa gọi compose. |
| Release của tag đã có tệp `trust-core-image-<X.Y.Z>.txt` (và `viewer-image-<X.Y.Z>.txt` từ v0.9.0) | Do workflow `release` sinh; script tải từ `https://github.com/PSA-OVNCR/dxos/releases/download/<tag>/`. Repo khác: `--repo-url`. Tệp Viewer chỉ cần khi hồ sơ là p16 và `.env` có `COMPOSE_PROFILES=viewer`. |
| Cổng đối soát đọc repo neo (tùy chọn, V34) | Đặt trong `.env` cả `VITE_ANCHOR_RAW_BASE=https://raw.githubusercontent.com/<org>/dxos-transparency-log/main` (đọc lúc dựng SPA) và `DXOS_ANCHOR_RAW_ORIGIN=https://raw.githubusercontent.com` (CSP của Caddy); hai giá trị phải khớp origin. Thiếu một trong hai thì cổng báo "chưa đối chiếu repo neo" hoặc CSP chặn. |
| Khóa ký tag trong `deploy/allowed_signers` (V42) | Chưa có khóa thì mọi tag bị từ chối (thoát 2); xem mục 2.2. |
| Cây làm việc sạch | `git status --porcelain` rỗng. `.env`, `deploy/release.env`, `deploy/deployments.log` đã nằm trong `.gitignore`. |

## 2. Ký tag và script làm gì

### 2.1. Mã thoát

| Mã | Nghĩa | Làm gì tiếp |
|---|---|---|
| 0 | Đạt: bản mới chạy khỏe. | Không. |
| 2 | **Từ chối trước khi đổi gì**: tham số sai, thiếu `.env`/`DXOS_DOMAIN`, thiếu `git`/`docker`/`curl`, cây làm việc bẩn, tag chưa ký hoặc ký bằng khóa không có trong `deploy/allowed_signers`. Không ghi vào `deployments.log`. | Sửa theo thông báo trên stderr (ký tag đúng khóa, mục 2.2) rồi chạy lại. |
| 3 | **Thiếu điều kiện trước khi chuyển bản**: `git fetch` bị từ chối (tag cục bộ khác remote), Release thiếu tệp hoặc digest sai, `docker compose pull` hỏng, dựng SPA hỏng (kể cả image Node chưa ghim). Ghi `result=failed`, in "Quay lại bằng: ops/deploy.sh <tag trước>". Container đang chạy chưa bị đổi; cây làm việc đã `HEAD` tách rời tại tag mới, và nếu lỗi đến từ bước dựng SPA thì volume `apps-static` có thể đã bị ghi dở. | Sửa điều kiện rồi chạy lại cùng tag; hoặc chạy lệnh quay lại đã in. |
| 4 | **Health hỏng sau khi chuyển, đã tự quay lui về bản tốt gần nhất và bản đó khỏe.** Log có `result=ok` cho bản tốt và `result=rolled-back` cho bản hỏng. | Điều tra bản hỏng (`docker compose -p dxos logs`), phát hành tag sửa. Máy đang ở bản cũ. |
| 5 | **Health hỏng và không quay lui được**: chưa có bản tốt nào trong log, quay lui cũng hỏng (kể cả tag cũ không qua được kiểm chữ ký), hoặc **bản mới thêm migration** nên cố ý không quay lui (mục 4). Script in hướng dẫn. | Làm theo hướng dẫn in ra và mục 4. Stack đang ở trạng thái không khỏe. |

Health hỏng gồm: `docker compose up -d --wait` báo container không khỏe, `/readyz` không trả 200, hoặc
`https://$DXOS_DOMAIN/verify/v1/keys` không trả 200.

### 2.2. Ký tag bằng SSH và thêm khóa vào `deploy/allowed_signers`

Làm một lần trên máy của người phát hành (việc V42, chưa làm khi viết mục này):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/dxos-release -C "truong-nhom"     # đặt passphrase
git config gpg.format ssh
git config user.signingkey ~/.ssh/dxos-release.pub
```

Thêm **khóa công khai** (tệp `.pub`, không bao giờ khóa riêng) vào `deploy/allowed_signers`, một dòng một khóa, rồi commit
và đẩy lên trước khi gắn tag:

```bash
echo "truong-nhom@example.vn namespaces=\"git\" $(cut -d' ' -f1,2 ~/.ssh/dxos-release.pub)" >> deploy/allowed_signers
git add deploy/allowed_signers && git commit -m "chore(ops): allow release signing key" && git push origin main
```

Ký và đẩy tag (tag ký là tag có chú thích, `-s` thay cho `-a`; tag nhẹ không có chữ ký nên bị từ chối):

```bash
git tag -s v0.4.0 -m "v0.4.0"
git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/v0.4.0
git push origin v0.4.0
```

Lệnh kiểm phải in dòng dạng `Good "git" signature for <principal> with ED25519 key SHA256:...`. **Phải có `for <principal>`**
(tên khớp một dòng trong `allowed_signers`); chỉ thấy `Good "git" signature with ...` mà không có `for ...` hoặc có
`No principal matched` thì chữ ký đúng về mặt toán học nhưng khóa chưa được phép: chưa coi là đạt.

Lưu ý:
- `deploy.sh` đọc `deploy/allowed_signers` từ bản **đang checkout** trên VPS (không từ tag sắp triển khai: neo tin cậy
  không nằm trong thứ cần kiểm). Sau mỗi lần triển khai VPS ở trạng thái `HEAD` tách rời tại tag, nên `git pull` sẽ lỗi.
  Để nhận khóa mới hay thu hồi khóa: `git checkout main && git pull` trên VPS **trước** khi triển khai tag đầu tiên ký bằng
  khóa mới (tag mới không tự đưa khóa của nó vào: khóa phải có sẵn trên VPS trước khi kiểm tag đó).
- Khi tự quay lui, cây làm việc đã ở tag vừa triển khai (tag này vừa qua kiểm chữ ký), nên bản cũ được kiểm bằng
  `allowed_signers` của tag đó. Hệ quả khi xoay khóa: nếu tag mới đã bỏ khóa cũ khỏi tệp thì quay lui về bản được ký bằng
  khóa cũ sẽ thoát 5. Muốn quay lui được thì giữ khóa cũ trong tệp cho tới khi không còn cần quay về các bản đó.
- Tệp không có dòng khóa nào (thiếu, rỗng, hoặc chỉ chú thích như hiện nay): `deploy.sh` thoát 2 ngay, trước cả `git fetch`,
  với thông báo trỏ tới V42. Hệ thống đóng mặc định. Thu hồi khóa = xóa dòng đó rồi commit.
- `verify-tag` **không** kiểm tên tag: một tag ký của bản cũ (`v1.0.0`) đẩy lên dưới tên mới (`refs/tags/v1.1.0`) vẫn có chữ
  ký hợp lệ. Vì vậy sau `verify-tag`, script đọc dòng `tag` trong thân tag đã ký (`git cat-file tag refs/tags/<tag>`) và thoát 2
  nếu khác `<tag>`; rồi giải `refs/tags/<tag>^{commit}` ra OID đúng một lần và `checkout --detach <OID>`. Tag nhẹ (không có
  thân tag) cũng bị từ chối.
- Tag bị từ chối (thoát 2): script xóa ref `refs/tags/<tag>` do chính lần fetch đó tạo ra (ref đã có từ trước thì giữ), để lần
  sau phát hành lại tag đã ký đúng không vướng. Nếu `git fetch` vẫn báo tag cục bộ khác remote (thoát 3) và bạn đã kiểm
  rằng tag trên remote được ký lại có chủ đích: `git tag -d <tag>` rồi chạy lại.
- Đường dẫn `deploy/allowed_signers` tính từ gốc repo; script tự `cd` về đó nên chạy từ thư mục nào cũng được.

### 2.3. `--allow-unsigned` (cấp cứu)

`ops/deploy.sh <tag> --allow-unsigned` **bỏ qua** kiểm chữ ký, in cảnh báo ra stderr và ghi `signed=no` vào log. Chỉ dùng
khi chưa có khóa trong `allowed_signers` mà phải triển khai ngay, và bạn tự xác nhận tag đến từ nguồn tin cậy. Cờ này tắt
cơ chế chống tag giả mạo (và cả kiểm tên tag, kiểm `allowed_signers` có khóa), nên không dùng làm thói quen và không
đưa vào cron/CI. Quay lui tự động cũng theo cùng chính sách: có cờ thì không kiểm chữ ký của bản cũ, không có cờ thì bản
cũ cũng phải qua `verify-tag`.

### 2.4. S4 bảo vệ gì và không bảo vệ gì

- Chữ ký tag đảm bảo **mã nguồn** (commit mà tag trỏ tới, nên cả `deploy/`, `ops/`, SPA dựng từ đó) do khóa trong
  `allowed_signers` phát hành.
- Chữ ký **không phủ digest image lõi**: digest lấy từ tệp `trust-core-image-<X.Y.Z>.txt` của GitHub Release, tệp này không
  nằm trong tag và không được ký. Ai có quyền sửa Release có thể trỏ `trust-core` sang image khác dù tag vẫn hợp lệ. Nên
  giới hạn quyền sửa Release/Package và đối chiếu digest với lần phát hành (CHANGELOG, `release.yml`). Ký digest là việc
  chưa làm (hạn chế đã biết của S4).
- Script không kiểm tag nằm trên nhánh `main`, chỉ kiểm khóa ký, tên tag và định dạng `vX.Y.Z`.

### 2.5. Các bước

Theo đúng thứ tự, dừng ở bước đầu tiên hỏng:

1. Kiểm tag `^v[0-9]+\.[0-9]+\.[0-9]+$`, profile `p16`/`p8`, `.env`. Sai: thoát 2, chưa làm gì.
2. Kiểm cây sạch. Không sạch: thoát 2.
3. Ghi nhớ **bản tốt gần nhất**: tag ở dòng `result=ok` cuối của `deploy/deployments.log` khác tag đang triển khai (cũng nhận
   dòng `OK` kiểu cũ), hoặc `none`. Đây là đích quay lui.
4. `git fetch origin refs/tags/<tag>:refs/tags/<tag>` **không** `--force`: nếu tag cục bộ khác tag trên remote, git từ chối
   và script thoát 3 (tag đã bị di chuyển; điều tra trước khi làm gì tiếp, xem `git tag -d` ở mục 2.2).
   Trước bước này, nếu `allowed_signers` không có khóa nào (và không có `--allow-unsigned`): thoát 2.
5. **Kiểm chữ ký**, trước mọi lệnh `docker` và trước `checkout`:
   `git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/<tag>`, rồi tên trong
   thân tag phải đúng `<tag>`. Không đạt: thoát 2 và bỏ ref vừa fetch.
6. `git rev-parse refs/tags/<tag>^{commit}` (một lần), rồi `git checkout --detach <OID>`.
7. Tải `trust-core-image-<X.Y.Z>.txt`, lấy digest. `release.yml` ghi hai dòng: `ghcr.io/psa-ovncr/trust-core:<X.Y.Z>`
   và `ghcr.io/psa-ovncr/trust-core@sha256:<64 hex>`; script lấy phần sau `@sha256:` (cũng nhận tệp chỉ có 64 hex).
   Digest phải khớp `^[0-9a-f]{64}$`, nếu không thoát 3 **trước** khi gọi compose. Ghi `deploy/release.env`.
   Cùng cách cho `viewer-image-<X.Y.Z>.txt` (ghi thêm `DXOS_VIEWER_DIGEST`), nhưng chỉ khi hồ sơ là p16, dịch vụ `viewer` bật
   (`COMPOSE_PROFILES` trong môi trường tiến trình, rồi `.env`, như compose) và `deploy/compose.release.yaml` của tag có
   `DXOS_VIEWER_DIGEST` (tag cũ trước v0.9.0 không có Viewer nên quay lui về chúng vẫn chạy). Thiếu hay sai thì thoát 3:
   máy chủ không bao giờ dựng Viewer từ mã nguồn. Chưa chạy thật trên VPS (V29, V40).
8. Với cùng một bộ tệp: `docker compose -p dxos --env-file .env --env-file deploy/release.env -f deploy/compose.yaml
   -f deploy/compose.<profile>.yaml [-f deploy/compose.anchor.yaml] -f deploy/compose.release.yaml`, chạy
   `pull --ignore-buildable` **trước** (hỏng: thoát 3, chưa có gì đang chạy bị đổi, kể cả SPA).
9. `ops/web_build_docker.sh`: dựng SPA từ mã nguồn của tag vào volume `apps-static`; rồi `up -d --wait --wait-timeout 600`
   (spec 16.3: `compose pull && up -d`). Script bỏ `DXOS_TRUST_CORE_DIGEST`, `DXOS_VIEWER_DIGEST` và `DXOS_RELEASE_TAG` khỏi môi trường của tiến trình ngay từ đầu: compose ưu tiên
   biến môi trường hơn `--env-file`, nên giá trị đã `export` trong shell sẽ lấn digest đã kiểm.
10. Kiểm sức khỏe: `/readyz` của `trust-core-api` (trong container) in `200`, và `https://$DXOS_DOMAIN/verify/v1/keys`
    trả 200. `curl` xác minh chứng chỉ TLS; chỉ khi `DXOS_DOMAIN` là `localhost` hoặc `*.localhost` (CA nội bộ của Caddy)
    mới dùng `curl -k`.
11. Hỏng ở bước 9 (`up --wait`) hoặc 10: **tự quay lui** (mục 4). Ghi dòng kết quả vào `deploy/deployments.log`.

`deploy.sh` đọc `.env` bằng `sed`, không `source`, và không in giá trị bí mật. Lõi chạy đúng image theo digest của Release
(không build trên VPS); SPA được dựng từ mã nguồn của tag. Script của bản đang chạy là script thực hiện việc triển khai
(bash đã đọc xong tệp trước khi `git checkout` thay nó), nên muốn dùng script mới hơn hãy `git checkout` nó trước.

## 3. Đọc `deploy/deployments.log`

Mỗi lần triển khai (từ bước 4 trở đi, trừ khi bị từ chối ở bước 5) thêm một dòng, các cột cách nhau bằng tab:

```
<UTC>	<tag>	<commit>	<digest>	result=ok|rolled-back|failed	signed=yes|no
2026-10-22T03:14:07Z	v0.3.0	0123…cdef	aaaa…aaaa	result=ok	signed=yes
```

- `result=ok` đạt; `result=failed` hỏng (thoát 3, hoặc thoát 5); `result=rolled-back` bản này hỏng health và đã được thay
  bằng bản tốt trước đó (thoát 4; ngay trước dòng này là dòng `result=ok` của lần quay lui).
- `signed=yes` tag qua `verify-tag`; `signed=no` triển khai bằng `--allow-unsigned`.
- `commit` và `digest` là `-` nếu script hỏng trước khi biết được (ví dụ `git fetch` bị từ chối, hay tệp digest sai).
- Dòng kiểu cũ của Plan 03 (`...<digest>\tOK` hoặc `...\tFAIL`, không có cột `signed`) vẫn nằm trong tệp và vẫn được đọc:
  `OK` được coi như `result=ok` khi tìm bản tốt gần nhất, `FAIL` thì không.
- Xem bản đang chạy tốt: `awk -F'\t' '$5=="result=ok"||$5=="OK"{t=$0} END{print t}' deploy/deployments.log`.
- Dòng `failed` không có nghĩa stack đã dừng: compose có thể đã chạy một phần. Xem `docker compose -p dxos ps` và log
  của dịch vụ không khỏe trước khi quyết định.

## 4. Quay lui

**Tự quay lui (S4).** Khi bản mới đã chuyển mà health hỏng, script chạy lại đúng chuỗi bước 4 đến 10 cho bản tốt gần nhất
(digest lấy từ Release của tag cũ, SPA dựng lại từ mã nguồn tag cũ, `pull`, `up --wait`, health) **một lần duy nhất**, không
đệ quy: quay lui hỏng thì dừng, không thử bản cũ hơn. Kết quả: thoát 4 (khỏe) hoặc 5 (không quay lui được). Nếu chưa có
dòng `result=ok` nào trong log (triển khai đầu tiên) thì thoát 5 ngay và in hướng dẫn khôi phục tay:

1. `docker compose -p dxos ps` và `docker compose -p dxos logs --tail=200 <dịch vụ không khỏe>`.
2. Biết một tag từng chạy tốt thì chạy lại `ops/deploy.sh <tag>` (kèm `--allow-unsigned` chỉ khi tag đó chưa ký và bạn chấp nhận rủi ro).
3. Chưa có tag tốt: sửa nguyên nhân từ log, phát hành tag mới đã ký, rồi `ops/deploy.sh <tag mới>`.

**Quay lui tay.** Với thoát 3 (chưa chuyển bản) script in đúng:

```
Triển khai <tag> hỏng. Quay lại bằng: ops/deploy.sh <tag trước>
```

Chạy lệnh đó: sau thoát 3 cây làm việc đang tách rời tại tag mới, chạy `ops/deploy.sh <tag trước>` cũng dựng lại SPA của tag
cũ vào `apps-static` (khôi phục SPA nếu nó đã bị ghi dở). Nếu `<tag trước>` là `none` thì chưa có bản nào từng chạy tốt qua script này.

**Không tự quay lui qua migration mới (R33).** `trust-core-api` chạy `migrate` mỗi lần khởi động, và `migrate` của bản cũ từ chối
CSDL đã có migration mà mã của nó không có (lỗi "DB đã có migration mà mã nguồn không có"). Nên nếu bản mới thêm tệp vào
`core/migrations/` so với bản tốt gần nhất (script so `git ls-tree --name-only` của hai tag, sau khi tag cũ qua kiểm chữ ký và
trước khi đổi cây làm việc hay container), quay lui sẽ chỉ làm API của bản cũ lặp chết. Khi đó script **không quay lui**: ghi
`result=failed` cho bản mới, in các migration thêm và hướng dẫn, rồi thoát 5; stack ở lại bản mới (chưa khỏe). Không bao giờ hạ
migration. Chọn một trong hai: (1) sửa tiếp (`docker compose -p dxos logs --tail=200 trust-core-api`, phát hành tag mới đã ký,
`ops/deploy.sh <tag mới>`); (2) khôi phục từ bản sao lưu lấy **trước** lần triển khai này bằng `ops/restore.sh` vào một project
riêng theo `docs/runbook-backup.md` (mục 4), kiểm dữ liệu rồi mới chuyển; không khôi phục đè lên project `dxos`. Vì vậy chạy
`ops/backup.sh` trước mỗi lần nâng lên bản có migration mới; ghi chú nâng cấp từ 0.3.0 ở mục "Nâng cấp từ 0.3.0" của
`CHANGELOG.md` mục [0.9.0]. Khi quay lui diễn ra (cùng migration), lệnh `up` của lần quay lui chạy kèm `--remove-orphans` để
container của dịch vụ mà bản cũ không có (Viewer của 0.9.0) không ở lại. Sau thoát 4 hoặc 5 cây làm việc đang ở `HEAD` tách rời tại tag cuối cùng script đã checkout.
Chạy thật tự quay lui trên VPS là việc V42 (mới kiểm bằng `git`, `docker`, `curl` giả).

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
