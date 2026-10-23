# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/license_scan.py: quét giấy phép gói Python (importlib.metadata) và gói npm (package-lock.json).

Dist giả dựng trong tmp_path (thư mục ``*.dist-info``) và truyền qua ``--python-path``, nên test không phụ
thuộc những gì đang cài trong venv.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("license_scan", ROOT / "ops/license_scan.py")
license_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(license_scan)

SECTION = "## Ngoại lệ đã duyệt"
HEADER = "| Hệ | Gói | Giấy phép | Phạm vi | Lý do |\n|---|---|---|---|---|\n"


def _allow(tmp_path, rows=(), extra=""):
    """Tệp LICENSES-THIRD-PARTY.md giả; ``rows`` là các dòng bảng của phần "Ngoại lệ đã duyệt"."""
    path = tmp_path / "LICENSES-THIRD-PARTY.md"
    text = "# Thành phần bên thứ ba\n\n| bảng khác | MPL-2.0 |\n\n"
    text += SECTION + "\n\n" + HEADER + "".join(r + "\n" for r in rows) + "\n" + extra
    path.write_text(text, encoding="utf-8")
    return path


def _dist(root, name, version="1.0", *, expr=None, lic=None, classifiers=(), requires=()):
    d = root / f"{name.replace('-', '_')}-{version}.dist-info"
    d.mkdir(parents=True)
    lines = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}"]
    if expr:
        lines.append(f"License-Expression: {expr}")
    if lic:
        lines.append(f"License: {lic}")
    lines += [f"Classifier: {c}" for c in classifiers]
    lines += [f"Requires-Dist: {r}" for r in requires]
    (d / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _py(tmp_path, allow=None, *extra):
    """Chạy ``main`` chỉ phần Python trên dist giả trong tmp_path/site."""
    allow = allow or _allow(tmp_path)
    return license_scan.main(
        ["--no-npm", "--python-path", str(tmp_path / "site"), "--allow-file", str(allow), *extra])


def _lock(tmp_path, packages):
    lock = tmp_path / "package-lock.json"
    body = {"name": "x", "lockfileVersion": 3, "packages": {"": {"name": "x"}, **{
        f"node_modules/{n}": v for n, v in packages.items()}}}
    lock.write_text(json.dumps(body), encoding="utf-8")
    return lock


def _npm(tmp_path, lock, allow=None):
    allow = allow or _allow(tmp_path)
    return license_scan.main(["--no-python", "--npm-lock", str(lock), "--allow-file", str(allow)])


# ---- Python ---------------------------------------------------------------------------------------------

def test_python_dists_outside_allowlist_fail(tmp_path, capsys):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", expr="Apache-2.0", requires=["evilpkg>=1", "goodpkg"])
    _dist(site, "evilpkg", "2.1", expr="GPL-3.0-only")
    _dist(site, "goodpkg", "1.0", expr="MIT")
    assert _py(tmp_path) == 1
    out = capsys.readouterr()
    assert "evilpkg" in out.out + out.err and "GPL-3.0-only" in out.out + out.err
    assert "goodpkg" not in out.err


def test_python_permissive_licences_pass_in_every_metadata_form(tmp_path, capsys):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", expr="Apache-2.0", requires=[
        "a-expr", "b-or", "c-legacy", "d-classifier", "e-psf", "f-dual", "g-and"])
    _dist(site, "a-expr", expr="BSD-3-Clause")
    _dist(site, "b-or", expr="Apache-2.0 OR GPL-2.0-only")                     # một nhánh OR đạt là đủ
    _dist(site, "c-legacy", lic="MIT License")
    _dist(site, "d-classifier", classifiers=["License :: OSI Approved :: Apache Software License"])
    _dist(site, "e-psf", lic="PSFL")
    _dist(site, "f-dual", lic="Dual License",
          classifiers=["License :: OSI Approved :: BSD License", "License :: OSI Approved :: MIT License"])
    _dist(site, "g-and", expr="(MIT AND ISC)")
    assert _py(tmp_path) == 0
    assert "7" in capsys.readouterr().out                                       # số gói đã quét


def test_python_and_expression_needs_every_part(tmp_path):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["mixed"])
    _dist(site, "mixed", expr="MIT AND GPL-2.0-only")
    assert _py(tmp_path) == 1


def test_python_unknown_licence_fails(tmp_path, capsys):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["mystery"])
    _dist(site, "mystery")
    assert _py(tmp_path) == 1
    assert "mystery" in capsys.readouterr().err


def test_pypdfium2_compound_licence_is_allowed_by_name(tmp_path):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["pypdfium2"])
    _dist(site, "pypdfium2", "5.14.0", lic="BSD-3-Clause, Apache-2.0, dependency licenses")
    assert _py(tmp_path, _allow(tmp_path)) == 1                                 # chưa có tên trong bảng: hỏng
    allow = _allow(tmp_path, ["| python | `pypdfium2` | giấy phép ghép | runtime | trưởng nhóm duyệt |"])
    assert _py(tmp_path, allow) == 0


def test_python_scope_is_runtime_closure_unless_all(tmp_path, capsys):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["good", "extra-only; extra == 'tls'"])
    _dist(site, "good", expr="MIT")
    _dist(site, "extra-only", expr="MIT")
    _dist(site, "dev-tool", expr="GPL-3.0-or-later")                  # có cài nhưng không ai phụ thuộc
    assert _py(tmp_path) == 0
    assert "dev-tool" not in capsys.readouterr().out
    assert _py(tmp_path, None, "--all-python") == 1


def test_python_extras_are_followed_only_when_requested(tmp_path):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["uvicorn[standard]"])
    _dist(site, "uvicorn", expr="BSD-3-Clause", requires=["fastloop; extra == 'standard'"])
    _dist(site, "fastloop", expr="AGPL-3.0-only")
    assert _py(tmp_path) == 1                                                   # extra standard được yêu cầu


