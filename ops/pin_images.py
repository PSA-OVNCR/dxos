# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ghim mọi image trong deploy/ bằng digest `@sha256:` (Plan 01 Global Constraints).

Tìm `image: <ref>` và `probe_image: <ref>` trong deploy/**/*.yaml và `FROM <ref>`
trong deploy/**/Dockerfile, và dòng `NODE_IMAGE=<ref>` / `PLAYWRIGHT_IMAGE=<ref>` trong ops/*.sh (image của
`make web-build` và `make web-live`, Plan 03 Task 10), và image `anchore/syft`, `zricethezav/gitleaks`
trong lệnh `docker run` của .github/workflows/*.yml (Plan 04 Task 1); tham chiếu nào chưa có digest thì hỏi
registry rồi ghi lại thành `<ref>@sha256:...`. Cần Docker có buildx (Docker Desktop có sẵn).

    python ops/pin_images.py            # ghim các ref chưa ghim
    python ops/pin_images.py --dry-run  # chỉ liệt kê

In ra bảng digest để chép vào LICENSES-THIRD-PARTY.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PATTERNS = [
    ("*.yaml", re.compile(r"^(?P<lead>\s*(?:image|probe_image):\s*)(?P<ref>[^\s#!][^\s#]*)", re.M)),
    ("Dockerfile", re.compile(r"^(?P<lead>FROM\s+)(?P<ref>[^\s#]+)", re.M | re.I)),
    ("*.sh", re.compile(r"^(?P<lead>(?:NODE|PLAYWRIGHT)_IMAGE=)(?P<ref>[^\s#]+)", re.M)),
    # .github/workflows/*.yml: chỉ hai image công cụ chạy bằng `docker run ... <image>:<tag>` (Plan 04).
    ("*.yml", re.compile(
        r"^(?P<lead>.*?\bdocker run\b[^\n]*?[ \t])"
        r"(?P<ref>(?:anchore/syft|zricethezav/gitleaks):[^\s\"']+)", re.M)),
]


def _files(root: Path):
    for glob, rx in PATTERNS:
        for path in sorted(root.rglob(glob)):
            yield path, rx


def _unpinned(ref: str) -> bool:
    return "@sha256:" not in ref and ref.lower() not in {"null", "scratch"}


def find_refs(root: Path) -> list[tuple[Path, str]]:
    found = []
    for path, rx in _files(root):
        for m in rx.finditer(path.read_text(encoding="utf-8")):
            if _unpinned(m["ref"]):
                found.append((path, m["ref"]))
    return found


def docker_resolver(ref: str) -> str:
    cmd = ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Manifest}}"]
    out = subprocess.run(  # noqa: S603 - lệnh cố định, ref lấy từ tệp trong repo
        cmd, capture_output=True, text=True, encoding="utf-8", check=True, timeout=120
    ).stdout
    return json.loads(out)["digest"]


def pin(root: Path, resolver: Callable[[str], str] = docker_resolver) -> dict[str, str]:
    refs = sorted({ref for _, ref in find_refs(root)})
    digests: dict[str, str] = {}
    for ref in refs:
        digest = resolver(ref)
        if not DIGEST.match(digest):
            raise ValueError(f"digest không hợp lệ cho {ref}: {digest!r}")
        digests[ref] = digest
    for path, rx in _files(root):
        text = path.read_text(encoding="utf-8")
        new = rx.sub(
            lambda m: m["lead"] + m["ref"] + "@" + digests[m["ref"]]
            if m["ref"] in digests else m.group(0),
            text,
        )
        if new != text:
            path.write_text(new, encoding="utf-8", newline="\n")
    return digests


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghim digest image trong deploy/")
    repo = Path(__file__).resolve().parents[1]
    ap.add_argument("--root", type=Path, action="append",
                    help="thư mục cần quét (lặp lại được); mặc định deploy/, ops/ và .github/workflows/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    roots = args.root or [repo / "deploy", repo / "ops", repo / ".github" / "workflows"]
    if args.dry_run:
        for root in roots:
            for path, ref in find_refs(root):
                shown = path.relative_to(repo) if path.is_relative_to(repo) else path.relative_to(root.parent)
                print(f"{shown}: {ref}")
        return 0
    digests: dict[str, str] = {}
    for root in roots:
        digests.update(pin(root))
    print("| Image | Digest |\n|---|---|")
    for ref, d in digests.items():
        print(f"| `{ref}` | `{d}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
