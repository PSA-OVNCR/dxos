#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Kiểm điều kiện của máy trước khi dựng DX-OS (Plan 04 Task 16, M5, AT-23). Chỉ ĐỌC: không cài gì, không sửa gì, không
# gọi mạng, không đọc .env (nên không có bí mật nào để in). Chạy được từ thư mục bất kỳ:
#
#   ops/doctor.sh [--profile p16|p8|dev-lite] [--web]
#
#   --profile  hồ sơ định dùng, quyết định ngưỡng RAM (mặc định p16).
#   --web      thêm kiểm Node 22 và npm đúng 11.6.2 (chỉ cần khi tự dựng web bằng `make web-check` hay
#              `sh ops/build_web.sh`; `make web-build` dựng trong container nên không cần Node trên máy).
#
# Mã thoát:
#   0  mọi điều kiện đạt (có thể kèm CẢNH BÁO, không chặn).
#   2  tham số sai.
#   3  có ít nhất một điều kiện THIẾU hoặc quá cũ. Tất cả được liệt kê (không dừng ở điều kiện đầu), kèm cách xử lý.
#
# Các điều kiện (nguồn: BUILD.md mục "Yêu cầu", docs/runbook-deploy.md mục 1, docs/capacity.md):
#   Docker Engine >= 24, Docker Compose >= 2.24 (overlay phát hành dùng !reset), Python >= 3.12 và module venv,
#   git, make, RAM đủ cho hồ sơ, cổng 443 trống (hoặc do chính stack dxos giữ), và với --web: Node >= 22 < 23, npm = 11.6.2.
# Ngưỡng RAM [ĐX] của đội, tính theo MemTotal của nhân (thấp hơn số trên nhãn máy): p16 14336 MiB, p8 7000 MiB,
# dev-lite 6000 MiB. Số đo thật của p8: docs/capacity.md.
set -euo pipefail

MIN_DOCKER=24
MIN_COMPOSE=2.24
MIN_PYTHON=3.12
NODE_MAJOR=22
NPM_EXACT=11.6.2

usage() {
    echo "dùng: ops/doctor.sh [--profile p16|p8|dev-lite] [--web]" >&2
    exit 2
}

# version_ge A B: A >= B theo thứ tự phiên bản (sort -V).
version_ge() {
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n 1)" = "$2" ]
}

failures=0
ok() { echo "[ĐẠT] $*"; }
warn() { echo "[CẢNH BÁO] $*"; }
missing() {
    failures=$((failures + 1))
    echo "[THIẾU] $*"
}

# Lấy dãy số phiên bản đầu tiên trong một chuỗi ("Docker version 27.3.1, build x" -> 27.3.1, "v2.29.7" -> 2.29.7).
first_version() {
    printf '%s' "$1" | sed -n 's/^[^0-9]*\([0-9][0-9]*\(\.[0-9][0-9]*\)*\).*$/\1/p' | head -n 1
}

check_docker() {
    local ver
    if ! command -v docker > /dev/null; then
        missing "Docker chưa cài. Cài Docker Engine theo https://docs.docker.com/engine/install/ubuntu/ (BUILD.md, mục \"Máy Ubuntu 24.04 sạch\")."
        missing "Docker Compose: cần Docker trước (gói docker-compose-plugin đi kèm hướng dẫn trên)."
        return
    fi
    if ! ver=$(docker version --format '{{.Server.Version}}' 2> /dev/null) || [ -z "$ver" ]; then
        missing "Docker daemon không trả lời. Chưa chạy (sudo systemctl enable --now docker), hoặc tài khoản chưa thuộc nhóm docker:" \
            "sudo usermod -aG docker \"\$USER\" rồi đăng xuất và đăng nhập lại."
        check_compose
        return
    fi
    ver=$(first_version "$ver")
    if [ -n "$ver" ] && version_ge "$ver" "$MIN_DOCKER"; then
        ok "Docker $ver (cần >= $MIN_DOCKER)"
    else
        missing "Docker ${ver:-không rõ phiên bản} quá cũ (cần >= $MIN_DOCKER). Gỡ bản của distro và cài lại theo https://docs.docker.com/engine/install/ubuntu/"
    fi
    check_compose
}

check_compose() {
    local ver
    if ! ver=$(docker compose version --short 2> /dev/null) || [ -z "$ver" ]; then
        missing "Docker Compose (plugin v2) chưa cài. Cài gói docker-compose-plugin theo https://docs.docker.com/engine/install/ubuntu/"
        return
    fi
    ver=$(first_version "$ver")
    if [ -n "$ver" ] && version_ge "$ver" "$MIN_COMPOSE"; then
        ok "Compose $ver (cần >= $MIN_COMPOSE)"
    else
        missing "Compose ${ver:-không rõ phiên bản} quá cũ (cần >= $MIN_COMPOSE: overlay phát hành dùng !reset, bản cũ sẽ build từ mã nguồn). Cập nhật gói docker-compose-plugin."
    fi
}

check_python() {
    local ver
    if ! command -v python3 > /dev/null; then
        missing "python3 chưa cài (cần >= $MIN_PYTHON). Ubuntu 24.04: sudo apt install python3 python3-venv"
        return
    fi
    ver=$(first_version "$(python3 --version 2> /dev/null || true)")
    if [ -z "$ver" ] || ! version_ge "$ver" "$MIN_PYTHON"; then
        missing "Python ${ver:-không rõ phiên bản} quá cũ (cần >= $MIN_PYTHON). Ubuntu 24.04 có sẵn 3.12; máy khác: cài python3.12."
        return
    fi
    ok "Python $ver (cần >= $MIN_PYTHON)"
    if python3 -c 'import venv, ensurepip' > /dev/null 2>&1; then
        ok "module venv và ensurepip có sẵn"
    else
        missing "thiếu module venv/ensurepip của Python. Ubuntu 24.04: sudo apt install python3-venv"
    fi
}

