# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tra vệ sinh kho mã phục vụ tiêu chí PoF (TL tr.2–3)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    "LICENSE", "NOTICE", "README.md", "README_EN.md", "CHANGELOG.md", "BUILD.md",
    "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
    "LICENSES-THIRD-PARTY.md", "REUSE.toml", ".gitattributes", ".env.example", "Makefile",
]


def test_required_files_exist():
    missing = [f for f in REQUIRED if not (ROOT / f).is_file()]
    assert missing == []


def test_gitattributes_forces_lf():
    assert "* text=auto eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_license_is_apache_2():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0, January 2004" in text


def test_env_example_has_no_real_secret():
    """Biến bí mật chỉ mang giá trị giữ chỗ `changeme...`; cấu hình thường (tên miền) được phép có giá trị."""
    secret_key = re.compile(r"PASSWORD|SECRET|_KEY$")
    url_password = re.compile(r"://[^:/@]+:([^@]+)@")
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if secret_key.search(key):
            assert value == "" or value.startswith(("changeme", "<")), line
        m = url_password.search(value)
        if m:
            assert m.group(1).startswith("changeme"), line
