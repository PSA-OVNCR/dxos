#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Bộ kiểm đầu-cuối trên Chromium thật (tests/web/live) cho App A, App B và cổng đối soát, chạy trong container
# Playwright cạnh stack dev-lite (Plan 03 Task 10). Chạy tay, KHÔNG nằm trong `make check`.
#
#   make web-live             # hoặc: bash ops/web_live.sh
#
# Cần (xem BUILD.md, mục "Kiểm trên trình duyệt thật"):
# - stack dev-lite đang chạy kèm overlay e2e, đã `make web-build`, App A và App B đã cài và ACTIVE (ops/e2e/install_apps.sh);
# - người dùng dev (realm dev, mật khẩu dev-only-password; DXOS_E2E_PASSWORD để đổi).
# Kết quả ở ${DXOS_WEB_LIVE_DIR:-test-results/web-live}: web-live-junit.xml, shots/*.png, artifacts/ (trace khi lỗi).
# Cách trỏ `localhost` về máy chủ Docker giống ops/e2e/run_e2e.sh; riêng Chromium bỏ qua /etc/hosts cho `localhost`
# nên cấu hình Playwright còn ép bằng --host-resolver-rules (DXOS_GATEWAY_IP).
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash trên Windows không được đổi đường dẫn kiểu /src, /out trong lệnh docker

# Ghim digest bằng `make pin-images` (cần Docker có buildx): dòng dưới đổi thành
# mcr.microsoft.com/playwright:v1.63.0-noble@sha256:<64 hex>.
PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

REPO=$(cd "$(dirname "$0")/.." && pwd)
OUT=${DXOS_WEB_LIVE_DIR:-$REPO/test-results/web-live}

if ! printf '%s' "$PLAYWRIGHT_IMAGE" | grep -Eq '@sha256:[0-9a-f]{64}$'; then
    echo "web_live.sh: PLAYWRIGHT_IMAGE chưa ghim digest ($PLAYWRIGHT_IMAGE)." >&2
    echo "Chạy 'make pin-images' (cần Docker có buildx) rồi commit ops/web_live.sh." >&2
    exit 3
fi
command -v docker >/dev/null || { echo "web_live.sh: không tìm thấy docker" >&2; exit 3; }

mkdir -p "$OUT"
# CA nội bộ của Caddy (dev) để phía Node tin chứng chỉ của https://localhost.
docker compose -p dxos cp caddy:/data/caddy/pki/authorities/local/root.crt "$OUT/caddy-root.crt" || {
    echo "web_live.sh: không lấy được CA của Caddy; stack dev-lite (project dxos) đã chạy chưa?" >&2
    exit 3
}

# Chép nguồn bằng tar nhưng không chép bí mật (.env*, .secrets/, deploy/release.env): npm ci chạy lifecycle script
# của bên thứ ba có mạng. Chặn mặc định mọi tệp .env* (kể cả .env.example: không mã nào trong container đọc nó).
INNER='set -eu
GW=$(getent ahostsv4 host.docker.internal | awk '"'"'NR==1 {print $1}'"'"')
[ -n "$GW" ] || { echo "không phân giải được host.docker.internal"; exit 3; }
grep -v -E "[[:space:]]localhost([[:space:]]|\$)" /etc/hosts > /tmp/hosts || true
echo "$GW localhost admin.localhost" >> /tmp/hosts
cat /tmp/hosts > /etc/hosts
export DXOS_GATEWAY_IP=$GW
mkdir /work
cd /src
tar cf - --exclude=node_modules --exclude=.git --exclude=dist --exclude=.venv --exclude=.superpowers \
    --exclude=__pycache__ --exclude=test-results \
    --exclude=".env*" --exclude=.secrets --exclude=deploy/release.env \
    . | tar xf - -C /work
cd /work
npm i -g npm@11.6.2
# Image Playwright 1.63.0 kèm Node 24, còn package.json đòi Node 22 (engine-strict): chỉ ở container chạy test này
# mới nới kiểm engine; bản dựng SPA (web_build_docker.sh) vẫn dùng Node 22 ghim digest (gặp khi chạy V27 22/10/2026).
npm_config_engine_strict=false npm ci
npx playwright test -c tests/web/live'

docker run --rm --ipc=host --add-host=host.docker.internal:host-gateway \
    -e DXOS_WEB_LIVE=1 -e DXOS_BASE_URL=https://localhost -e DXOS_E2E_PASSWORD \
    -e DXOS_WEB_LIVE_OUT=/out -e DXOS_SHOT_DIR=/out/shots -e NODE_EXTRA_CA_CERTS=/out/caddy-root.crt \
    -v "$REPO":/src:ro -v "$OUT":/out "$PLAYWRIGHT_IMAGE" bash -c "$INNER"
