# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Gói dxos-viewer: đúng bốn phụ thuộc, chỉ import thư viện cho phép, Dockerfile đúng chuẩn (P4-D1, P4-D6)."""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "viewer" / "src" / "dxos_viewer"
ALLOWED_THIRD_PARTY = {"fastapi", "starlette", "httpx", "pypdfium2", "uvicorn", "dxos_viewer"}


def test_exactly_four_runtime_dependencies():
    data = tomllib.loads((ROOT / "viewer/pyproject.toml").read_text(encoding="utf-8"))
    names = {re.match(r"[A-Za-z0-9._-]+", d)[0].lower() for d in data["project"]["dependencies"]}
    assert names == {"fastapi", "uvicorn", "httpx", "pypdfium2"}
    assert data["project"]["name"] == "dxos-viewer" and data["project"]["version"] == "0.9.0"
    assert any(d.startswith("uvicorn[standard]") for d in data["project"]["dependencies"])


def test_every_dependency_is_pinned_in_constraints():
    lines = (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines()
    pins = {line.split("==")[0].lower() for line in lines if line and not line.startswith("#")}
    assert {"fastapi", "uvicorn", "httpx", "pypdfium2"} <= pins


def test_viewer_imports_only_allowed_libraries_and_never_core_or_storage():
    stdlib = sys.stdlib_module_names
    seen = set()
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                seen |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                seen.add((node.module or "").split(".")[0])
    third_party = {m for m in seen if m not in stdlib}
    assert third_party <= ALLOWED_THIRD_PARTY, sorted(third_party - ALLOWED_THIRD_PARTY)
    assert not {"dxos_core", "boto3", "asyncpg", "psycopg", "jwt", "yaml"} & seen


def test_dockerfile_same_base_digest_constraints_and_non_root():
    docker = (ROOT / "viewer/Dockerfile").read_text(encoding="utf-8")
    core = (ROOT / "core/Dockerfile").read_text(encoding="utf-8")
    base = re.search(r"^FROM (python:3\.12-slim@sha256:[0-9a-f]{64})$", core, re.M)[1]
    assert f"FROM {base}\n" in docker
    assert re.search(r"pip install -c /tmp/src/constraints\.txt\b", docker)
    assert "COPY constraints.txt /tmp/src/constraints.txt" in docker
    user = re.findall(r"^USER (\S+)$", docker, re.M)
    assert user and user[-1] not in {"root", "0", "0:0"}
    assert "PYTHONDONTWRITEBYTECODE=1" in docker                      # chạy được trên hệ tệp gốc chỉ đọc
    ignore = (ROOT / "viewer/Dockerfile.dockerignore").read_text(encoding="utf-8").splitlines()
    assert "!constraints.txt" in ignore and "!viewer/" in ignore
