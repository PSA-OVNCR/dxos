# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/build_web.sh`` (Plan 03 Task 10) chạy thật trong một bản sao repo tạm, với ``npm`` giả đặt đầu PATH.

Kiểm: ``npm ci`` trước ``npm run build``; chép đúng ba thư mục dist (danh sách cố định); ``BUILD-INFO.json``;
build vào ``OUT.tmp`` rồi mới thay ``OUT`` (một bước lỗi thì ``OUT`` cũ còn nguyên); chạy được khi ``OUT`` là
điểm gắn (volume Docker, không đổi tên được).
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/build_web.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"
ALL_OUT = ["BUILD-INFO.json", "chung-nhan", "phong-ho-so", "verify"]
DISTS = {"phong-ho-so": "apps/phong-ho-so/web/dist", "chung-nhan": "apps/chung-nhan/web/dist",
         "verify": "verify-portal/app/dist"}

# npm giả: ghi lời gọi vào $FAKE_LOG; `run build` tạo dist cho từng workspace (trừ FAKE_SKIP_DIST/FAKE_FAIL).
FAKE_NPM = r"""#!/bin/sh
echo "npm $* | VITE_ANCHOR_RAW_BASE=${VITE_ANCHOR_RAW_BASE:-}" >> "$FAKE_LOG"
case "$1" in
  ci) [ "${FAKE_FAIL:-}" = ci ] && { echo "npm ci lỗi" >&2; exit 7; } ; exit 0 ;;
  run)
    [ "${FAKE_FAIL:-}" = build ] && { echo "build lỗi" >&2; exit 9; }
    for d in apps/phong-ho-so/web apps/chung-nhan/web verify-portal/app; do
      [ "${FAKE_SKIP_DIST:-}" = "$d" ] && continue
      mkdir -p "$d/dist/assets"
      echo "<!doctype html><title>$d</title>" > "$d/dist/index.html"
      echo "x" > "$d/dist/assets/a.js"
    done
    exit 0 ;;
esac
exit 1
"""


@pytest.fixture
def env(tmp_path):
    if shutil.which("git") is None or shutil.which("sh") is None:
        pytest.skip("cần git và sh")
    repo = tmp_path / "repo"
    (repo / "ops").mkdir(parents=True)
    if SCRIPT.exists():
        shutil.copy2(SCRIPT, repo / "ops/build_web.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npm").write_text(FAKE_NPM, encoding="utf-8")
    (bin_dir / "npm").chmod(0o755)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)  # noqa: S603, S607
    (repo / "README").write_text("x", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)  # noqa: S603
    subprocess.run([*git, "commit", "-qm", "init"], check=True)  # noqa: S603
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603
                          check=True).stdout.strip()
    return repo, bin_dir, tmp_path / "log", head


def _run(env, out: Path, **extra: str) -> subprocess.CompletedProcess:
    repo, bin_dir, log, _ = env
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("DXOS_", "FAKE_", "VITE_"))}
    base.update({"PATH": f"{bin_dir}{os.pathsep}{base['PATH']}", "FAKE_LOG": str(log), **extra})
    return subprocess.run(["sh", str(repo / "ops/build_web.sh"), str(out)], env=base,  # noqa: S603, S607
                          capture_output=True, text=True, check=False, timeout=60, cwd=repo)


def test_npm_ci_runs_before_the_workspace_build(env, tmp_path):
    out = tmp_path / "out"
    r = _run(env, out)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln.split(" | ")[0] for ln in env[2].read_text(encoding="utf-8").splitlines()]
    assert lines == ["npm ci", "npm run build --workspaces --if-present"]


def test_copies_exactly_the_fixed_list_of_dist_folders(env, tmp_path):
    out = tmp_path / "out"
    r = _run(env, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in out.iterdir()) == ALL_OUT
    for name, dist in DISTS.items():
        html = (out / name / "index.html").read_text(encoding="utf-8")
        assert html == f"<!doctype html><title>{dist[:-5]}</title>\n"
        assert (out / name / "assets/a.js").is_file()
    assert not (tmp_path / "out.tmp").exists()                     # thư mục tạm đã được dọn


def test_build_info_has_commit_from_git_and_utc_time(env, tmp_path):
    out = tmp_path / "out"
    assert _run(env, out).returncode == 0
    info = json.loads((out / "BUILD-INFO.json").read_text(encoding="utf-8"))
    assert info["commit"] == env[3]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", info["built_at"])
    assert set(info) == {"commit", "built_at"}


