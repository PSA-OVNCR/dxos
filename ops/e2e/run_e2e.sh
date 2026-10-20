#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Chạy E2E mốc M1 trong một container python:3.12-slim cạnh stack dev-lite (Plan 01 Task 17).
#   docker run --rm -v <repo>:/src:ro -v <thư mục kết quả>:/out -v dxos_anchor-repo:/var/lib/dxos:ro \
#     python:3.12-slim@sha256:... sh /src/ops/e2e/run_e2e.sh
# Cần /out/caddy-root.crt (CA nội bộ của Caddy, lấy bằng `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt`).
set -eu
export PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends git >/dev/null
mkdir -p /tmp/pkgs && cp -r /src/libs/dxos-proof /src/witness /tmp/pkgs/
python -m pip install -q /tmp/pkgs/dxos-proof /tmp/pkgs/witness "pytest>=8" "httpx>=0.27"
git config --global safe.directory '*'

# Tên `localhost` / `admin.localhost` nằm trong issuer của token và chứng chỉ Caddy: trỏ chúng về máy chủ Docker.
GW=$(getent ahostsv4 host.docker.internal | awk 'NR==1 {print $1}')
[ -n "$GW" ] || { echo "không phân giải được host.docker.internal"; exit 3; }
grep -v -E '[[:space:]]localhost([[:space:]]|$)' /etc/hosts > /tmp/hosts || true
echo "$GW localhost admin.localhost" >> /tmp/hosts
cat /tmp/hosts > /etc/hosts
export SSL_CERT_FILE=/out/caddy-root.crt

cd /src
python -m pytest -p no:cacheprovider -m e2e tests/e2e -v --junitxml=/out/e2e-junit.xml
