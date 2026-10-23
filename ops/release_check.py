# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm trước khi phát hành (Plan 04 Task 2). Chỉ đọc: không sửa tệp, không gắn nhãn phát hành, không đẩy gì.

    python ops/release_check.py X.Y.Z [--no-fetch]

Kiểm, theo đúng BUILD.md mục "Phát hành":
1. `version = "X.Y.Z"` trong pyproject.toml của 4 gói và `__version__ = "X.Y.Z"` trong 3 tệp `__init__.py`;
2. CHANGELOG.md có dòng `## [X.Y.Z] - YYYY-MM-DD` (đã ghi ngày);
3. cây làm việc sạch (`git status --porcelain` rỗng);
4. `HEAD` đúng là `origin/main` (chạy `git fetch origin main` trước, bỏ qua bằng --no-fetch).

Thoát 0 nếu đạt cả bốn, 1 nếu có chỗ lệch (mỗi chỗ một dòng trên stderr), 2 nếu đối số sai.
Việc gắn nhãn là của trưởng nhóm, ngoài script này.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECTS = (
    "libs/dxos-proof/pyproject.toml", "core/pyproject.toml", "witness/pyproject.toml", "cli/pyproject.toml",
)
INITS = (
    "core/src/dxos_core/__init__.py", "witness/src/dxos_witness/__init__.py", "cli/src/dxos_cli/__init__.py",
)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def check_versions(root: Path, version: str) -> list[str]:
    problems = []
    for rel, pattern in [(f, f'version = "{version}"') for f in PYPROJECTS] + [
        (f, f'__version__ = "{version}"') for f in INITS
    ]:
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        if pattern not in lines:
            problems.append(f'{rel} không có dòng {pattern}')
    return problems


def check_changelog(root: Path, version: str) -> list[str]:
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", text, re.M):
        return [f"CHANGELOG.md: không có mục '## [{version}] - YYYY-MM-DD' (chưa ghi ngày hoặc thiếu mục)"]
    return []


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # lệnh git cố định, tham số do script đặt
    return subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False  # noqa: S607
    )


def check_git(root: Path, fetch: bool = True) -> list[str]:
    problems = []
    status = _git(root, "status", "--porcelain")
    if status.returncode != 0:
        return [f"git status lỗi: {status.stderr.strip()}"]
    if status.stdout.strip():
        problems.append("cây làm việc chưa sạch (git status --porcelain không rỗng)")
    if fetch:
        got = _git(root, "fetch", "origin", "main")
        if got.returncode != 0:
            problems.append(f"git fetch origin main lỗi: {got.stderr.strip()}")
            return problems
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    origin = _git(root, "rev-parse", "origin/main")
    if origin.returncode != 0:
        problems.append("không có origin/main để so")
    elif head != origin.stdout.strip():
        problems.append(f"HEAD ({head[:7]}) không phải origin/main ({origin.stdout.strip()[:7]})")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("version", help="X.Y.Z, không có chữ v")
    ap.add_argument("--no-fetch", action="store_true", help="không git fetch (dùng origin/main đã có)")
    args = ap.parse_args(argv)
    if not SEMVER.match(args.version):
        print(f"phiên bản '{args.version}' không có dạng X.Y.Z", file=sys.stderr)
        return 2
    problems = (
        check_versions(ROOT, args.version)
        + check_changelog(ROOT, args.version)
        + check_git(ROOT, fetch=not args.no_fetch)
    )
    for p in problems:
        print(f"release-check {args.version}: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"release-check {args.version}: đạt (4 pyproject, 3 __init__, CHANGELOG có ngày, "
          "cây sạch, HEAD = origin/main)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
