#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Checklist 60 phút trước giờ demo (Plan 04 Task 16, M5; Plan 00 mục 10, spec 16.4, docs/runbook-openbao.md mục 5). Chạy ở
# máy sẽ demo (laptop p8 hoặc VPS), từ thư mục bất kỳ trong repo:
#
#   ops/demo_preflight.sh [--strict] [--skip-network]
#
#   --strict        CẢNH BÁO cũng làm thoát 1 (dùng trong lần tập cuối).
#   --skip-network  bỏ kiểm đường ra Internet (máy cố ý ngoại tuyến).
#
# Chỉ ĐỌC: không mở khóa OpenBao, không neo, không nạp dữ liệu, không ghi gì. Không in bí mật (.env chỉ được đọc
# DXOS_DOMAIN, DXOS_ADMIN_HOST, DXOS_ANCHOR_REMOTE và không in giá trị nào khác). Chạy hết mọi mục rồi mới kết luận.
#
# Mã thoát:
#   0  không có mục LỖI (có thể có CẢNH BÁO; với --strict thì cũng không được có CẢNH BÁO).
#   1  có ít nhất một mục LỖI. OpenBao đang khóa thì in lệnh mở khóa trong docs/runbook-openbao.md (script không tự chạy nó).
#   2  tham số sai, thiếu .env / DXOS_DOMAIN hợp lệ, thiếu docker hoặc curl.
#
# Các mục:
#   1. OpenBao đã mở khóa (`bao status`).
#   2. Mọi container của project dxos khỏe (chạy, không unhealthy / đang khởi động; container dùng một lần phải thoát 0)
#      và có caddy, trust-core-api.
#   3. /readyz của trust-core-api trả 200; https://$DXOS_DOMAIN/verify/v1/keys có đủ seal-key và sth-key.
#   4. STH mới nhất đã neo: so cỡ STH (/verify/v1/sth/latest) với cỡ lớn nhất trong bảng anchors (CẢNH BÁO nếu chưa).
#   5. Mạng ra github.com (nơi worker đẩy STH; CẢNH BÁO nếu không tới được).
#   6. Dữ liệu demo: App A có >= 3 văn bản "[DEMO] ..." (LỖI nếu thiếu); App B có dữ liệu trước khi cài trên sân khấu là
#      CẢNH BÁO (bước cài sẽ thành giả, xem demo/README.md "Thứ tự khi diễn thật").
# Sau cùng in danh sách việc kiểm tay mà script không làm được.
set -euo pipefail

usage() {
    echo "dùng: ops/demo_preflight.sh [--strict] [--skip-network]" >&2
    exit 2
}

fails=0
warns=0
ok() { echo "[ĐẠT] $*"; }
warn() {
    warns=$((warns + 1))
    echo "[CẢNH BÁO] $*"
}
fail() {
    fails=$((fails + 1))
    echo "[LỖI] $*"
}

