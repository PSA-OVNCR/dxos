#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Minh chứng AT-13 (spec 14 "Bằng chứng tái sử dụng", 19; Plan 02 Task 15): cài App B trên CÙNG image trust-core
# đã phát hành, không đổi lõi, không đổi gateway, rồi chạy e2e của App B.
#
# Chạy trên VPS, ở thư mục gốc repo, khi stack đang chạy bằng image phát hành (deploy/compose.release.yaml) và App B
# CHƯA ACTIVE ở phiên bản trong apps/chung-nhan/manifest.yaml:
#   DXOS_TRUST_CORE_DIGEST=<64 hex, như trong .env> DXOS_SERVER=https://admin.<miền> \
#   DXOS_E2E_BASE=https://<miền> DXOS_E2E_ADMIN_BASE=https://admin.<miền> DXOS_ORG_NAME='<như .env>' \
#   [DXOS_TOKEN=<token người nộp>] [DXOS_APPROVER_TOKEN=<token người duyệt>] ops/at13_reuse.sh
#
# - Người nộp: DXOS_TOKEN, hoặc token đã lưu của `dxos login`. Người duyệt PHẢI là thành viên khác. Không có
#   DXOS_APPROVER_TOKEN thì script in lệnh duyệt rồi chờ (tối đa AT13_WAIT_S giây, mặc định 1800) tới khi App B ACTIVE.
# - DXOS_ALLOW_SELF_APPROVAL phải là false trên stack (script đọc Settings() trong container trust-core-api).
# - CẢNH BÁO: bước e2e App B lấy token bằng client dxos-test và người dùng dev (mật khẩu đã biết), chỉ có ở realm dev.
#   Thêm tạm chúng vào realm VPS là quyết định của trưởng nhóm; gỡ ngay sau khi chạy (lệnh gỡ: docs/evidence/README.md).
# - Kết quả: bảng so sánh ở docs/evidence/at13-reuse.txt (đổi bằng AT13_OUT). Mã thoát 0 chỉ khi mọi giá trị trước và
#   sau giống hệt, `git diff` của core/ và cấu hình gateway rỗng, và test_m2_app_b.py đạt.
# - Script không in token.
set -euo pipefail

PROJECT=${DXOS_PROJECT:-dxos}
OUT=${AT13_OUT:-docs/evidence/at13-reuse.txt}
APP_DIR=${AT13_APP_DIR:-apps/chung-nhan}
WAIT_S=${AT13_WAIT_S:-1800}
PY=${PYTHON:-python3}
REPO=ghcr.io/psa-ovncr/trust-core
: "${DXOS_TRUST_CORE_DIGEST:?đặt DXOS_TRUST_CORE_DIGEST (digest image trust-core đã phát hành, 64 hex)}"
: "${DXOS_SERVER:?đặt DXOS_SERVER=https://admin.<miền>}"
[[ $DXOS_TRUST_CORE_DIGEST =~ ^[0-9a-f]{64}$ ]] || { echo "DXOS_TRUST_CORE_DIGEST phải là 64 hex thường" >&2; exit 1; }
EXPECTED_IMAGE="$REPO@sha256:$DXOS_TRUST_CORE_DIGEST"
cd "$(dirname "$0")/.."

die() { echo "AT-13: $*" >&2; exit 1; }
dx() {
    if [[ -n ${DXOS_CA_FILE:-} ]]; then dxos --server "$DXOS_SERVER" --ca-file "$DXOS_CA_FILE" "$@"
    else dxos --server "$DXOS_SERVER" "$@"; fi
}

