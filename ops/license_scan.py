# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Quét giấy phép gói bên thứ ba (Plan 04 Task 1): gói Python trong venv hiện tại và gói npm trong lockfile.

    python ops/license_scan.py [--npm-lock package-lock.json] [--allow-file LICENSES-THIRD-PARTY.md]

Thoát 0 nếu sạch, 1 nếu có vi phạm (mỗi vi phạm một dòng trên stderr, kèm tên gói và giấy phép).

Danh sách cho phép (Plan 01): MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, PSF-2.0, ISC. Ngoài danh sách chỉ
được qua nếu tên gói nằm trong bảng của phần "Ngoại lệ đã duyệt" trong LICENSES-THIRD-PARTY.md (trưởng nhóm
duyệt):

    | Hệ | Gói | Giấy phép | Phạm vi | Lý do |

- Hệ `python`: miễn theo tên gói (ví dụ pypdfium2, giấy phép ghép).
- Hệ `npm`: miễn theo tên gói **và** đúng giấy phép ghi trong bảng, chỉ cho mục `dev` của lockfile (chỉ dùng
  lúc build/test, không vào bundle). Gói chạy thật (không `dev`) phải thuộc danh sách cho phép.
Phần khác của tệp không có hiệu lực miễn.

Phạm vi quét Python mặc định là bao đóng phụ thuộc runtime của bốn gói dxos-* (đúng cái được cài vào
image và máy người dùng); công cụ phát triển như `reuse` (GPL) nằm ngoài. `--all-python` quét mọi dist.
Đọc giấy phép bằng importlib.metadata: `License-Expression`, rồi `License`, rồi classifier `License ::`.
Chỉ dùng thư viện chuẩn (CI cài venv chỉ có phụ thuộc runtime).

    python ops/license_scan.py --freeze-runtime   # in `Tên==phiên bản` của bao đóng runtime (constraints.txt)
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

ALLOWED = {"mit", "bsd-2-clause", "bsd-3-clause", "apache-2.0", "psf-2.0", "isc"}
TEAM = {"dxos-proof", "dxos-core", "dxos-witness", "dxos-cli"}
SECTION = "Ngoại lệ đã duyệt"

# Chuỗi `License` kiểu cũ (tự do) và classifier về id SPDX.
ALIASES = {
    "mit": "MIT", "mit license": "MIT", "the mit license": "MIT",
    "bsd": "BSD-3-Clause", "bsd license": "BSD-3-Clause", "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause", "3-clause bsd license": "BSD-3-Clause", "new bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause", "bsd 2-clause": "BSD-2-Clause", "simplified bsd license": "BSD-2-Clause",
    "apache": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0", "apache software license 2.0": "Apache-2.0",
    "psf": "PSF-2.0", "psfl": "PSF-2.0", "psf-2.0": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "isc": "ISC", "isc license": "ISC", "isc license (iscl)": "ISC",
}
CLASSIFIERS = {
    "MIT License": "MIT", "ISC License (ISCL)": "ISC", "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause", "Python Software Foundation License": "PSF-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0", "MIT No Attribution License (MIT-0)": "MIT-0",
}
GENERIC = {"", "unknown", "dual license", "dual-licensed", "see license file", "see license", "license",
           "multiple licenses", "various"}


class Waiver(NamedTuple):
    ecosystem: str      # "python" | "npm"
    name: str           # python: tên chuẩn hóa; npm: tên gói
    license: str


class Violation(NamedTuple):
    ecosystem: str
    name: str
    version: str
    license: str
    reason: str

    def line(self) -> str:
        return f"VI PHẠM {self.ecosystem} {self.name} {self.version}: {self.license} ({self.reason})"


def canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ---- biểu thức SPDX ---------------------------------------------------------------------------------------

