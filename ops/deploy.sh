#!/bin/bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Triển khai một phiên bản đã gắn tag lên VPS (Plan 03 Task 12, spec S9.2, R-3; Plan 04 Task 11, S4). Chạy ở thư mục
# repo trên máy chủ:
#
#   ops/deploy.sh <vX.Y.Z> [--profile p16|p8] [--repo-url URL] [--allow-unsigned]
#
# Mã thoát:
#   0  đạt.
#   2  từ chối TRƯỚC khi đổi gì: tham số sai, thiếu .env/DXOS_DOMAIN, thiếu công cụ, cây làm việc bẩn, tag chưa ký, ký bằng khóa không
#      có trong deploy/allowed_signers hoặc có tên trong thân tag khác tên ref, allowed_signers không có khóa nào.
#   3  thiếu điều kiện trước khi chuyển bản (không lấy được tag, Release thiếu/sai digest, compose pull hỏng, dựng SPA hỏng).
#   4  health hỏng sau khi chuyển, đã tự quay lui về bản tốt gần nhất và bản đó khỏe.
#   5  health hỏng và KHÔNG quay lui được (chưa có bản tốt nào, bản mới thêm migration, hoặc quay lui cũng hỏng); in hướng dẫn.
#
# Các bước, theo đúng thứ tự (mỗi bước hỏng thì dừng, không chạy bước sau):
#   1. Tag phải khớp ^v[0-9]+.[0-9]+.[0-9]+$, profile là p16 hoặc p8, .env phải có DXOS_DOMAIN. Sai thì thoát 2.
#   2. Cây làm việc phải sạch (git status --porcelain rỗng). Không sạch thì thoát 2.
#   3. Ghi nhớ bản tốt gần nhất: tag ở dòng result=ok (hoặc dòng OK kiểu cũ) cuối cùng của deploy/deployments.log, khác
#      tag đang triển khai; hoặc "none".
#   4. git fetch origin refs/tags/<tag>:refs/tags/<tag> (KHÔNG --force: tag cục bộ khác tag trên remote thì git từ chối).
#   5. Kiểm chữ ký TRƯỚC mọi lệnh docker và trước khi checkout:
#      git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/<tag>
#      rồi tên trong thân tag (dòng "tag " của git cat-file tag) phải đúng <tag> (verify-tag không kiểm tên: chặn việc
#      đẩy tag ký của bản cũ dưới tên mới). Không đạt, hoặc allowed_signers không có khóa nào, thì thoát 2 và bỏ ref
#      vừa fetch (nếu trước đó chưa có). Tệp allowed_signers lấy từ bản đang checkout (neo tin cậy không nằm trong thứ
#      cần kiểm). --allow-unsigned bỏ qua bước này, in cảnh báo và ghi signed=no.
#   6. Giải refs/tags/<tag>^{commit} MỘT lần ra OID và git checkout --detach <OID> (không checkout theo tên).
#   7. Tải trust-core-image-<X.Y.Z>.txt từ Release của tag; lấy digest 64 hex (dạng release.yml ghi: dòng
#      ghcr.io/psa-ovncr/trust-core@sha256:<64 hex>, hoặc chỉ 64 hex). Sai định dạng thì thoát 3 TRƯỚC khi gọi compose.
#      Cùng cách cho viewer-image-<X.Y.Z>.txt (Plan 04 Task 15, ruling R28), nhưng chỉ khi hồ sơ là p16, dịch vụ `viewer`
#      được bật (COMPOSE_PROFILES có `viewer`, theo biến môi trường rồi tới .env như compose) và deploy/compose.release.yaml
#      của tag có DXOS_VIEWER_DIGEST (tag cũ trước 0.9.0 không có Viewer: bỏ qua, nên quay lui về chúng vẫn chạy). Thiếu
#      hoặc sai digest Viewer thì thoát 3: máy chủ không bao giờ dựng Viewer từ mã nguồn.
#      Ghi deploy/release.env (DXOS_TRUST_CORE_DIGEST, DXOS_RELEASE_TAG, và DXOS_VIEWER_DIGEST khi cần).
#   8. docker compose pull --ignore-buildable (hỏng thì thoát 3, chưa có gì đang chạy bị đổi).
#   9. ops/web_build_docker.sh: dựng SPA từ mã nguồn của tag vào volume apps-static (thoát 3 nếu image Node chưa ghim),
#      rồi up -d --wait (spec 16.3: pull && up -d): lõi chạy đúng image theo digest (compose.release.yaml); thêm
#      compose.anchor.yaml chỉ khi .env có DXOS_ANCHOR_REMOTE khác rỗng.
#  10. Kiểm sức khỏe: /readyz của trust-core-api trả 200 và https://$DXOS_DOMAIN/verify/v1/keys trả 200. `up --wait` hỏng
#      (container không khỏe) hoặc kiểm sức khỏe hỏng nghĩa là đã chuyển nhưng bản mới không khỏe: tự quay lui (S4).
#  11. Quay lui: chạy lại đúng chuỗi trên (bước 4 đến 10) cho bản tốt gần nhất, MỘT lần, không đệ quy, `up` kèm
#      --remove-orphans. Khỏe thì thoát 4, không thì thoát 5. Chưa có bản tốt nào thì thoát 5 ngay. KHÔNG quay lui khi bản
#      mới thêm tệp vào core/migrations/ so với bản tốt (git ls-tree, sau khi tag cũ đã qua kiểm chữ ký, trước checkout): bản cũ
#      không chạy được trên DB đã nâng cấp và không bao giờ hạ migration; thoát 5 và in hướng dẫn (sửa tiếp, hoặc khôi phục
#      từ bản sao lưu bằng ops/restore.sh vào project riêng).
#  12. Mỗi lần triển khai từ bước 4 trở đi ghi một dòng vào deploy/deployments.log, cột cách nhau bằng tab:
#      <UTC>\t<tag>\t<commit>\t<digest>\tresult=ok|rolled-back|failed\tsigned=yes|no
#      Dòng kiểu cũ (cột 5 là OK hoặc FAIL, không có cột 6) vẫn được đọc khi tìm bản tốt gần nhất.
#
# Hỏng ở bước 4 đến 9 (thoát 3): ghi dòng result=failed và in: "Triển khai <tag> hỏng. Quay lại bằng:
# ops/deploy.sh <tag trước>" (stack đang chạy chưa bị chuyển).
#
# - .env được đọc bằng sed, không `source` (tệp .env không được chạy như mã). Không in giá trị bí mật.
# - Toàn bộ thân script nằm trong hàm main để bash đọc xong tệp trước khi `git checkout` thay đổi ops/deploy.sh.
set -euo pipefail

