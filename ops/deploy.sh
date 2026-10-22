#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Triển khai một phiên bản đã gắn tag lên VPS (Plan 03 Task 12, spec S9.2, R-3). Chạy ở thư mục repo trên máy chủ:
#
#   ops/deploy.sh <vX.Y.Z> [--profile p16|p8] [--repo-url URL]
#
# Các bước, theo đúng thứ tự (mỗi bước hỏng thì dừng, không chạy bước sau):
#   1. Tag phải khớp ^v[0-9]+.[0-9]+.[0-9]+$, profile là p16 hoặc p8, .env phải có DXOS_DOMAIN. Sai thì thoát 2.
#   2. Cây làm việc phải sạch (git status --porcelain rỗng). Không sạch thì thoát 2.
#   3. Ghi nhớ bản đang chạy tốt: tag ở dòng OK cuối cùng của deploy/deployments.log, hoặc "none".
#   4. git fetch origin refs/tags/<tag>:refs/tags/<tag> (KHÔNG --force: tag cục bộ khác tag trên remote thì git từ chối).
#   5. git checkout --detach <tag>.
#   6. Tải trust-core-image-<X.Y.Z>.txt từ Release của tag; lấy digest 64 hex (dạng release.yml ghi: dòng
#      ghcr.io/psa-ovncr/trust-core@sha256:<64 hex>, hoặc chỉ 64 hex). Sai định dạng thì thoát 1 TRƯỚC khi gọi compose.
#      Ghi deploy/release.env (DXOS_TRUST_CORE_DIGEST, DXOS_RELEASE_TAG).
#   7. ops/web_build_docker.sh: dựng SPA từ mã nguồn của tag vào volume apps-static (thoát 3 nếu image Node chưa ghim).
#   8. docker compose pull --ignore-buildable rồi up -d --wait (spec 16.3: pull && up -d): lõi chạy đúng image theo
#      digest (compose.release.yaml); thêm compose.anchor.yaml
#      chỉ khi .env có DXOS_ANCHOR_REMOTE khác rỗng.
#   9. Kiểm sức khỏe: /readyz của trust-core-api trả 200 và https://$DXOS_DOMAIN/verify/v1/keys trả 200.
#  10. Ghi một dòng vào deploy/deployments.log: <UTC>\t<tag>\t<commit>\t<digest>\tOK|FAIL.
#
# Từ bước 4 trở đi, hỏng ở đâu cũng ghi dòng FAIL, thoát 1 và in: "Triển khai <tag> hỏng. Quay lại bằng:
# ops/deploy.sh <tag trước>". KHÔNG tự quay lui (tự quay lui là S4, Plan 04); người vận hành chạy lại lệnh đó.
#
# - .env được đọc bằng sed, không `source` (tệp .env không được chạy như mã). Không in giá trị bí mật.
# - Toàn bộ thân script nằm trong hàm main để bash đọc xong tệp trước khi `git checkout` thay đổi ops/deploy.sh.
set -euo pipefail

DEFAULT_REPO_URL=https://github.com/PSA-OVNCR/dxos

usage() {
    echo "dùng: ops/deploy.sh <vX.Y.Z> [--profile p16|p8] [--repo-url URL]" >&2
    exit 2
}

