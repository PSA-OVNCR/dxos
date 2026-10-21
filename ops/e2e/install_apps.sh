#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Cài ứng dụng Tầng 2 bằng CLI `dxos` (Plan 02 Task 15), duyệt theo bốn mắt (P2-D21): một admin nộp, một admin
# KHÁC duyệt. Thay cho ops/seed_manifests.py (nay chỉ dùng cho test lõi).
#
#   DXOS_SERVER=https://admin.<miền> [DXOS_CA_FILE=<CA của Caddy>] \
#   [DXOS_TOKEN=<token người nộp>] [DXOS_APPROVER_TOKEN=<token người duyệt>] \
#   sh ops/e2e/install_apps.sh [THƯ-MỤC-APP ...]          # mặc định: apps/phong-ho-so apps/chung-nhan
#
# - Không đặt DXOS_TOKEN: CLI dùng token đã lưu của người đang chạy (`dxos login --server "$DXOS_SERVER"`).
# - Có DXOS_APPROVER_TOKEN (E2E: token của admin2): script tự duyệt bằng token đó. Không có: chỉ nộp, rồi in lệnh
#   `dxos app approve` để người duyệt thứ hai tự chạy trên máy của mình (trên VPS là hai thành viên khác nhau).
# - Phiên bản đã ACTIVE thì bỏ qua (chạy lại được); phiên bản đã DISABLED thì dừng với mã 1.
# - Không bao giờ in token. Mã thoát khác 0 của `dxos` (1: API 4xx, 2: mạng/5xx, 3: token) được trả nguyên.
# - DXOS_ALLOW_SELF_APPROVAL không liên quan tới script này và KHÔNG được bật khi lấy minh chứng AT-13.
set -eu

: "${DXOS_SERVER:?đặt DXOS_SERVER=https://admin.<miền>}"
PY=${PYTHON:-python3}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
[ "$#" -gt 0 ] || set -- "$ROOT/apps/phong-ho-so" "$ROOT/apps/chung-nhan"

dx() {
    if [ -n "${DXOS_CA_FILE:-}" ]; then
        dxos --server "$DXOS_SERVER" --ca-file "$DXOS_CA_FILE" "$@"
    else
        dxos --server "$DXOS_SERVER" "$@"
    fi
}

# In "<id> <version>" của manifest.yaml (yaml.safe_load, như CLI).
id_version() {
    "$PY" - "$1/manifest.yaml" <<'PY'
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as f:
    m = yaml.safe_load(f)
print(m["app"]["id"], m["app"]["version"])
PY
}

# Trạng thái của <id> <version> theo `dxos app list --json` (chuỗi rỗng nếu chưa nộp).
status_of() {
    dx --json app list | "$PY" -c '
import json, sys
rows = json.load(sys.stdin)
print(next((r["status"] for r in rows if r["app_id"] == sys.argv[1] and r["version"] == sys.argv[2]), ""))
' "$1" "$2"
}

pending=""
for dir in "$@"; do
    iv=$(id_version "$dir")
    app=${iv% *} ver=${iv#* }
    st=$(status_of "$app" "$ver")
    case "$st" in
        ACTIVE)   echo "== $app $ver đã ACTIVE, bỏ qua"; continue ;;
        DISABLED) echo "== $app $ver đã DISABLED: tăng version trong manifest rồi nộp lại" >&2; exit 1 ;;
    esac
    echo "== nộp $app $ver từ $dir"
    dx app install "$dir"
    if [ -n "${DXOS_APPROVER_TOKEN:-}" ]; then
        echo "== duyệt $app $ver (token người duyệt thứ hai)"
        # Subshell: token người duyệt chỉ dùng cho đúng lệnh này, không lọt sang lần nộp app kế tiếp.
        (DXOS_TOKEN=$DXOS_APPROVER_TOKEN; export DXOS_TOKEN; dx app approve "$app" "$ver")
        st=$(status_of "$app" "$ver")
        [ "$st" = "ACTIVE" ] || { echo "== $app $ver chưa ACTIVE sau khi duyệt (trạng thái: $st)" >&2; exit 1; }
        echo "== $app $ver ACTIVE"
    else
        pending="$pending $app@$ver"
        echo "== CHƯA DUYỆT: người duyệt thứ hai (khác người nộp) chạy:"
        echo "     dxos --server $DXOS_SERVER app diff $app $ver"
        echo "     dxos --server $DXOS_SERVER app approve $app $ver"
    fi
done
[ -z "$pending" ] || echo "== còn chờ duyệt:$pending"
