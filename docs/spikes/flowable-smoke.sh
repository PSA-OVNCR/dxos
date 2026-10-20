#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
# Chạy smoke Flowable trong mạng net-wf của stack đang chạy (make up). Dòng cuối: SMOKE OK.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
PY_IMAGE=$(grep -m1 -o 'python:3.12-slim@sha256:[0-9a-f]*' deploy/compose.yaml)
docker run --rm --network dxos_net-wf \
  -e FLOWABLE_REST_PASSWORD -e FLOWABLE_REST_USER="${FLOWABLE_REST_USER:-rest-admin}" \
  -v "$PWD/docs/spikes:/spike:ro" "$PY_IMAGE" python /spike/flowable_smoke.py
