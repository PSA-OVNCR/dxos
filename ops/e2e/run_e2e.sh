#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Chạy E2E (mốc M1 của Plan 01 Task 17 và mốc M2 của Plan 02 Task 15) trong một container python:3.12-slim cạnh
# stack dev-lite:
#   docker run --rm -e DXOS_ORG_NAME -v <repo>:/src:ro -v <thư mục kết quả>:/out -v dxos_anchor-repo:/var/lib/dxos:ro \
#     python:3.12-slim@sha256:... sh /src/ops/e2e/run_e2e.sh
# Cần:
# - /out/caddy-root.crt (CA nội bộ của Caddy, lấy bằng `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt`);
# - DXOS_ORG_NAME giống giá trị trong .env của stack (AT-28 so issuer.name; lõi từ chối niêm phong khi còn giá trị mẫu).
# Ứng dụng được cài bằng CLI `dxos` theo bốn mắt (ops/e2e/install_apps.sh): admin1 nộp, admin2 duyệt. Không còn dùng
# ops/seed_manifests.py. AT-20 (khóa OpenBao) cần docker nên được bỏ qua trong container này; chạy trên máy chủ
# (xem tests/e2e/test_m2_attacks.py).
set -eu
export PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends git >/dev/null
mkdir -p /tmp/pkgs && cp -r /src/libs/dxos-proof /src/witness /src/cli /tmp/pkgs/
python -m pip install -q /tmp/pkgs/dxos-proof /tmp/pkgs/witness /tmp/pkgs/cli "pytest>=8" "httpx>=0.27" "PyYAML>=6"
git config --global safe.directory '*'

# Tên `localhost` / `admin.localhost` nằm trong issuer của token và chứng chỉ Caddy: trỏ chúng về máy chủ Docker.
GW=$(getent ahostsv4 host.docker.internal | awk 'NR==1 {print $1}')
[ -n "$GW" ] || { echo "không phân giải được host.docker.internal"; exit 3; }
grep -v -E '[[:space:]]localhost([[:space:]]|$)' /etc/hosts > /tmp/hosts || true
echo "$GW localhost admin.localhost" >> /tmp/hosts
cat /tmp/hosts > /etc/hosts
export SSL_CERT_FILE=/out/caddy-root.crt
export DXOS_E2E_REQUIRE=1          # stack không trả lời thì LỖI, không bỏ qua

# Token dev (client dxos-test, chỉ có ở realm dev) của hai admin khác nhau.
token() {
    python - "$1" <<'PY'
import os
import sys

import httpx

r = httpx.post("https://localhost/auth/realms/dxos/protocol/openid-connect/token", timeout=20, data={
    "grant_type": "password", "client_id": "dxos-test", "username": sys.argv[1],
    "password": os.environ.get("DXOS_E2E_PASSWORD", "dev-only-password"), "scope": "openid"})
r.raise_for_status()
print(r.json()["access_token"])
PY
}
DXOS_TOKEN=$(token admin1) DXOS_APPROVER_TOKEN=$(token admin2) \
    DXOS_SERVER=https://admin.localhost DXOS_CA_FILE="$SSL_CERT_FILE" PYTHON=python \
    sh /src/ops/e2e/install_apps.sh /src/apps/phong-ho-so /src/apps/chung-nhan

cd /src
python -m pytest -p no:cacheprovider -m e2e tests/e2e -v -rs --junitxml=/out/e2e-junit.xml
