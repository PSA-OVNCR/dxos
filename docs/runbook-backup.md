<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Runbook: sao lưu mã hóa, khôi phục, diễn tập AT-21

Áp dụng spec S4 và quyết định P4-D9 (Plan 04 Task 12). Ba script trong `ops/`:

| Script | Việc |
|---|---|
| `ops/backup.sh <thư mục ra>` | Sao lưu stack `dxos` thành một gói mã hóa kèm băm sha256. |
| `ops/restore.sh <gói> --project <tên>` | Khôi phục gói vào một compose project **riêng**; từ chối `dxos`. |
| `ops/at21_drill.sh ...` | Diễn tập AT-21: sao lưu, khôi phục vào `dxos-restore`, đối soát sổ cái và một niêm phong. |

**Chưa chạy thật ở đâu cả khi viết tài liệu này.** Script mới được kiểm bằng `docker` và `dxos-witness` giả với
`openssl` thật (`tests/ops/test_backup_restore.py`). Diễn tập thật trên laptop (hồ sơ p8) rồi VPS là việc **V43**; kết quả
ghi vào `docs/progress/`. Cho tới khi V43 xong, đừng coi backup là đã được kiểm chứng.

## 1. Gói chứa gì, không chứa gì

`dxos-backup-<UTC>.tar.enc` là tar đã mã hóa bằng `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt`, đi kèm
`dxos-backup-<UTC>.tar.enc.sha256` (dạng `sha256sum`). Bên trong, đúng bảy tệp:

| Tệp | Nguồn |
|---|---|
| `pg/core-db.dump`, `pg/kc-db.dump`, `pg/flowable-db.dump` | `pg_dump -Fc` của cơ sở dữ liệu lõi (sổ cái, bản ghi, niêm phong, STH), Keycloak (realm, người dùng) và Flowable |
| `volumes/seaweedfs-data.tar` | tệp đã tải lên (SeaweedFS), lấy bằng container `busybox` đã ghim digest, `--volumes-from <container>:ro`, không mạng |
| `volumes/openbao-data.tar` | kho dữ liệu của OpenBao (khóa ký niêm phong và STH, **vẫn bị mã hóa bằng unseal key**) |
| `MANIFEST.txt`, `SHA256SUMS` | định dạng `dxos-backup/1`, thời điểm UTC, băm từng tệp dữ liệu |

**Không nằm trong gói** (phải có cách giữ riêng, nếu không khôi phục không đủ):

- **Unseal key của OpenBao**: không có thì kho OpenBao đã khôi phục vẫn khóa, lõi không ký được và không đọc được khóa
  công khai. Giữ như `docs/runbook-openbao.md` mục 1 (ngoài máy chủ).
- **`.env`** (mật khẩu DB, khóa HMAC, token OpenBao của lõi, tên miền): giữ bản sao ở nơi an toàn, ngoài máy chủ.
- **`.secrets/`** (deploy key của repo neo, mật khẩu backup này).
- Dữ liệu dựng lại được: `apps-static` (chạy `make web-build`), `clamav-db` (ClamAV tự tải), `caddy-data` (chứng chỉ TLS cấp lại),
  `anchor-repo` (clone lại từ repo neo).

## 2. Mật khẩu backup

Mật khẩu nằm ở **`.secrets/backup-passphrase`** trong thư mục repo trên máy chủ (`.secrets/` đã có trong `.gitignore`):

```bash
mkdir -p .secrets
openssl rand -base64 32 > .secrets/backup-passphrase
chmod 600 .secrets/backup-passphrase
```

- Script chỉ đọc **dòng đầu** của tệp bằng `-pass file:`; không bao giờ đưa mật khẩu lên dòng lệnh hay in ra. Từ chối (mã 3)
  khi tệp thiếu hoặc dòng đầu ngắn hơn 16 ký tự. Cảnh báo khi nhóm hay người khác đọc được tệp (`chmod 600`).
- **Giữ thêm một bản ở ngoài máy chủ**, tách khỏi nơi để các gói (trình quản lý mật khẩu của trưởng nhóm hoặc USB).
  Mất mật khẩu là mất mọi gói; ai có cả gói lẫn mật khẩu đọc được toàn bộ dữ liệu, kể cả dữ liệu cá nhân.
