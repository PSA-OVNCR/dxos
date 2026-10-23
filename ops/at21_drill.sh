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
#                      được khóa công khai. Đọc từ tệp và đưa vào `docker exec` qua biến môi trường (`-e BAO_DXOS_UNSEAL`),
#                      nên KHÔNG nằm trên dòng lệnh docker của máy chủ hay lịch sử shell. Giới hạn: `bao operator unseal`
#                      nhận khóa như một đối số, nên trong vài giây khóa nằm trong argv của tiến trình `bao` TRONG container
#                      `dxos-restore-openbao-*` (giống docs/runbook-openbao.md mục 2). Chưa có cách đưa khóa qua stdin trong
#                      image OpenBao 2.2.0 mà không thêm công cụ (`bao operator unseal -` không đọc stdin), nên chấp nhận.
#   --file             tệp gốc của niêm phong có `require_file: true` (App A): lấy gói bằng POST :bundle với băm của
#                      tệp và đưa tệp cho verify-bundle. Không có thì dùng GET .../bundle (niêm phong `require_file: false`).
#   --keep             giữ project diễn tập sau khi đạt (mặc định: `down -v` project `dxos-restore`).
#
# Các bước (mỗi bước hỏng thì dừng):
#   1. Kiểm tham số và điều kiện (stack `dxos` đang chạy trust-core-api, .secrets/backup-passphrase, .env).
#   2. TRƯỚC khi sao lưu, ở stack thật: ghi STH mới nhất (`/verify/v1/sth/latest`), gói bằng chứng của niêm phong,
#      băm của `/verify/v1/keys` (đi qua OpenBao transit) và các tệp đính kèm của niêm phong đọc được từ SeaweedFS (S3 GET
#      qua `ObjectStore.read_object` của lõi, tự băm lại; có --file thì băm của nó phải nằm trong đó, và niêm phong phải có
#      ít nhất một tệp đính kèm). `dxos-witness verify-bundle` gói đó phải đạt (không thì diễn tập vô nghĩa).
#   3. ops/backup.sh vào thư mục tạm.
#   4. `docker compose -p dxos-restore ... down -v` (xóa project diễn tập CŨ nếu có; chỉ tên cố định này), rồi
#      DXOS_DOMAIN=restore.localhost ops/restore.sh <gói> --project dxos-restore.
#   5. Dựng openbao + seaweedfs, mở khóa OpenBao (rồi `bao status` phải thoát 0: `bao operator unseal` thoát 0 cả khi còn
#      thiếu phần khóa), dựng trust-core-api (cùng image với stack thật). KHÔNG dựng caddy và
#      apisix, nên không tranh cổng 80/443 với stack thật; không dựng Keycloak, Flowable, ClamAV để không nhân đôi RAM
#      (dữ liệu của chúng vẫn được khôi phục vào volume). Mọi lời gọi API đi qua `docker exec ... python` trong container.
#   6. Lấy lại STH mới nhất và gói của cùng niêm phong từ bản khôi phục, `verify-bundle` lần hai, rồi SO `tree_size` và
#      `root_hash` trước/sau (cả STH mới nhất lẫn STH nằm trong gói), băm `/verify/v1/keys` trước/sau (chứng minh kho OpenBao
#      đã khôi phục còn đọc được khóa công khai) và các tệp đính kèm trước/sau (chứng minh kho SeaweedFS đã khôi phục đọc được và
#      băm khớp). Mọi thứ khớp thì ĐẠT. Sau khôi phục, đọc hỏng hay lệch khóa/tệp là KHÔNG ĐẠT (mã 1), không phải lỗi hạ tầng.
#
# Phải chạy lúc stack thật không có ghi nào giữa bước 2 và bước 3 (STH mới sinh ở giữa làm tree_size lệch).
# Không bao giờ chạy lệnh ghi/xóa nào lên project `dxos`: stack thật chỉ được đọc (docker ps, docker exec ... GET).
#
# Mã thoát:
#   0  AT-21 ĐẠT.
#   1  AT-21 KHÔNG ĐẠT: niêm phong không qua verify-bundle (trước hoặc sau khôi phục), tree_size/root lệch, khóa công khai
#      lệch hay không đọc được, tệp đính kèm không đọc được hay lệch sau khôi phục.
#   2  tham số sai.
#   3  thiếu điều kiện trước khi đổi gì (thiếu công cụ, mật khẩu, .env, stack thật không chạy, không lấy được niêm phong).
#   4  một bước hạ tầng hỏng sau khi đã sao lưu (backup, restore, dựng stack, OpenBao vẫn khóa sau khi mở khóa). Chạy lại; project
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

