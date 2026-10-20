# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tổng hợp CSV của ops/measure.sh thành bảng đỉnh RAM cho docs/capacity.md (AT-22).

    python ops/capacity_report.py measure.csv [--threshold 0.8]

CSV: timestamp,source,name,mem
- source=docker: mem là cột MemUsage của `docker stats` ("393.4MiB / 15.22GiB")
- source=host:   mem là "<used>MiB / <total>MiB" lấy từ `free -m`
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_UNITS = {
    "b": 1, "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40,
    "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
}
_RX = re.compile(r"^\s*([0-9.]+)\s*([a-zA-Z]+)\s*$")


def parse_mib(text: str) -> float:
    m = _RX.match(text)
    if not m:
        raise ValueError(f"không đọc được dung lượng: {text!r}")
    return float(m[1]) * _UNITS[m[2].lower()] / 2**20


@dataclass
class Summary:
    peak: dict[str, float] = field(default_factory=dict)
    peak_total: float = 0.0
    peak_total_at: str = ""
    limit_mib: float = 0.0
    host_peak_used: float | None = None
    host_total: float | None = None
    samples: int = 0


def summarize(path: Path) -> Summary:
    s = Summary()
    per_ts: dict[str, float] = defaultdict(float)
    with Path(path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            used, _, total = row["mem"].partition("/")
            used_mib, total_mib = parse_mib(used), parse_mib(total)
            if row["source"] == "docker":
                s.peak[row["name"]] = max(s.peak.get(row["name"], 0.0), used_mib)
                per_ts[row["timestamp"]] += used_mib
                s.limit_mib = max(s.limit_mib, total_mib)
            elif row["source"] == "host":
                s.host_peak_used = max(s.host_peak_used or 0.0, used_mib)
                s.host_total = total_mib
    s.samples = len(per_ts)
    if per_ts:
        s.peak_total_at, s.peak_total = max(per_ts.items(), key=lambda kv: kv[1])
    return s


def render(s: Summary, threshold: float = 0.8) -> str:
    lines = ["| Container | Đỉnh RAM (MiB) |", "|---|---:|"]
    for name, mib in sorted(s.peak.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {mib:,.0f} |")
    limit = s.host_total or s.limit_mib
    used = s.host_peak_used if s.host_peak_used is not None else s.peak_total
    ratio = used / limit if limit else 0.0
    verdict = "Đạt" if ratio < threshold else "KHÔNG đạt"
    lines += [
        "",
        f"- Số mẫu: {s.samples}",
        f"- Tổng RAM container tại thời điểm đỉnh ({s.peak_total_at}): **{s.peak_total:,.0f} MiB**",
    ]
    if s.host_peak_used is not None:
        lines.append(f"- Đỉnh RAM máy (`free -m` used): **{s.host_peak_used:,.0f} MiB**")
    lines.append(
        f"- So với RAM khả dụng {limit:,.0f} MiB: **{ratio:.0%}** "
        f"(ngưỡng AT-22 < {threshold:.0%}) → **{verdict}**"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--threshold", type=float, default=0.8)
    args = ap.parse_args(argv)
    print(render(summarize(args.csv), args.threshold))
    return 0


if __name__ == "__main__":
    sys.exit(main())