- Đổi mật khẩu thì gói cũ vẫn cần mật khẩu cũ: giữ mật khẩu cũ cho tới khi hết hạn giữ gói cũ.
- Quyết định P4-D9: **không có xác thực MAC riêng**. Chế độ CBC không tự phát hiện sửa đổi; `restore.sh` bù bằng sha256 ghi kèm
  và băm từng tệp trong `SHA256SUMS`. Đó chỉ chống hỏng hay nhầm, **không** chống kẻ sửa được cả gói lẫn tệp `.sha256` mà
  biết mật khẩu. Chép gói và `.sha256` ra nơi hạn chế ghi.

## 3. Sao lưu

```bash
cd /đường/dẫn/tới/dxos          # thư mục repo trên máy chủ, stack `dxos` đang chạy
ops/backup.sh /var/backups/dxos
```

Cần: `docker` (người chạy dùng được docker), `openssl`, `tar`, stack `dxos` đang chạy (core-db, kc-db, flowable-db, và
container seaweedfs, openbao). Không cần `.env`.

- Thư mục tạm (`mktemp -d`, quyền 0700, xóa khi thoát kể cả khi lỗi) chứa bản **chưa mã hóa** của dữ liệu trong lúc làm việc.
  Chỉ gói đã mã hóa và `.sha256` được ghi vào thư mục ra. **Đặt `TMPDIR`** trỏ tới ổ đủ chỗ (cỡ tổng dữ liệu) và không phải
  tmpfs/RAM, và chỉ người chạy đọc được: `TMPDIR=/var/backups/dxos/tmp ops/backup.sh /var/backups/dxos`.
- Tệp ghi qua `.partial` rồi đổi tên, nên gói dở không bao giờ mang tên gói thật.
- Tính nhất quán: `pg_dump` cho ảnh chụp nhất quán của từng DB, nhưng SeaweedFS và OpenBao được tar khi đang chạy. [ĐX] Chạy
  lúc ít ghi nhất (đêm); muốn chắc hơn thì `docker compose -p dxos stop trust-core-worker` trước và `start` sau. Gói lệch giữa
  DB và tệp (một tệp đã tải lên mà DB chưa ghi, hay ngược lại) là rủi ro đã biết, chưa có cách kiểm tự động.
- [ĐX] Chép gói ra khỏi máy chủ (máy khác, ổ ngoài): script không làm việc này. Một bản sao chỉ nằm trên chính máy chủ sẽ mất
  cùng máy chủ.

| Mã thoát | Nghĩa |
|---|---|
| 0 | Xong. In đường dẫn gói và sha256. |
| 2 | Tham số sai (thiếu hay thừa đối số, thư mục ra là một tệp, trùng tên gói đã có). |
| 3 | Thiếu điều kiện hoặc một bước hỏng: thiếu/ngắn mật khẩu, thiếu công cụ, một dịch vụ không chạy, `pg_dump`/tar/mã hóa lỗi. Không để lại tệp nào ở thư mục ra. |

### 3.1. Lịch hằng đêm bằng systemd timer (mẫu, không bật mặc định)

Repo **không** cài hay bật timer nào. Muốn bật, người vận hành tạo hai tệp dưới đây (chỉnh `User`, đường dẫn) rồi tự bật.
`User` phải dùng được docker và đọc được `.secrets/backup-passphrase`.

`/etc/systemd/system/dxos-backup.service`:

```ini
[Unit]
Description=DX-OS sao luu ma hoa
Wants=docker.service
After=docker.service

[Service]
Type=oneshot
User=dxos
WorkingDirectory=/opt/dxos
Environment=TMPDIR=/var/backups/dxos/tmp
ExecStart=/opt/dxos/ops/backup.sh /var/backups/dxos
Nice=10
IOSchedulingClass=idle
```

`/etc/systemd/system/dxos-backup.timer`:

```ini
[Unit]
Description=DX-OS sao luu hang dem

[Timer]
OnCalendar=*-*-* 02:30:00
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo mkdir -p /var/backups/dxos/tmp && sudo chown -R dxos: /var/backups/dxos && sudo chmod 700 /var/backups/dxos/tmp
sudo systemctl daemon-reload
sudo systemctl enable --now dxos-backup.timer      # chỉ khi trưởng nhóm đã quyết định bật
systemctl list-timers dxos-backup.timer            # xem lần chạy kế
journalctl -u dxos-backup.service -n 50            # kết quả lần gần nhất (mã thoát khác 0 là lỗi)
```

