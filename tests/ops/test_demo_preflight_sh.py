# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/demo_preflight.sh`` (Plan 04 Task 16, M5): checklist 60 phút trước giờ demo (Plan 00 mục 10,
spec 16.4, ``docs/runbook-openbao.md`` mục 5) với ``docker`` và ``curl`` giả đặt đầu PATH, trong một bản
sao repo tạm có ``.env``. Mọi lời gọi được ghi vào một tệp log. Chạy thật trước buổi demo là việc V48."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/demo_preflight.sh"
RUNBOOK = ROOT / "docs/runbook-openbao.md"
DOMAIN = "dxos.example.test"
SECRET = "S3cr3t-Value-Never-Print-0042"
ENV = (f"DXOS_DOMAIN={DOMAIN}\nDXOS_ADMIN_HOST=admin.{DOMAIN}\nDXOS_ANCHOR_REMOTE=git@github.com:o/log.git\n"
       f"KEYCLOAK_ADMIN_PASSWORD={SECRET}\nOPENBAO_CORE_TOKEN={SECRET}\n")
BASIC_TOOLS = ("bash", "sh", "sed", "awk", "grep", "tr", "sort", "head", "tail", "cat", "cut", "dirname",
               "basename", "wc", "env", "mktemp", "rm", "true", "false", "tee")
HEALTHY = (
    "dxos-caddy-1|Up 5 hours\n"
    "dxos-trust-core-api-1|Up 5 hours (healthy)\n"
    "dxos-trust-core-worker-1|Up 5 hours (healthy)\n"
    "dxos-openbao-1|Up 5 hours (healthy)\n"
    "dxos-core-db-1|Up 5 hours (healthy)\n"
    "dxos-web-build-1|Exited (0) 5 hours ago\n"
)
KEYS = '{"seal-key":{"1":"AAAA"},"sth-key":{"1":"BBBB"},"statements":{"seal-key":{}}}'
STH = '{"tree_size":42,"root_hash":"' + "ab" * 32 + '","ts":"2026-10-23T00:00:00+00:00","key_version":1}'

FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
case "$*" in
  *"bao status"*)
    case "${FAKE_BAO:-unsealed}" in
      unsealed) echo '{"initialized": true, "sealed": false, "t": 1}' ;;
      sealed) echo '{"initialized": true, "sealed": true, "t": 1}'; exit 2 ;;
      error) echo "Error checking seal status" >&2; exit 1 ;;
      garbage) echo 'hello' ;;
    esac ;;
  "ps -a --filter label=com.docker.compose.project=dxos --format {{.Names}}|{{.Status}}")
    printf '%s' "${FAKE_PS-}" ;;
  *"trust-core-api python -c"*)
    [ -z "${FAKE_READYZ_FAIL:-}" ] || { echo "urllib.error.HTTPError: 503" >&2; exit 1; }
    echo "${FAKE_READYZ:-200}" ;;
  *"core-db psql"*)
    case "$*" in
      *anchors*) echo "${FAKE_ANCHOR_MAX:-42}" ;;
      *records*) printf '%s' "${FAKE_DEMO_ROWS-}" ;;
    esac ;;
esac
exit 0
"""
FAKE_CURL = r"""#!/bin/sh
echo "curl $*" >> "$FAKE_LOG"
for last; do :; done
case "$last" in
  */verify/v1/keys) [ -z "${FAKE_KEYS_FAIL:-}" ] || exit 22; printf '%s' "${FAKE_KEYS_BODY:-}" ;;
  */verify/v1/sth/latest) [ -z "${FAKE_STH_FAIL:-}" ] || exit 22; printf '%s' "${FAKE_STH_BODY:-}" ;;
  https://github.com*) [ -z "${FAKE_NET_FAIL:-}" ] || exit 6 ;;
