# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``DXOS_REQUIRE_CADDY=1`` (đặt ở job ``caddy-live`` của CI) biến "thiếu Caddy" từ bỏ qua thành LỖI, để job
kiểm danh sách IP host quản trị không thể xanh vì bỏ qua (Plan 02 Task 10, fix round 2)."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = "tests/deploy/test_caddy_admin_allowlist_live.py"
# Số test của mô-đun kiểm sống (không ghi cứng: thêm test thì con số tự theo).
N = len(re.findall(r"^def test_", (ROOT / LIVE).read_text(encoding="utf-8"), re.M))


def _run_live(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess:
    """Chạy pytest trên mô-đun kiểm sống trong tiến trình con, không có caddy trên PATH."""
    empty = tmp_path / "empty-path"
    empty.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("CADDY_BIN", "DXOS_REQUIRE_CADDY")}
    env.update(PATH=str(empty), PYTHONDONTWRITEBYTECODE="1", **extra)
    return subprocess.run([sys.executable, "-m", "pytest", LIVE, "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                          env=env, capture_output=True, text=True, timeout=120)


def test_missing_caddy_skips_by_default(tmp_path):
    r = _run_live(tmp_path)
    assert r.returncode == 0 and f"{N} skipped" in r.stdout, r.stdout


def test_missing_caddy_fails_when_required(tmp_path):
    r = _run_live(tmp_path, DXOS_REQUIRE_CADDY="1")
    assert r.returncode != 0 and f"{N} failed" in r.stdout and "skipped" not in r.stdout, r.stdout


def test_unusable_caddy_binary_fails_when_required(tmp_path):
    fake = tmp_path / "caddy"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    r = _run_live(tmp_path, DXOS_REQUIRE_CADDY="1", CADDY_BIN=str(fake))
    assert r.returncode != 0 and f"{N} failed" in r.stdout, r.stdout
    r = _run_live(tmp_path, DXOS_REQUIRE_CADDY="1", CADDY_BIN=str(tmp_path / "không-có"))
    assert r.returncode != 0 and f"{N} failed" in r.stdout, r.stdout