main() {
    # Compose ưu tiên biến môi trường của tiến trình hơn --env-file: bỏ giá trị người vận hành đã export để compose
    # chỉ thấy digest và tag đã kiểm trong deploy/release.env (dòng log phải khớp thứ thực sự chạy).
    unset DXOS_TRUST_CORE_DIGEST DXOS_RELEASE_TAG
    # Biến trạng thái cho on_exit (EXIT trap) là biến toàn cục: bash có thể đã bỏ biến local khi trap chạy sau set -e.
    tag="" log_file=deploy/deployments.log previous=none commit=- digest=- started=0
    local profile=p16 repo_url=$DEFAULT_REPO_URL
    while [ $# -gt 0 ]; do
        case $1 in
            --profile) [ $# -ge 2 ] || usage; profile=$2; shift 2 ;;
            --repo-url) [ $# -ge 2 ] || usage; repo_url=$2; shift 2 ;;
            -*) echo "deploy.sh: tùy chọn không hợp lệ: $1" >&2; usage ;;
            *) [ -z "$tag" ] || usage; tag=$1; shift ;;
        esac
    done
    [ -n "$tag" ] || usage
    if ! [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "deploy.sh: tag phải có dạng vX.Y.Z (nhận được: $tag)" >&2
        exit 2
    fi
    case $profile in p16 | p8) ;; *) echo "deploy.sh: --profile phải là p16 hoặc p8 (nhận được: $profile)" >&2; exit 2 ;; esac
    if ! [[ $repo_url =~ ^https?://[A-Za-z0-9._~:/%@+-]+$ ]]; then
        echo "deploy.sh: --repo-url phải là địa chỉ http(s) hợp lệ" >&2
        exit 2
    fi
    repo_url=${repo_url%/}
    local version=${tag#v}

    local repo
    repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    cd "$repo"
    local env_file=.env release_env=deploy/release.env

    # Đọc KEY=giá trị từ .env mà không `source`. Bản cuối thắng; bỏ \r và cặp nháy ngoài.
    env_get() {
        [ -f "$env_file" ] || return 0
        sed -n "s/^$1=//p" "$env_file" | tail -n 1 | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
    }

    [ -f "$env_file" ] || { echo "deploy.sh: thiếu .env (sao từ .env.example và điền đủ)" >&2; exit 2; }
    local domain anchor_remote
    domain=$(env_get DXOS_DOMAIN)
    if ! [[ $domain =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]+)?$ ]]; then
        echo "deploy.sh: .env phải có DXOS_DOMAIN hợp lệ (tên miền, có thể kèm cổng)" >&2
        exit 2
    fi
    anchor_remote=$(env_get DXOS_ANCHOR_REMOTE)
    local tool
    for tool in git docker curl; do
        command -v "$tool" > /dev/null || { echo "deploy.sh: không tìm thấy $tool" >&2; exit 2; }
    done

    if [ -n "$(git status --porcelain)" ]; then
        echo "deploy.sh: cây làm việc không sạch; commit hoặc hoàn tác thay đổi trước khi triển khai" >&2
        exit 2
    fi

    # Bản đang chạy tốt gần nhất (để in lệnh quay lại).
    if [ -f "$log_file" ]; then
        previous=$(awk -F'\t' '$5 == "OK" { t = $2 } END { print t }' "$log_file")
        [ -n "$previous" ] || previous=none
    fi

    record() {
        mkdir -p "$(dirname "$log_file")"
        printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$tag" "$commit" "$digest" "$1" >> "$log_file"
    }
    # shellcheck disable=SC2329  # gọi qua trap on_exit EXIT
    on_exit() {
        local rc=$?
        trap - EXIT
        if [ "$rc" -ne 0 ] && [ "$started" = 1 ]; then
            record FAIL || true
            echo "Triển khai $tag hỏng. Quay lại bằng: ops/deploy.sh $previous"
            [ "$previous" != none ] || echo "(chưa có bản nào chạy tốt được ghi trong $log_file)"
        fi
        exit "$rc"
    }
    die() { echo "deploy.sh: $*" >&2; exit 1; }
    trap on_exit EXIT
    started=1

    echo "deploy.sh: lấy tag $tag"
    git fetch origin "refs/tags/$tag:refs/tags/$tag" || die "git fetch từ chối tag $tag (tag cục bộ khác remote?); không dùng --force"
    git -c advice.detachedHead=false checkout --detach "$tag"
    commit=$(git rev-parse HEAD)

    local body line
    body=$(curl -fsSL "$repo_url/releases/download/$tag/trust-core-image-$version.txt" --max-time 60) \
        || die "không tải được trust-core-image-$version.txt từ Release $tag"
    line=$(printf '%s\n' "$body" | tr -d '\r' | grep -F '@sha256:' | head -n 1 || true)
    if [ -n "$line" ]; then
        digest=${line##*@sha256:}
    else
        digest=$(printf '%s' "$body" | tr -d '\r\n ')
    fi
    if ! [[ $digest =~ ^[0-9a-f]{64}$ ]]; then
        digest=-
        die "digest trong trust-core-image-$version.txt không phải 64 chữ số hex; dừng trước khi gọi compose"
    fi
    printf 'DXOS_TRUST_CORE_DIGEST=%s\nDXOS_RELEASE_TAG=%s\n' "$digest" "$tag" > "$release_env"

    echo "deploy.sh: dựng SPA từ mã nguồn của $tag"
    local rc=0
    bash ops/web_build_docker.sh || rc=$?
    if [ "$rc" -eq 3 ]; then
        die "ops/web_build_docker.sh thoát 3: image Node chưa ghim digest. Chạy 'make pin-images' (cần Docker có buildx)," \
            "commit rồi phát hành tag mới; chưa gọi compose"
    elif [ "$rc" -ne 0 ]; then
        die "ops/web_build_docker.sh thoát $rc; chưa gọi compose"
    fi

    local compose=(docker compose -p dxos --env-file "$env_file" --env-file "$release_env"
        -f deploy/compose.yaml -f "deploy/compose.$profile.yaml")
    [ -z "$anchor_remote" ] || compose+=(-f deploy/compose.anchor.yaml)
    compose+=(-f deploy/compose.release.yaml)

    echo "deploy.sh: docker compose pull + up (hồ sơ $profile, digest $digest)"
    "${compose[@]}" pull --ignore-buildable
    "${compose[@]}" up -d --wait --wait-timeout 600

    echo "deploy.sh: kiểm sức khỏe"
    local ready
    ready=$("${compose[@]}" exec -T trust-core-api python -c \
        "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status)") \
        || die "/readyz của trust-core-api không trả 200"
    [ "$(printf '%s' "$ready" | tr -d '\r\n ')" = 200 ] || die "/readyz trả '$ready', cần 200"
    # Chỉ bỏ xác minh TLS (-k) với localhost/*.localhost (Caddy tự ký); tên miền thật phải có chứng chỉ hợp lệ.
    local curl_tls=-fs
    case $domain in localhost | *.localhost) curl_tls=-fsk ;; esac
    curl "$curl_tls" --max-time 20 "https://$domain/verify/v1/keys" > /dev/null || die "https://$domain/verify/v1/keys không trả 200"

    record OK
    started=0
    echo "deploy.sh: xong $tag (commit $commit, digest $digest)"
}

main "$@"
exit $?
