#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Dựng các SPA của workspace npm và gom bản build vào <out_dir> (Plan 03 Task 10). Trong stack, <out_dir> là volume
# apps-static (Caddy phục vụ ở /srv/apps); chạy bằng `make web-build` (ops/web_build_docker.sh, trong container Node).
#
#   sh ops/build_web.sh <out_dir>
#
# - `npm ci` rồi `npm run build --workspaces --if-present`. VITE_ANCHOR_RAW_BASE (nếu đặt trong môi trường) được npm
#   truyền xuống Vite: cổng đối soát build vào đó.
# - Chép đúng DIST_MAP (danh sách cố định) vào <out_dir>/<tên>, ghi <out_dir>/BUILD-INFO.json.
# - Dựng vào <out_dir>.tmp rồi mới thay <out_dir>: bước nào lỗi thì thoát khác 0 và <out_dir> cũ còn nguyên.
#   Nếu <out_dir> là điểm gắn (volume Docker, không đổi tên được) thì sau khi build xong mới xóa nội dung cũ rồi
#   chép bản mới vào (không nguyên tử, nhưng chỉ chạy khi mọi bước build đã thành công).
# - Mã commit lấy từ DXOS_BUILD_COMMIT, nếu không có thì `git rev-parse HEAD` (container không có .git nên
#   ops/web_build_docker.sh truyền biến này).
set -eu

# Danh sách cố định <tên-thư-mục-đích>:<thư mục dist trong repo>. Plan 03 Task 13 thêm so-muon-sach.
DIST_MAP="phong-ho-so:apps/phong-ho-so/web/dist chung-nhan:apps/chung-nhan/web/dist verify:verify-portal/app/dist"

[ $# -eq 1 ] && [ -n "$1" ] || { echo "dùng: sh ops/build_web.sh <out_dir>" >&2; exit 2; }
OUT=$1
while [ "${OUT%/}" != "$OUT" ] && [ "$OUT" != "/" ]; do OUT=${OUT%/}; done
case $OUT in /*) ;; *) OUT=$PWD/$OUT ;; esac
REPO=$(cd "$(dirname "$0")/.." && pwd)
TMP=$OUT.tmp

COMMIT=${DXOS_BUILD_COMMIT:-}
if [ -z "$COMMIT" ]; then
    COMMIT=$(git -C "$REPO" rev-parse HEAD 2>/dev/null) || {
        echo "build_web.sh: không có git để lấy mã commit; đặt DXOS_BUILD_COMMIT=<sha>" >&2
        exit 2
    }
fi
case $COMMIT in
    *[!0-9a-f]*) echo "build_web.sh: mã commit không hợp lệ (chỉ chữ số hex thường): $COMMIT" >&2; exit 2 ;;
esac
if [ "${#COMMIT}" -lt 7 ] || [ "${#COMMIT}" -gt 64 ]; then
    echo "build_web.sh: mã commit phải dài 7-64 ký tự hex: $COMMIT" >&2
    exit 2
fi

rm -rf "$TMP"
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT TERM

cd "$REPO"
npm ci
npm run build --workspaces --if-present

mkdir -p "$TMP"
for entry in $DIST_MAP; do
    name=${entry%%:*}
    dist=${entry#*:}
    [ -d "$REPO/$dist" ] || { echo "build_web.sh: thiếu $dist (workspace chưa có script build?)" >&2; exit 1; }
    cp -R "$REPO/$dist" "$TMP/$name"
done
printf '{"commit": "%s", "built_at": "%s"}\n' "$COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$TMP/BUILD-INFO.json"

# Đến đây mọi bước đã thành công: thay <out_dir>.
if [ ! -e "$OUT" ]; then
    mv "$TMP" "$OUT"
else
    rm -rf "$OUT.old"
    if mv "$OUT" "$OUT.old" 2>/dev/null; then
        if mv "$TMP" "$OUT"; then
            rm -rf "$OUT.old"
        else
            mv "$OUT.old" "$OUT"
            exit 1
        fi
    else
        find "$OUT" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        cp -pR "$TMP/." "$OUT/"
    fi
fi
echo "build_web.sh: đã ghi $OUT (commit $COMMIT)"
