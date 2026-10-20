# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Image trust-core (dùng chung cho trust-core-api và trust-core-worker).
# Build từ thư mục gốc repo (cần libs/dxos-proof):
#   docker build -f core/Dockerfile -t dxos-trust-core .
# Tệp bỏ qua khi build: core/Dockerfile.dockerignore.

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DXOS_MIGRATIONS_DIR=/opt/dxos/migrations

COPY libs/dxos-proof /tmp/src/dxos-proof
COPY core /tmp/src/core
RUN pip install /tmp/src/dxos-proof /tmp/src/core \
 && mkdir -p /opt/dxos \
 && cp -r /tmp/src/core/migrations /opt/dxos/migrations \
 && install -m 0755 /tmp/src/core/docker/api-entrypoint.sh /usr/local/bin/dxos-api-entrypoint \
 && rm -rf /tmp/src \
 && useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin dxos

# Không chạy bằng root.
USER 10001:10001
WORKDIR /opt/dxos
EXPOSE 8000

# Mặc định là API; trust-core-worker ghi đè command thành `python -m dxos_core.worker`.
CMD ["dxos-api-entrypoint"]
