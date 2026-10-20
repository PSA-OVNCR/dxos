# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: tệp mẫu và fake clamd (dùng lại deploy/fake-av/fake_av.py)."""

import base64
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = ROOT / "core/tests/fixtures/files"


def fixture(name: str) -> bytes:
    return (FILES / name).read_bytes()


def eicar() -> bytes:
    """Chuỗi thử EICAR, giải mã lúc chạy (không lưu nguyên văn trong repo)."""
    raw = base64.b64decode((FILES / "eicar.xor5a.b64").read_text(encoding="ascii").strip())
    return bytes(b ^ 0x5A for b in raw)   # XOR để Windows Defender không nhận ra tệp mẫu


def load_fake_av():
    spec = importlib.util.spec_from_file_location("fake_av", ROOT / "deploy/fake-av/fake_av.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