def test_commit_comes_from_env_when_there_is_no_git(env, tmp_path):
    shutil.rmtree(env[0] / ".git")                                 # như /work trong container: không có .git
    out = tmp_path / "out"
    assert _run(env, out, DXOS_BUILD_COMMIT=SHA).returncode == 0
    assert json.loads((out / "BUILD-INFO.json").read_text(encoding="utf-8"))["commit"] == SHA
    bad = _run(env, tmp_path / "out2")                              # không git, không biến: từ chối
    assert bad.returncode != 0 and "DXOS_BUILD_COMMIT" in bad.stderr
    assert not (tmp_path / "out2").exists()


def test_commit_from_env_must_look_like_a_commit(env, tmp_path):
    r = _run(env, tmp_path / "out", DXOS_BUILD_COMMIT='x", "y": "z')
    assert r.returncode != 0 and not (tmp_path / "out").exists()


@pytest.mark.parametrize("step", ["ci", "build"])
def test_failing_step_exits_non_zero_and_leaves_previous_output_untouched(env, tmp_path, step):
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("giữ nguyên", encoding="utf-8")
    r = _run(env, out, FAKE_FAIL=step)
    assert r.returncode != 0
    assert [p.name for p in out.iterdir()] == ["old.txt"]
    assert (out / "old.txt").read_text(encoding="utf-8") == "giữ nguyên"
    assert not (tmp_path / "out.tmp").exists()


def test_missing_dist_folder_fails_without_creating_output(env, tmp_path):
    r = _run(env, tmp_path / "out", FAKE_SKIP_DIST="verify-portal/app")
    assert r.returncode != 0 and "verify-portal/app/dist" in r.stderr
    assert not (tmp_path / "out").exists() and not (tmp_path / "out.tmp").exists()


def test_stale_tmp_folder_and_previous_output_are_replaced(env, tmp_path):
    out, tmp = tmp_path / "out", tmp_path / "out.tmp"
    out.mkdir()
    (out / "old.txt").write_text("cũ", encoding="utf-8")
    tmp.mkdir()
    (tmp / "rác.txt").write_text("dở dang", encoding="utf-8")
    assert _run(env, out).returncode == 0
    assert sorted(p.name for p in out.iterdir()) == ALL_OUT
    assert not tmp.exists()


def test_vite_anchor_base_is_passed_through_to_npm(env, tmp_path):
    base = "https://raw.githubusercontent.com/PSA-OVNCR/dxos-transparency-log/main"
    assert _run(env, tmp_path / "out", VITE_ANCHOR_RAW_BASE=base).returncode == 0
    build = [ln for ln in env[2].read_text(encoding="utf-8").splitlines() if ln.startswith("npm run")]
    assert build == [f"npm run build --workspaces --if-present | VITE_ANCHOR_RAW_BASE={base}"]


def test_relative_out_dir_is_resolved_against_the_caller_cwd(env, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    repo, bin_dir, log, _ = env
    base = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(log)}
    r = subprocess.run(["sh", str(repo / "ops/build_web.sh"), "rel-out"], env=base, cwd=work,  # noqa: S603, S607
                       capture_output=True, text=True, check=False, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (work / "rel-out/BUILD-INFO.json").is_file()


def test_usage_error_without_out_dir(env):
    repo, bin_dir, log, _ = env
    path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    r = subprocess.run(["sh", str(repo / "ops/build_web.sh")], capture_output=True, text=True,  # noqa: S603, S607
                       check=False, timeout=30, env={**os.environ, "PATH": path})
    assert r.returncode == 2 and "out_dir" in r.stderr


def test_output_that_is_a_mount_point_is_refreshed_in_place(env, tmp_path):
    """Volume Docker (``/out``) là điểm gắn, không đổi tên được: nội dung cũ chỉ bị thay khi đã build xong."""
    if os.geteuid() != 0 or shutil.which("mount") is None:
        pytest.skip("cần root và mount để dựng một điểm gắn thật")
    out = tmp_path / "out"
    out.mkdir()
    probe = subprocess.run(["mount", "-t", "tmpfs", "tmpfs", str(out)], capture_output=True)  # noqa: S603, S607
    if probe.returncode != 0:
        pytest.skip("không gắn được tmpfs trong sandbox này")
    try:
        (out / "old.txt").write_text("cũ", encoding="utf-8")
        failed = _run(env, out, FAKE_FAIL="build")
        assert failed.returncode != 0 and (out / "old.txt").is_file()      # lỗi: nội dung cũ còn nguyên
        r = _run(env, out)
        assert r.returncode == 0, r.stdout + r.stderr
        assert sorted(p.name for p in out.iterdir()) == ALL_OUT
        assert not (tmp_path / "out.tmp").exists()
    finally:
        subprocess.run(["umount", str(out)], check=False)  # noqa: S603, S607
