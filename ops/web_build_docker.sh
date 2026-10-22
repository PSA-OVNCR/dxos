#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Dựng các SPA (App A, App B, cổng đối soát) trong MỘT container Node dùng một lần rồi ghi vào volume apps-static
# mà Caddy phục vụ ở /srv/apps (Plan 03 Task 10, P3-D7). Không thêm dịch vụ vào compose.
#
#   make web-build            # hoặc: bash ops/web_build_docker.sh
#
# - Chép /src (repo, chỉ đọc) sang /work, bỏ node_modules, .git, dist; `npm i -g npm@11.6.2` (đúng bản của repo);
#   rồi `sh /work/ops/build_web.sh /out`. build_web.sh tự dựng vào /out.tmp và chỉ thay nội dung /out khi mọi bước
#   đã thành công, nên build lỗi KHÔNG làm mất bản đang chạy (vì vậy không xóa /out trước).
# - Mã commit lấy ở máy chủ (container không có .git) và truyền qua DXOS_BUILD_COMMIT.
# - VITE_ANCHOR_RAW_BASE (cổng đối soát build kèm repo neo): lấy từ môi trường, nếu không có thì từ ./.env
#   (ENV_FILE=... để đổi). Phải đi kèm DXOS_ANCHOR_RAW_ORIGIN trong cùng .env (CSP của Caddy).
# - Volume tên cố định dxos_apps-static = volume `apps-static` của dự án compose `dxos` (make up -p dxos).
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash trên Windows không được đổi đường dẫn kiểu /src, /out trong lệnh docker

# Ghim digest bằng `make pin-images` (cần Docker có buildx): dòng dưới đổi thành node:22-bookworm-slim@sha256:<64 hex>.
NODE_IMAGE=node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d
APPS_VOLUME=dxos_apps-static

REPO=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-$REPO/.env}

if ! printf '%s' "$NODE_IMAGE" | grep -Eq '@sha256:[0-9a-f]{64}$'; then
    echo "web_build_docker.sh: NODE_IMAGE chưa ghim digest ($NODE_IMAGE)." >&2
    echo "Chạy 'make pin-images' (cần Docker có buildx) rồi commit ops/web_build_docker.sh." >&2
    exit 3
fi
command -v docker >/dev/null || { echo "web_build_docker.sh: không tìm thấy docker" >&2; exit 3; }

# Đọc KEY=giá trị từ .env mà không `source` (tệp .env không được chạy như mã). Bản cuối thắng; bỏ \r và cặp nháy ngoài.
env_get() {
    [ -f "$ENV_FILE" ] || return 0
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

VITE_ANCHOR_RAW_BASE=${VITE_ANCHOR_RAW_BASE:-$(env_get VITE_ANCHOR_RAW_BASE)}
if [ -n "$VITE_ANCHOR_RAW_BASE" ] && [ -z "${DXOS_ANCHOR_RAW_ORIGIN:-$(env_get DXOS_ANCHOR_RAW_ORIGIN)}" ]; then
    echo "web_build_docker.sh: cảnh báo: có VITE_ANCHOR_RAW_BASE nhưng DXOS_ANCHOR_RAW_ORIGIN trống; CSP của Caddy sẽ chặn" \
         "trình duyệt đọc repo neo." >&2
fi
DXOS_BUILD_COMMIT=${DXOS_BUILD_COMMIT:-$(git -C "$REPO" rev-parse HEAD)}

ENV_ARGS=(-e DXOS_BUILD_COMMIT="$DXOS_BUILD_COMMIT")
[ -z "$VITE_ANCHOR_RAW_BASE" ] || ENV_ARGS+=(-e VITE_ANCHOR_RAW_BASE="$VITE_ANCHOR_RAW_BASE")

# Chạy trong container (sh của Debian): chép nguồn bằng tar, bỏ thư mục sinh ra và thư mục riêng của máy phát triển.
# Không chép bí mật (.env*, .secrets/, deploy/release.env) vào container: npm ci chạy lifecycle script của bên
# thứ ba có mạng. Chặn mặc định mọi tệp .env* (kể cả .env.example: không mã nào trong container đọc nó).
INNER='set -eu
mkdir /work
cd /src
tar cf - --exclude=node_modules --exclude=.git --exclude=dist --exclude=.venv --exclude=.superpowers \
    --exclude=__pycache__ --exclude=test-results \
    --exclude=".env*" --exclude=.secrets --exclude=deploy/release.env \
    . | tar xf - -C /work
npm i -g npm@11.6.2
sh /work/ops/build_web.sh /out'

docker run --rm "${ENV_ARGS[@]}" -v "$REPO":/src:ro -v "$APPS_VOLUME":/out "$NODE_IMAGE" sh -c "$INNER"
echo "web_build_docker.sh: xong. Caddy phục vụ ngay (volume apps-static); HTML luôn được tải lại, assets có băm trong tên."
