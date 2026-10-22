# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/web_build_docker.sh`` và ``ops/web_live.sh`` (Plan 03 Task 10) với ``docker`` giả: kiểm lệnh
``docker run`` được dựng đúng (mount, image ghim, biến môi trường) và script từ chối chạy khi image chưa ghim
digest. Chạy thật trong Docker là việc V27 của máy trưởng nhóm."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "ab" * 32
FAKE_DOCKER = r"""#!/bin/sh
{ for a in "$@"; do printf '%s\037' "$a"; done; printf '\036'; } >> "$FAKE_LOG"
if [ "$1" = compose ]; then
  [ -z "${FAKE_CP_FAIL:-}" ] || exit 1
  for last; do :; done
  echo "-----BEGIN CERTIFICATE-----" > "$last"
fi
exit 0
"""


# Bí mật của stack (``.env`` của VPS, khóa ghi repo neo, digest phát hành) không được chép vào container npm,
# nơi lifecycle script của bên thứ ba chạy với mạng (review cuối Plan 03, I2). Chặn mặc định mọi tệp
# ``.env*``.
SECRET_EXCLUDES = ('".env*"', ".secrets", "deploy/release.env")


def _assert_secrets_not_copied(inner: str, tmp_path: Path) -> None:
    for excluded in SECRET_EXCLUDES:
        assert f"--exclude={excluded} " in inner or f"--exclude={excluded}\n" in inner, excluded
    # Chạy đúng lệnh tar của INNER trên một cây giả: không tệp .env* nào (kể cả tên lạ, kể cả .env.example) và
    # không bí mật nào lọt qua; mã nguồn vẫn còn.
    start = inner.index("tar cf - ")
    end = inner.index("-C /work", start) + len("-C /work")
    src, dst = tmp_path / "tar-src", tmp_path / "tar-dst"
    for rel in (".env", ".env.bak", ".env.vps", ".env.local", ".env.production.local", ".env.example",
                ".secrets/anchor-deploy-key", "deploy/release.env", "deploy/compose.yaml",
                "apps/x/.env", "apps/x/.env.example", "ops/build_web.sh"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x", encoding="utf-8")
    dst.mkdir()
    cmd = inner[start:end].replace("\\\n", " ").replace("-C /work", f"-C {dst}")
    subprocess.run(["sh", "-c", cmd], cwd=src, check=True)  # noqa: S603, S607
    copied = sorted(str(f.relative_to(dst)) for f in dst.rglob("*") if f.is_file())
    assert copied == ["deploy/compose.yaml", "ops/build_web.sh"], copied


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("cần git và bash")
    r = tmp_path / "repo"
    (r / "ops").mkdir(parents=True)
    for name in ("web_build_docker.sh", "web_live.sh"):
        shutil.copy2(ROOT / "ops" / name, r / "ops" / name)
        # Bản sao bắt đầu ở trạng thái chưa ghim (bỏ digest thật nếu repo đã ghim);
        # test tự ghim digest giả khi cần.
        script = r / "ops" / name
        script.write_text(re.sub(r"^((?:NODE|PLAYWRIGHT)_IMAGE=\S+?)@sha256:[0-9a-f]{64}$", r"\1",
                                 script.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    git = ["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(r)], check=True)  # noqa: S603, S607
    (r / "x").write_text("x", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True)  # noqa: S603
    subprocess.run([*git, "commit", "-qm", "init"], check=True)  # noqa: S603
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603
                          check=True).stdout.strip()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (bin_dir / "docker").chmod(0o755)
    return r, bin_dir, tmp_path / "log", head


def _pin(repo_dir: Path, script: str, var: str) -> str:
    """Thay dòng ``VAR=ref`` bằng ``VAR=ref@sha256:<digest>`` (như `make pin-images`); trả về ref đã ghim."""
    path = repo_dir / "ops" / script
    text = path.read_text(encoding="utf-8")
    text, n = re.subn(rf"^({var}=)(\S+)$", rf"\g<1>\g<2>@sha256:{DIGEST}", text, flags=re.M)
    assert n == 1
    path.write_text(text, encoding="utf-8")
    return re.search(rf"^{var}=(\S+)$", text, re.M).group(1)


def _run(env, script: str, **extra: str) -> subprocess.CompletedProcess:
    repo_dir, bin_dir, log, _ = env
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DXOS_", "VITE_", "FAKE_", "ENV_FILE"))}
    base.update({"PATH": f"{bin_dir}{os.pathsep}{base['PATH']}", "FAKE_LOG": str(log), **extra})
    return subprocess.run(["bash", str(repo_dir / "ops" / script)], env=base, capture_output=True,  # noqa: S603, S607
                          text=True, check=False, timeout=60, cwd=repo_dir)


def _calls(log: Path) -> list[list[str]]:
    """Mỗi lời gọi docker là một danh sách đối số (docker giả ghi \\x1f giữa đối số, \\x1e giữa lời gọi)."""
    raw = log.read_text(encoding="utf-8") if log.exists() else ""
    return [rec.split("\x1f")[:-1] for rec in raw.split("\x1e") if rec]


def _run_call(calls: list[list[str]]) -> list[str]:
    runs = [c for c in calls if c[0] == "run"]
    assert len(runs) == 1, calls
    return runs[0]


# ---------- web_build_docker.sh ----------

def test_build_refuses_an_unpinned_node_image(repo):
    r = _run(repo, "web_build_docker.sh")
    assert r.returncode == 3 and "NODE_IMAGE" in r.stderr and "make pin-images" in r.stderr
    assert _calls(repo[2]) == []                                    # không gọi docker


def test_build_runs_one_shot_node_container_into_the_apps_volume(repo):
    image = _pin(repo[0], "web_build_docker.sh", "NODE_IMAGE")
    assert image == f"node:22-bookworm-slim@sha256:{DIGEST}"
    r = _run(repo, "web_build_docker.sh")
    assert r.returncode == 0, r.stdout + r.stderr
    args = _run_call(_calls(repo[2]))
    assert args[:2] == ["run", "--rm"]
    assert f"{repo[0]}:/src:ro" in args and "dxos_apps-static:/out" in args
    assert args.index(image) > args.index("dxos_apps-static:/out")
    assert f"DXOS_BUILD_COMMIT={repo[3]}" in args
    assert not any(a.startswith("VITE_ANCHOR_RAW_BASE") for a in args)
    inner = args[-1]
    assert args[-3:-1] == ["sh", "-c"]
    assert inner.index("npm i -g npm@11.6.2") < inner.index("sh /work/ops/build_web.sh /out")
    for excluded in ("node_modules", ".git", "dist"):
        assert f"--exclude={excluded}" in inner
    _assert_secrets_not_copied(inner, repo[0].parent)
    assert "rm -rf /out" not in inner                      # build_web.sh tự thay /out khi đã build xong


def test_build_passes_vite_anchor_base_from_env_file_and_environment_wins(repo):
    _pin(repo[0], "web_build_docker.sh", "NODE_IMAGE")
    base = "https://raw.githubusercontent.com/PSA-OVNCR/dxos-transparency-log/main"
    (repo[0] / ".env").write_text(
        f"DXOS_ANCHOR_RAW_ORIGIN=https://raw.githubusercontent.com\r\nVITE_ANCHOR_RAW_BASE=\"{base}\"\r\n"
        "OTHER=1\r\n", encoding="utf-8")
    r = _run(repo, "web_build_docker.sh")
    assert r.returncode == 0 and r.stderr == "", r.stdout + r.stderr
    assert f"VITE_ANCHOR_RAW_BASE={base}" in _run_call(_calls(repo[2]))
    repo[2].unlink()
    r = _run(repo, "web_build_docker.sh", VITE_ANCHOR_RAW_BASE="https://example.test/base")
    assert "VITE_ANCHOR_RAW_BASE=https://example.test/base" in _run_call(_calls(repo[2]))


def test_build_warns_when_anchor_base_has_no_csp_origin(repo):
    _pin(repo[0], "web_build_docker.sh", "NODE_IMAGE")
    r = _run(repo, "web_build_docker.sh", VITE_ANCHOR_RAW_BASE="https://example.test/base")
    assert r.returncode == 0 and "DXOS_ANCHOR_RAW_ORIGIN" in r.stderr


def test_build_does_not_execute_the_env_file(repo):
    _pin(repo[0], "web_build_docker.sh", "NODE_IMAGE")
    marker = repo[0].parent / "pwned"
    body = f"VITE_ANCHOR_RAW_BASE=x\ntouch {marker}\n$(touch {marker})\n"
    (repo[0] / ".env").write_text(body, encoding="utf-8")
    assert _run(repo, "web_build_docker.sh").returncode == 0
    assert not marker.exists()


# ---------- web_live.sh ----------

def test_live_refuses_an_unpinned_playwright_image(repo):
    r = _run(repo, "web_live.sh")
    assert r.returncode == 3 and "PLAYWRIGHT_IMAGE" in r.stderr and "make pin-images" in r.stderr
    assert _calls(repo[2]) == []


def test_live_runs_the_suite_in_the_pinned_playwright_container(repo):
    image = _pin(repo[0], "web_live.sh", "PLAYWRIGHT_IMAGE")
    assert image == f"mcr.microsoft.com/playwright:v1.63.0-noble@sha256:{DIGEST}"
    r = _run(repo, "web_live.sh", DXOS_WEB_LIVE_DIR=str(repo[0].parent / "res"))
    assert r.returncode == 0, r.stdout + r.stderr
    calls = _calls(repo[2])
    assert calls[0][:3] == ["compose", "-p", "dxos"] and calls[0][3] == "cp"       # lấy CA của Caddy
    assert (repo[0].parent / "res/caddy-root.crt").is_file()
    args = _run_call(calls)
    for need in ("--add-host=host.docker.internal:host-gateway", "DXOS_WEB_LIVE=1",
                 "NODE_EXTRA_CA_CERTS=/out/caddy-root.crt", "DXOS_SHOT_DIR=/out/shots",
                 "DXOS_WEB_LIVE_OUT=/out",
                 f"{repo[0]}:/src:ro", f"{repo[0].parent / 'res'}:/out"):
        assert need in args, need
    assert image in args
    inner = args[-1]
    assert "host.docker.internal" in inner and "/etc/hosts" in inner and "DXOS_GATEWAY_IP" in inner
    assert inner.index("npm ci") < inner.index("playwright test -c tests/web/live")
    _assert_secrets_not_copied(inner, repo[0].parent)


def test_live_stops_when_the_caddy_ca_cannot_be_read(repo):
    _pin(repo[0], "web_live.sh", "PLAYWRIGHT_IMAGE")
    r = _run(repo, "web_live.sh", FAKE_CP_FAIL="1", DXOS_WEB_LIVE_DIR=str(repo[0].parent / "res"))
    assert r.returncode == 3 and "CA của Caddy" in r.stderr
    assert not any(c[0] == "run" for c in _calls(repo[2]))


def test_repo_scripts_have_pinned_images():
    """V35 đã chạy (22/10/2026): image của hai script trong repo phải ghim digest (nếu không: thoát mã 3)."""
    for name, var in (("web_build_docker.sh", "NODE_IMAGE"), ("web_live.sh", "PLAYWRIGHT_IMAGE")):
        text = (ROOT / "ops" / name).read_text(encoding="utf-8")
        assert re.search(rf"^{var}=\S+@sha256:[0-9a-f]{{64}}$", text, re.M), name


def test_build_commit_lookup_works_under_git_bash():
    """Git Bash + MSYS_NO_PATHCONV=1: `git -C /e/...` hỏng trên Windows; script phải `cd` rồi mới gọi git."""
    text = (ROOT / "ops" / "web_build_docker.sh").read_text(encoding="utf-8")
    assert 'git -C "$REPO"' not in text
    assert '$(cd "$REPO" && git rev-parse HEAD)' in text

