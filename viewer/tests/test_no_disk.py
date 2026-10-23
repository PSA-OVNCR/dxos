# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Viewer không bao giờ ghi đĩa (Plan 04 Task 7; P4-D6, ràng buộc chung): test tĩnh quét mã nguồn và test chạy
thật chặn mọi lần mở tệp để ghi trong một lần dựng trang."""

import ast
import builtins
import os
from pathlib import Path

import pytest
from dxos_viewer import render
from viewer_helpers import make_pdf

SRC = Path(__file__).resolve().parents[1] / "src" / "dxos_viewer"
FORBIDDEN_MODULES = {"tempfile", "shutil", "sqlite3", "dbm", "shelve", "pickle", "mmap"}
FORBIDDEN_ATTRS = {"write_bytes", "write_text", "mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
                   "SpooledTemporaryFile", "TemporaryDirectory", "touch", "save", "FPDF_SaveAsCopy",
                   "FPDF_SaveWithVersion"}
OS_ATTRS = {"makedirs", "mkdir", "rename", "replace", "remove", "unlink", "symlink", "rmdir", "truncate"}
FORBIDDEN_CALLS = {"open"}                       # open(...) bất kỳ chế độ nào: Viewer không có lý do mở tệp


def violations(source: str, name: str = "<mem>") -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source, name)):
        where = f"{name}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Import):
            found += [f"{where} import {a.name}" for a in node.names
                      if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in FORBIDDEN_MODULES:
            found.append(f"{where} from {node.module}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            found.append(f"{where} .{node.attr}")
        elif (isinstance(node, ast.Attribute) and node.attr in OS_ATTRS
              and isinstance(node.value, ast.Name) and node.value.id == "os"):
            found.append(f"{where} os.{node.attr}")          # str.replace / list.remove không bị tính
        elif isinstance(node, ast.Call):
            func = node.func
            called = (func.id if isinstance(func, ast.Name)
                      else func.attr if isinstance(func, ast.Attribute) else "")
            if called in FORBIDDEN_CALLS:
                found.append(f"{where} {called}()")
    return found


def test_static_scan_finds_nothing_in_viewer_src():
    files = sorted(SRC.glob("*.py"))
    assert {f.name for f in files} >= {"app.py", "render.py", "png.py", "settings.py", "__init__.py"}
    assert [v for f in files for v in violations(f.read_text(encoding="utf-8"), f.name)] == []


@pytest.mark.parametrize("snippet", [
    "import tempfile", "from tempfile import mkstemp", "import shutil", "open('x', 'w')",
    "io.open('x', 'wb')", "Path('x').open('w')", "Path('x').write_bytes(b'')", "p.write_text('')",
    "os.makedirs('x')", "doc.save(f)",
    "os.rename(a, b)", "tempfile.NamedTemporaryFile()", "import sqlite3", "open('x')",
])
def test_scanner_catches_known_offenders(snippet):
    assert violations(snippet), snippet


@pytest.mark.parametrize("snippet",
                         ["s.replace('a', 'b')", "items.remove(1)", "os.environ.get('X')", "x = 1"])
def test_scanner_ignores_harmless_code(snippet):
    assert violations(snippet) == []


def test_no_disk_writes(monkeypatch):
    """Một lần dựng trang đầy đủ, chặn open() ghi, os.open ghi và os.mkdir/rename/remove."""
    attempts = []
    real_open, real_os_open = builtins.open, os.open

    def guard_open(file, mode="r", *args, **kwargs):
        if set(str(mode)) & set("wax+"):
            attempts.append(("open", file, mode))
            raise AssertionError(f"ghi đĩa: open({file!r}, {mode!r})")
        return real_open(file, mode, *args, **kwargs)

    def guard_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            attempts.append(("os.open", path, flags))
            raise AssertionError(f"ghi đĩa: os.open({path!r})")
        return real_os_open(path, flags, *args, **kwargs)

    def forbid(name):
        def inner(*a, **k):
            attempts.append((name, a))
            raise AssertionError(f"ghi đĩa: {name}")
        return inner

    data = make_pdf(pages=2, text="Hop dong")                       # dựng trước khi chặn
    monkeypatch.setattr(builtins, "open", guard_open)
    monkeypatch.setattr(os, "open", guard_os_open)
    for name in ("mkdir", "makedirs", "rename", "replace", "remove", "unlink", "symlink"):
        monkeypatch.setattr(os, name, forbid(f"os.{name}"))
    import tempfile
    monkeypatch.setattr(tempfile, "mkstemp", forbid("mkstemp"))
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbid("NamedTemporaryFile"))

    from datetime import UTC, datetime
    assert render.page_count(data) == 2
    png = render.render_page(data, 2, "0f1e2d3c-aaaa", datetime(2026, 12, 10, tzinfo=UTC))
    assert png.startswith(b"\x89PNG")
    assert attempts == []