def spdx_allowed(expr: str) -> bool:
    """OR: một nhánh đạt là đủ; AND: mọi nhánh phải đạt; `WITH <ngoại lệ>` không đổi kết quả của id."""
    tokens = re.findall(r"\(|\)|[^\s()]+", expr)
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def atom() -> bool:
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("thiếu id")
        pos += 1
        if tok == "(":
            value = or_expr()
            if peek() != ")":
                raise ValueError("thiếu )")
            pos += 1
            return value
        if tok == ")" or tok.upper() in {"AND", "OR", "WITH"}:
            raise ValueError(tok)
        if (peek() or "").upper() == "WITH":
            pos += 2
        return tok.lower().rstrip("+") in ALLOWED

    def and_expr() -> bool:
        nonlocal pos
        value = atom()
        while (peek() or "").upper() == "AND":
            pos += 1
            value = atom() and value
        return value

    def or_expr() -> bool:
        nonlocal pos
        value = and_expr()
        while (peek() or "").upper() == "OR":
            pos += 1
            value = and_expr() or value
        return value

    try:
        value = or_expr()
    except ValueError:
        return False
    return value and pos == len(tokens)


# ---- bảng ngoại lệ ----------------------------------------------------------------------------------------

def parse_exceptions(text: str) -> list[Waiver]:
    waivers: list[Waiver] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("#"):
            in_section = line.lstrip("#").strip() == SECTION
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() not in {"python", "npm"}:
            continue                                    # dòng tiêu đề, dòng kẻ
        eco, name = cells[0].lower(), cells[1].strip("`").strip()
        waivers.append(Waiver(eco, canon(name) if eco == "python" else name, cells[2]))
    return waivers


# ---- Python -----------------------------------------------------------------------------------------------

def _judge(dist: md.Distribution) -> tuple[bool, str]:
    """(đạt?, giấy phép để hiển thị)."""
    meta = dist.metadata
    expr = (meta.get("License-Expression") or "").strip()
    if expr:
        return spdx_allowed(expr), expr
    lic = (meta.get("License") or "").strip()
    short = lic if len(lic) <= 100 and "\n" not in lic else ""     # trường dài thường là cả văn bản giấy phép
    if short.lower() not in GENERIC:
        norm = ALIASES.get(short.lower(), short)
        return spdx_allowed(norm), short
    shown, ok = [], True
    for cls in meta.get_all("Classifier") or []:
        if not cls.startswith("License ::"):
            continue
        label = cls.rsplit("::", 1)[-1].strip()
        spdx = CLASSIFIERS.get(label, label)
        shown.append(spdx)
        ok = ok and spdx_allowed(spdx)
    if not shown:
        return False, short or "(không khai giấy phép)"
    return ok, " + ".join(shown)


def _requires(dist: md.Distribution, extras: frozenset[str]) -> list[tuple[str, frozenset[str]]]:
    out = []
    for raw in dist.requires or []:
        spec, _, marker = raw.partition(";")
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?", spec)
        if not m:
            continue
        wanted = {canon(e) for e in re.findall(r"""extra\s*==\s*['"]([^'"]+)['"]""", marker)}
        if wanted and not (wanted & extras):
            continue                                    # phụ thuộc của một extra không được yêu cầu
        sub = frozenset(canon(e) for e in (m.group(2) or "").split(",") if e.strip())
        out.append((canon(m.group(1)), sub))
    return out


def load_dists(paths: list[str] | None) -> dict[str, md.Distribution]:
    dists: dict[str, md.Distribution] = {}
    for d in md.distributions(path=paths) if paths else md.distributions():
        name = d.metadata["Name"]
        if name:
            dists.setdefault(canon(name), d)
    return dists


def runtime_closure(dists: dict[str, md.Distribution]) -> list[md.Distribution]:
    """Bao đóng phụ thuộc runtime của gói dxos-* có mặt, không gồm chính các gói dxos-*. Điều kiện marker (hệ
    điều hành, phiên bản Python) không được loại trừ: đếm dư còn hơn bỏ sót; gói không cài thì bỏ qua."""
    visited: set[tuple[str, frozenset[str]]] = set()
    queue: list[tuple[str, frozenset[str]]] = [(t, frozenset()) for t in sorted(TEAM) if t in dists]
    while queue:
        key = queue.pop()
        name, extras = key
        if key in visited or name not in dists:
            continue
        visited.add(key)
        queue.extend(_requires(dists[name], extras))
    names = {n for n, _ in visited} - TEAM
    return [dists[n] for n in sorted(names)]


