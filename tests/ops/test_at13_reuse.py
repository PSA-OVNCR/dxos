# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/at13_reuse.sh`` (Plan 02 Task 15) chạy thật trong một bản sao repo tạm, với CLI ``dxos`` thật trước
API quản trị giả (``fake_admin``), ``docker`` giả và ``python -m pytest`` giả (lần chạy thật là việc của
VPS).

Kiểm logic của script: kiểm image trước khi cài, so ảnh chụp trước/sau, ``git diff`` của ``core/`` và gateway,
kết quả e2e, và chỉ trả 0 khi mọi thứ giống hệt.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "ab" * 32
IMAGE = f"ghcr.io/psa-ovncr/trust-core@sha256:{DIGEST}"

FAKE_DOCKER = r"""#!/bin/sh
# docker giả: inspect / image inspect / exec theo biến FAKE_*
case "$1" in
  inspect)
    case "$3" in
      '{{.Config.Image}}') echo "$FAKE_IMAGE" ;;
      '{{.Image}}') echo "sha256:1111" ;;
      '{{.State.StartedAt}}')
        n=$(cat "$FAKE_STATE/count" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE_STATE/count"
        if [ -n "${FAKE_RESTART:-}" ] && [ "$n" -gt 2 ]; then echo 2026-11-02T00:00:00Z
        else echo 2026-11-01T00:00:00Z; fi ;;
    esac ;;
  image) echo "$FAKE_IMAGE" ;;
  exec) echo "${FAKE_SELF_APPROVAL:-false}" ;;
esac
"""

FAKE_PYTHON = r"""#!/bin/sh
# python giả: chỉ thay "python -m pytest ..." (e2e), còn lại chạy python thật.
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
  if [ -n "${FAKE_COMMIT_CORE:-}" ]; then
    echo "# đổi lõi" >> core/x.py && git add core/x.py && git -c user.name=t -c user.email=t@t commit -qm core
  fi
  exit "${FAKE_E2E_RC:-0}"
fi
exec "$REAL_PYTHON" "$@"
"""


@pytest.fixture
def repo(tmp_path):
    """Bản sao tối thiểu của repo (script, app B, cấu hình gateway, core/) trong một git repo mới."""
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("cần git và bash")
    r = tmp_path / "repo"
    for rel in ["ops/at13_reuse.sh", "ops/e2e/install_apps.sh", "apps/chung-nhan", "deploy/apisix",
                "deploy/caddy"]:
        src, dst = ROOT / rel, r / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    (r / "core").mkdir()
    (r / "core/x.py").write_text("# lõi\n", encoding="utf-8")
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(r)], check=True)  # noqa: S603, S607
    subprocess.run([*git, "add", "-A"], check=True)  # noqa: S603
    subprocess.run([*git, "commit", "-qm", "init"], check=True)  # noqa: S603
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("fakepython", FAKE_PYTHON)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (tmp_path / "state").mkdir()
    return r, bin_dir


def _run(repo, server: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    r, bin_dir = repo
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DXOS_", "FAKE_", "AT13_"))}
    base.update({
        "PATH": f"{bin_dir}{os.pathsep}{base['PATH']}", "PYTHON": str(bin_dir / "fakepython"),
        "REAL_PYTHON": sys.executable, "FAKE_IMAGE": IMAGE, "FAKE_STATE": str(tmp_path / "state"),
        "DXOS_TRUST_CORE_DIGEST": DIGEST, "DXOS_SERVER": server, "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
        "DXOS_TOKEN": "tok-member-a", "DXOS_APPROVER_TOKEN": "tok-member-b",
        "AT13_OUT": str(tmp_path / "at13-reuse.txt"), **env})
    return subprocess.run(["bash", str(r / "ops/at13_reuse.sh")], env=base, capture_output=True,  # noqa: S603, S607
                          text=True, check=False, timeout=180)


def _posts(state) -> list[tuple[str, str]]:
    return [(p, tok) for m, p, tok in state.calls if m == "POST"]


def test_unchanged_stack_passes_and_writes_comparison_table(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert state.apps[("chung-nhan", "1.1.0")]["status"] == "ACTIVE"
    assert _posts(state) == [("/admin/v1/apps", "tok-member-a"),
                             ("/admin/v1/apps/chung-nhan:approve", "tok-member-b")]
    text = (tmp_path / "at13-reuse.txt").read_text(encoding="utf-8")
    assert "KẾT QUẢ: ĐẠT" in text and "(rỗng)" in text and "| KHÁC |" not in text
    for key in ("trust-core-api.repo_digests", "trust-core-worker.started_at",
                "sha256:deploy/caddy/Caddyfile",
                "sha256:deploy/apisix/apisix.yaml", "git.head"):
        assert f"| {key} |" in text, key
    assert IMAGE in text
    assert "tok-member" not in out.stdout + out.stderr + text                   # không in token


def test_restarted_core_container_fails(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path, FAKE_RESTART="1")
    assert out.returncode != 0
    text = (tmp_path / "at13-reuse.txt").read_text(encoding="utf-8")
    assert "KẾT QUẢ: KHÔNG ĐẠT" in text
    assert any(line.startswith("| trust-core-worker.started_at |") and line.endswith("| KHÁC |")
               for line in text.splitlines())


def test_commit_to_core_during_install_fails(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path, FAKE_COMMIT_CORE="1")
    assert out.returncode != 0
    text = (tmp_path / "at13-reuse.txt").read_text(encoding="utf-8")
    assert "core/x.py" in text and "KẾT QUẢ: KHÔNG ĐẠT" in text


def test_failing_app_b_e2e_fails(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path, FAKE_E2E_RC="1")
    assert out.returncode != 0
    assert "KẾT QUẢ: KHÔNG ĐẠT" in (tmp_path / "at13-reuse.txt").read_text(encoding="utf-8")


def test_unreleased_image_is_refused_before_install(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path, FAKE_IMAGE="dxos-trust-core-api:latest")
    assert out.returncode == 1 and "compose.release.yaml" in out.stderr
    assert _posts(state) == []


def test_self_approval_enabled_is_refused(repo, fake_admin, tmp_path):
    state, server = fake_admin
    out = _run(repo, server, tmp_path, FAKE_SELF_APPROVAL="true")
    assert out.returncode == 1 and "DXOS_ALLOW_SELF_APPROVAL" in out.stderr
    assert _posts(state) == []


def test_app_b_already_active_is_refused(repo, fake_admin, tmp_path):
    state, server = fake_admin
    state.apps[("chung-nhan", "1.1.0")] = {"status": "ACTIVE", "by": "x"}
    out = _run(repo, server, tmp_path)
    assert out.returncode == 1 and "đã ACTIVE từ trước" in out.stderr
    assert _posts(state) == []
