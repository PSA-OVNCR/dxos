# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/capacity_report.py: đọc CSV của ops/measure.sh, tính đỉnh RAM (AT-22)."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("capacity_report", ROOT / "ops/capacity_report.py")
cr = importlib.util.module_from_spec(_spec)
sys.modules["capacity_report"] = cr
_spec.loader.exec_module(cr)

CSV = """timestamp,source,name,mem
2026-10-20T10:00:00Z,docker,dxos-keycloak-1,600MiB / 15.22GiB
2026-10-20T10:00:00Z,docker,dxos-clamav-1,1.2GiB / 15.22GiB
2026-10-20T10:00:00Z,host,used,3000MiB / 16000MiB
2026-10-20T10:00:05Z,docker,dxos-keycloak-1,650MiB / 15.22GiB
2026-10-20T10:00:05Z,docker,dxos-clamav-1,2.4GiB / 15.22GiB
2026-10-20T10:00:05Z,host,used,4100MiB / 16000MiB
2026-10-20T10:00:10Z,docker,dxos-keycloak-1,700MiB / 15.22GiB
2026-10-20T10:00:10Z,docker,dxos-clamav-1,1.1GiB / 15.22GiB
"""


@pytest.mark.parametrize(("text", "mib"), [
    ("393.4MiB", 393.4), ("1.5GiB", 1536.0), ("512KiB", 0.5), ("0B", 0.0),
    ("100MB", 100e6 / 2**20), ("2GB", 2e9 / 2**20), ("1024kB", 1024e3 / 2**20),
])
def test_parse_mib(text, mib):
    assert cr.parse_mib(text) == pytest.approx(mib)


def test_summary_peaks_per_container_and_total(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(CSV, encoding="utf-8")
    s = cr.summarize(p)
    assert s.peak["dxos-keycloak-1"] == pytest.approx(700)
    assert s.peak["dxos-clamav-1"] == pytest.approx(2.4 * 1024)
    # tổng đỉnh là đỉnh của tổng tại cùng thời điểm, không phải tổng các đỉnh
    assert s.peak_total == pytest.approx(650 + 2.4 * 1024)
    assert s.limit_mib == pytest.approx(15.22 * 1024)
    assert s.host_peak_used == pytest.approx(4100)
    assert s.samples == 3


def test_markdown_flags_threshold(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(CSV, encoding="utf-8")
    md = cr.render(cr.summarize(p), threshold=0.8)
    assert "dxos-clamav-1" in md and "Đạt" in md
    md_fail = cr.render(cr.summarize(p), threshold=0.1)
    assert "KHÔNG đạt" in md_fail