def test_team_packages_are_not_checked(tmp_path):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0")                                           # không khai giấy phép
    assert _py(tmp_path) == 0


def test_freeze_runtime_lists_pins_of_the_closure(tmp_path, capsys):
    site = tmp_path / "site"
    _dist(site, "dxos-core", "0.3.0", requires=["PyJWT"])
    _dist(site, "PyJWT", "2.15.1", expr="MIT")
    _dist(site, "dev-tool", "9.9", expr="MIT")
    assert license_scan.main(["--freeze-runtime", "--python-path", str(site)]) == 0
    assert capsys.readouterr().out.splitlines() == ["PyJWT==2.15.1"]


# ---- npm ------------------------------------------------------------------------------------------------

BUILD_ONLY = {
    "lightningcss": "MPL-2.0", "glob": "BlueOak-1.0.0", "@csstools/color-helpers": "MIT-0",
    "mdn-data": "CC0-1.0",
}


def _build_only_lock(tmp_path):
    return _lock(tmp_path, {n: {"version": "1.0.0", "license": lic, "dev": True}
                            for n, lic in BUILD_ONLY.items()})


def _rows(names=BUILD_ONLY):
    return [f"| npm | `{n}` | {BUILD_ONLY[n]} | dev | chỉ build/test (V30) |" for n in names]


def test_build_only_npm_exceptions_pass(tmp_path, capsys):
    lock = _build_only_lock(tmp_path)
    assert _npm(tmp_path, lock, _allow(tmp_path, _rows())) == 0
    # Không có tên trong bảng ngoại lệ thì hỏng, và báo đúng tên.
    assert _npm(tmp_path, lock, _allow(tmp_path)) == 1
    err = capsys.readouterr().err
    for name in BUILD_ONLY:
        assert name in err
    # Thiếu đúng một gói thì chỉ gói đó bị báo.
    assert _npm(tmp_path, lock, _allow(tmp_path, _rows(["lightningcss", "glob", "mdn-data"]))) == 1
    assert "@csstools/color-helpers" in capsys.readouterr().err


def test_runtime_npm_must_be_permissive(tmp_path, capsys):
    lock = _lock(tmp_path, {"lightningcss": {"version": "1.0.0", "license": "MPL-2.0"}})   # không dev
    assert _npm(tmp_path, lock, _allow(tmp_path)) == 1
    assert _npm(tmp_path, lock, _allow(tmp_path, _rows(["lightningcss"]))) == 1      # ngoại lệ chỉ cho dev
    assert "lightningcss" in capsys.readouterr().err


def test_npm_exception_is_bound_to_its_licence(tmp_path):
    lock = _lock(tmp_path, {"lightningcss": {"version": "2.0.0", "license": "AGPL-3.0", "dev": True}})
    assert _npm(tmp_path, lock, _allow(tmp_path, _rows(["lightningcss"]))) == 1   # đổi giấy phép: duyệt lại


def test_npm_permissive_and_workspace_links_pass(tmp_path, capsys):
    lock = _lock(tmp_path, {
        "a": {"version": "1.0.0", "license": "MIT"},
        "b": {"version": "1.0.0", "license": "(MIT OR Apache-2.0)", "dev": True},
        "c": {"version": "1.0.0", "license": "ISC"},
        "dxos-sdk-js": {"resolved": "sdk/js", "link": True},
    })
    assert _npm(tmp_path, lock) == 0
    assert "3" in capsys.readouterr().out                                            # a, b, c; link bị bỏ


def test_npm_missing_licence_fails(tmp_path, capsys):
    lock = _lock(tmp_path, {"nolicence": {"version": "1.0.0"}})
    assert _npm(tmp_path, lock) == 1
    assert "nolicence" in capsys.readouterr().err


def test_pending_section_grants_nothing(tmp_path):
    """Gói còn "chờ duyệt" nằm ngoài phần "Ngoại lệ đã duyệt" thì không được miễn."""
    lock = _lock(tmp_path, {"tslib": {"version": "2.8.1", "license": "0BSD", "dev": True}})
    pending = ("## Chờ trưởng nhóm duyệt\n\n" + HEADER +
               "| npm | `tslib` | 0BSD | dev | chưa duyệt |\n")
    assert _npm(tmp_path, lock, _allow(tmp_path, extra=pending)) == 1


# ---- tệp thật của kho --------------------------------------------------------------------------------------

def test_repo_approved_exceptions_cover_the_v30_licences():
    """Mọi gói npm giấy phép MPL-2.0, BlueOak-1.0.0, MIT-0, CC0-1.0 trong lockfile thật đều có trong bảng
    ngoại lệ đã duyệt (V30), và chỉ gói dev."""
    exceptions = license_scan.parse_exceptions((ROOT / "LICENSES-THIRD-PARTY.md").read_text(encoding="utf-8"))
    violations, scanned = license_scan.scan_npm(ROOT / "package-lock.json", exceptions)
    v30 = {"MPL-2.0", "BlueOak-1.0.0", "MIT-0", "CC0-1.0"}
    assert scanned > 100
    assert [v for v in violations if v.license in v30] == []
    assert any(e.ecosystem == "python" and e.name == "pypdfium2" for e in exceptions)
    listed = {e.name for e in exceptions if e.ecosystem == "npm"}
    assert {"lightningcss", "glob", "minimatch", "lru-cache", "mdn-data"} <= listed


def test_repo_lockfile_passes_with_the_approved_table():
    """Lockfile thật của kho đạt với bảng "Ngoại lệ đã duyệt" thật (npm không phụ thuộc môi trường)."""
    assert license_scan.main(["--no-python"]) == 0
