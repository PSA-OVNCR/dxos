#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Diễn tập khôi phục AT-21 (Plan 04 Task 12, spec S4): sao lưu stack thật rồi khôi phục vào project riêng `dxos-restore`,
# dựng phần lõi trên tên miền khác và chứng minh sổ cái cùng một niêm phong chọn trước vẫn đối soát được.
#
#   ops/at21_drill.sh --seal-id <mã niêm phong> --anchor-dir <bản clone repo neo> --unseal-key-file <tệp> \
#       [--file <tệp gốc>] [--profile p16|p8] [--env-file FILE] [--keep]
#
#   --seal-id          niêm phong đã chọn TRƯỚC khi sao lưu (tra ở trang đối soát hay danh sách niêm phong).
#   --anchor-dir       bản clone repo neo, để `dxos-witness verify-bundle` ghim khóa công khai (AT-17).
#   --unseal-key-file  unseal key của OpenBao trong stack gốc, mỗi dòng một khóa (dòng trống và dòng bắt đầu bằng # bị
#                      bỏ qua). Gói không chứa khóa này; không có nó thì OpenBao đã khôi phục vẫn khóa và không ký/đọc
#                      được khóa công khai. Đọc từ tệp, truyền qua biến môi trường, không bao giờ nằm trên dòng lệnh.
#   --file             tệp gốc của niêm phong có `require_file: true` (App A): lấy gói bằng POST :bundle với băm của
#                      tệp và đưa tệp cho verify-bundle. Không có thì dùng GET .../bundle (niêm phong `require_file: false`).
#   --keep             giữ project diễn tập sau khi đạt (mặc định: `down -v` project `dxos-restore`).
#
# Các bước (mỗi bước hỏng thì dừng):
#   1. Kiểm tham số và điều kiện (stack `dxos` đang chạy trust-core-api, .secrets/backup-passphrase, .env).
#   2. TRƯỚC khi sao lưu, ở stack thật: ghi STH mới nhất (`/verify/v1/sth/latest`) và gói bằng chứng của niêm phong;
#      `dxos-witness verify-bundle` gói đó phải đạt (không thì diễn tập vô nghĩa).
#   3. ops/backup.sh vào thư mục tạm.
#   4. `docker compose -p dxos-restore ... down -v` (xóa project diễn tập CŨ nếu có; chỉ tên cố định này), rồi
#      DXOS_DOMAIN=restore.localhost ops/restore.sh <gói> --project dxos-restore.
#   5. Dựng openbao + seaweedfs, mở khóa OpenBao, dựng trust-core-api (cùng image với stack thật). KHÔNG dựng caddy và
#      apisix, nên không tranh cổng 80/443 với stack thật; không dựng Keycloak, Flowable, ClamAV để không nhân đôi RAM
#      (dữ liệu của chúng vẫn được khôi phục vào volume). Mọi lời gọi API đi qua `docker exec ... python` trong container.
#   6. Lấy lại STH mới nhất và gói của cùng niêm phong từ bản khôi phục, `verify-bundle` lần hai, rồi SO `tree_size` và
#      `root_hash` trước/sau (cả STH mới nhất lẫn STH nằm trong gói). Khớp hết thì ĐẠT.
#
# Phải chạy lúc stack thật không có ghi nào giữa bước 2 và bước 3 (STH mới sinh ở giữa làm tree_size lệch).
# Không bao giờ chạy lệnh ghi/xóa nào lên project `dxos`: stack thật chỉ được đọc (docker ps, docker exec ... GET).
#
# Mã thoát:
#   0  AT-21 ĐẠT.
#   1  AT-21 KHÔNG ĐẠT: niêm phong không qua verify-bundle (trước hoặc sau khôi phục) hay tree_size/root lệch.
#   2  tham số sai.
#   3  thiếu điều kiện trước khi đổi gì (thiếu công cụ, mật khẩu, .env, stack thật không chạy, không lấy được niêm phong).
#   4  một bước hạ tầng hỏng sau khi đã sao lưu (backup, restore, dựng stack, mở khóa, lấy dữ liệu). Chạy lại; project
#      diễn tập còn lại thì dọn bằng `docker compose -p dxos-restore down -v`.
set -euo pipefail

