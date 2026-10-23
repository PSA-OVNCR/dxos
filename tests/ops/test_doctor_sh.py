# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/doctor.sh`` (Plan 04 Task 16, M5, AT-23): kiểm điều kiện của máy sạch bằng ``docker``, ``ss``,
``node``, ``npm``, ``git``, ``make``, ``python3`` giả. PATH của lệnh chạy chỉ gồm thư mục lệnh giả và các
công cụ cơ bản (liên kết tượng trưng), nên máy chạy test có Docker thật hay không cũng không đổi kết quả.
Chạy thật trên máy Ubuntu 24.04 sạch là việc V45."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/doctor.sh"
SECRET = "S3cr3t-Value-Never-Print-0042"
BASIC_TOOLS = ("bash", "sh", "sed", "awk", "grep", "tr", "sort", "head", "tail", "cat", "cut", "dirname",
               "basename", "uname", "wc", "df", "env", "printf", "tee", "mktemp", "rm", "true", "false", "id")

# Mỗi lệnh giả đọc phiên bản từ biến FAKE_* (mặc định: đủ điều kiện).
FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
case "$*" in
  "version --format {{.Server.Version}}")
    [ -z "${FAKE_DAEMON_DOWN:-}" ] || { echo "Cannot connect to the Docker daemon" >&2; exit 1; }
    echo "${FAKE_DOCKER_VERSION:-27.3.1}" ;;
  "compose version --short")
    [ -z "${FAKE_NO_COMPOSE:-}" ] || { echo "docker: 'compose' is not a docker command." >&2; exit 1; }
    echo "${FAKE_COMPOSE_VERSION:-2.29.7}" ;;
  "ps --filter label=com.docker.compose.project=dxos --filter publish=443 --format {{.Names}}")
    printf '%s' "${FAKE_DXOS_443:-}" ;;
esac
exit 0
"""
FAKE_SS = r"""#!/bin/sh
echo "ss $*" >> "$FAKE_LOG"
[ -z "${FAKE_PORT_443_BUSY:-}" ] || echo "LISTEN 0 4096 0.0.0.0:443 0.0.0.0:*"
exit 0
"""
FAKE_NODE = r"""#!/bin/sh
echo "v${FAKE_NODE_VERSION:-22.22.0}"
"""
FAKE_NPM = r"""#!/bin/sh
echo "${FAKE_NPM_VERSION:-11.6.2}"
"""
FAKE_GIT = r"""#!/bin/sh
echo "git version ${FAKE_GIT_VERSION:-2.43.0}"
"""
FAKE_MAKE = r"""#!/bin/sh
echo "GNU Make 4.3"
"""
FAKE_PYTHON3 = r"""#!/bin/sh
case "$*" in
  --version) echo "Python ${FAKE_PY_VERSION:-3.12.3}" ;;
  *ensurepip*) [ -z "${FAKE_NO_VENV:-}" ] || { echo "No module named ensurepip" >&2; exit 1; } ;;
