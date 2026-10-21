# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/e2e/install_apps.sh`` (Plan 02 Task 15) chạy thật với CLI ``dxos`` thật, trước API quản trị
giả (``fake_admin`` trong conftest.py): người nộp và người duyệt dùng hai token khác nhau (bốn mắt), chạy lại
thì bỏ qua bản đã ACTIVE."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/e2e/install_apps.sh"


def _run(server: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items() if not k.startswith("DXOS_")}
    base.update({"DXOS_SERVER": server, "XDG_CONFIG_HOME": str(tmp_path / "cfg"), **env})
    return subprocess.run(["sh", str(SCRIPT)], env=base, capture_output=True, text=True,  # noqa: S603, S607
                          check=False, timeout=120)


def test_submitter_and_approver_use_different_tokens_and_both_apps_become_active(fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(server, tmp_path, DXOS_TOKEN="tok-admin1", DXOS_APPROVER_TOKEN="tok-admin2")
    assert out.returncode == 0, out.stdout + out.stderr
    assert {k: v["status"] for k, v in state.apps.items()} == {
        ("phong-ho-so", "1.1.0"): "ACTIVE", ("chung-nhan", "1.1.0"): "ACTIVE"}
    posts = [(p, tok) for m, p, tok in state.calls if m == "POST"]
    assert posts == [("/admin/v1/apps", "tok-admin1"),
                     ("/admin/v1/apps/phong-ho-so:approve", "tok-admin2"),
                     ("/admin/v1/apps", "tok-admin1"),
                     ("/admin/v1/apps/chung-nhan:approve", "tok-admin2")]
    assert "tok-admin" not in out.stdout + out.stderr                       # không bao giờ in token


def test_rerun_skips_active_versions(fake_admin, tmp_path):
    state, server = fake_admin
    assert _run(server, tmp_path, DXOS_TOKEN="t1", DXOS_APPROVER_TOKEN="t2").returncode == 0
    n = len([c for c in state.calls if c[0] == "POST"])
    out = _run(server, tmp_path, DXOS_TOKEN="t1", DXOS_APPROVER_TOKEN="t2")
    assert out.returncode == 0, out.stdout + out.stderr
    assert len([c for c in state.calls if c[0] == "POST"]) == n
    assert out.stdout.count("đã ACTIVE, bỏ qua") == 2


def test_without_approver_token_only_submits_and_prints_approve_command(fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(server, tmp_path, DXOS_TOKEN="t1")
    assert out.returncode == 0, out.stdout + out.stderr
    assert {v["status"] for v in state.apps.values()} == {"PENDING"}
    assert f"dxos --server {server} app approve phong-ho-so 1.1.0" in out.stdout
    assert "còn chờ duyệt: phong-ho-so@1.1.0 chung-nhan@1.1.0" in out.stdout


def test_same_token_for_both_steps_fails_with_cli_exit_1(fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(server, tmp_path, DXOS_TOKEN="same", DXOS_APPROVER_TOKEN="same")
    assert out.returncode == 1, out.stdout + out.stderr
    assert state.apps[("phong-ho-so", "1.1.0")]["status"] == "PENDING"
    assert ("chung-nhan", "1.1.0") not in state.apps            # dừng ngay, không nộp app kế tiếp


def test_cli_network_and_token_exit_codes_are_preserved(fake_admin, tmp_path):
    state, server = fake_admin
    state.list_status = 500
    assert _run(server, tmp_path, DXOS_TOKEN="t1", DXOS_APPROVER_TOKEN="t2").returncode == 2   # 5xx
    state.list_status = 401
    assert _run(server, tmp_path, DXOS_TOKEN="t1", DXOS_APPROVER_TOKEN="t2").returncode == 3   # token sai
    assert [c for c in state.calls if c[0] == "POST"] == []