PROG=at21_drill.sh
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=ops/backup_lib.sh
. "$REPO/ops/backup_lib.sh"

DRILL_DOMAIN=restore.localhost
# Chạy trong container trust-core-api: GET (hoặc POST {"sha256": ...} nếu có đối số thứ hai) và in một dòng
# "<tree_size> <root_hash>" của STH (của chính phản hồi nếu là STH, hoặc trường `sth` nếu là gói) rồi thân JSON gốc.
PYGET='import json,sys,urllib.request as u;a=sys.argv;r=u.Request("http://127.0.0.1:8000"+a[1],data=json.dumps({"sha256":a[2]}).encode() if len(a)>2 else None,headers={"Content-Type":"application/json"});raw=u.urlopen(r,timeout=30).read();d=json.loads(raw);s=d if "root_hash" in d else d["sth"];print(s["tree_size"],s["root_hash"]);sys.stdout.write(raw.decode())'

usage() {
    echo "dùng: ops/at21_drill.sh --seal-id ID --anchor-dir DIR --unseal-key-file FILE [--file PATH] [--profile p16|p8] [--env-file FILE] [--keep]" >&2
    exit 2
}

SEAL="" ANCHOR="" UNSEAL_FILE="" FILE="" PROFILE=p16 ENV_FILE="" KEEP=0
while [ $# -gt 0 ]; do
    case $1 in
        --seal-id) [ $# -ge 2 ] || usage; SEAL=$2; shift 2 ;;
        --anchor-dir) [ $# -ge 2 ] || usage; ANCHOR=$2; shift 2 ;;
        --unseal-key-file) [ $# -ge 2 ] || usage; UNSEAL_FILE=$2; shift 2 ;;
        --file) [ $# -ge 2 ] || usage; FILE=$2; shift 2 ;;
        --profile) [ $# -ge 2 ] || usage; PROFILE=$2; shift 2 ;;
        --env-file) [ $# -ge 2 ] || usage; ENV_FILE=$2; shift 2 ;;
        --keep) KEEP=1; shift ;;
        *) echo "$PROG: đối số không hợp lệ: $1" >&2; usage ;;
    esac