# Băm của /verify/v1/keys (JSON chuẩn hóa), bắt buộc có cả seal-key lẫn sth-key: đường này đi qua OpenBao transit.
PYKEYS='import hashlib,json,sys,urllib.request as u;d=json.loads(u.urlopen("http://127.0.0.1:8000"+sys.argv[1],timeout=30).read());assert d["seal-key"] and d["sth-key"];print(hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest())'
# Đọc tệp đính kèm của niêm phong (payload.attachments của gói) từ SeaweedFS bằng chính ObjectStore của lõi, đối số như PYGET:
# read_object băm lại nội dung, lệch hay thiếu thì lỗi. Có sha256 (đối số 2) và nó nằm trong danh sách thì chỉ đọc tệp đó,
# không thì đọc tối đa 5 tệp đầu. In "<số tệp> <băm>...".
PYOBJ='import json,sys,urllib.request as u;from dxos_core.objects.storage import ObjectStore;from dxos_core.settings import Settings;a=sys.argv;r=u.Request("http://127.0.0.1:8000"+a[1],data=json.dumps({"sha256":a[2]}).encode() if len(a)>2 else None,headers={"Content-Type":"application/json"});al=sorted(json.loads(u.urlopen(r,timeout=30).read())["payload"]["attachments"]);h=[a[2]] if len(a)>2 and a[2] in al else al[:5];o=ObjectStore(Settings());[o.read_object(x) for x in h];print(len(h),*h)'

