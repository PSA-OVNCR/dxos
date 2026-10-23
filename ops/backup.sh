#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Sao lưu mã hóa của stack DX-OS (Plan 04 Task 12, spec S4, P4-D9). Chạy ở máy chủ có stack `dxos` đang chạy:
#
#   ops/backup.sh <thư mục ra>
#
# Tạo trong <thư mục ra>:
#   dxos-backup-<UTC>.tar.enc      gói đã mã hóa: openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt
#   dxos-backup-<UTC>.tar.enc.sha256   băm sha256 của gói (dạng `sha256sum`), restore.sh kiểm trước khi giải mã
# Mật khẩu ở .secrets/backup-passphrase (chỉ đọc bằng `-pass file:`, không bao giờ nằm trên dòng lệnh hay in ra).
# Gói không có xác thực MAC riêng (P4-D9): sha256 ghi kèm chỉ chống hỏng/nhầm, không chống kẻ sửa cả hai tệp.
#
# Nội dung gói (bảy thành viên, xem BUNDLE_MEMBERS trong ops/backup_lib.sh):
#   pg/core-db.dump, pg/kc-db.dump, pg/flowable-db.dump   `pg_dump -Fc` qua `docker exec` (không cần mật khẩu DB)
#   volumes/seaweedfs-data.tar, volumes/openbao-data.tar  tar volume qua container busybox đã ghim digest,
#                                                          `--volumes-from <container>:ro` (chỉ đọc), không mạng
#   MANIFEST.txt, SHA256SUMS                               định dạng, thời điểm, băm từng thành viên
# Dữ liệu không nằm trong gói: .env, unseal key của OpenBao, .secrets/ (giữ riêng, xem docs/runbook-backup.md).
#
# Tệp chưa mã hóa KHÔNG BAO GIỜ nằm ở <thư mục ra>: các thành viên được gom vào một thư mục tạm riêng (mktemp -d,
# quyền 0700, xóa khi thoát, kể cả khi lỗi hay bị ngắt), tar chảy thẳng qua đường ống vào openssl, ghi ra
# <tên>.partial rồi mới đổi tên. Đặt TMPDIR nếu /tmp nhỏ: thư mục tạm chứa bản sao đầy đủ chưa mã hóa của dữ liệu.
#
# Mã thoát:
#   0  xong.
#   2  tham số sai (thiếu/thừa đối số, <thư mục ra> là tệp hay trùng tên gói đã có).
#   3  thiếu điều kiện hoặc một bước hỏng: thiếu/ngắn .secrets/backup-passphrase, thiếu docker/openssl/tar, một dịch vụ
#      không chạy, pg_dump / tar volume / mã hóa hỏng. Không để lại tệp nào ở <thư mục ra>.
#
# SeaweedFS và OpenBao được tar khi đang chạy: chạy lúc ít ghi nhất, hoặc dừng trust-core-worker/api trước (runbook).
set -euo pipefail
umask 077

PROG=backup.sh
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=ops/backup_lib.sh
. "$REPO/ops/backup_lib.sh"

usage() {
    echo "dùng: ops/backup.sh <thư mục ra>" >&2
    exit 2
}

[ $# -eq 1 ] && [ -n "$1" ] || usage
case $1 in -*) echo "$PROG: tùy chọn không hợp lệ: $1" >&2; usage ;; esac
OUT=$1
[ ! -e "$OUT" ] || [ -d "$OUT" ] || die 2 "$OUT đã tồn tại và không phải thư mục"

need_tools docker openssl tar head
require_passphrase
mkdir -p "$OUT" || die 3 "không tạo được $OUT"

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/dxos-backup.XXXXXX") || die 3 "không tạo được thư mục tạm"
PARTIAL=""
# shellcheck disable=SC2329  # gọi qua trap EXIT
cleanup() {
    [ -z "$PARTIAL" ] || rm -f "$PARTIAL"
    if [ -n "$STAGE" ] && [ -d "$STAGE" ] && [ "$STAGE" != / ]; then rm -rf "$STAGE"; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
mkdir "$STAGE/pg" "$STAGE/volumes"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FINAL=$OUT/dxos-backup-$STAMP.tar.enc
[ ! -e "$FINAL" ] || die 2 "$FINAL đã tồn tại (chờ một giây rồi chạy lại)"

echo "$PROG: pg_dump ba cơ sở dữ liệu của project $LIVE_PROJECT"
for target in "${PG_TARGETS[@]}"; do
    IFS=: read -r svc user db <<< "$target"
    cid=$(find_cid "$LIVE_PROJECT" "$svc") || die 3 "docker ps lỗi"
    [ -n "$cid" ] || die 3 "dịch vụ $svc của project $LIVE_PROJECT không chạy; chạy docker compose -p $LIVE_PROJECT ps"
    docker exec "$cid" pg_dump -Fc -U "$user" -d "$db" > "$STAGE/pg/$svc.dump" || die 3 "pg_dump $svc hỏng"
    [ -s "$STAGE/pg/$svc.dump" ] || die 3 "pg_dump $svc trả về rỗng"
done

echo "$PROG: tar hai volume (SeaweedFS, OpenBao), chỉ đọc"
for target in "${VOLUME_TARGETS[@]}"; do
    IFS=: read -r vol svc path <<< "$target"
    cid=$(find_cid "$LIVE_PROJECT" "$svc" all) || die 3 "docker ps lỗi"
    [ -n "$cid" ] || die 3 "không có container của dịch vụ $svc trong project $LIVE_PROJECT"
    docker run --rm --network none --volumes-from "$cid:ro" "$BUSYBOX_IMAGE" tar -cf - -C "$path" . \
        > "$STAGE/volumes/$vol.tar" || die 3 "tar volume $vol hỏng"
    [ -s "$STAGE/volumes/$vol.tar" ] || die 3 "tar volume $vol trả về rỗng"
done

{
    for member in "${DATA_MEMBERS[@]}"; do
        printf '%s  %s\n' "$(sha256_of "$STAGE/$member")" "$member"
    done
} > "$STAGE/SHA256SUMS"
printf 'format=%s\ncreated_utc=%s\nsource_project=%s\nmembers=%s\n' \
    "$BACKUP_FORMAT" "$STAMP" "$LIVE_PROJECT" "${#BUNDLE_MEMBERS[@]}" > "$STAGE/MANIFEST.txt"

echo "$PROG: mã hóa (AES-256-CBC, PBKDF2 600000 vòng)"
PARTIAL=$FINAL.partial
tar -C "$STAGE" -cf - "${BUNDLE_MEMBERS[@]}" |
    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:"$PASS_FILE" -out "$PARTIAL" ||
    die 3 "mã hóa hỏng"
mv "$PARTIAL" "$FINAL" || die 3 "không đổi tên được gói"
PARTIAL=""
printf '%s  %s\n' "$(sha256_of "$FINAL")" "$(basename "$FINAL")" > "$FINAL.sha256"

echo "$PROG: đã ghi $FINAL"
echo "$PROG: sha256 $(cut -d' ' -f1 "$FINAL.sha256")"