DEFAULT_REPO_URL=https://github.com/PSA-OVNCR/dxos

usage() {
    echo "dùng: ops/deploy.sh <vX.Y.Z> [--profile p16|p8] [--repo-url URL] [--allow-unsigned]" >&2
    exit 2
}

main() {
    # Compose ưu tiên biến môi trường của tiến trình hơn --env-file: bỏ giá trị người vận hành đã export để compose
    # chỉ thấy digest và tag đã kiểm trong deploy/release.env (dòng log phải khớp thứ thực sự chạy).
    unset DXOS_TRUST_CORE_DIGEST DXOS_VIEWER_DIGEST DXOS_RELEASE_TAG
    # Biến trạng thái cho on_exit (EXIT trap) là biến toàn cục: bash có thể đã bỏ biến local khi trap chạy sau set -e.
    # cur, commit, digest, signed mô tả lần triển khai (hoặc quay lui) đang chạy.
    tag="" log_file=deploy/deployments.log previous=none cur="" commit=- digest=- signed=no started=0
    local profile=p16 repo_url=$DEFAULT_REPO_URL allow_unsigned=0
    while [ $# -gt 0 ]; do
        case $1 in
            --profile) [ $# -ge 2 ] || usage; profile=$2; shift 2 ;;
            --repo-url) [ $# -ge 2 ] || usage; repo_url=$2; shift 2 ;;
            --allow-unsigned) allow_unsigned=1; shift ;;
            -*) echo "deploy.sh: tùy chọn không hợp lệ: $1" >&2; usage ;;
            *) [ -z "$tag" ] || usage; tag=$1; shift ;;
        esac
    done
    [ -n "$tag" ] || usage
    local tag_re='^v[0-9]+\.[0-9]+\.[0-9]+$'
    if ! [[ $tag =~ $tag_re ]]; then
        echo "deploy.sh: tag phải có dạng vX.Y.Z (nhận được: $tag)" >&2
        exit 2
    fi
    case $profile in p16 | p8) ;; *) echo "deploy.sh: --profile phải là p16 hoặc p8 (nhận được: $profile)" >&2; exit 2 ;; esac
    if ! [[ $repo_url =~ ^https?://[A-Za-z0-9._~:/%@+-]+$ ]]; then
        echo "deploy.sh: --repo-url phải là địa chỉ http(s) hợp lệ" >&2
        exit 2
    fi
    repo_url=${repo_url%/}

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

    # Bản tốt gần nhất, khác tag đang triển khai: dòng result=ok (cột 5), hoặc dòng OK kiểu cũ (trước Plan 04 Task 11,
    # không có cột signed). Cũng là đích quay lui.
    if [ -f "$log_file" ]; then
        previous=$(awk -F'\t' -v self="$tag" '$2 != self && ($5 == "result=ok" || $5 == "OK") { t = $2 } END { print t }' "$log_file")
        if [ -z "$previous" ] || ! [[ $previous =~ $tag_re ]]; then previous=none; fi
    fi

    # release_digest <tag> <tên tệp>: tải tệp image từ Release của tag, in ra digest 64 hex (dạng release.yml ghi: dòng
    # ghcr.io/...@sha256:<64 hex>, hoặc chỉ 64 hex). Lỗi thì in lý do ra stderr và trả 1.
    release_digest() {
        local t=$1 name=$2 body line d
        body=$(curl -fsSL "$repo_url/releases/download/$t/$name" --max-time 60) || {
            echo "deploy.sh: không tải được $name từ Release $t" >&2
            return 1
        }
        line=$(printf '%s\n' "$body" | tr -d '\r' | grep -F '@sha256:' | head -n 1 || true)
        if [ -n "$line" ]; then
            d=${line##*@sha256:}
        else
            d=$(printf '%s' "$body" | tr -d '\r\n ')
        fi
        if ! [[ $d =~ ^[0-9a-f]{64}$ ]]; then
            echo "deploy.sh: digest trong $name không phải 64 chữ số hex; dừng trước khi gọi compose" >&2
            return 1
        fi
        printf '%s\n' "$d"
    }
    # viewer_enabled: dịch vụ `viewer` có được bật không. Compose ưu tiên COMPOSE_PROFILES trong môi trường tiến trình
    # (kể cả rỗng) hơn .env, nên đọc theo đúng thứ tự đó; `*` bật mọi hồ sơ.
    viewer_enabled() {
        local profiles
        profiles=$(printf '%s' "${COMPOSE_PROFILES-$(env_get COMPOSE_PROFILES)}" | tr -d ' ')
        case ",$profiles," in *,viewer,* | *,\*,*) return 0 ;; *) return 1 ;; esac
    }

    # record <result> [tag commit digest signed]: mặc định mô tả lần triển khai đang chạy.
    record() {
        local result=$1 t=${2:-$cur} c=${3:-$commit} d=${4:-$digest} s=${5:-$signed}
        mkdir -p "$(dirname "$log_file")"
        printf '%s\t%s\t%s\t%s\tresult=%s\tsigned=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$t" "$c" "$d" "$result" "$s" >> "$log_file"
    }
    hint_previous() {
        echo "Triển khai $tag hỏng. Quay lại bằng: ops/deploy.sh $previous"
        [ "$previous" != none ] || echo "(chưa có bản nào chạy tốt được ghi trong $log_file)"
    }
    manual_recovery() {
        cat << MANUAL
Không tự quay lui được. Khôi phục tay (docs/runbook-deploy.md, mục 4):
  1. Xem trạng thái: docker compose -p dxos ps ; docker compose -p dxos logs --tail=200 <dịch vụ không khỏe>
  2. Biết một tag từng chạy tốt thì chạy lại: ops/deploy.sh <tag> (chỉ thêm --allow-unsigned khi tag đó chưa ký và bạn chấp nhận rủi ro).
  3. Chưa có tag tốt: sửa nguyên nhân từ log ở bước 1, phát hành tag mới (đã ký) rồi chạy ops/deploy.sh <tag mới>.
MANUAL
    }
    no_rollback_migrations() {
        cat << NOROLLBACK
Triển khai $1 hỏng sức khỏe và KHÔNG tự quay lui về $2: $1 thêm migration cơ sở dữ liệu mà $2 không biết, nên $2 sẽ không
khởi động trên DB đã nâng cấp (migrate từ chối DB có migration lạ). Không bao giờ hạ migration. Stack đang ở $1 (chưa khỏe).
Chọn một trong hai (docs/runbook-deploy.md mục 4, CHANGELOG mục "Nâng cấp từ 0.3.0"):
  1. Sửa tiếp (fix forward): đọc log (docker compose -p dxos logs --tail=200 trust-core-api), sửa nguyên nhân, phát hành tag
     mới đã ký rồi ops/deploy.sh <tag mới>.
  2. Khôi phục từ bản sao lưu lấy TRƯỚC lần triển khai này: ops/restore.sh vào một project riêng theo docs/runbook-backup.md
     (mục 4), kiểm dữ liệu rồi mới chuyển. Không khôi phục đè lên project dxos.
NOROLLBACK
    }
    # shellcheck disable=SC2329  # gọi qua trap on_exit EXIT
    on_exit() {
        local rc=$?
        trap - EXIT
        if [ "$rc" -ne 0 ] && [ "$started" = 1 ]; then
            record failed || true
            hint_previous
        fi
        exit "$rc"
    }
    trap on_exit EXIT

    # chain <tag>: chuỗi triển khai một tag (bước 4 đến 10). Dùng cho cả triển khai lẫn quay lui. Trả về:
    #   0 đạt; 2 tag chưa ký/khóa lạ (chưa đổi gì); 3 thiếu điều kiện trước khi chuyển; 10 đã chuyển nhưng sức khỏe hỏng.
    # Chạy trong ngữ cảnh `|| rc=$?` nên set -e không có tác dụng ở đây: mọi lệnh phải tự `|| return`.
    chain() {
        local t=$1 version=${1#v} rc=0 ready curl_tls=-fs viewer_digest="" rollback_from=${2:-} up_extra=()
        [ -z "$rollback_from" ] || up_extra=(--remove-orphans)   # quay lui: bỏ container của dịch vụ bản cũ không có (Viewer)
        cur=$t commit=- digest=- signed=no

        local signers=deploy/allowed_signers
        if [ "$allow_unsigned" != 1 ] && ! grep -Eqv '^[[:space:]]*(#|$)' "$signers" 2> /dev/null; then
            echo "deploy.sh: $signers không có khóa nào (thiếu hoặc chỉ có chú thích): mọi tag bị từ chối cho tới khi thêm khóa công khai (việc V42, docs/runbook-deploy.md mục 2.2)" >&2
            return 2
        fi

        echo "deploy.sh: lấy tag $t"
        # Nhớ tag cục bộ đã có trước đó: nếu tag bị từ chối thì chỉ xóa ref do chính lần fetch này tạo ra.
        local had_ref
        had_ref=$(git rev-parse -q --verify "refs/tags/$t" 2> /dev/null || true)
        git fetch origin "refs/tags/$t:refs/tags/$t" || {
            echo "deploy.sh: git fetch từ chối tag $t (tag cục bộ khác remote?); không dùng --force." >&2
            echo "deploy.sh: nếu tag đã được ký lại và di chuyển có chủ đích, kiểm rồi xóa bản cục bộ: git tag -d $t" >&2
            return 3
        }
        # refuse: bỏ ref vừa fetch (nếu trước đó chưa có) để lần chạy sau không vướng, rồi từ chối (mã 2).
        refuse() {
            [ -n "$had_ref" ] || git update-ref -d "refs/tags/$t" > /dev/null 2>&1 || true
            echo "deploy.sh: $1; từ chối, chưa đổi gì" >&2
            return 2
        }
        if [ "$allow_unsigned" = 1 ]; then
            echo "deploy.sh: CẢNH BÁO: --allow-unsigned, KHÔNG kiểm chữ ký của tag $t (ghi signed=no vào $log_file)" >&2
        else
            git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag "refs/tags/$t" ||
                { refuse "tag $t chưa ký hoặc ký bằng khóa không có trong deploy/allowed_signers"; return 2; }
            # verify-tag không kiểm tên: một tag ký của bản cũ đẩy lên dưới tên mới vẫn qua. Tên trong thân tag phải là $t.
            local named
            named=$(git cat-file tag "refs/tags/$t" 2> /dev/null | sed -n '/^$/q;s/^tag //p') || named=""
            [ "$named" = "$t" ] ||
                { refuse "tên trong thân tag đã ký ('${named:-không có}') không khớp refs/tags/$t (tag ký bị đổi tên?)"; return 2; }
            signed=yes
        fi
        # Giải một lần ra OID rồi checkout đúng OID đó (không để tên tag được giải lần hai).
        commit=$(git rev-parse "refs/tags/$t^{commit}") || return 3
        [[ $commit =~ ^[0-9a-f]{40}$ ]] || { echo "deploy.sh: không giải được commit của tag $t" >&2; commit=-; return 3; }

        # Quay lui (R33): bản mới thêm migration thì bản cũ không chạy được trên DB đã nâng cấp (migrate từ chối DB có
        # migration mà mã nguồn không có) và không bao giờ hạ migration: dừng ở đây, trước khi đổi cây làm việc hay container.
        if [ -n "$rollback_from" ]; then
            local from_migs to_migs added
            from_migs=$(git ls-tree --name-only "refs/tags/$rollback_from^{commit}" core/migrations/ 2> /dev/null | sort) || from_migs=""
            to_migs=$(git ls-tree --name-only "refs/tags/$t^{commit}" core/migrations/ 2> /dev/null | sort) || to_migs=""
            added=$(comm -23 <(printf '%s\n' "$from_migs") <(printf '%s\n' "$to_migs") | sed '/^$/d' | sed 's|^core/migrations/||' | tr '\n' ' ')
            if [ -n "$added" ]; then
                echo "deploy.sh: $rollback_from thêm migration mà $t không có: ${added% }" >&2
                return 11
            fi
        fi
        git -c advice.detachedHead=false checkout --detach "$commit" || return 3

        digest=$(release_digest "$t" "trust-core-image-$version.txt") || { digest=-; return 3; }
        printf 'DXOS_TRUST_CORE_DIGEST=%s\nDXOS_RELEASE_TAG=%s\n' "$digest" "$t" > "$release_env" || return 3
        # Viewer (R28): chỉ khi p16 bật nó và overlay của tag có chỗ cho digest của nó.
        if [ "$profile" = p16 ] && viewer_enabled && grep -q DXOS_VIEWER_DIGEST deploy/compose.release.yaml 2> /dev/null; then
            viewer_digest=$(release_digest "$t" "viewer-image-$version.txt") || return 3
            printf 'DXOS_VIEWER_DIGEST=%s\n' "$viewer_digest" >> "$release_env" || return 3
        fi

        local compose=(docker compose -p dxos --env-file "$env_file" --env-file "$release_env"
            -f deploy/compose.yaml -f "deploy/compose.$profile.yaml")
        [ -z "$anchor_remote" ] || compose+=(-f deploy/compose.anchor.yaml)
        compose+=(-f deploy/compose.release.yaml)

        # Kéo image trước khi đụng tới SPA: pull hỏng (mã 3) thì chưa có gì đang chạy bị đổi.
        echo "deploy.sh: docker compose pull (hồ sơ $profile, digest $digest${viewer_digest:+, viewer $viewer_digest})"
        "${compose[@]}" pull --ignore-buildable || {
            echo "deploy.sh: docker compose pull hỏng; chưa đổi gì đang chạy" >&2
            return 3
        }

        echo "deploy.sh: dựng SPA từ mã nguồn của $t"
        bash ops/web_build_docker.sh || rc=$?
        if [ "$rc" -eq 3 ]; then
            echo "deploy.sh: ops/web_build_docker.sh thoát 3: image Node chưa ghim digest. Chạy 'make pin-images' (cần Docker có buildx)," \
                "commit rồi phát hành tag mới; chưa chạy compose up" >&2
            return 3
        elif [ "$rc" -ne 0 ]; then
            echo "deploy.sh: ops/web_build_docker.sh thoát $rc; chưa chạy compose up" >&2
            return 3
        fi

        echo "deploy.sh: docker compose up"
        # Từ đây bản đang chạy bị thay: hỏng nghĩa là cần quay lui (return 10).
        "${compose[@]}" up -d --wait --wait-timeout 600 ${up_extra[@]+"${up_extra[@]}"} || {
            echo "deploy.sh: docker compose up --wait hỏng (có container không khỏe)" >&2
            return 10
        }

        echo "deploy.sh: kiểm sức khỏe"
        ready=$("${compose[@]}" exec -T trust-core-api python -c \
            "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/readyz', timeout=5).status)") || {
            echo "deploy.sh: /readyz của trust-core-api không trả 200" >&2
            return 10
        }
        [ "$(printf '%s' "$ready" | tr -d '\r\n ')" = 200 ] || { echo "deploy.sh: /readyz trả '$ready', cần 200" >&2; return 10; }
        # Chỉ bỏ xác minh TLS (-k) với localhost/*.localhost (Caddy tự ký); tên miền thật phải có chứng chỉ hợp lệ.
        case $domain in localhost | *.localhost) curl_tls=-fsk ;; esac
        curl "$curl_tls" --max-time 20 "https://$domain/verify/v1/keys" > /dev/null || {
            echo "deploy.sh: https://$domain/verify/v1/keys không trả 200" >&2
            return 10
        }
        return 0
    }

    started=1
    local rc=0
    chain "$tag" || rc=$?
    case $rc in
        0)
            record ok
            started=0
            echo "deploy.sh: xong $tag (commit $commit, digest $digest, signed=$signed)"
            return 0
            ;;
        2)
            started=0   # từ chối trước khi đổi gì: không phải một lần triển khai, không ghi log
            exit 2
            ;;
        3)
            record failed
            started=0
            hint_previous
            exit 3
            ;;
    esac

    # rc = 10: bản mới đã chuyển nhưng health hỏng. Nhớ thông tin của nó để ghi sau khi quay lui xong.
    local bad_commit=$commit bad_digest=$digest bad_signed=$signed
    if [ "$previous" = none ]; then
        record failed "$tag" "$bad_commit" "$bad_digest" "$bad_signed"
        started=0
        echo "Triển khai $tag hỏng sức khỏe và chưa có bản nào chạy tốt để quay lui (không có dòng result=ok trong $log_file)."
        manual_recovery
        exit 5
    fi
    local target=$previous
    echo "deploy.sh: $tag hỏng sức khỏe; tự quay lui về $target (bản tốt gần nhất)"
    rc=0
    chain "$target" "$tag" || rc=$?
    if [ "$rc" -eq 11 ]; then
        record failed "$tag" "$bad_commit" "$bad_digest" "$bad_signed"
        started=0
        no_rollback_migrations "$tag" "$target"
        exit 5
    fi
    if [ "$rc" -eq 0 ]; then
        record ok                                                       # quay lui về $target đã khỏe
        record rolled-back "$tag" "$bad_commit" "$bad_digest" "$bad_signed"
        started=0
        echo "Triển khai $tag hỏng sức khỏe. Đã quay lui về $target và $target khỏe. Điều tra $tag trước khi thử lại."
        exit 4
    fi
    record failed                                                       # quay lui $target cũng hỏng
    record failed "$tag" "$bad_commit" "$bad_digest" "$bad_signed"
    started=0
    echo "Triển khai $tag hỏng sức khỏe và quay lui về $target cũng hỏng (mã nội bộ $rc)."
    manual_recovery
    exit 5
}

main "$@"
exit $?
