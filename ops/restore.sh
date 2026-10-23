#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Khôi phục một gói do ops/backup.sh tạo vào một compose project RIÊNG (Plan 04 Task 12, spec S4, P4-D9). Không bao giờ
# khôi phục đè lên project thật `dxos`.
#
#   ops/restore.sh <tệp.tar.enc> --project <tên> [--profile p16|p8] [--env-file FILE]
#
# <tên>: chữ thường, chữ số, `-`, `_`; khác `dxos`. Diễn tập dùng `dxos-restore`. Chỉ sinh volume, mạng, container mang
# nhãn compose project này: volume `<tên>_seaweedfs-data`, `<tên>_openbao-data`, `<tên>_core-db-data`, ...
#
# Thứ tự (mỗi bước hỏng thì dừng; bước 1 đến 5 KHÔNG gọi docker, nên gói hỏng hay mật khẩu sai không để lại gì):
#   1. Tham số; project khác `dxos`; công cụ; .secrets/backup-passphrase.
#   2. sha256 của <tệp.tar.enc> phải khớp tệp `.sha256` đi kèm.
#   3. Giải mã vào thư mục tạm riêng (mktemp -d, xóa khi thoát). Mật khẩu sai hay gói bị sửa: dừng.
#   4. Kiểm gói: đúng bảy thành viên (không thừa, không thiếu, không đường dẫn lạ), MANIFEST đúng định dạng, băm
#      từng thành viên khớp SHA256SUMS. CBC không tự xác thực, nên bước 4 mới là chỗ bắt gói giải mã ra rác.
#   5. Project phải chưa có container hay volume nào (docker ps -a / volume ls theo nhãn).
#   6. Tạo hai volume (SeaweedFS, OpenBao) có nhãn compose của project, giải tar vào bằng busybox đã ghim.
#   7. docker compose -p <tên> up -d --wait core-db kc-db flowable-db (volume DB mới), tạo role `dxos_core` (pg_dump
#      từng DB không mang role), `pg_restore --exit-on-error` ba DB.
#   Các dịch vụ còn lại KHÔNG được dựng: dựng và mở khóa OpenBao theo docs/runbook-backup.md hoặc ops/at21_drill.sh.
#
# Mã thoát:
#   0  xong.
#   2  từ chối TRƯỚC khi đổi gì: tham số sai, --project là `dxos` hay tên không hợp lệ, sha256 không khớp, mật khẩu sai
#      hoặc gói hỏng/bị sửa, project đã có tài nguyên.
#   3  thiếu điều kiện: thiếu/ngắn .secrets/backup-passphrase, thiếu docker/openssl/tar, thiếu .env hay tệp compose.
#   4  hỏng SAU khi bắt đầu tạo (volume, compose up, pg_restore): in lệnh dọn `docker compose -p <tên> down -v`.
set -euo pipefail

PROG=restore.sh
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=ops/backup_lib.sh
. "$REPO/ops/backup_lib.sh"

usage() {
    echo "dùng: ops/restore.sh <tệp.tar.enc> --project <tên> [--profile p16|p8] [--env-file FILE]" >&2
    exit 2
}

FILE="" PROJECT="" PROFILE=p16 ENV_FILE=
have_project=0
while [ $# -gt 0 ]; do
    case $1 in
        --project) [ $# -ge 2 ] || usage; PROJECT=$2; have_project=1; shift 2 ;;
        --profile) [ $# -ge 2 ] || usage; PROFILE=$2; shift 2 ;;
        --env-file) [ $# -ge 2 ] || usage; ENV_FILE=$2; shift 2 ;;
        -*) echo "$PROG: tùy chọn không hợp lệ: $1" >&2; usage ;;
        *) [ -z "$FILE" ] || usage; FILE=$1; shift ;;
    esac
done
[ -n "$FILE" ] && [ "$have_project" = 1 ] || usage