done
[ -n "$SEAL" ] && [ -n "$ANCHOR" ] && [ -n "$UNSEAL_FILE" ] || usage
seal_re='^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'
[[ $SEAL =~ $seal_re ]] || die 2 "--seal-id '$SEAL' không hợp lệ (chữ, số, '.', '_', '-')"
case $PROFILE in p16 | p8) ;; *) die 2 "--profile phải là p16 hoặc p8 (nhận được: $PROFILE)" ;; esac
[ -d "$ANCHOR" ] || die 2 "--anchor-dir $ANCHOR không phải thư mục"
[ -f "$UNSEAL_FILE" ] || die 2 "--unseal-key-file $UNSEAL_FILE không phải tệp"
grep -Eqv '^[[:space:]]*(#|$)' "$UNSEAL_FILE" || die 2 "--unseal-key-file $UNSEAL_FILE không có khóa nào"
[ -z "$FILE" ] || [ -f "$FILE" ] || die 2 "--file $FILE không phải tệp"
case $ENV_FILE in "" | /*) ;; *) ENV_FILE=$PWD/$ENV_FILE ;; esac
case $ANCHOR in /*) ;; *) ANCHOR=$PWD/$ANCHOR ;; esac
case $UNSEAL_FILE in /*) ;; *) UNSEAL_FILE=$PWD/$UNSEAL_FILE ;; esac
case $FILE in "" | /*) ;; *) FILE=$PWD/$FILE ;; esac

need_tools docker openssl tar dxos-witness head
require_passphrase
cd "$REPO"
ENV_FILE=${ENV_FILE:-.env}
check_compose_inputs "$PROFILE" "$ENV_FILE"
[ "$RESTORE_PROJECT" != "$LIVE_PROJECT" ] || die 3 "lỗi nội bộ: project diễn tập trùng project thật"

live_cid=$(find_cid "$LIVE_PROJECT" trust-core-api) || die 3 "docker ps lỗi (daemon không chạy?)"
[ -n "$live_cid" ] || die 3 "trust-core-api của project $LIVE_PROJECT không chạy: không có gì để sao lưu"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/dxos-drill.XXXXXX") || die 3 "không tạo được thư mục tạm"
# shellcheck disable=SC2329  # gọi qua trap EXIT
cleanup() {
    if [ -n "$WORK" ] && [ -d "$WORK" ] && [ "$WORK" != / ]; then rm -rf "$WORK"; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# Bản khôi phục dùng tên miền khác; biến môi trường thắng --env-file của compose, nên restore.sh và mọi lệnh compose
# bên dưới đều thấy restore.localhost mà .env của stack thật không bị đổi.
export DXOS_DOMAIN=$DRILL_DOMAIN

FILE_ARGS=()
SHA=""
if [ -n "$FILE" ]; then
    FILE_ARGS=(--file "$FILE")
    SHA=$(sha256_of "$FILE")
fi

step_fail() {
    echo "$PROG: $*" >&2
    echo "$PROG: diễn tập dừng giữa chừng. Dọn project diễn tập (không đụng project $LIVE_PROJECT):" \
        "docker compose -p $RESTORE_PROJECT down -v" >&2
    exit 4
}

# fetch <container> <tệp ra> <đường dẫn API> [sha256]: <tệp ra> = dòng "T R" rồi JSON.
fetch() {
    local cid=$1 out=$2
    shift 2
    docker exec "$cid" python -c "$PYGET" "$@" > "$out"
}
sth_re='^[0-9]+ [0-9a-f]{64}$'
bundle_path="/verify/v1/seals/$SEAL/bundle"
[ -z "$FILE" ] || bundle_path="/verify/v1/seals/$SEAL:bundle"

# Lấy STH mới nhất và gói của niêm phong ở container $1, đặt <tiền tố>_sth, <tiền tố>_bundle_sth và ghi gói vào $WORK/<tên>.json.
# Trả khác 0 nếu không lấy được hay định dạng lạ.
snapshot() {
    local cid=$1 prefix=$2 name=$3
    fetch "$cid" "$WORK/$name-sth.out" /verify/v1/sth/latest || return 1
    fetch "$cid" "$WORK/$name-bundle.out" "$bundle_path" ${SHA:+"$SHA"} || return 1
    local sth bsth
    sth=$(head -n 1 "$WORK/$name-sth.out")
    bsth=$(head -n 1 "$WORK/$name-bundle.out")
    [[ $sth =~ $sth_re ]] && [[ $bsth =~ $sth_re ]] || return 1
    tail -n +2 "$WORK/$name-bundle.out" > "$WORK/$name.json"
    printf -v "${prefix}_sth" '%s' "$sth"
    printf -v "${prefix}_bundle_sth" '%s' "$bsth"
}

verify_bundle() { # <tệp gói>
    dxos-witness verify-bundle "$1" --anchor-dir "$ANCHOR" ${FILE_ARGS[@]+"${FILE_ARGS[@]}"}
}

# ---- 2. trước khi sao lưu
echo "$PROG: [1/6] ghi STH và gói của niêm phong $SEAL ở stack thật"
pre_sth="" pre_bundle_sth="" post_sth="" post_bundle_sth=""
snapshot "$live_cid" pre before ||
    die 3 "không lấy được STH hoặc gói của niêm phong $SEAL từ stack thật (niêm phong sai mã, chưa ban hành, hay cần --file)"
verify_bundle "$WORK/before.json" ||
    { echo "$PROG: AT-21 KHÔNG ĐẠT: niêm phong $SEAL không qua verify-bundle ở stack thật TRƯỚC khi sao lưu; chọn niêm phong khác" >&2; exit 1; }
echo "$PROG: trước sao lưu: STH mới nhất [tree_size root] = $pre_sth ; STH trong gói = $pre_bundle_sth"

# ---- 3, 4. sao lưu, dọn project diễn tập cũ, khôi phục
echo "$PROG: [2/6] sao lưu"
bash "$REPO/ops/backup.sh" "$WORK/backup" || step_fail "ops/backup.sh hỏng"
bundle=""
for f in "$WORK"/backup/dxos-backup-*.tar.enc; do bundle=$f; done
[ -f "$bundle" ] || step_fail "ops/backup.sh không tạo gói"

echo "$PROG: [3/6] xóa project diễn tập cũ $RESTORE_PROJECT (nếu có) và khôi phục"
compose_for "$RESTORE_PROJECT" "$PROFILE" "$ENV_FILE"
"${COMPOSE[@]}" down -v --remove-orphans || step_fail "không xóa được project $RESTORE_PROJECT cũ"
bash "$REPO/ops/restore.sh" "$bundle" --project "$RESTORE_PROJECT" --profile "$PROFILE" --env-file "$ENV_FILE" ||
    step_fail "ops/restore.sh hỏng"

# ---- 5. dựng phần lõi trên restore.localhost, mở khóa OpenBao
echo "$PROG: [4/6] dựng openbao và seaweedfs, mở khóa OpenBao (DXOS_DOMAIN=$DRILL_DOMAIN)"
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 openbao seaweedfs || step_fail "dựng openbao/seaweedfs hỏng"
bao_cid=$(find_cid "$RESTORE_PROJECT" openbao) || step_fail "docker ps lỗi"
[ -n "$bao_cid" ] || step_fail "không thấy container openbao của project $RESTORE_PROJECT"
while IFS= read -r key || [ -n "$key" ]; do
    key=${key%$'\r'}
    case $key in "" | "#"*) continue ;; esac
    BAO_DXOS_UNSEAL=$key docker exec -e BAO_DXOS_UNSEAL "$bao_cid" sh -c 'bao operator unseal "$BAO_DXOS_UNSEAL" > /dev/null' ||
        step_fail "mở khóa OpenBao hỏng (sai khóa?)"
done < "$UNSEAL_FILE"
unset key
echo "$PROG: [5/6] dựng trust-core-api"
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 trust-core-api || step_fail "dựng trust-core-api hỏng"
api_cid=$(find_cid "$RESTORE_PROJECT" trust-core-api) || step_fail "docker ps lỗi"
[ -n "$api_cid" ] || step_fail "không thấy container trust-core-api của project $RESTORE_PROJECT"

# ---- 6. đối soát
echo "$PROG: [6/6] đối soát"
snapshot "$api_cid" post after || step_fail "không lấy được STH hoặc gói của niêm phong $SEAL từ bản khôi phục"
bad=0
verify_bundle "$WORK/after.json" || { echo "$PROG: verify-bundle KHÔNG đạt trên bản khôi phục" >&2; bad=1; }

compare() { # <nhãn> <trước> <sau>
    local bt br at ar
    read -r bt br <<< "$2"
    read -r at ar <<< "$3"
    if [ "$bt" = "$at" ] && [ "$br" = "$ar" ]; then
        echo "  $1: tree_size $bt, root $br  KHỚP"
    else
        echo "  $1: tree_size $bt -> $at, root $br -> $ar  LỆCH"
        bad=1
    fi
}
echo "So sánh trước (stack thật) và sau (project $RESTORE_PROJECT):"
compare "STH mới nhất" "$pre_sth" "$post_sth"
compare "STH trong gói $SEAL" "$pre_bundle_sth" "$post_bundle_sth"

if [ "$bad" -ne 0 ]; then
    echo "AT-21 KHÔNG ĐẠT."
    echo "Nếu tree_size lệch mà root cùng tiền tố: có thể stack thật đã ghi thêm giữa bước 1 và bước 2; chạy lại lúc yên."
    echo "Project diễn tập còn lại để điều tra. Dọn: docker compose -p $RESTORE_PROJECT down -v"
    exit 1
fi
echo "AT-21 ĐẠT: sau khôi phục, sổ cái giữ nguyên tree_size $(cut -d' ' -f1 <<< "$post_sth") và root $(cut -d' ' -f2 <<< "$post_sth"); niêm phong $SEAL qua verify-bundle trước và sau."
if [ "$KEEP" = 1 ]; then
    echo "$PROG: --keep: giữ project $RESTORE_PROJECT. Dọn: docker compose -p $RESTORE_PROJECT down -v"
else
    "${COMPOSE[@]}" down -v --remove-orphans || echo "$PROG: cảnh báo: không dọn được project $RESTORE_PROJECT; chạy docker compose -p $RESTORE_PROJECT down -v" >&2
fi