**Thời hạn giữ gói không có ở đây.** Mẫu trên không xóa gói cũ, cũng không đặt số ngày nào: thời hạn giữ do trưởng nhóm
chốt (việc V21, `docs/runbook-pii-erasure.md` mục 5). Chốt rồi mới thêm bước xóa gói quá hạn; không tự điền số.

## 4. Khôi phục

Mục tiêu của `restore.sh` là một project **khác** `dxos`. Nó từ chối `--project dxos` (mã 2) và mọi tên viết hoa của nó.

```bash
# 1. Chép gói và .sha256 về cùng một thư mục; mật khẩu ở .secrets/backup-passphrase của repo này.
ops/restore.sh /var/backups/dxos/dxos-backup-20261023T023000Z.tar.enc --project dxos-restore
```

Thứ tự trong script: kiểm sha256 của gói, giải mã vào thư mục tạm, kiểm gói (đúng bảy tệp, băm khớp) rồi **mới** gọi docker.
Gói hỏng, bị sửa, hay mật khẩu sai đều dừng ở đó với mã 2 và chưa tạo gì. Sau đó: project phải chưa có container hay volume
nào, tạo volume `dxos-restore_seaweedfs-data` và `dxos-restore_openbao-data` (có nhãn compose) rồi giải tar vào, dựng ba
DB, tạo role `dxos_core`, `pg_restore --exit-on-error`. Chỉ tài nguyên của project được chỉ định bị tạo; stack `dxos` không bị đụng.

| Mã thoát | Nghĩa |
|---|---|
| 0 | Xong: volume SeaweedFS, OpenBao và ba DB đã khôi phục (DB đang chạy). |
| 2 | Từ chối **trước khi đổi gì**: tham số sai, `--project dxos`, sha256 không khớp, sai mật khẩu hay gói hỏng, project đã có tài nguyên. |
| 3 | Thiếu điều kiện: mật khẩu, `docker`/`openssl`/`tar`, `.env`, tệp compose. |
| 4 | Hỏng sau khi bắt đầu tạo. In lệnh dọn: `docker compose -p <tên> down -v`. |

Project đã tồn tại (chạy lại diễn tập): xóa trước bằng `docker compose -p dxos-restore down -v`. Script không tự xóa.

Tùy chọn: `--profile p16|p8` (mặc định p16) và `--env-file FILE` (mặc định `.env` của repo).

### 4.1. Dựng và mở khóa bản khôi phục

`restore.sh` chỉ khôi phục **dữ liệu**. Để đọc được sổ cái và niêm phong từ bản khôi phục:

```bash
export DXOS_DOMAIN=restore.localhost        # tên miền khác stack thật; biến môi trường thắng --env-file
C="docker compose -p dxos-restore --env-file .env -f deploy/compose.yaml -f deploy/compose.p16.yaml"
$C up -d --wait openbao seaweedfs
read -rs BAO_DXOS_UNSEAL && export BAO_DXOS_UNSEAL        # dán unseal key của stack gốc
$C exec -e BAO_DXOS_UNSEAL openbao sh -c 'bao operator unseal "$BAO_DXOS_UNSEAL"'
unset BAO_DXOS_UNSEAL
$C up -d --wait trust-core-api
```

**Không tranh cổng với stack thật:** chỉ `caddy` công bố cổng 80/443 (`tests/infra/test_compose_static.py`), và các lệnh trên **không
dựng caddy** (cũng không apisix). Đọc API của bản khôi phục bằng `docker compose -p dxos-restore exec -T trust-core-api python -c ...`
(port 8000 trong container), như `ops/at21_drill.sh`. Cũng không dựng Keycloak, Flowable, ClamAV trong diễn tập để không nhân đôi
RAM (dữ liệu của chúng vẫn được khôi phục vào volume và dựng lên được khi cần). Nhớ `unset DXOS_DOMAIN` hoặc mở shell khác sau
khi xong, kẻo lệnh compose của stack thật dùng nhầm tên miền.

Dọn khi xong: `docker compose -p dxos-restore down -v`.

### 4.2. Khôi phục thật khi mất máy chủ (chưa có script, [ĐX])

