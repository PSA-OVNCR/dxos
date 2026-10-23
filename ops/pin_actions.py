# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ghim GitHub Actions theo SHA commit (Plan 04 Task 1, an toàn chuỗi cung ứng).

Đổi mọi `uses: owner/repo@vN` trong .github/workflows/*.yml thành `uses: owner/repo@<sha40> # vN`.
SHA lấy bằng

    git ls-remote https://github.com/owner/repo refs/tags/vN refs/tags/vN^{}

(tag có chú thích thì lấy commit đã bóc `^{}`). Bỏ qua `uses` đã là SHA 40 ký tự, action cục bộ (`./...`)
và `docker://...`. Chạy thật là việc V37 trên máy trưởng nhóm; cloud chỉ chạy test với resolver giả.

    python ops/pin_actions.py            # ghim
    python ops/pin_actions.py --dry-run  # chỉ liệt kê, không hỏi mạng, không ghi tệp

Không ghi gì nếu có một action không phân giải được (tất cả hoặc không gì). Chạy lại là no-op.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(
    r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)(?P<action>[^\s@#]+)@(?P<ref>[^\s#]+)"
    r"(?P<tail>[ \t]*(?:#[^\n]*)?)$",
    re.M,
)


def _skip(action: str, ref: str) -> bool:
    return action.startswith(("./", "docker://")) or bool(SHA.match(ref))


def _files(root: Path):
    for pattern in ("*.yml", "*.yaml"):
        yield from sorted(root.glob(pattern))


def find_uses(root: Path) -> list[tuple[Path, str, str]]:
    found = []
    for path in _files(root):
        for m in USES.finditer(path.read_text(encoding="utf-8")):
            if not _skip(m["action"], m["ref"]):
                found.append((path, m["action"], m["ref"]))
    return found


def git_resolver(repo: str, tag: str) -> str:
    # Lệnh cố định; repo và tag lấy từ tệp workflow trong kho, không chạy qua shell.
    cmd = ["git", "ls-remote", f"https://github.com/{repo}", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"]
    out = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=120,
    ).stdout
    refs = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        refs[ref.strip()] = sha.strip()
    sha = refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")
    if not sha:
        raise ValueError(f"{repo}: không có tag {tag} (chỉ ghim được tag, không ghim nhánh)")
    return sha


def pin(root: Path, resolver: Callable[[str, str], str] = git_resolver, *, dry_run: bool = False
        ) -> list[tuple[Path, str, str, str | None]]:
    """Trả về danh sách thay đổi ``(tệp, action, ref cũ, sha)``; ``sha`` là None khi ``dry_run``."""
    changes = [(p, a, r) for p, a, r in find_uses(root)]
    if dry_run:
        return [(p, a, r, None) for p, a, r in changes]
    shas: dict[tuple[str, str], str] = {}
    for _, action, ref in changes:
        repo = "/".join(action.split("/")[:2])                    # owner/repo/đường/dẫn/con -> owner/repo
        if (repo, ref) not in shas:
            sha = resolver(repo, ref)
            if not SHA.match(sha):
                raise ValueError(f"SHA không hợp lệ cho {repo}@{ref}: {sha!r}")
            shas[(repo, ref)] = sha
    writes: dict[Path, str] = {}
    for path in {p for p, _, _ in changes}:
        def rewrite(m: re.Match[str]) -> str:
            if _skip(m["action"], m["ref"]):
                return m.group(0)
            sha = shas["/".join(m["action"].split("/")[:2]), m["ref"]]
            note = m["tail"].strip().lstrip("#").strip()
            comment = f"# {m['ref']} ({note})" if note else f"# {m['ref']}"
            return f"{m['lead']}{m['action']}@{sha} {comment}"

        writes[path] = USES.sub(rewrite, path.read_text(encoding="utf-8"))
    for path, text in writes.items():                             # chỉ ghi khi mọi phân giải đã thành công
        path.write_text(text, encoding="utf-8", newline="\n")
    return [(p, a, r, shas["/".join(a.split("/")[:2]), r]) for p, a, r in changes]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghim GitHub Actions theo SHA commit")
    repo = Path(__file__).resolve().parents[1]
    ap.add_argument("--root", type=Path, default=repo / ".github" / "workflows",
                    help="thư mục workflow (mặc định .github/workflows)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ liệt kê, không hỏi mạng, không ghi tệp")
    args = ap.parse_args(argv)
    try:
        changes = pin(args.root, dry_run=args.dry_run)
    except (ValueError, subprocess.SubprocessError, OSError) as e:
        print(f"Không ghim được, chưa ghi tệp nào: {e}", file=sys.stderr)
        return 1
    for path, action, ref, sha in changes:
        print(f"{path.name}: {action}@{ref}" + (f" -> {sha}" if sha else ""))
    if not changes:
        print("Không có `uses:` nào cần ghim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