# Lệnh từ chối quan trọng nhất: so cả dạng viết hoa (compose chuẩn hóa tên project về chữ thường).
lower=$(printf '%s' "$PROJECT" | tr '[:upper:]' '[:lower:]')
[ "$lower" != "$LIVE_PROJECT" ] || die 2 "từ chối --project $PROJECT: không bao giờ khôi phục vào project thật '$LIVE_PROJECT'"
project_re='^[a-z0-9][a-z0-9_-]{0,62}$'
[[ $PROJECT =~ $project_re ]] || die 2 "--project '$PROJECT' không hợp lệ (chữ thường, chữ số, '-', '_', bắt đầu bằng chữ hoặc số)"
[ "$PROJECT" != "$LIVE_PROJECT" ] || die 2 "từ chối --project $PROJECT"
case $PROFILE in p16 | p8) ;; *) die 2 "--profile phải là p16 hoặc p8 (nhận được: $PROFILE)" ;; esac
case $ENV_FILE in "" | /*) ;; *) ENV_FILE=$PWD/$ENV_FILE ;; esac     # đường dẫn tương đối tính từ nơi gọi, trước khi cd
case $FILE in /*) ;; *) FILE=$PWD/$FILE ;; esac

need_tools docker openssl tar head
require_passphrase
cd "$REPO"
ENV_FILE=${ENV_FILE:-.env}
check_compose_inputs "$PROFILE" "$ENV_FILE"

# --- 2. sha256 của gói
[ -f "$FILE" ] || die 2 "không có tệp $FILE"
[ -f "$FILE.sha256" ] || die 2 "thiếu $FILE.sha256 (không kiểm được toàn vẹn của gói)"
want=$(head -n 1 "$FILE.sha256" | cut -d' ' -f1 | tr -d '\r')
sha_re='^[0-9a-f]{64}$'
[[ $want =~ $sha_re ]] || die 2 "$FILE.sha256 không có băm sha256 hợp lệ ở đầu dòng đầu"
[ "$(sha256_of "$FILE")" = "$want" ] || die 2 "sha256 của $FILE không khớp $FILE.sha256 (gói hỏng hoặc bị sửa)"

# --- 3, 4. giải mã và kiểm gói trong thư mục tạm riêng
WORK=$(mktemp -d "${TMPDIR:-/tmp}/dxos-restore.XXXXXX") || die 3 "không tạo được thư mục tạm"
# shellcheck disable=SC2329  # gọi qua trap EXIT
cleanup() {
    if [ -n "$WORK" ] && [ -d "$WORK" ] && [ "$WORK" != / ]; then rm -rf "$WORK"; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:"$PASS_FILE" -in "$FILE" -out "$WORK/bundle.tar" \
    2> /dev/null || die 2 "giải mã thất bại: sai mật khẩu trong $PASSPHRASE_REL hoặc gói bị cắt/sửa. Chưa tạo gì."
listing=$(tar -tf "$WORK/bundle.tar" 2> /dev/null) || die 2 "gói giải mã ra không phải tar hợp lệ (sai mật khẩu hoặc gói bị sửa). Chưa tạo gì."
got=$(printf '%s\n' "$listing" | LC_ALL=C sort)
expected=$(printf '%s\n' "${BUNDLE_MEMBERS[@]}" | LC_ALL=C sort)
[ "$got" = "$expected" ] || die 2 "gói có thành viên khác bảy tệp dự kiến (thừa, thiếu hay đường dẫn lạ). Chưa tạo gì."
mkdir "$WORK/x"
tar -xf "$WORK/bundle.tar" -C "$WORK/x" 2> /dev/null || die 2 "không giải được tar của gói. Chưa tạo gì."
grep -qx "format=$BACKUP_FORMAT" "$WORK/x/MANIFEST.txt" || die 2 "MANIFEST.txt không phải định dạng $BACKUP_FORMAT. Chưa tạo gì."
sums_ok "$WORK/x" || die 2 "băm các thành viên không khớp SHA256SUMS (gói bị sửa hoặc giải mã sai). Chưa tạo gì."
echo "$PROG: gói hợp lệ ($(grep '^created_utc=' "$WORK/x/MANIFEST.txt" || true))"

# --- 5. project chưa có gì
label="label=com.docker.compose.project=$PROJECT"
existing_c=$(docker ps -aq --filter "$label") || die 3 "docker ps lỗi (daemon không chạy?)"
existing_v=$(docker volume ls -q --filter "$label") || die 3 "docker volume ls lỗi"
if [ -n "$existing_c$existing_v" ]; then
    die 2 "project $PROJECT đã có container hoặc volume; không khôi phục đè. Xóa bằng: docker compose -p $PROJECT down -v"
fi

# --- 6, 7. từ đây bắt đầu tạo tài nguyên: lỗi thì mã 4 và in lệnh dọn
fail() {
    echo "$PROG: $*" >&2
    echo "$PROG: khôi phục dở dang. Dọn project $PROJECT (không đụng project $LIVE_PROJECT): docker compose -p $PROJECT down -v" \
        "(volume tạo tay còn lại: docker volume ls --filter $label)" >&2
    exit 4
}

for target in "${VOLUME_TARGETS[@]}"; do
    IFS=: read -r vol _ _ <<< "$target"
    name=${PROJECT}_$vol
    echo "$PROG: volume $name"
    docker volume create --label "com.docker.compose.project=$PROJECT" --label "com.docker.compose.volume=$vol" "$name" \
        > /dev/null || fail "docker volume create $name hỏng"
    docker run --rm -i --network none -v "$name:/data" "$BUSYBOX_IMAGE" tar -xf - -C /data \
        < "$WORK/x/volumes/$vol.tar" || fail "giải tar vào volume $name hỏng"
done

compose_for "$PROJECT" "$PROFILE" "$ENV_FILE"
echo "$PROG: dựng ba cơ sở dữ liệu của project $PROJECT"
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 core-db kc-db flowable-db || fail "docker compose up (ba DB) hỏng"

# pg_dump từng DB không mang role. Role ứng dụng của lõi do migration 001 tạo (không mật khẩu; trust-core-api đặt mật
# khẩu mỗi lần khởi động); phải có trước pg_restore vì dump có GRANT cho role này.
ROLE_SQL="DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dxos_core') THEN CREATE ROLE dxos_core LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; END IF; END \$\$;"
for target in "${PG_TARGETS[@]}"; do
    IFS=: read -r svc user db <<< "$target"
    cid=$(find_cid "$PROJECT" "$svc") || fail "docker ps lỗi"
    [ -n "$cid" ] || fail "dịch vụ $svc của project $PROJECT không chạy"
    if [ "$svc" = core-db ]; then
        docker exec "$cid" psql -U "$user" -d "$db" -v ON_ERROR_STOP=1 -c "$ROLE_SQL" > /dev/null ||
            fail "tạo role dxos_core hỏng"
    fi
    echo "$PROG: pg_restore $svc"
    docker exec -i "$cid" pg_restore -U "$user" -d "$db" --exit-on-error < "$WORK/x/pg/$svc.dump" ||
        fail "pg_restore $svc hỏng"
done

cat << DONE
$PROG: xong. Dữ liệu đã vào project $PROJECT: volume SeaweedFS và OpenBao, ba cơ sở dữ liệu (đang chạy).
Chưa dựng dịch vụ nào khác. Bước tiếp (docs/runbook-backup.md mục 4):
  - dựng OpenBao + SeaweedFS rồi MỞ KHÓA OpenBao bằng unseal key của stack gốc (gói không chứa key này);
  - dựng trust-core-api; để chạy cạnh stack thật đặt DXOS_DOMAIN khác và KHÔNG dựng caddy (cổng 80/443).
Dọn khi xong: docker compose -p $PROJECT down -v
DONE