def scan_python(dists: dict[str, md.Distribution], waivers: list[Waiver], *, everything: bool = False
                ) -> tuple[list[Violation], int]:
    chosen = ([d for n, d in sorted(dists.items()) if n not in TEAM]
              if everything else runtime_closure(dists))
    by_name = {w.name for w in waivers if w.ecosystem == "python"}
    violations = []
    for d in chosen:
        ok, shown = _judge(d)
        if not ok and canon(d.metadata["Name"]) not in by_name:
            violations.append(Violation("python", d.metadata["Name"], d.version, shown,
                                        'ngoài danh sách cho phép và chưa có trong "Ngoại lệ đã duyệt"'))
    return violations, len(chosen)


# ---- npm --------------------------------------------------------------------------------------------------

def scan_npm(lock: Path, waivers: list[Waiver]) -> tuple[list[Violation], int]:
    packages = json.loads(lock.read_text(encoding="utf-8")).get("packages", {})
    approved = {(w.name, w.license) for w in waivers if w.ecosystem == "npm"}
    approved_names = {w.name for w in waivers if w.ecosystem == "npm"}
    violations, scanned = [], 0
    for key, info in packages.items():
        if key == "" or info.get("link"):
            continue                                    # gốc workspace và liên kết tới gói của đội
        scanned += 1
        name = info.get("name") or key.rsplit("node_modules/", 1)[-1]
        lic = info.get("license")
        version = info.get("version", "?")
        if lic is None:
            violations.append(Violation("npm", name, version, "(thiếu)", "lockfile không có trường license"))
        elif not isinstance(lic, str):
            violations.append(Violation("npm", name, version, json.dumps(lic), "license không phải chuỗi"))
        elif spdx_allowed(lic):
            continue
        elif (name, lic) in approved and info.get("dev"):
            continue
        elif name in approved_names and not info.get("dev"):
            violations.append(Violation("npm", name, version, lic, "ngoại lệ chỉ cho gói dev"))
        elif name in approved_names:
            violations.append(Violation("npm", name, version, lic, "giấy phép khác với giấy phép đã duyệt"))
        else:
            violations.append(Violation("npm", name, version, lic,
                                        'ngoài danh sách cho phép và chưa có trong "Ngoại lệ đã duyệt"'))
    return violations, scanned


# ---- dòng lệnh --------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(
        description="Quét giấy phép gói npm và gói Python; phạm vi Python mặc định là bao đóng phụ thuộc "
        "runtime của bốn gói dxos-* (công cụ dev nằm ngoài, --all-python để quét hết)")
    ap.add_argument("--npm-lock", type=Path, default=repo / "package-lock.json")
    ap.add_argument("--allow-file", type=Path, default=repo / "LICENSES-THIRD-PARTY.md")
    ap.add_argument("--python-path", action="append",
                    help="thư mục chứa *.dist-info thay cho sys.path (lặp lại được; dùng trong test)")
    ap.add_argument("--all-python", action="store_true",
                    help="quét mọi dist trong môi trường, không chỉ runtime")
    ap.add_argument("--no-python", action="store_true")
    ap.add_argument("--no-npm", action="store_true")
    ap.add_argument("--freeze-runtime", action="store_true",
                    help="in `Tên==phiên bản` của bao đóng runtime rồi thoát (sinh constraints.txt)")
    args = ap.parse_args(argv)

    dists = load_dists(args.python_path)
    if args.freeze_runtime:
        pins = sorted((d.metadata["Name"], d.version) for d in runtime_closure(dists))
        for name, version in sorted(pins, key=lambda p: canon(p[0])):
            print(f"{name}=={version}")
        return 0

    waivers = parse_exceptions(args.allow_file.read_text(encoding="utf-8"))
    violations: list[Violation] = []
    if not args.no_python:
        found, count = scan_python(dists, waivers, everything=args.all_python)
        violations += found
        scope = "mọi dist" if args.all_python else "bao đóng runtime của dxos-*"
        print(f"python: đã quét {count} gói ({scope}), {len(found)} vi phạm")
    if not args.no_npm:
        found, count = scan_npm(args.npm_lock, waivers)
        violations += found
        print(f"npm: đã quét {count} gói trong {args.npm_lock.name}, {len(found)} vi phạm")
    for v in violations:
        print(v.line(), file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
