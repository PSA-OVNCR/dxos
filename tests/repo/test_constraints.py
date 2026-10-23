# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""constraints.txt ghim phụ thuộc runtime của các gói Python (Plan 04 Task 1; thêm viewer ở Task 7)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ["libs/dxos-proof", "core", "witness", "cli", "viewer"]
PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==\d+(\.\d+)*((\.post|\.dev|a|b|rc)\d+)?$")


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            pins[_canon(name)] = version
    return pins


def _declared() -> set[str]:
    names = set()
    for pkg in PACKAGES:
        data = tomllib.loads((ROOT / pkg / "pyproject.toml").read_text(encoding="utf-8"))
        for dep in data["project"]["dependencies"]:
            names.add(_canon(re.match(r"[A-Za-z0-9._-]+", dep)[0]))
    return names


def test_every_line_is_an_exact_pin():
    lines = [ln for ln in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    assert len(lines) > 30
    assert [ln for ln in lines if not PIN.match(ln)] == []
    assert len({_canon(ln.split("==")[0]) for ln in lines}) == len(lines)          # không trùng tên


def test_header_has_spdx_and_how_to_regenerate():
    head = (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()[:4]
    # Ghép chuỗi để `reuse lint` không đọc dòng này như thẻ SPDX của chính tệp test.
    assert head[0] == "# SPDX-" + "FileCopyrightText: 2026 PSA_OVNCR"
    assert head[1] == "# SPDX-" + "License-Identifier: Apache-2.0"
    assert "ops/license_scan.py --freeze-runtime" in head[2]


def test_every_declared_dependency_is_pinned():
    declared = _declared() - {"dxos-proof"}                 # dxos-proof cài từ thư mục, không từ PyPI
    assert {"fastapi", "pypdfium2", "httpx", "cryptography", "pyyaml"} <= declared
    assert sorted(declared - set(_pins())) == []


def test_extras_and_transitive_dependencies_are_pinned():
    pins = _pins()
    # uvicorn[standard] và pyjwt[crypto] kéo thêm các gói này; starlette/pydantic là phụ thuộc của fastapi.
    for name in ("uvloop", "httptools", "watchfiles", "websockets", "python-dotenv", "cryptography",
                 "starlette", "pydantic", "pydantic-core", "botocore", "s3transfer", "cffi", "h11",
                 "httpcore"):
        assert name in pins, name


def test_team_and_dev_packages_are_not_pinned_here():
    pins = _pins()
    assert not [n for n in pins if n.startswith("dxos-")]
    assert not {"pytest", "ruff", "reuse", "respx"} & set(pins)


def test_core_dockerfile_installs_with_constraints():
    text = (ROOT / "core/Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"pip install -c /tmp/src/constraints\.txt\b", text)
    assert "COPY constraints.txt /tmp/src/constraints.txt" in text
    ignore = (ROOT / "core/Dockerfile.dockerignore").read_text(encoding="utf-8")
    assert "!constraints.txt" in ignore.splitlines()        # nếu không thì COPY không thấy tệp trong context


def test_dev_install_and_ci_licenses_job_use_constraints():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "-c constraints.txt" in makefile
    assert re.search(r"^licenses:\n\t\$\(PYTHON\) ops/license_scan\.py", makefile, re.M)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = ci.split("\n  licenses:\n", 1)[1].split("\n\n", 1)[0]
    assert "-c constraints.txt" in job
    assert "npm ci" in job and "python ops/license_scan.py" in job