main() {
    local strict=0 skip_net=0
    while [ $# -gt 0 ]; do
        case $1 in
            --strict) strict=1; shift ;;
            --skip-network) skip_net=1; shift ;;
            *) usage ;;
        esac
    done

    local repo env_file
    repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    cd "$repo"
    env_file=.env
    [ -f "$env_file" ] || { echo "demo_preflight.sh: thiếu .env ở $repo (sao từ .env.example)" >&2; exit 2; }
    local tool
    for tool in docker curl; do
        command -v "$tool" > /dev/null || { echo "demo_preflight.sh: không tìm thấy $tool" >&2; exit 2; }
    done

    # Đọc KEY=giá trị từ .env mà không `source` (cùng cách với ops/deploy.sh). Bản cuối thắng; bỏ \r và cặp nháy ngoài.
    env_get() {
        sed -n "s/^$1=//p" "$env_file" | tail -n 1 | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
    }
    local domain admin_host anchor_remote
    domain=$(env_get DXOS_DOMAIN)
    if ! [[ $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]+)?$ ]]; then
        echo "demo_preflight.sh: .env phải có DXOS_DOMAIN hợp lệ (tên miền, có thể kèm cổng)" >&2
        exit 2
    fi
    admin_host=$(env_get DXOS_ADMIN_HOST)
    anchor_remote=$(env_get DXOS_ANCHOR_REMOTE)

    # Chỉ bỏ xác minh TLS (-k) với localhost/*.localhost (Caddy tự ký); tên miền thật phải có chứng chỉ hợp lệ.
    local tls=-fsS host=${domain%%:*}
    case $host in localhost | *.localhost) tls=-fsSk ;; esac
    local dc=(docker compose -p dxos)

    echo "demo_preflight.sh: checklist 60 phút trước demo ($domain)"

    # ---- 1. OpenBao
    local bao rc=0
    bao=$("${dc[@]}" exec -T openbao bao status -format=json 2> /dev/null) || rc=$?
    if [[ $bao =~ \"sealed\":[[:space:]]*true ]]; then
        fail "OpenBao đang KHÓA: niêm phong và STH bị từ chối (fail-closed). Script này không tự mở khóa. Mở khóa, gõ unseal key khi được hỏi (không gõ lên dòng lệnh):"
        echo
        echo "    docker compose -p dxos exec openbao bao operator unseal"
        echo
        echo "      rồi kiểm: docker compose -p dxos exec openbao bao status   (phải thấy Sealed: false). Chi tiết: docs/runbook-openbao.md, mục 2."
    elif [[ $bao =~ \"sealed\":[[:space:]]*false ]]; then
        ok "OpenBao đã mở khóa"
    else
        fail "OpenBao: không đọc được trạng thái (container chưa chạy hay chưa khởi tạo? mã $rc). Xem docs/runbook-openbao.md."
    fi

    # ---- 2. Container
    local ps_out name status bad=0 total=0 has_caddy=0 has_core=0 bad_names=""
    ps_out=$(docker ps -a --filter label=com.docker.compose.project=dxos --format '{{.Names}}|{{.Status}}' 2> /dev/null) || ps_out=""
    while IFS='|' read -r name status; do
        [ -n "$name" ] || continue
        total=$((total + 1))
        case $name in *-caddy-*) has_caddy=1 ;; *-trust-core-api-*) has_core=1 ;; esac
        case $status in
            Exited\ \(0\)*) ;;                                           # container dùng một lần đã xong
            *"(unhealthy)"* | *"(health: starting)"* | *"(Paused)"*) bad=$((bad + 1)); bad_names="$bad_names $name" ;;
            Up*) ;;
            *) bad=$((bad + 1)); bad_names="$bad_names $name" ;;
        esac
    done <<< "$ps_out"
    if [ "$total" -eq 0 ]; then
        fail "container: không có container nào của project dxos (stack chưa chạy? make up PROFILE=p8)"
    elif [ "$bad" -gt 0 ]; then
        fail "container không khỏe:$bad_names (xem: docker compose -p dxos ps; docker compose -p dxos logs --tail=100 <dịch vụ>)"
    elif [ "$has_caddy" -eq 0 ] || [ "$has_core" -eq 0 ]; then
        fail "container: thiếu caddy hoặc trust-core-api trong project dxos ($total container đang có)"
    else
        ok "container: $total container của project dxos đều khỏe (có caddy, trust-core-api)"
    fi

    # ---- 3. readyz và khóa công khai
    local ready
    if ready=$("${dc[@]}" exec -T trust-core-api python -c \
        "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status)" 2> /dev/null) \
        && [ "$(printf '%s' "$ready" | tr -d '\r\n ')" = 200 ]; then
        ok "/readyz của trust-core-api trả 200"
    else
        fail "/readyz của trust-core-api không trả 200 (xem docker compose -p dxos logs trust-core-api)"
    fi
    local keys
    if keys=$(curl "$tls" --max-time 15 "https://$domain/verify/v1/keys" 2> /dev/null) \
        && [[ $keys == *'"seal-key"'* ]] && [[ $keys == *'"sth-key"'* ]]; then
        ok "khóa công khai (seal-key, sth-key) có ở https://$domain/verify/v1/keys"
    else
        fail "khóa công khai: https://$domain/verify/v1/keys không trả đủ seal-key và sth-key (OpenBao khóa hay lõi chưa sẵn sàng?)"
    fi

    # ---- 4. STH mới nhất đã neo
    local sth size anchored
    sth=$(curl "$tls" --max-time 15 "https://$domain/verify/v1/sth/latest" 2> /dev/null) || sth=""
    size=$(printf '%s' "$sth" | sed -n 's/.*"tree_size": *\([0-9][0-9]*\).*/\1/p' | head -n 1)
    if [ -z "$size" ]; then
        warn "neo: chưa có STH nào (hoặc /verify/v1/sth/latest không trả): chạy dxos anchor run để lập STH rồi neo, sau đó chạy lại."
    elif [ -z "$anchor_remote" ]; then
        warn "neo: STH mới nhất cỡ $size nhưng việc neo đang TẮT (DXOS_ANCHOR_REMOTE rỗng trong .env, docs/runbook-anchor.md mục 3)."
    else
        anchored=$("${dc[@]}" exec -T core-db psql -U dxos_owner -d dxos -Atc \
            "SELECT coalesce(max(tree_size), 0) FROM anchors" 2> /dev/null | tr -d '\r\n ') || anchored=""
        if ! [[ $anchored =~ ^[0-9]+$ ]]; then
            warn "neo: không đọc được bảng anchors từ core-db; kiểm tay bằng dxos ledger status."
        elif [ "$anchored" -ge "$size" ]; then
            ok "STH mới nhất (cỡ $size) đã neo (neo gần nhất: cỡ $anchored)"
        else
            warn "STH mới nhất (cỡ $size) CHƯA neo (neo gần nhất: cỡ $anchored). Chạy dxos --server https://${admin_host:-<DXOS_ADMIN_HOST>} anchor run, chờ việc neo xong, rồi chạy lại."
        fi
    fi

    # ---- 5. Mạng
    if [ "$skip_net" -eq 1 ]; then
        echo "[BỎ QUA] mạng (--skip-network)"
    elif curl -fsS --max-time 8 -o /dev/null https://github.com > /dev/null 2>&1; then
        ok "mạng: tới được https://github.com (nơi worker đẩy STH và khán giả xem repo neo)"
    else
        warn "mạng: không tới được https://github.com. Việc neo STH và phần xem repo neo của demo sẽ không chạy; chuẩn bị ảnh chụp dự phòng."
    fi

    # ---- 6. Dữ liệu demo
    local rows a_count b_count
    if rows=$("${dc[@]}" exec -T core-db psql -U dxos_owner -d dxos -At -F ' ' -c \
        "SELECT app_id, count(*) FROM records WHERE data::text LIKE '%[DEMO] %' GROUP BY app_id ORDER BY app_id" 2> /dev/null); then
        a_count=$(printf '%s\n' "$rows" | awk '$1 == "phong-ho-so" { print $2 }' | head -n 1)
        b_count=$(printf '%s\n' "$rows" | awk '$1 == "chung-nhan" { print $2 }' | head -n 1)
        a_count=${a_count:-0}
        b_count=${b_count:-0}
        if [ "$a_count" -ge 3 ]; then
            ok "dữ liệu demo App A: $a_count văn bản [DEMO]"
        else
            fail "dữ liệu demo App A: có $a_count văn bản [DEMO], cần >= 3. Nạp: make demo-seed ARGS=\"--only a\" (demo/README.md)."
        fi
        if [ "$b_count" -gt 0 ]; then
            warn "dữ liệu demo App B: đã có $b_count bản ghi trước giờ demo, nên đoạn cài App B trên sân khấu sẽ thành giả (bước cài bị bỏ qua vì bản đang hoạt động). Chỉ nạp --only b SAU khi cài và duyệt App B trên sân khấu (demo/README.md, \"Thứ tự khi diễn thật\")."
        else
            ok "dữ liệu demo App B: chưa nạp (đúng: nạp sau khi cài trên sân khấu)"
        fi
    else
        fail "dữ liệu demo: không truy vấn được core-db (container core-db chạy chưa?)"
    fi

    cat << EOF

