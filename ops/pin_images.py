# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ghim mọi image trong deploy/ bằng digest `@sha256:` (Plan 01 Global Constraints).

Tìm `image: <ref>` và `probe_image: <ref>` trong deploy/**/*.yaml và `FROM <ref>`
trong deploy/**/Dockerfile; tham chiếu nào chưa có digest thì hỏi registry rồi
ghi lại thành `<ref>@sha256:...`. Cần Docker có buildx (Docker Desktop có sẵn).

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
        cmd, capture_output=True, text=True, check=True, timeout=120
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
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "deploy")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.dry_run:
        for path, ref in find_refs(args.root):
            print(f"{path.relative_to(args.root)}: {ref}")
        return 0
    digests = pin(args.root)
    print("| Image | Digest |\n|---|---|")
    for ref, d in digests.items():
        print(f"| `{ref}` | `{d}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