# fetch <container> <tệp ra> <đường dẫn API> [sha256]: <tệp ra> = dòng "T R" rồi JSON.
fetch() {
    local cid=$1 out=$2
    shift 2
    dk exec "$cid" python -c "$PYGET" "$@" > "$out"
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

keys_re='^[0-9a-f]{64}$'
objects_re='^[1-9][0-9]*( [0-9a-f]{64})+$'
# keys_hash <container>, objects_line <container>: in một dòng; trả khác 0 nếu không đọc được hay định dạng lạ.
keys_hash() {
    local out
    out=$(dk exec "$1" python -c "$PYKEYS" /verify/v1/keys) || return 1
    [[ $out =~ $keys_re ]] || return 1
    printf '%s' "$out"
}
objects_line() {
    local out
    out=$(dk exec "$1" python -c "$PYOBJ" "$bundle_path" ${SHA:+"$SHA"}) || return 1
    [[ $out =~ $objects_re ]] || return 1
    printf '%s' "$out"
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
pre_keys=$(keys_hash "$live_cid") || die 3 "không đọc được /verify/v1/keys từ stack thật (OpenBao khóa?)"
pre_objects=$(objects_line "$live_cid") ||
    die 3 "không đọc được tệp đính kèm của niêm phong $SEAL từ SeaweedFS của stack thật (niêm phong không có tệp, hay kho hỏng)"
[ "${pre_objects%% *}" -ge 1 ] || die 3 "niêm phong $SEAL không có tệp đính kèm nên không thử được kho SeaweedFS; chọn niêm phong có tệp"
[ -z "$SHA" ] || [[ $pre_objects == *" $SHA"* ]] || die 3 "băm của --file không nằm trong tệp đính kèm của niêm phong $SEAL (sai tệp?)"
echo "$PROG: trước sao lưu: STH mới nhất [tree_size root] = $pre_sth ; STH trong gói = $pre_bundle_sth"
echo "$PROG: trước sao lưu: sha256 của /verify/v1/keys = $pre_keys ; tệp đính kèm đọc được = $pre_objects"

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
    BAO_DXOS_UNSEAL=$key dk exec -e BAO_DXOS_UNSEAL "$bao_cid" sh -c 'bao operator unseal "$BAO_DXOS_UNSEAL" > /dev/null' ||
        step_fail "mở khóa OpenBao hỏng (sai khóa?)"
done < "$UNSEAL_FILE"
unset key
# `bao operator unseal` thoát 0 cả khi còn cần thêm phần khóa; `bao status` thoát 0 chỉ khi đã mở khóa (2 nếu còn khóa).
dk exec "$bao_cid" bao status > /dev/null ||
    step_fail "OpenBao vẫn khóa sau khi dùng hết khóa trong $UNSEAL_FILE (thiếu phần khóa Shamir, hoặc sai khóa)"
echo "$PROG: [5/6] dựng trust-core-api"
"${COMPOSE[@]}" up -d --wait --wait-timeout 300 trust-core-api || step_fail "dựng trust-core-api hỏng"
api_cid=$(find_cid "$RESTORE_PROJECT" trust-core-api) || step_fail "docker ps lỗi"
[ -n "$api_cid" ] || step_fail "không thấy container trust-core-api của project $RESTORE_PROJECT"

# ---- 6. đối soát
echo "$PROG: [6/6] đối soát"
# Stack khôi phục đã lên khỏe: từ đây đọc hỏng nghĩa là dữ liệu hay khóa đã khôi phục không dùng được, tức KHÔNG ĐẠT.
bad=0
have_sth=0
if snapshot "$api_cid" post after; then
    have_sth=1
    verify_bundle "$WORK/after.json" || { echo "$PROG: verify-bundle KHÔNG đạt trên bản khôi phục" >&2; bad=1; }
else
    echo "$PROG: không lấy được STH hoặc gói của niêm phong $SEAL từ bản khôi phục" >&2
    bad=1
fi
post_keys="" post_objects=""
post_keys=$(keys_hash "$api_cid") || { echo "$PROG: không đọc được /verify/v1/keys từ bản khôi phục (kho OpenBao đã khôi phục không dùng được?)" >&2; bad=1; }
post_objects=$(objects_line "$api_cid") ||
    { echo "$PROG: không đọc được (hay băm lệch) tệp đính kèm của niêm phong $SEAL từ SeaweedFS đã khôi phục" >&2; bad=1; }

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
if [ "$have_sth" = 1 ]; then
    compare "STH mới nhất" "$pre_sth" "$post_sth"
    compare "STH trong gói $SEAL" "$pre_bundle_sth" "$post_bundle_sth"
fi
same() { # <nhãn> <trước> <sau>
    if [ "$2" = "$3" ]; then
        echo "  $1: $2  KHỚP"
    else
        echo "  $1: $2 -> ${3:-không đọc được}  LỆCH"
        bad=1
    fi
}
same "băm khóa công khai /verify/v1/keys" "$pre_keys" "$post_keys"
same "tệp đính kèm đọc được từ SeaweedFS" "$pre_objects" "$post_objects"

if [ "$bad" -ne 0 ]; then
    echo "AT-21 KHÔNG ĐẠT."
    echo "Nếu tree_size lệch mà root cùng tiền tố: có thể stack thật đã ghi thêm giữa bước 1 và bước 2; chạy lại lúc yên."
    echo "Project diễn tập còn lại để điều tra. Dọn: docker compose -p $RESTORE_PROJECT down -v"
    exit 1
fi
echo "AT-21 ĐẠT: sau khôi phục, sổ cái giữ nguyên tree_size $(cut -d' ' -f1 <<< "$post_sth") và root $(cut -d' ' -f2 <<< "$post_sth"); niêm phong $SEAL qua verify-bundle trước và sau; khóa công khai và tệp đính kèm đọc lại được từ OpenBao và SeaweedFS đã khôi phục."
if [ "$KEEP" = 1 ]; then
    echo "$PROG: --keep: giữ project $RESTORE_PROJECT. Dọn: docker compose -p $RESTORE_PROJECT down -v"
else
    "${COMPOSE[@]}" down -v --remove-orphans || echo "$PROG: cảnh báo: không dọn được project $RESTORE_PROJECT; chạy docker compose -p $RESTORE_PROJECT down -v" >&2
fi