read -r APP VER < <("$PY" -c 'import sys, yaml; m = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["app"]
print(m["id"], m["version"])' "$APP_DIR/manifest.yaml")

status_of() {
    local json
    json=$(dx --json app list) || return $?        # giữ mã thoát 2/3 của dxos
    printf '%s' "$json" | "$PY" -c '
import json, sys
rows = json.load(sys.stdin)
print(next((r["status"] for r in rows if r["app_id"] == sys.argv[1] and r["version"] == sys.argv[2]), ""))' "$APP" "$VER"
}

# Ảnh chụp các giá trị phải giữ nguyên, dạng "khóa<TAB>giá trị", theo thứ tự cố định.
snapshot() {
    local svc c img
    for svc in trust-core-api trust-core-worker; do
        c="$PROJECT-$svc-1"
        img=$(docker inspect -f '{{.Image}}' "$c")
        printf '%s.config_image\t%s\n' "$svc" "$(docker inspect -f '{{.Config.Image}}' "$c")"
        printf '%s.image_id\t%s\n' "$svc" "$img"
        printf '%s.repo_digests\t%s\n' "$svc" "$(docker image inspect -f '{{join .RepoDigests ","}}' "$img")"
        printf '%s.started_at\t%s\n' "$svc" "$(docker inspect -f '{{.State.StartedAt}}' "$c")"
    done
    local f
    for f in deploy/apisix/*.yaml deploy/caddy/Caddyfile; do
        printf 'sha256:%s\t%s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
    done
    printf 'git.head\t%s\n' "$(git rev-parse HEAD)"
    printf 'git.local_changes(core,deploy/apisix,deploy/caddy)\t%s\n' \
        "$(git status --porcelain -- core deploy/apisix deploy/caddy | wc -l | tr -d ' ')"
}

# ---------------------------------------------------------------- kiểm trước
for svc in trust-core-api trust-core-worker; do
    got=$(docker inspect -f '{{.Config.Image}}' "$PROJECT-$svc-1") || die "không thấy container $PROJECT-$svc-1"
    [[ $got == "$EXPECTED_IMAGE" ]] || die "$svc chạy image '$got', không phải $EXPECTED_IMAGE (dùng deploy/compose.release.yaml)"
done
# Giá trị HIỆU LỰC (Settings của lõi, đúng cách lõi đọc biến môi trường); kiểm không được thì dừng, không coi là "tắt".
self=$(docker exec "$PROJECT-trust-core-api-1" python -c \
    'from dxos_core.settings import Settings; print(Settings().allow_self_approval)') \
    || die "không đọc được DXOS_ALLOW_SELF_APPROVAL hiệu lực trong $PROJECT-trust-core-api-1"
[[ $self == "False" ]] || die "DXOS_ALLOW_SELF_APPROVAL hiệu lực là '$self'; AT-13 phải duyệt bốn mắt (cần False)"
st=$(status_of)
[[ $st != "ACTIVE" ]] || die "$APP $VER đã ACTIVE từ trước; AT-13 cần cài App B trong lần chạy này"

STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BEFORE=$(snapshot)
HEAD_BEFORE=$(git rev-parse HEAD)
[[ $(printf '%s\n' "$BEFORE" | awk -F'\t' '$1 ~ /^git.local_changes/ {print $2}') == 0 ]] \
    || die "core/ hoặc cấu hình gateway có thay đổi chưa commit; AT-13 cần cây sạch"

# ---------------------------------------------------------------- cài và duyệt App B bằng CLI
PYTHON=$PY sh ops/e2e/install_apps.sh "$APP_DIR"
if [[ -z ${DXOS_APPROVER_TOKEN:-} ]]; then
    echo "== chờ người duyệt thứ hai chạy: dxos --server $DXOS_SERVER app approve $APP $VER (tối đa ${WAIT_S}s)"
    deadline=$((SECONDS + WAIT_S))
    until [[ $(status_of) == "ACTIVE" ]]; do
        (( SECONDS < deadline )) || die "$APP $VER chưa ACTIVE sau ${WAIT_S}s"
        sleep 10
    done
fi
[[ $(status_of) == "ACTIVE" ]] || die "$APP $VER chưa ACTIVE"

# ---------------------------------------------------------------- e2e của App B
set +e
DXOS_E2E_REQUIRE=1 "$PY" -m pytest -p no:cacheprovider -m e2e tests/e2e/test_m2_app_b.py -v -rs
E2E_RC=$?
set -e

# ---------------------------------------------------------------- so sánh
AFTER=$(snapshot)
FINISHED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DIFF_STAT=$(git diff --stat "$HEAD_BEFORE" HEAD -- core/ deploy/apisix deploy/caddy)

ok=1
table=$(paste <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER" | cut -f2) | while IFS=$'\t' read -r key before after; do
    same="GIỐNG"; [[ $before == "$after" ]] || same="KHÁC"
    printf '| %s | %s | %s | %s |\n' "$key" "$before" "$after" "$same"
done)
grep -q '| KHÁC |$' <<<"$table" && ok=0
[[ -z $DIFF_STAT ]] || ok=0
(( E2E_RC == 0 )) || ok=0

mkdir -p "$(dirname "$OUT")"
{
    echo "AT-13: cài App B ($APP $VER) trên image trust-core đã phát hành (ops/at13_reuse.sh)"
    echo "Bắt đầu: $STARTED  Kết thúc: $FINISHED  Máy: $(hostname)"
    echo "Image mong đợi: $EXPECTED_IMAGE"
    echo
    echo "| Giá trị | Trước khi cài | Sau khi cài và chạy e2e | So sánh |"
    echo "|---|---|---|---|"
    printf '%s\n' "$table"
    echo
    echo "git diff --stat $HEAD_BEFORE HEAD -- core/ deploy/apisix deploy/caddy:"
    if [[ -z $DIFF_STAT ]]; then echo "(rỗng)"; else printf '%s\n' "$DIFF_STAT"; fi
    echo
    echo "tests/e2e/test_m2_app_b.py: mã thoát $E2E_RC"
    if (( ok )); then echo "KẾT QUẢ: ĐẠT"; else echo "KẾT QUẢ: KHÔNG ĐẠT"; fi
} > "$OUT"
cat "$OUT"
(( ok ))