check_tool() {
    local tool=$1 hint=$2 line
    if line=$("$tool" --version 2> /dev/null | head -n 1) && [ -n "$line" ]; then
        ok "$tool: $line"
    else
        missing "$tool chưa cài. $hint"
    fi
}

check_ram() {
    local profile=$1 need file kb mib
    case $profile in
        p16) need=14336 ;;
        p8) need=7000 ;;
        *) need=6000 ;;
    esac
    # DXOS_DOCTOR_MEMINFO chỉ để test đổi nguồn; mặc định là /proc/meminfo.
    file=${DXOS_DOCTOR_MEMINFO:-/proc/meminfo}
    kb=$(sed -n 's/^MemTotal:[[:space:]]*\([0-9][0-9]*\) kB.*/\1/p' "$file" 2> /dev/null | head -n 1 || true)
    if [ -z "$kb" ]; then
        warn "không đọc được RAM ($file): tự kiểm máy có đủ cho hồ sơ $profile (xem docs/capacity.md). Docker Desktop thì xem RAM cấp cho máy ảo WSL2."
        return
    fi
    mib=$((kb / 1024))
    if [ "$mib" -ge "$need" ]; then
        ok "RAM $mib MiB (hồ sơ $profile cần >= $need MiB)"
    else
        missing "RAM $mib MiB không đủ cho hồ sơ $profile (cần >= $need MiB). Máy 8 GB dùng --profile p8; xem docs/capacity.md."
    fi
}

check_port_443() {
    local listing held
    if ! command -v ss > /dev/null; then
        warn "không có lệnh ss để kiểm cổng 443 (gói iproute2): tự kiểm không có dịch vụ nào đang giữ cổng 443."
        return
    fi
    listing=$(ss -H -ltn 'sport = :443' 2> /dev/null || true)
    if [ -z "$listing" ]; then
        ok "cổng 443 trống"
        return
    fi
    held=""
    if command -v docker > /dev/null; then
        held=$(docker ps --filter label=com.docker.compose.project=dxos --filter publish=443 --format '{{.Names}}' 2> /dev/null || true)
    fi
    if [ -n "$held" ]; then
        ok "cổng 443 đang do stack dxos giữ (đúng dự kiến nếu stack đang chạy)"
    else
        missing "cổng 443 đang bị một tiến trình khác giữ (Caddy của stack cần cổng 80 và 443). Tìm: ss -ltnp 'sport = :443'; dừng nginx/apache nếu có."
    fi
}

check_web() {
    local node_v npm_v major
    if command -v node > /dev/null; then
        node_v=$(node --version 2> /dev/null | head -n 1)
        major=$(printf '%s' "$node_v" | sed -n 's/^v\([0-9][0-9]*\)\..*/\1/p')
        if [ "$major" = "$NODE_MAJOR" ]; then
            ok "Node $node_v (cần $NODE_MAJOR.x)"
        else
            missing "Node $node_v không phải $NODE_MAJOR.x (package.json: >=22 <23). Cài Node 22 LTS (nvm hoặc NodeSource), hoặc bỏ --web và dùng make web-build (Node trong container)."
        fi
    else
        missing "Node chưa cài (cần $NODE_MAJOR.x để dựng web bằng make web-check). Cài Node 22 LTS, hoặc dùng make web-build (Node trong container)."
    fi
    if command -v npm > /dev/null; then
        npm_v=$(npm --version 2> /dev/null | head -n 1)
        if [ "$npm_v" = "$NPM_EXACT" ]; then
            ok "npm $npm_v (cần đúng $NPM_EXACT)"
        else
            missing "npm $npm_v khác $NPM_EXACT (engine-strict bật nên npm ci dừng). Chạy: npm install -g npm@$NPM_EXACT"
        fi
    else
        missing "npm chưa cài (cần đúng $NPM_EXACT). Cài cùng Node rồi: npm install -g npm@$NPM_EXACT"
    fi
}

main() {
    local profile=p16 web=0
    while [ $# -gt 0 ]; do
        case $1 in
            --profile) [ $# -ge 2 ] || usage; profile=$2; shift 2 ;;
            --web) web=1; shift ;;
            *) usage ;;
        esac
    done
    case $profile in p16 | p8 | dev-lite) ;; *) usage ;; esac

    echo "doctor.sh: kiểm điều kiện máy (hồ sơ $profile$([ "$web" = 1 ] && echo ', có dựng web'))"
    check_docker
    check_python
    check_tool git "Ubuntu 24.04: sudo apt install git"
    check_tool make "Ubuntu 24.04: sudo apt install make"
    check_ram "$profile"
    check_port_443
    if [ "$web" = 1 ]; then
        check_web
    else
        echo "[BỎ QUA] Node và npm (không dùng --web; make web-build dựng web trong container)"
    fi

    if [ "$failures" -gt 0 ]; then
        echo "doctor.sh: $failures điều kiện chưa đạt (xem các dòng THIẾU ở trên); sửa rồi chạy lại." >&2
        exit 3
    fi
    echo "doctor.sh: đạt. Bước tiếp theo: BUILD.md, mục \"Máy Ubuntu 24.04 sạch, từng lệnh\"."
}

main "$@"