Việc kiểm tay (script không làm được):
  - Laptop p8 đã khởi động đủ stack, pin/sạc ổn, tắt thông báo; p8 KHÔNG có Viewer (chỉ p16): đừng hứa cảnh xem trang PDF trên laptop.
  - Đăng nhập thử trang quản trị https://${admin_host:-<DXOS_ADMIN_HOST>}/ui/ (tài khoản dxos-admin) và có hai quản trị viên để duyệt bốn mắt.
  - Kiểm witness độc lập (dxos-witness): lần chạy gần nhất của người ngoài đội báo OK; repo neo mở được trong trình duyệt.
  - Ngay sau khi niêm phong ở App A, chạy dxos anchor run (đoạn quét QR cần STH đã neo; CDN của raw.githubusercontent.com trễ tới ~5 phút).
  - App B CHƯA nạp dữ liệu: chỉ chạy make demo-seed ARGS="--only b" sau khi cài và duyệt App B trên sân khấu.
  - 6 video dự phòng V1 đến V6 mở được khi ngoại tuyến (docs/demo/kich-ban.md); bản ảnh chụp trang repo neo.
EOF

    echo
    echo "demo_preflight.sh: $fails lỗi, $warns cảnh báo."
    if [ "$fails" -gt 0 ] || { [ "$strict" -eq 1 ] && [ "$warns" -gt 0 ]; }; then
        exit 1
    fi
}

main "$@"
