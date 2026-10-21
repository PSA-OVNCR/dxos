# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture của test CLI ``dxos``. Không import ``dxos_core`` (wheel riêng); chỉ đọc tệp mẫu của lõi."""

import re
from pathlib import Path

import pytest

CORE_FIXTURES = Path(__file__).resolve().parents[2] / "core" / "tests" / "fixtures"
MANIFEST_TEXT = (CORE_FIXTURES / "manifest-test-flow.yaml").read_text(encoding="utf-8")
BPMN_BYTES = (CORE_FIXTURES / "bpmn" / "test-review.bpmn").read_bytes()

# Nội dung 202 của POST /admin/v1/apps (task-12-report.md).
SUBMITTED = {
    "app_id": "test-flow",
    "version": "0.1.0",
    "status": "PENDING",
    "manifest_sha256": "ab" * 32,
    "files": {"bpmn/test-review.bpmn": "cd" * 32},
}


def MANIFEST_WITH_BPMN_PATH(path: str) -> str:  # noqa: N802 - tên theo hợp đồng C9
    """Văn bản manifest test-flow với ``workflow.bpmn`` thay bằng ``path`` (đã trích dẫn an toàn)."""
    quoted = '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'
    text, n = re.subn(r"(?m)^(  bpmn: ).*$", lambda m: m.group(1) + quoted, MANIFEST_TEXT)
    assert n == 1
    return text


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    """Thư mục app tạm: manifest.yaml của test-flow và bpmn/test-review.bpmn (chép từ core/tests/fixtures)."""
    root = tmp_path / "app"
    (root / "bpmn").mkdir(parents=True)
    (root / "manifest.yaml").write_text(MANIFEST_TEXT, encoding="utf-8")
    (root / "bpmn" / "test-review.bpmn").write_bytes(BPMN_BYTES)
    return root


@pytest.fixture
def token_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Đặt DXOS_TOKEN giả (dùng được cho mọi server) và cô lập XDG_CONFIG_HOME; trả về giá trị token."""
    monkeypatch.setenv("DXOS_TOKEN", "dummy-token-value")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return "dummy-token-value"


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch: pytest.MonkeyPatch):
    """Không ngủ thật khi thử lại hoặc chờ device flow; trả về danh sách các lần ngủ để test kiểm tra."""
    sleeps: list[float] = []
    monkeypatch.setattr("dxos_cli.client.sleep", sleeps.append, raising=False)
    monkeypatch.setattr("dxos_cli.auth.sleep", sleeps.append, raising=False)
    return sleeps
