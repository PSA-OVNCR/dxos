#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
# Lấy mẫu RAM mỗi 5 giây (spec 16.2, AT-22): docker stats + free -m.
#   ops/measure.sh <giây> <out.csv>
# Tổng hợp: python ops/capacity_report.py <out.csv>
set -euo pipefail
dur=${1:?cần số giây}; out=${2:?cần tệp CSV}
interval=${MEASURE_INTERVAL:-5}
echo "timestamp,source,name,mem" > "$out"
end=$(( $(date +%s) + dur ))
while [ "$(date +%s)" -lt "$end" ]; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  docker stats --no-stream --format '{{.Name}},{{.MemUsage}}' \
    | sed "s#^#${ts},docker,#" >> "$out"
  free -m | awk -v ts="$ts" '/^Mem:/ {printf "%s,host,used,%sMiB / %sMiB\n", ts, $3, $2}' >> "$out"
  sleep "$interval"
done
echo "đã ghi $(($(wc -l < "$out") - 1)) dòng vào $out"