`restore.sh` cố ý không có cách ghi vào project `dxos`. Với sự cố thật trên máy chủ mới chưa có project `dxos`: chạy
`restore.sh --project dxos-restore` để kiểm gói và nạp dữ liệu, dựng stack đầy đủ dưới project đó (`-p dxos-restore`, Caddy
lấy được 80/443 vì máy chưa chạy gì), mở khóa OpenBao (mục 4.1) rồi kiểm sổ cái và một niêm phong bằng tay. Việc chuyển về tên
project `dxos` là một đợt riêng, chưa được thử. Đây là khoảng trống đã biết, ghi vào V43.

Sau khi khôi phục từ gói cũ hơn một lần xóa dữ liệu cá nhân, **chạy lại các lần xóa sau thời điểm của gói** trước khi mở lại
hệ thống (`docs/runbook-pii-erasure.md` mục 5).

## 5. Diễn tập AT-21

AT-21 (SHOULD): sau khôi phục, dữ liệu và niêm phong vẫn đối soát được. Chạy ở máy có stack `dxos` đang chạy, lúc không có ghi:

```bash
# Chọn TRƯỚC một niêm phong đã ban hành (mã trên trang đối soát) và có bản clone repo neo:
ops/at21_drill.sh --seal-id <mã niêm phong> --anchor-dir ../dxos-transparency-log \
    --unseal-key-file /đường/dẫn/unseal.key [--file hồ-sơ-gốc.pdf] [--profile p8] [--keep]
```

`--file` bắt buộc khi niêm phong thuộc loại `require_file: true` (App A): script gửi băm của tệp tới `POST .../seals/<mã>:bundle`
như trang đối soát; không có thì dùng `GET .../seals/<mã>/bundle`. `--unseal-key-file`: mỗi dòng một unseal key (đọc từ tệp,
đưa vào container qua biến môi trường, không lên dòng lệnh); xóa tệp khi xong.

Script làm, theo thứ tự (mỗi bước hỏng thì dừng):

1. Ở stack **thật**, qua `docker exec` (chỉ đọc): ghi STH mới nhất và gói bằng chứng của niêm phong; `dxos-witness verify-bundle ... --anchor-dir`
   gói đó phải đạt.
2. `ops/backup.sh` vào thư mục tạm.
3. `docker compose -p dxos-restore ... down -v` (xóa project diễn tập cũ, tên cố định này), rồi `DXOS_DOMAIN=restore.localhost ops/restore.sh ... --project dxos-restore`.
4. Dựng openbao + seaweedfs, mở khóa OpenBao, dựng trust-core-api (cùng image với stack thật, theo `deploy/release.env` nếu có).
5. Lấy lại STH mới nhất và gói của **cùng niêm phong** từ bản khôi phục, `verify-bundle` lần hai.
6. So `tree_size` và `root_hash` trước/sau, cho cả STH mới nhất lẫn STH trong gói. Khớp hết và hai lần verify đạt thì in `AT-21 ĐẠT`.

| Mã thoát | Nghĩa |
|---|---|
| 0 | AT-21 ĐẠT. Project `dxos-restore` được dọn (trừ khi có `--keep`). |
| 1 | AT-21 KHÔNG ĐẠT: niêm phong không qua `verify-bundle` (trước hoặc sau) hay `tree_size`/root lệch. Project diễn tập còn lại để điều tra. |
| 2 | Tham số sai. |
| 3 | Thiếu điều kiện trước khi đổi gì (công cụ, mật khẩu, `.env`, stack thật không chạy, không lấy được niêm phong). |
| 4 | Một bước hạ tầng hỏng (backup, restore, dựng stack, mở khóa, lấy dữ liệu). |

Lưu ý: nếu stack thật ghi thêm giữa bước 1 và bước 2, STH mới làm `tree_size` lệch dù khôi phục đúng. Chạy lúc yên rồi chạy lại.
RAM: diễn tập chạy song song stack thật; phần dựng thêm là 3 PostgreSQL, SeaweedFS, OpenBao, trust-core-api. Trên laptop p8 đóng bớt
việc khác. Trên Windows chạy bằng Git Bash (`MSYS_NO_PATHCONV=1` do script tự đặt).

**Ghi kết quả** (việc V43): `docs/progress/<ngày>-at21-<nơi chạy>.md` với đầu ra của script, hồ sơ (p8/p16), kích thước gói và
thời gian, và nói rõ chạy ở laptop hay VPS. Chưa ai chạy thì `docs/acceptance.md` giữ "chưa có — V43".
