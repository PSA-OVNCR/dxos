# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Vệ sinh mã web (Tầng 2): không API nguy hiểm, header SPDX, phiên bản npm ghim chính xác."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Thư mục mã nguồn web (chỉ `src/`, để fixture trong `test/` không bị quét).
SRC_GLOBS = ["sdk/js/src", "verify-portal/app/src", "apps/*/web/src", "examples/*/web/src"]
PACKAGE_GLOBS = ["sdk/js", "verify-portal/app", "apps/*/web", "examples/*/web"]

FORBIDDEN = {
    "v-html": re.compile(r"v-html"),
    "innerHTML": re.compile(r"innerHTML"),
    "insertAdjacentHTML": re.compile(r"insertAdjacentHTML"),
    "outerHTML": re.compile(r"outerHTML"),
    "eval(": re.compile(r"\beval\s*\("),
    "new Function": re.compile(r"\bnew\s+Function\b"),
    "localStorage": re.compile(r"localStorage"),
    "http://": re.compile(r"http://"),
    "https://cdn": re.compile(r"https://cdn"),
}
SPDX_HEAD = ("SPDX-FileCopyrightText: 2026 PSA_OVNCR", "SPDX-License-Identifier: Apache-2.0")
CODE_SUFFIXES = {".ts", ".vue"}


def _dirs(globs):
    return [d for g in globs for d in sorted(ROOT.glob(g)) if d.is_dir()]


def _src_files():
    return [
        f for d in _dirs(SRC_GLOBS) for f in sorted(d.rglob("*"))
        if f.is_file() and f.suffix in CODE_SUFFIXES | {".js", ".mjs", ".css", ".html"}
    ]


def _violations(text):
    return [name for name, rx in FORBIDDEN.items() if rx.search(text)]


def test_scanner_detects_each_forbidden_pattern():
    samples = {
        "v-html": '<div v-html="x"/>',
        "innerHTML": "a.innerHTML = b",
        "insertAdjacentHTML": "a.insertAdjacentHTML()",
        "outerHTML": "a.outerHTML",
        "eval(": "eval(x)",
        "new Function": "new Function('a')",
        "localStorage": "localStorage.getItem('k')",
        "http://": "fetch('http://x')",
        "https://cdn": "https://cdn.example/x.js",
    }
    assert set(samples) == set(FORBIDDEN)
    for name, text in samples.items():
        assert name in _violations(text), name
    assert _violations("const retrieval = 1; // https://dxos.dev/problems/x") == []


def test_web_sources_exist_and_have_no_forbidden_api():
    files = _src_files()
    assert any(f.is_relative_to(ROOT / "sdk/js/src") for f in files), "không tìm thấy sdk/js/src"
    bad = {str(f.relative_to(ROOT)): v for f in files if (v := _violations(f.read_text(encoding="utf-8")))}
    assert bad == {}


def test_every_ts_and_vue_file_has_team_spdx_header():
    missing = []
    for f in _src_files():
        if f.suffix not in CODE_SUFFIXES:
            continue
        head = "\n".join(f.read_text(encoding="utf-8").splitlines()[:5])
        if not all(line in head for line in SPDX_HEAD):
            missing.append(str(f.relative_to(ROOT)))
    assert missing == []


def test_npm_versions_are_pinned_exactly():
    workspace_manifests = [d / "package.json" for d in _dirs(PACKAGE_GLOBS) if (d / "package.json").is_file()]
    manifests = [ROOT / "package.json", *workspace_manifests]
    assert len(manifests) >= 2
    loose = []
    for m in manifests:
        data = json.loads(m.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for name, version in data.get(section, {}).items():
                if version.startswith(("^", "~")):
                    loose.append(f"{m.relative_to(ROOT)}: {name} {version}")
    assert loose == []


# Slug chỉ quản trị (contract-tier2.md mục 8 "Admin only"): SDK Tầng 2 không cần câu tiếng Việt cho chúng.
ADMIN_ONLY_SLUGS = {
    "manifest-invalid", "app-version-not-found", "version-not-newer", "install-in-progress",
    "app-version-conflict", "deployment-mismatch", "app-version-not-pending", "idp-admin-unavailable",
}
# Nơi lõi dựng problem+json: ProblemError(status, "slug"...), problem(status, "slug"...),
# _conflict("slug"...) và refuse(reason, "slug"...) của R-1; ngoài ra HTTP_SLUGS mặc định và slug dự phòng
# của errors.py.
_SLUG_SOURCES = [
    re.compile(r'ProblemError\(\s*[^,()]+,\s*"([a-z0-9-]+)"'),
    re.compile(r'(?<![\w.])problem\(\s*\d+,\s*"([a-z0-9-]+)"'),
    re.compile(r'(?<!\w)_conflict\(\s*"([a-z0-9-]+)"'),
    re.compile(r'refuse\(\s*"[a-z_]+",\s*"([a-z0-9-]+)"'),
    re.compile(r'HTTP_SLUGS\.get\([^)]*"([a-z0-9-]+)"\)'),
]


def _raised_slugs():
    slugs = set()
    for f in (ROOT / "core/src").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for rx in _SLUG_SOURCES:
            slugs |= set(rx.findall(text))
    errors_py = (ROOT / "core/src/dxos_core/errors.py").read_text(encoding="utf-8")
    table = re.search(r"HTTP_SLUGS[^=]*=\s*\{(.*?)\}", errors_py, re.S)
    assert table, "không đọc được HTTP_SLUGS"
    slugs |= set(re.findall(r':\s*"([a-z0-9-]+)"', table.group(1)))
    return slugs


def _core_slugs_in_sdk():
    text = (ROOT / "sdk/js/src/vue/messages.ts").read_text(encoding="utf-8")
    block = re.search(r"CORE_SLUGS\s*=\s*\[(.*?)\]\s*as const", text, re.S)
    assert block, "không tìm thấy CORE_SLUGS trong messages.ts"
    return re.findall(r"'([a-z0-9-]+)'", re.sub(r"//[^\n]*", "", block.group(1)))


def test_sdk_core_slugs_match_the_problems_the_core_raises():
    raised = _raised_slugs() - ADMIN_ONLY_SLUGS
    assert len(raised) > 40, "regex không bắt đủ slug: kiểm tra lại _SLUG_SOURCES"
    in_sdk = _core_slugs_in_sdk()
    assert len(in_sdk) == len(set(in_sdk)), "CORE_SLUGS có slug trùng"
    assert set(in_sdk) == raised, {
        "thiếu trong SDK": sorted(raised - set(in_sdk)),
        "thừa trong SDK": sorted(set(in_sdk) - raised),
    }


def test_admin_only_slugs_are_really_raised_by_the_core():
    # Chống danh sách loại trừ chết: slug quản trị bị đổi tên thì phải sửa lại ở đây.
    assert ADMIN_ONLY_SLUGS <= _raised_slugs()


def test_only_the_testing_module_imports_vitest():
    imports_vitest = re.compile(r"""['"]vitest['"]""")
    bad = [
        str(f.relative_to(ROOT)) for f in _src_files()
        if f.suffix in CODE_SUFFIXES and f.name != "testing.ts"
        and imports_vitest.search(f.read_text(encoding="utf-8"))
    ]
    assert bad == []
    for entry in ("sdk/js/src/index.ts", "sdk/js/src/vue/index.ts"):
        assert "testing" not in (ROOT / entry).read_text(encoding="utf-8"), entry