esac
exit 0
"""


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


class Stubs:
    def __init__(self) -> None:
        self.env: str | None = ENV
        self.cwd: Path | None = None
        self.vars = {"FAKE_PS": HEALTHY, "FAKE_KEYS_BODY": KEYS, "FAKE_STH_BODY": STH,
                     "FAKE_DEMO_ROWS": "phong-ho-so 3\n"}


@pytest.fixture
def stubs():
    return Stubs()


@pytest.fixture
def run(tmp_path, stubs):
    if shutil.which("bash") is None:
        pytest.skip("cần bash")
    repo = tmp_path / "repo"
    (repo / "ops").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "ops/demo_preflight.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in BASIC_TOOLS:
        real = shutil.which(tool)
        if real:
            (bin_dir / tool).symlink_to(real)
    for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "calls.log"

    def _run(*args: str, missing: tuple[str, ...] = (), **extra: str) -> Result:
        env_file = repo / ".env"
        env_file.unlink(missing_ok=True)
        if stubs.env is not None:
            env_file.write_text(stubs.env, encoding="utf-8")
        for name in missing:
            (bin_dir / name).unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        base = {"PATH": str(bin_dir), "HOME": str(tmp_path), "FAKE_LOG": str(log), **stubs.vars, **extra}
        proc = subprocess.run([str(bin_dir / "bash"), str(repo / "ops/demo_preflight.sh"), *args],  # noqa: S603
                              env=base, capture_output=True, text=True, check=False, timeout=60,
                              cwd=stubs.cwd or repo)
        return Result(proc, log)

    return _run


# ---------- mọi thứ xanh ----------

def test_all_green_exits_0_and_covers_the_whole_checklist(run):
    r = run()
    assert r.returncode == 0, r.text
    for token in ("OpenBao", "container", "readyz", "khóa công khai", "neo", "mạng", "dữ liệu demo"):
        assert token in r.out, token
    assert "[LỖI]" not in r.out and "[CẢNH BÁO]" not in r.out
    assert "[ĐẠT] OpenBao đã mở khóa" in r.out


def test_checks_use_the_configured_domain_with_tls_verification_for_a_real_domain(run):
    r = run()
    curls = [c for c in r.calls() if c.startswith("curl")]
    assert any(f"https://{DOMAIN}/verify/v1/keys" in c for c in curls)
    assert any(f"https://{DOMAIN}/verify/v1/sth/latest" in c for c in curls)
    assert all(" -k" not in c and "fsSk" not in c for c in curls), curls


def test_localhost_skips_tls_verification_only_for_localhost(run, stubs):
    stubs.env = "DXOS_DOMAIN=localhost\nDXOS_ANCHOR_REMOTE=\n"
    r = run()
    key_calls = [c for c in r.calls() if "/verify/v1/keys" in c]
    assert key_calls and "-fsSk" in key_calls[0]


# ---------- OpenBao ----------

def test_sealed_openbao_exits_1_prints_the_unseal_command_and_never_unseals(run):
    r = run(FAKE_BAO="sealed")
    assert r.returncode == 1
    assert "[LỖI] OpenBao đang KHÓA" in r.out
    assert "docker compose -p dxos exec openbao bao operator unseal" in r.out
    assert "docs/runbook-openbao.md" in r.out
    assert not [c for c in r.calls() if "unseal" in c]                     # chỉ in, không tự mở khóa
    assert SECRET not in r.text


def test_printed_unseal_command_is_the_one_in_the_runbook(run):
    r = run(FAKE_BAO="sealed")
    shown = re.search(r"^\s*(docker compose -p dxos exec openbao bao operator unseal)\s*$", r.out, re.M)
    assert shown and shown.group(1) in RUNBOOK.read_text(encoding="utf-8")


@pytest.mark.parametrize("state", ["error", "garbage"])
def test_unreadable_openbao_status_is_a_failure(run, state):
    r = run(FAKE_BAO=state)
    assert r.returncode == 1 and "[LỖI] OpenBao" in r.out
    assert "operator unseal" not in r.out                         # không biết là khóa: đừng gợi ý sai


def test_sealed_openbao_does_not_stop_the_other_checks(run):
    r = run(FAKE_BAO="sealed", FAKE_READYZ_FAIL="1")
    assert r.returncode == 1 and "readyz" in r.out and "[LỖI] OpenBao" in r.out


# ---------- sức khỏe ----------

def test_unhealthy_container_fails_and_names_it(run, stubs):
    stubs.vars["FAKE_PS"] = HEALTHY.replace("trust-core-worker-1|Up 5 hours (healthy)",
                                            "dxos-trust-core-worker-1|Up 5 hours (unhealthy)")
    r = run()
    assert r.returncode == 1 and "dxos-trust-core-worker-1" in r.out and "[LỖI]" in r.out


def test_starting_restarting_and_failed_exit_are_failures(run, stubs):
    for status in ("Up 3 seconds (health: starting)", "Restarting (1) 4 seconds ago",
                   "Exited (137) 1 minute ago", "Created", "Paused"):
        stubs.vars["FAKE_PS"] = HEALTHY + f"dxos-flowable-1|{status}\n"
        r = run()
        assert r.returncode == 1 and "dxos-flowable-1" in r.out, status


def test_exited_zero_one_shot_container_is_fine(run):
    assert run().returncode == 0


def test_empty_stack_is_a_failure(run, stubs):
    stubs.vars["FAKE_PS"] = ""
    r = run()
    assert r.returncode == 1 and "không có container" in r.out


def test_missing_core_services_is_a_failure(run, stubs):
    stubs.vars["FAKE_PS"] = "dxos-openbao-1|Up 5 hours (healthy)\n"
    r = run()
    assert r.returncode == 1 and "caddy" in r.out and "trust-core-api" in r.out


def test_readyz_not_200_fails(run):
    r = run(FAKE_READYZ_FAIL="1")
    assert r.returncode == 1 and "[LỖI] /readyz" in r.out


def test_public_keys_missing_or_incomplete_fails(run, stubs):
    r = run(FAKE_KEYS_FAIL="1")
    assert r.returncode == 1 and "[LỖI] khóa công khai" in r.out
    stubs.vars["FAKE_KEYS_BODY"] = '{"seal-key":{"1":"AAAA"}}'
    r = run()
    assert r.returncode == 1 and "sth-key" in r.out


# ---------- STH đã neo ----------

def test_latest_sth_anchored_is_ok(run):
    r = run(FAKE_ANCHOR_MAX="42")
    assert "[ĐẠT] STH mới nhất (cỡ 42) đã neo" in r.out


def test_anchor_covering_a_later_tree_size_counts_as_anchored(run):
    assert "[ĐẠT] STH mới nhất" in run(FAKE_ANCHOR_MAX="50").out


def test_latest_sth_not_anchored_warns_and_still_exits_0(run):
    r = run(FAKE_ANCHOR_MAX="30")
    assert r.returncode == 0
    assert "[CẢNH BÁO] STH mới nhất (cỡ 42) CHƯA neo" in r.out
    assert "anchor run" in r.out                                           # nói cách neo


def test_strict_turns_warnings_into_exit_1(run):
    assert run("--strict", FAKE_ANCHOR_MAX="30").returncode == 1
    assert run("--strict").returncode == 0


def test_no_anchor_row_at_all_warns(run):
    r = run(FAKE_ANCHOR_MAX="0")
    assert r.returncode == 0 and "CHƯA neo" in r.out


def test_anchoring_disabled_in_env_warns(run, stubs):
    stubs.env = f"DXOS_DOMAIN={DOMAIN}\nDXOS_ANCHOR_REMOTE=\n"
    r = run()
    assert r.returncode == 0 and "[CẢNH BÁO]" in r.out and "DXOS_ANCHOR_REMOTE" in r.out
    assert not [c for c in r.calls() if "anchors" in c]


def test_no_sth_yet_warns(run):
    r = run(FAKE_STH_FAIL="1")
    assert r.returncode == 0 and "chưa có STH" in r.out


# ---------- mạng ----------

def test_network_down_warns_and_names_the_target(run):
    r = run(FAKE_NET_FAIL="1")
    assert r.returncode == 0 and "[CẢNH BÁO] mạng" in r.out and "github.com" in r.out


def test_skip_network_makes_no_internet_call(run):
    r = run("--skip-network")
    assert r.returncode == 0 and not [c for c in r.calls() if "https://github.com" in c]


# ---------- dữ liệu demo ----------

def test_missing_app_a_demo_data_fails_with_the_seed_command(run, stubs):
    stubs.vars["FAKE_DEMO_ROWS"] = ""
    r = run()
    assert r.returncode == 1
    assert '[LỖI] dữ liệu demo' in r.out and 'make demo-seed ARGS="--only a"' in r.out


def test_too_few_app_a_documents_fails(run, stubs):
    stubs.vars["FAKE_DEMO_ROWS"] = "phong-ho-so 2\n"
    assert run().returncode == 1


def test_app_b_data_before_the_stage_install_warns(run, stubs):
    stubs.vars["FAKE_DEMO_ROWS"] = "chung-nhan 12\nphong-ho-so 3\n"
    r = run()
    assert r.returncode == 0 and "[CẢNH BÁO] dữ liệu demo App B" in r.out
    assert "sân khấu" in r.out


# ---------- việc kiểm tay in ra cuối ----------

def test_prints_the_manual_items_that_a_script_cannot_check(run):
    r = run()
    for token in ("Việc kiểm tay", "p8", "Viewer", "admin", "witness", "anchor run", "--only b"):
        assert token in r.out, token


# ---------- đầu vào ----------

def test_missing_env_exits_2_before_any_call(run, stubs):
    stubs.env = None
    r = run()
    assert r.returncode == 2 and ".env" in r.err and r.calls() == []


def test_bad_domain_exits_2(run, stubs):
    stubs.env = "DXOS_DOMAIN=bad domain;rm -rf /\n"
    r = run()
    assert r.returncode == 2 and "DXOS_DOMAIN" in r.err and r.calls() == []


@pytest.mark.parametrize("args", [("--bogus",), ("extra",)])
def test_bad_arguments_exit_2(run, args):
    r = run(*args)
    assert r.returncode == 2 and "dùng:" in r.err and r.calls() == []


@pytest.mark.parametrize("tool", ["docker", "curl"])
def test_missing_tool_exits_2(run, tool):
    r = run(missing=(tool,))
    assert r.returncode == 2 and tool in r.err


def test_runs_from_any_directory(run, stubs, tmp_path):
    stubs.cwd = tmp_path
    assert run().returncode == 0


# ---------- bí mật, chỉ đọc ----------

def test_never_prints_env_secrets_in_any_scenario(run):
    for kwargs in ({}, {"FAKE_BAO": "sealed"}, {"FAKE_ANCHOR_MAX": "1"}, {"FAKE_KEYS_FAIL": "1"}):
        assert SECRET not in run(**kwargs).text


def test_only_read_only_docker_and_get_requests(run):
    r = run()
    for c in r.calls():
        if c.startswith("docker"):
            assert re.search(r"docker (ps|compose -p dxos exec -T)", c), c
            assert not re.search(r"\b(up|down|rm|restart|stop|kill|unseal|init|write|delete)\b", c), c
        else:
            assert not re.search(r" -X | --data| -d | -T ", c), c


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