esac
exit 0
"""
FAKES = {"docker": FAKE_DOCKER, "ss": FAKE_SS, "node": FAKE_NODE, "npm": FAKE_NPM, "git": FAKE_GIT,
         "make": FAKE_MAKE, "python3": FAKE_PYTHON3}


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, log: Path):
        self.proc = proc
        self.log = log

    returncode = property(lambda self: self.proc.returncode)
    out = property(lambda self: self.proc.stdout)
    err = property(lambda self: self.proc.stderr)
    text = property(lambda self: self.proc.stdout + self.proc.stderr)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


@pytest.fixture
def run(tmp_path):
    if shutil.which("bash") is None:
        pytest.skip("cần bash")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in BASIC_TOOLS:
        real = shutil.which(tool)
        if real:
            (bin_dir / tool).symlink_to(real)
    log = tmp_path / "calls.log"
    meminfo = tmp_path / "meminfo"

    def _run(*args: str, missing: tuple[str, ...] = (), ram_mib: int = 16000, **env: str) -> Result:
        for name, body in FAKES.items():
            target = bin_dir / name
            target.unlink(missing_ok=True)
            if name not in missing:
                target.write_text(body, encoding="utf-8")
                target.chmod(0o755)
        meminfo.write_text(f"MemTotal:       {ram_mib * 1024} kB\nMemFree:        1 kB\n", encoding="utf-8")
        log.unlink(missing_ok=True)
        base = {"PATH": str(bin_dir), "HOME": str(tmp_path), "FAKE_LOG": str(log),
                "DXOS_DOCTOR_MEMINFO": str(meminfo), "DXOS_ADMIN_PASSWORD": SECRET,
                "KEYCLOAK_ADMIN_PASSWORD": SECRET, "OPENBAO_CORE_TOKEN": SECRET, **env}
        proc = subprocess.run([str(bin_dir / "bash"), str(SCRIPT), *args], env=base,  # noqa: S603
                              capture_output=True, text=True, check=False, timeout=60, cwd=tmp_path)
        return Result(proc, log)

    return _run


# ---------- đủ điều kiện ----------

def test_all_good_exits_0_and_names_every_check(run):
    r = run()
    assert r.returncode == 0, r.text
    for token in ("Docker 27.3.1", "Compose 2.29.7", "RAM", "443", "Python 3.12.3", "git", "make"):
        assert token in r.out, token
    assert "THIẾU" not in r.out


def test_compose_prefixed_with_v_is_parsed(run):
    r = run(FAKE_COMPOSE_VERSION="v2.24.0")
    assert r.returncode == 0, r.text


def test_boundaries_are_inclusive(run):
    assert run(FAKE_DOCKER_VERSION="24.0.0", FAKE_COMPOSE_VERSION="2.24.0").returncode == 0


# ---------- thiếu / cũ: thoát 3 với thông báo rõ ----------

def test_compose_2_23_exits_3_and_says_why(run):
    r = run(FAKE_COMPOSE_VERSION="2.23.3")
    assert r.returncode == 3
    assert "THIẾU" in r.out and "Compose 2.23.3" in r.out and "2.24" in r.out
    assert "2.23.3" in r.err or "chưa đạt" in r.err


def test_compose_missing_exits_3(run):
    r = run(FAKE_NO_COMPOSE="1")
    assert r.returncode == 3 and "Compose" in r.out and "THIẾU" in r.out


def test_docker_23_exits_3(run):
    r = run(FAKE_DOCKER_VERSION="23.0.6")
    assert r.returncode == 3 and "Docker 23.0.6" in r.out and "24" in r.out


def test_docker_missing_exits_3(run):
    r = run(missing=("docker",))
    assert r.returncode == 3 and "Docker" in r.out and "THIẾU" in r.out
    assert "docs.docker.com/engine/install/ubuntu" in r.out


def test_docker_daemon_down_exits_3_with_group_hint(run):
    r = run(FAKE_DAEMON_DOWN="1")
    assert r.returncode == 3 and "daemon" in r.out.lower()
    assert "usermod -aG docker" in r.out


def test_all_failures_are_listed_not_just_the_first(run):
    r = run(FAKE_DOCKER_VERSION="20.10.0", FAKE_COMPOSE_VERSION="2.10.0", ram_mib=2000)
    assert r.returncode == 3
    assert r.out.count("THIẾU") >= 3
    assert "3 điều kiện" in r.err


def test_python_older_than_3_12_exits_3(run):
    r = run(FAKE_PY_VERSION="3.11.9")
    assert r.returncode == 3 and "Python 3.11.9" in r.out and "3.12" in r.out


def test_python_venv_module_missing_exits_3_with_apt_hint(run):
    r = run(FAKE_NO_VENV="1")
    assert r.returncode == 3 and "python3-venv" in r.out


@pytest.mark.parametrize("tool", ["git", "make", "python3"])
def test_basic_tool_missing_exits_3(run, tool):
    r = run(missing=(tool,))
    assert r.returncode == 3 and "THIẾU" in r.out


# ---------- RAM theo hồ sơ ----------

def test_ram_profile_thresholds(run):
    assert run(ram_mib=16000).returncode == 0                                # p16 mặc định
    assert run(ram_mib=8000).returncode == 3                                 # 8 GB không đủ cho p16
    assert run("--profile", "p8", ram_mib=8000).returncode == 0
    assert run("--profile", "p8", ram_mib=4000).returncode == 3
    assert run("--profile", "dev-lite", ram_mib=8000).returncode == 0


def test_ram_message_shows_measured_and_needed(run):
    r = run(ram_mib=8000)
    assert "8000 MiB" in r.out and "p16" in r.out


def test_unreadable_meminfo_is_a_warning_not_a_failure(run, tmp_path):
    r = run(DXOS_DOCTOR_MEMINFO=str(tmp_path / "nope"))
    assert r.returncode == 0 and "CẢNH BÁO" in r.out


# ---------- cổng 443 ----------

def test_port_443_busy_by_someone_else_exits_3(run):
    r = run(FAKE_PORT_443_BUSY="1")
    assert r.returncode == 3 and "443" in r.out and "THIẾU" in r.out


def test_port_443_held_by_the_dxos_stack_is_fine(run):
    r = run(FAKE_PORT_443_BUSY="1", FAKE_DXOS_443="dxos-caddy-1")
    assert r.returncode == 0 and "stack dxos" in r.out


def test_missing_ss_is_a_warning(run):
    r = run(missing=("ss",))
    assert r.returncode == 0 and "CẢNH BÁO" in r.out


# ---------- Node và npm chỉ khi dựng web ----------

def test_node_not_required_without_web_flag(run):
    assert run(missing=("node", "npm")).returncode == 0


def test_web_flag_accepts_node22_npm_11_6_2(run):
    r = run("--web")
    assert r.returncode == 0 and "Node v22.22.0" in r.out and "npm 11.6.2" in r.out


@pytest.mark.parametrize("node", ["20.18.0", "23.1.0", "24.0.0"])
def test_web_flag_rejects_other_node_majors(run, node):
    r = run("--web", FAKE_NODE_VERSION=node)
    assert r.returncode == 3 and f"Node v{node}" in r.out and "22" in r.out


@pytest.mark.parametrize("npm", ["10.9.2", "11.6.3", "11.6.1"])
def test_web_flag_demands_exactly_npm_11_6_2(run, npm):
    r = run("--web", FAKE_NPM_VERSION=npm)
    assert r.returncode == 3 and f"npm {npm}" in r.out and "npm install -g npm@11.6.2" in r.out


def test_web_flag_missing_node_exits_3(run):
    r = run("--web", missing=("node",))
    assert r.returncode == 3 and "Node" in r.out


# ---------- tham số ----------

@pytest.mark.parametrize("args", [("--profile",), ("--profile", "p4"), ("--bogus",), ("extra",)])
def test_bad_arguments_exit_2_without_calling_docker(run, args):
    r = run(*args)
    assert r.returncode == 2 and "dùng:" in r.err
    assert r.calls() == []


# ---------- không in bí mật, không đổi gì ----------

def test_never_prints_secrets_and_reads_no_env_file(run, tmp_path):
    (tmp_path / ".env").write_text(f"KEYCLOAK_ADMIN_PASSWORD={SECRET}\n", encoding="utf-8")
    for r in (run(), run(FAKE_COMPOSE_VERSION="2.1.0"), run("--web")):
        assert SECRET not in r.text


def test_only_read_only_docker_queries(run):
    r = run("--web")
    allowed = ("docker version", "docker compose version", "docker ps")
    assert r.calls() and all(c.startswith(allowed) for c in r.calls() if c.startswith("docker")), r.calls()


# ---------- tệp script ----------

def test_script_header_syntax_and_shellcheck():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/bash\n")
    assert "SPDX-" + "License-Identifier: Apache-2.0" in text and "set -euo pipefail" in text
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0  # noqa: S603, S607
    if shutil.which("shellcheck"):
        proc = subprocess.run(["shellcheck", "-S", "warning", str(SCRIPT)],  # noqa: S603, S607
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout


def test_script_refuses_nothing_destructive():
    text = SCRIPT.read_text(encoding="utf-8")
    for bad in ("rm -rf", "docker rm", "docker stop", "docker kill", "curl ", "eval "):
        assert bad not in text, bad
    # chỉ GỢI Ý lệnh cài (in ra), không tự chạy: không dòng nào bắt đầu bằng sudo / apt
    assert not [ln for ln in text.splitlines() if ln.lstrip().startswith(("sudo ", "apt ", "apt-get "))]
