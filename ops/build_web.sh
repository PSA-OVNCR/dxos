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
# - Từ chối (mã 2) khi <out_dir> có thành phần "." hoặc ".." (trừ "." trần), là /, repo, thư mục cha của repo, $HOME,
#   một tệp, thư mục không đọc được, hay thư mục không rỗng không có BUILD-INFO.json: bước thay <out_dir> xóa nội dung cũ.
# - Dựng vào <out_dir>.tmp rồi mới thay <out_dir>: bước nào lỗi thì thoát khác 0 và <out_dir> cũ còn nguyên.
#   Nếu <out_dir> là điểm gắn (volume Docker, không đổi tên được) thì sau khi build xong mới xóa nội dung cũ rồi
#   chép bản mới vào (không nguyên tử, nhưng chỉ chạy khi mọi bước build đã thành công).
# - Mã commit lấy từ DXOS_BUILD_COMMIT, nếu không có thì `git rev-parse HEAD` (container không có .git nên
#   ops/web_build_docker.sh truyền biến này).
set -eu

# Danh sách cố định <tên-thư-mục-đích>:<thư mục dist trong repo> (so-muon-sach: ví dụ của hướng dẫn, Plan 03 Task 13;
# admin-ui: trang quản trị web, Caddy phát ở /ui/ trên host admin, Plan 04 Task 10).
DIST_MAP="phong-ho-so:apps/phong-ho-so/web/dist chung-nhan:apps/chung-nhan/web/dist so-muon-sach:examples/so-muon-sach/web/dist verify:verify-portal/app/dist admin-ui:admin-ui/dist"

[ $# -eq 1 ] && [ -n "$1" ] || { echo "dùng: sh ops/build_web.sh <out_dir>" >&2; exit 2; }
OUT=$1
refuse() { echo "build_web.sh: từ chối <out_dir> $OUT: $*" >&2; exit 2; }
# Thành phần "." hoặc ".." bị từ chối ngay trên tham số, trước mọi chuẩn hóa: khi OUT và thư mục cha chưa tồn tại thì
# không chuẩn hóa được, `mkdir -p OUT.tmp` tạo thành phần còn thiếu và OUT (ví dụ `../nope/..`) trỏ về một thư mục có
# thật để bước thay xóa. Riêng "." trần (cả "./") được nhận: luôn chuẩn hóa được, các quy tắc bên dưới quyết định.
bare=$OUT
while [ "${bare%/}" != "$bare" ]; do bare=${bare%/}; done
if [ "$bare" != . ]; then
    case /$OUT/ in */./* | */../*) refuse 'có thành phần "." hoặc ".."; ghi đường dẫn không có "." / ".."' ;; esac
fi
while [ "${OUT%/}" != "$OUT" ] && [ "$OUT" != "/" ]; do OUT=${OUT%/}; done
case $OUT in /*) ;; *) OUT=$PWD/$OUT ;; esac
unset CDPATH
canon_dir() { (cd "$1" 2>/dev/null && pwd -P); }
REPO=$(canon_dir "$(dirname "$0")/..")

# Đưa OUT về đường dẫn thật (bỏ ".", "..", liên kết tượng trưng) để guard bên dưới so được với REPO và HOME.
if [ -d "$OUT" ]; then
    OUT=$(canon_dir "$OUT") || refuse "không vào được thư mục"
elif parent=$(canon_dir "$(dirname "$OUT")"); then
    OUT=${parent%/}/$(basename "$OUT")
fi
# Guard: bước thay <out_dir> ở cuối xóa nội dung cũ, nên không bao giờ nhận /, repo, thư mục cha của repo, $HOME,
# tệp thường, hay thư mục không rỗng mà không phải bản build trước (không có BUILD-INFO.json). Volume apps-static
# (điểm gắn /out trong container) rỗng ở lần đầu và có BUILD-INFO.json từ lần sau, nên vẫn qua.
[ "$OUT" != / ] || refuse "là thư mục gốc /"
case $REPO/ in "$OUT"/*) refuse "là repo hoặc thư mục cha của repo ($REPO)" ;; esac
if HOME_DIR=$(canon_dir "${HOME:-/nonexistent}") && [ "$OUT" = "$HOME_DIR" ]; then refuse "là \$HOME"; fi
if [ -e "$OUT" ] || [ -L "$OUT" ]; then
    [ -d "$OUT" ] || refuse "đã tồn tại và không phải thư mục"
    listing=$(ls -A "$OUT" 2>/dev/null) || refuse "không đọc được nội dung thư mục"
    if [ -n "$listing" ] && [ ! -f "$OUT/BUILD-INFO.json" ]; then
        refuse "thư mục không rỗng và không có BUILD-INFO.json (không phải bản build trước của script này)"
    fi
fi
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
