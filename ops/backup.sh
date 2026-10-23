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
# TMPDIR PHẢI nằm ngoài <thư mục ra> (thoát 2 nếu trùng hay nằm trong, kể cả qua liên kết tượng trưng): thư mục tạm còn sót
# sau một lần chết đột ngột mà nằm trong thư mục ra sẽ bị chép ra ngoài máy chủ cùng các gói. Thư mục tạm cũ
# `dxos-backup.*` còn sót trong TMPDIR bị cảnh báo (không tự xóa): chúng chứa dữ liệu chưa mã hóa, hãy kiểm rồi xóa tay.
#
# Mã thoát:
#   0  xong.
#   2  tham số sai (thiếu/thừa đối số, <thư mục ra> là tệp hay trùng tên gói đã có, TMPDIR nằm trong <thư mục ra>).
#   3  thiếu điều kiện hoặc một bước hỏng: thiếu/ngắn .secrets/backup-passphrase, thiếu docker/openssl/tar, một dịch vụ
#      không chạy, pg_dump / tar volume / mã hóa hỏng. Không để lại tệp nào ở <thư mục ra>.
#
# Tính nhất quán: container seaweedfs được `docker pause` đúng trong lúc tar volume của nó (kho đối tượng nhất quán khi
# gặp sự cố; API/worker gọi S3 trong khoảng đó sẽ chậm hay lỗi, nên chạy lúc yên), rồi `docker unpause`; bẫy EXIT bảo đảm
# unpause kể cả khi lỗi hay bị ngắt. Kho OpenBao vẫn được tar khi đang chạy (giới hạn đã biết, docs/runbook-backup.md):
# ops/at21_drill.sh đọc lại khóa công khai từ bản khôi phục để phát hiện bản tar lệch. DB, kho đối tượng và OpenBao
# không cùng một thời điểm: chạy lúc ít ghi nhất.
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

# TMPDIR không được trùng hay nằm trong <thư mục ra>. So đường dẫn thật (bỏ liên kết tượng trưng, ".", ".."). <thư mục ra>
# chưa tồn tại thì chưa thể chứa một TMPDIR đang có.
TMP_BASE=${TMPDIR:-/tmp}
TMP_REAL=$(cd "$TMP_BASE" 2> /dev/null && pwd -P) || die 3 "TMPDIR=$TMP_BASE không phải thư mục"
if [ -d "$OUT" ]; then
    OUT_REAL=$(cd "$OUT" 2> /dev/null && pwd -P) || die 2 "không vào được $OUT"
    case $TMP_REAL/ in
        "$OUT_REAL"/*) die 2 "TMPDIR ($TMP_REAL) nằm trong thư mục ra ($OUT_REAL): thư mục tạm chứa dữ liệu chưa mã hóa sẽ bị chép ra ngoài cùng các gói. Đặt TMPDIR ở nơi khác, ví dụ /var/lib/dxos-backup/tmp (0700)" ;;
    esac
fi
for stale in "$TMP_REAL"/dxos-backup.*; do
    [ ! -d "$stale" ] || echo "$PROG: cảnh báo: $stale là thư mục tạm cũ của một lần sao lưu bị ngắt, chứa dữ liệu chưa mã hóa. Kiểm rồi xóa tay (script không tự xóa)." >&2
done

mkdir -p "$OUT" || die 3 "không tạo được $OUT"

STAGE=$(mktemp -d "$TMP_REAL/dxos-backup.XXXXXX") || die 3 "không tạo được thư mục tạm"
PARTIAL=""
PAUSED=""
# shellcheck disable=SC2329  # gọi qua trap EXIT
cleanup() {
    [ -z "$PAUSED" ] || dk unpause "$PAUSED" > /dev/null 2>&1 || echo "$PROG: CẢNH BÁO: không unpause được $PAUSED; chạy: docker unpause $PAUSED" >&2
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
    dk exec "$cid" pg_dump -Fc -U "$user" -d "$db" > "$STAGE/pg/$svc.dump" || die 3 "pg_dump $svc hỏng"
    [ -s "$STAGE/pg/$svc.dump" ] || die 3 "pg_dump $svc trả về rỗng"
done

echo "$PROG: tar hai volume (SeaweedFS, OpenBao), chỉ đọc"
for target in "${VOLUME_TARGETS[@]}"; do
    IFS=: read -r vol svc path <<< "$target"
    cid=$(find_cid "$LIVE_PROJECT" "$svc" all) || die 3 "docker ps lỗi"
    [ -n "$cid" ] || die 3 "không có container của dịch vụ $svc trong project $LIVE_PROJECT"
    # Chỉ kho đối tượng được dừng (bẫy EXIT unpause nếu script chết giữa chừng). Container đã dừng sẵn thì không cần dừng.
    if [ "$svc" = seaweedfs ] && [ -n "$(find_cid "$LIVE_PROJECT" "$svc")" ]; then
        # Đặt PAUSED TRƯỚC khi dừng: pause có thể đã dừng một phần rồi mới báo lỗi, bẫy EXIT phải unpause được cả khi đó
        # (unpause một container chưa dừng chỉ cảnh báo).
        PAUSED=$cid
        dk pause "$cid" > /dev/null || die 3 "không docker pause được $svc; không tar kho đối tượng khi chưa dừng nó"
    fi
    dk run --rm --network none --volumes-from "$cid:ro" "$BUSYBOX_IMAGE" tar -cf - -C "$path" . \
        > "$STAGE/volumes/$vol.tar" || die 3 "tar volume $vol hỏng"
    if [ -n "$PAUSED" ]; then
        dk unpause "$PAUSED" > /dev/null || die 3 "docker unpause $PAUSED hỏng; chạy ngay: docker unpause $PAUSED"
        PAUSED=""
    fi
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
