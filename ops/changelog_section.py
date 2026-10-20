# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""In mục ``## [<version>]`` của CHANGELOG.md (dùng làm mô tả GitHub Release).

    python ops/changelog_section.py 0.1.0 > notes.md
Không có mục cho phiên bản đó thì thoát mã 1 (release phải có ghi chú).
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(text: str, version: str) -> str | None:
    head = re.compile(rf"^## \[{re.escape(version)}\][^\n]*$", re.M)
    m = head.search(text)
    if not m:
        return None
    nxt = re.compile(r"^## \[", re.M).search(text, m.end())
    return text[m.start(): nxt.start() if nxt else len(text)].strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("cách dùng: changelog_section.py <version>", file=sys.stderr)
        return 2
    out = section(CHANGELOG.read_text(encoding="utf-8"), argv[0].lstrip("v"))
    if out is None:
        print(f"CHANGELOG.md không có mục [{argv[0]}]", file=sys.stderr)
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
