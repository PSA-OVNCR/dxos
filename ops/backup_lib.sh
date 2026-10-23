#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Hằng số và hàm dùng chung của ops/backup.sh, ops/restore.sh, ops/at21_drill.sh (Plan 04 Task 12, S4, P4-D9).
# Chỉ để `source`, không chạy trực tiếp. Bên gọi đặt PROG (tên script, dùng trong thông báo) và REPO (gốc repo) trước.

# shellcheck disable=SC2034  # hằng số được các script `source` tệp này dùng

# Windows (Git Bash) không được đổi đường dẫn kiểu /data trong đối số của docker. Biến chỉ đặt cho riêng lệnh docker
# (hàm dk), không export cho cả script: openssl, tar, dxos-witness vẫn nhận đường dẫn như thường.
dk() {
    MSYS_NO_PATHCONV=1 docker "$@"
}

# Image busybox dùng để tar volume. Cùng ref với net-probe-app trong deploy/compose.yaml; ops/pin_images.py
# quét dòng này (biến *_IMAGE= trong ops/*.sh) nên `make pin-images` giữ nó ghim. Đây là NƠI DUY NHẤT định nghĩa.
BUSYBOX_IMAGE=busybox:1.37@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e
LIVE_PROJECT=dxos
RESTORE_PROJECT=dxos-restore
BACKUP_FORMAT=dxos-backup/1
PASSPHRASE_REL=.secrets/backup-passphrase
MIN_PASSPHRASE_CHARS=16

# <dịch vụ>:<người dùng>:<cơ sở dữ liệu> (khớp deploy/compose.yaml; mọi DB là PostgreSQL 17, socket nội bộ tin cậy).
PG_TARGETS=("core-db:dxos_owner:dxos" "kc-db:keycloak:keycloak" "flowable-db:flowable:flowable")
# <tên volume trong compose>:<dịch vụ giữ volume>:<đường dẫn mount trong container đó>
VOLUME_TARGETS=("seaweedfs-data:seaweedfs:/data" "openbao-data:openbao:/openbao/file")
# Đúng bảy thành viên của gói, theo thứ tự ghi vào tar. Restore từ chối gói có thành viên khác hay thiếu.
BUNDLE_MEMBERS=(MANIFEST.txt SHA256SUMS pg/core-db.dump pg/kc-db.dump pg/flowable-db.dump
    volumes/seaweedfs-data.tar volumes/openbao-data.tar)
# Thành viên có băm trong SHA256SUMS (mọi thành viên trừ hai tệp mô tả).
DATA_MEMBERS=(pg/core-db.dump pg/kc-db.dump pg/flowable-db.dump volumes/seaweedfs-data.tar volumes/openbao-data.tar)

die() {
    local rc=$1
    shift
    echo "$PROG: $*" >&2
    exit "$rc"
}

need_tools() {
    local tool
    for tool in "$@"; do
        command -v "$tool" > /dev/null || die 3 "không tìm thấy $tool"
    done
}

sha256_of() {
    if command -v sha256sum > /dev/null; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# Đặt PASS_FILE; thoát 3 khi thiếu, rỗng hay ngắn. Không bao giờ in nội dung. openssl -pass file: chỉ đọc DÒNG ĐẦU.
require_passphrase() {
    PASS_FILE=$REPO/$PASSPHRASE_REL
    [ -f "$PASS_FILE" ] || die 3 "thiếu $PASSPHRASE_REL (tạo: openssl rand -base64 32 > $PASSPHRASE_REL && chmod 600 $PASSPHRASE_REL)"
    local first
    first=$(head -n 1 "$PASS_FILE") || die 3 "không đọc được $PASSPHRASE_REL"
    # openssl -pass file: giữ nguyên ký tự CR cuối dòng, nên CRLF làm mật khẩu khác với những gì người dùng gõ: từ chối.
    case $first in *$'\r'*) die 3 "$PASSPHRASE_REL có CRLF (lưu bằng trình soạn thảo Windows?); lưu lại với dấu xuống dòng LF" ;; esac
    [ "${#first}" -ge "$MIN_PASSPHRASE_CHARS" ] ||
        die 3 "dòng đầu của $PASSPHRASE_REL phải dài ít nhất $MIN_PASSPHRASE_CHARS ký tự (hiện ${#first})"
    if [ -n "$(find "$PASS_FILE" -perm /077 2> /dev/null)" ]; then
        echo "$PROG: cảnh báo: $PASSPHRASE_REL cho nhóm/người khác đọc; chạy chmod 600" >&2
    fi
}

# Container đầu tiên của dịch vụ trong project (nhãn compose). $3 = all: kể cả container đã dừng.
find_cid() {
    local flag=-q
    [ "${3:-}" != all ] || flag=-aq
    dk ps "$flag" --filter "label=com.docker.compose.project=$1" --filter "label=com.docker.compose.service=$2" |
        head -n 1
}

# Kiểm SHA256SUMS trong thư mục $1: đúng năm thành viên dữ liệu, mỗi băm khớp. Trả khác 0 nếu không.
sums_ok() {
    local dir=$1 lines member want
    lines=$(wc -l < "$dir/SHA256SUMS")
    [ "$lines" -eq "${#DATA_MEMBERS[@]}" ] || return 1
    for member in "${DATA_MEMBERS[@]}"; do
        want=$(sed -n "s|^\([0-9a-f]\{64\}\)  $member\$|\1|p" "$dir/SHA256SUMS")
        [ -n "$want" ] && [ -f "$dir/$member" ] && [ "$(sha256_of "$dir/$member")" = "$want" ] || return 1
    done
}

# Dựng mảng COMPOSE cho một project: `docker compose -p <project> --env-file ... -f ...` (đường dẫn tương đối nên
# bên gọi phải đã `cd "$REPO"`). Dùng overlay phát hành khi VPS đã triển khai bằng ops/deploy.sh (deploy/release.env).
# Dùng: compose_for <project> <profile> <env_file>
compose_for() {
    COMPOSE=(dk compose -p "$1" --env-file "$3")
    [ ! -f deploy/release.env ] || COMPOSE+=(--env-file deploy/release.env)
    COMPOSE+=(-f deploy/compose.yaml -f "deploy/compose.$2.yaml")
    [ ! -f deploy/release.env ] || COMPOSE+=(-f deploy/compose.release.yaml)
}

# Kiểm .env và các tệp compose của hồ sơ tồn tại; thoát 3 nếu không. Dùng: check_compose_inputs <profile> <env_file>
check_compose_inputs() {
    [ -f "$2" ] || die 3 "không có tệp env $2 (sao từ .env.example)"
    [ -f deploy/compose.yaml ] && [ -f "deploy/compose.$1.yaml" ] || die 3 "thiếu deploy/compose.yaml hoặc deploy/compose.$1.yaml"
}
