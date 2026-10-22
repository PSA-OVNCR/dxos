# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/deploy.sh`` (Plan 03 Task 12, S9.2, R-3) với ``git``, ``docker``, ``curl`` giả đặt đầu PATH và
``ops/web_build_docker.sh`` giả trong một bản sao repo tạm. Mọi lời gọi được ghi vào một tệp log
(một lời gọi một dòng, đối số cách nhau bằng dấu cách) để kiểm thứ tự. Chạy thật trên VPS là việc V29."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/deploy.sh"
DIGEST = "a" * 64
COMMIT = "0123456789abcdef0123456789abcdef01234567"
DOMAIN = "dxos.example.test"
ENV = f"DXOS_DOMAIN={DOMAIN}\nDXOS_ANCHOR_REMOTE=\n"
# Đúng nội dung release.yml ghi vào dist/trust-core-image-<X.Y.Z>.txt (có test đối chiếu bên dưới).
RELEASE_TXT = "ghcr.io/psa-ovncr/trust-core:{v}\nghcr.io/psa-ovncr/trust-core@sha256:{d}\n"

FAKE_GIT = r"""#!/bin/sh
echo "git $*" >> "$FAKE_LOG"
case "$*" in
  "status --porcelain") printf '%s' "${FAKE_GIT_STATUS:-}" ;;
  fetch*) [ -z "${FAKE_FETCH_FAIL:-}" ] || { echo "! [rejected] would clobber existing tag" >&2; exit 1; } ;;
  "rev-parse HEAD") echo "${FAKE_COMMIT}" ;;
esac
exit 0
"""
FAKE_CURL = r"""#!/bin/sh
echo "curl $*" >> "$FAKE_LOG"
case "$*" in
  *trust-core-image-*) [ -z "${FAKE_CURL_FAIL:-}" ] || exit 22; printf '%s' "$FAKE_DIGEST_BODY" ;;
  *) [ -z "${FAKE_VERIFY_FAIL:-}" ] || exit 22; echo '{"keys":[]}' ;;
esac
exit 0
"""
FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
if [ "$1" = compose ]; then
  echo "env digest=${DXOS_TRUST_CORE_DIGEST:-} tag=${DXOS_RELEASE_TAG:-}" >> "$FAKE_LOG.env"
fi
case "$*" in
  *"exec -T trust-core-api"*)
    if [ -n "${FAKE_READYZ_PRINT:-}" ]; then echo "$FAKE_READYZ_PRINT"; exit 0; fi
    if [ "${FAKE_READYZ:-200}" = 200 ]; then echo 200; exit 0; fi
    echo "urllib.error.HTTPError: HTTP Error ${FAKE_READYZ}: Service Unavailable" >&2; exit 1 ;;
  *" pull "*) [ -z "${FAKE_PULL_FAIL:-}" ] || { echo "pull access denied" >&2; exit 1; } ;;
  *" up "*) [ -z "${FAKE_UP_FAIL:-}" ] || { echo "container dxos-x-1 is unhealthy" >&2; exit 1; } ;;
esac
exit 0
"""
FAKE_WEB = """#!/bin/sh
echo "web_build_docker.sh $*" >> "$FAKE_LOG"
if [ -n "${FAKE_WEB_RC:-}" ]; then
  echo "web_build_docker.sh: NODE_IMAGE chưa ghim digest" >&2; exit "$FAKE_WEB_RC"
fi
exit 0
"""


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, repo: Path, log: Path):
        self.returncode, self.stdout, self.stderr = proc.returncode, proc.stdout, proc.stderr
        self.repo = repo
        self.calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        self.text = "\n".join(self.calls)

    def file(self, rel: str) -> str:
        return (self.repo / rel).read_text(encoding="utf-8")

    def log_lines(self) -> list[str]:
        p = self.repo / "deploy/deployments.log"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def log_last(self) -> str:
        return self.log_lines()[-1]

    def order(self, needles: list[str]) -> bool:
        """Mỗi chuỗi trong ``needles`` có ở một dòng gọi, theo đúng thứ tự (không nhất thiết liền nhau)."""
        i = 0
        for call in self.calls:
            if i < len(needles) and needles[i] in call:
                i += 1
        return i == len(needles)


class Stubs:
    """Cấu hình của các lệnh giả: đặt thuộc tính trước khi gọi ``run``."""

    def __init__(self) -> None:
        self.git_status = ""
        self.digest_body: str | None = None          # None = dựng từ tag theo định dạng của release.yml
        self.env: str | None = ENV
        self.log_before = ""
        self.previous_ok_tag: str | None = None
        self.readyz = "200"
        self.extra: dict[str, str] = {}

    def environ(self, tag: str) -> dict[str, str]:
        body = self.digest_body if self.digest_body is not None else RELEASE_TXT.format(v=tag[1:], d=DIGEST)
        env = {"FAKE_GIT_STATUS": self.git_status, "FAKE_COMMIT": COMMIT, "FAKE_DIGEST_BODY": body,
               "FAKE_READYZ": self.readyz}
        return {**env, **self.extra}


@pytest.fixture
def stubs():
    return Stubs()


@pytest.fixture
def run(tmp_path, stubs):
    if shutil.which("bash") is None:
        pytest.skip("cần bash")
    repo = tmp_path / "repo"
    (repo / "ops").mkdir(parents=True)
    (repo / "deploy").mkdir()
    shutil.copy2(SCRIPT, repo / "ops/deploy.sh")
    (repo / "ops/web_build_docker.sh").write_text(FAKE_WEB, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("git", FAKE_GIT), ("curl", FAKE_CURL), ("docker", FAKE_DOCKER)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    log = tmp_path / "calls.log"

    def _run(*args: str) -> Result:
        if stubs.env is not None:
            (repo / ".env").write_text(stubs.env, encoding="utf-8")
        log.unlink(missing_ok=True)
        entries = stubs.log_before
        if stubs.previous_ok_tag:
            entries += f"2026-10-01T00:00:00Z\t{stubs.previous_ok_tag}\t{'b' * 40}\t{'c' * 64}\tOK\n"
        if entries:
            (repo / "deploy/deployments.log").write_text(entries, encoding="utf-8")
        tag = args[0] if args else "v0.3.0"
        base = {k: v for k, v in os.environ.items() if not k.startswith(("DXOS_", "FAKE_"))}
        path = f"{bin_dir}{os.pathsep}{base['PATH']}"
        base.update({"PATH": path, "FAKE_LOG": str(log), **stubs.environ(tag)})
        proc = subprocess.run(["bash", str(repo / "ops/deploy.sh"), *args], env=base,  # noqa: S603, S607
                              capture_output=True, text=True, check=False, timeout=60, cwd=repo)
        return Result(proc, repo, log)

    return _run


# ---------- kiểm đầu vào: không tác dụng phụ ----------

@pytest.mark.parametrize("tag", ["v1.0", "1.0.0", "v1.0.0-rc1", "v1.0.0.1", "vx.y.z", "v1.0.0;ls", ""])
def test_rejects_bad_tag_without_side_effects(run, tag):
    r = run(tag)
    assert r.returncode == 2 and r.calls == []
    assert r.log_lines() == [] and not (r.repo / "deploy/release.env").exists()


def test_rejects_missing_tag_argument(run):
    r = run()
    assert r.returncode == 2 and r.calls == []


def test_rejects_unknown_profile_and_unknown_option(run):
    for args in (("v0.3.0", "--profile", "p4"), ("v0.3.0", "--profile"), ("v0.3.0", "--bogus"),
                 ("v0.3.0", "--repo-url", "ftp://x/y")):
        r = run(*args)
        assert r.returncode == 2 and r.calls == [], args


def test_rejects_dirty_tree(run, stubs):
    stubs.git_status = " M core/x.py\n"
    r = run("v0.3.0")
    assert r.returncode == 2 and "compose" not in r.text
    assert r.calls == ["git status --porcelain"]            # chưa fetch, chưa checkout
    assert r.log_lines() == []                              # chưa bắt đầu triển khai: không ghi FAIL


def test_rejects_missing_env_or_domain(run, stubs):
    stubs.env = None
    r = run("v0.3.0")
    assert r.returncode == 2 and r.calls == []
    stubs.env = "DXOS_ANCHOR_REMOTE=\n"
    r = run("v0.3.0")
    assert r.returncode == 2 and r.calls == [] and "DXOS_DOMAIN" in r.stderr


# ---------- đường chạy đúng ----------

def test_happy_path_order(run):
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.order([
        "git status --porcelain",
        "git fetch origin refs/tags/v0.3.0:refs/tags/v0.3.0",
        "git -c advice.detachedHead=false checkout --detach v0.3.0",
        "curl -fsSL https://github.com/PSA-OVNCR/dxos/releases/download/v0.3.0/trust-core-image-0.3.0.txt",
        "web_build_docker.sh",
        " pull --ignore-buildable",
        " up -d --wait --wait-timeout 600",
        "exec -T trust-core-api",
        "/verify/v1/keys",
    ]), r.text
    assert "DXOS_TRUST_CORE_DIGEST=" + DIGEST in r.file("deploy/release.env")
    assert "DXOS_RELEASE_TAG=v0.3.0" in r.file("deploy/release.env")


def test_fetch_never_forces(run):
    r = run("v0.3.0")
    fetch = next(c for c in r.calls if c.startswith("git fetch"))
    assert "--force" not in fetch and " -f" not in fetch and not fetch.split()[2].startswith("+")
    assert not any("+refs" in c for c in r.calls)


def test_fetch_failure_exits_1_and_logs_fail(run, stubs):
    stubs.extra["FAKE_FETCH_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1
    assert not any("checkout" in c or "docker" in c or "curl" in c for c in r.calls)
    assert r.log_last().endswith("\tFAIL") and "Triển khai v0.3.0 hỏng." in r.stdout


def test_compose_command_line(run):
    r = run("v0.3.0")
    up = next(c for c in r.calls if c.startswith("docker compose") and " up " in c)
    assert up == ("docker compose -p dxos --env-file .env --env-file deploy/release.env "
                  "-f deploy/compose.yaml -f deploy/compose.p16.yaml -f deploy/compose.release.yaml "
                  "up -d --wait --wait-timeout 600")
    assert "compose.anchor.yaml" not in up


def test_pull_precedes_up_with_the_same_compose_files(run, stubs):
    stubs.env = "DXOS_DOMAIN=d.test\nDXOS_ANCHOR_REMOTE=git@github.com:o/r.git\n"
    r = run("v0.3.0")
    pull = next(c for c in r.calls if " pull " in c)
    up = next(c for c in r.calls if " up " in c)
    assert r.calls.index(pull) < r.calls.index(up)
    assert pull == up.replace(" up -d --wait --wait-timeout 600", " pull --ignore-buildable")
    assert "compose.anchor.yaml" in pull and "compose.release.yaml" in pull


def test_pull_failure_logs_fail_and_does_not_run_up(run, stubs):
    stubs.extra["FAKE_PULL_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1 and not any(" up " in c for c in r.calls)
    assert r.log_last().endswith("\tFAIL") and "Triển khai v0.3.0 hỏng." in r.stdout


def test_inherited_digest_and_tag_env_never_reach_compose(run, stubs, tmp_path):
    stubs.extra.update({"DXOS_TRUST_CORE_DIGEST": "f" * 64, "DXOS_RELEASE_TAG": "v9.9.9"})
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    seen = (tmp_path / "calls.log.env").read_text(encoding="utf-8").splitlines()
    assert len(seen) >= 3                                       # pull, up, exec
    assert set(seen) == {"env digest= tag="}                    # compose chỉ đọc deploy/release.env
    assert r.file("deploy/release.env") == f"DXOS_TRUST_CORE_DIGEST={DIGEST}\nDXOS_RELEASE_TAG=v0.3.0\n"
    assert r.log_last().split("\t")[3] == DIGEST and "f" * 64 not in r.log_last()


def test_profile_p8_selected(run):
    r = run("v0.3.0", "--profile", "p8")
    up = next(c for c in r.calls if " up " in c)
    assert "-f deploy/compose.p8.yaml" in up and "compose.p16.yaml" not in up


def test_anchor_overlay_only_when_remote_configured(run, stubs):
    stubs.env = "DXOS_DOMAIN=d.test\nDXOS_ANCHOR_REMOTE=git@github.com:o/r.git\n"
    r = run("v0.3.0")
    up = next(c for c in r.calls if " up " in c)
    assert up.index("compose.p16.yaml") < up.index("compose.anchor.yaml") < up.index("compose.release.yaml")
    stubs.env = "DXOS_DOMAIN=d.test\nDXOS_ANCHOR_REMOTE=\"\"\n"
    assert "compose.anchor.yaml" not in run("v0.3.0").text
    stubs.env = "DXOS_DOMAIN=d.test\n"
    assert "compose.anchor.yaml" not in run("v0.3.0").text


def test_health_checks_use_same_compose_files_and_domain_from_env(run, stubs):
    stubs.env = 'DXOS_DOMAIN="dxos.vn"\r\nDXOS_ANCHOR_REMOTE=\r\n'
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    ex = next(c for c in r.calls if "exec -T trust-core-api" in c)
    assert ex.startswith("docker compose -p dxos --env-file .env --env-file deploy/release.env ")
    assert "compose.release.yaml exec -T trust-core-api python -c " in ex and "/readyz" in ex
    assert "curl -fs --max-time 20 https://dxos.vn/verify/v1/keys" in r.calls   # tên miền thật: xác minh TLS


@pytest.mark.parametrize("domain", ["localhost", "dxos.localhost"])
def test_health_check_skips_tls_verify_only_for_localhost(run, stubs, domain):
    stubs.env = f"DXOS_DOMAIN={domain}\nDXOS_ANCHOR_REMOTE=\n"
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"curl -fsk --max-time 20 https://{domain}/verify/v1/keys" in r.calls


def test_health_check_verifies_tls_for_lookalike_domain(run, stubs):
    stubs.env = "DXOS_DOMAIN=localhost.example.vn\nDXOS_ANCHOR_REMOTE=\n"
    r = run("v0.3.0")
    assert "curl -fs --max-time 20 https://localhost.example.vn/verify/v1/keys" in r.calls
    assert "curl -fsk" not in r.text


def test_log_line_format_and_append(run, stubs):
    stubs.log_before = "old line\n"
    r = run("v0.3.0")
    assert r.log_lines()[0] == "old line"
    ts, tag, commit, digest, status = r.log_last().split("\t")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)
    assert (tag, commit, digest, status) == ("v0.3.0", COMMIT, DIGEST, "OK")
    assert len(r.log_lines()) == 2


def test_release_files_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "deploy/release.env" in ignored and "deploy/deployments.log" in ignored


# ---------- digest ----------

@pytest.mark.parametrize("body", ["not-hex", "", "sha256:" + "a" * 64, "A" * 64, "a" * 63, "a" * 65,
                                  "ghcr.io/psa-ovncr/trust-core:0.3.0\nghcr.io/psa-ovncr/trust-core@sha256:xyz\n",
                                  "<html>404</html>", "a" * 64 + "\n" + "b" * 64])
def test_bad_digest_stops_before_compose(run, stubs, body):
    stubs.digest_body = body
    r = run("v0.3.0")
    assert r.returncode == 1 and "docker compose" not in r.text and "web_build" not in r.text
    assert not (r.repo / "deploy/release.env").exists()
    assert r.log_last().endswith("\tFAIL")


@pytest.mark.parametrize("body", [DIGEST, DIGEST + "\n", DIGEST + "\r\n",
                                  f"ghcr.io/psa-ovncr/trust-core@sha256:{DIGEST}\r\n"])
def test_accepts_bare_digest_and_release_yml_format(run, stubs, body):
    stubs.digest_body = body
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.file("deploy/release.env") == f"DXOS_TRUST_CORE_DIGEST={DIGEST}\nDXOS_RELEASE_TAG=v0.3.0\n"


def test_digest_file_download_failure_exits_1(run, stubs):
    stubs.extra["FAKE_CURL_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1 and "docker compose" not in r.text and r.log_last().endswith("\tFAIL")


def test_repo_url_option_and_trailing_slash(run):
    r = run("v1.2.3", "--repo-url", "https://example.test/o/r/")
    assert any(c.startswith("curl -fsSL https://example.test/o/r/releases/download/v1.2.3/trust-core-image-1.2.3.txt")
               for c in r.calls), r.calls


def test_release_yml_writes_what_the_parser_expects():
    wf = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["release"]["steps"]
    run_text = next(s["run"] for s in steps if "trust-core-image-" in s.get("run", ""))
    assert "printf 'ghcr.io/psa-ovncr/trust-core:%s\\nghcr.io/psa-ovncr/trust-core@sha256:%s\\n'" in run_text
    assert '"dist/trust-core-image-${VERSION}.txt"' in run_text


# ---------- bước dựng web ----------

def test_web_build_exit_3_is_surfaced_and_stops_before_compose(run, stubs):
    stubs.extra["FAKE_WEB_RC"] = "3"
    r = run("v0.3.0")
    assert r.returncode == 1 and "docker compose" not in r.text
    assert "make pin-images" in r.stdout + r.stderr and "chưa ghim" in r.stdout + r.stderr
    assert r.log_last().endswith("\tFAIL") and "Triển khai v0.3.0 hỏng." in r.stdout


def test_web_build_other_failure_stops_before_compose(run, stubs):
    stubs.extra["FAKE_WEB_RC"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1 and "docker compose" not in r.text


# ---------- hỏng và quay lại ----------

def test_health_failure_logs_fail_and_prints_previous_tag(run, stubs):
    stubs.previous_ok_tag = "v0.2.0"
    stubs.readyz = "503"
    r = run("v0.3.0")
    assert r.returncode == 1
    assert "Triển khai v0.3.0 hỏng. Quay lại bằng: ops/deploy.sh v0.2.0" in r.stdout
    assert r.log_last().endswith("\tFAIL") and r.log_last().split("\t")[1] == "v0.3.0"
    assert "/verify/v1/keys" not in r.text                    # dừng ở readyz, không đi tiếp


def test_unexpected_readyz_output_is_a_failure(run, stubs):
    stubs.extra["FAKE_READYZ_PRINT"] = "204"                   # exec thoát 0 nhưng không in đúng 200
    r = run("v0.3.0")
    assert r.returncode == 1 and "/verify/v1/keys" not in r.text and r.log_last().endswith("\tFAIL")


def test_verify_keys_failure_logs_fail(run, stubs):
    stubs.extra["FAKE_VERIFY_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1 and r.log_last().endswith("\tFAIL")


def test_compose_up_failure_logs_fail_with_commit_and_digest(run, stubs):
    stubs.extra["FAKE_UP_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 1 and "exec -T" not in r.text, r.stdout + r.stderr
    _, tag, commit, digest, status = r.log_last().split("\t")
    assert (tag, commit, digest, status) == ("v0.3.0", COMMIT, DIGEST, "FAIL")


def test_previous_tag_is_last_ok_line_not_a_failed_one(run, stubs):
    stubs.log_before = (f"2026-10-01T00:00:00Z\tv0.1.0\t{'b' * 40}\t{'c' * 64}\tOK\n"
                        f"2026-10-02T00:00:00Z\tv0.2.0\t{'b' * 40}\t{'c' * 64}\tOK\n"
                        f"2026-10-03T00:00:00Z\tv0.2.5\t{'b' * 40}\t{'c' * 64}\tFAIL\n")
    stubs.readyz = "503"
    r = run("v0.3.0")
    assert "Quay lại bằng: ops/deploy.sh v0.2.0" in r.stdout


def test_no_previous_ok_prints_none(run, stubs):
    stubs.readyz = "503"
    r = run("v0.3.0")
    assert "Quay lại bằng: ops/deploy.sh none" in r.stdout and "chưa có bản nào chạy tốt" in r.stdout


def test_success_prints_no_failure_message(run):
    r = run("v0.3.0")
    assert "hỏng" not in r.stdout + r.stderr


# ---------- an toàn ----------

def test_env_file_is_parsed_not_sourced(run, stubs, tmp_path):
    marker = tmp_path / "pwned"
    stubs.env = (f"DXOS_DOMAIN=d.test\nDXOS_ANCHOR_REMOTE=\n$(touch {marker})\ntouch {marker}\n"
                 f"X=`touch {marker}`\n")
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not marker.exists()


def test_does_not_echo_env_values_other_than_domain(run, stubs):
    stubs.env = "DXOS_DOMAIN=d.test\nDXOS_ANCHOR_REMOTE=\nSECRET_TOKEN=hunter2hunter2\n"
    r = run("v0.3.0")
    assert "hunter2" not in r.stdout + r.stderr + r.text


def test_script_header_syntax_and_shellcheck():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/bash\n")
    assert "SPDX-" + "License-Identifier: Apache-2.0" in text and "set -euo pipefail" in text
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0  # noqa: S603, S607
    if shutil.which("shellcheck"):
        # -S warning: ghi chú mức info của shellcheck mới (runner đổi image) không làm CI đỏ; warning, error
        # vẫn bị bắt.
        proc = subprocess.run(["shellcheck", "-S", "warning", str(SCRIPT)],  # noqa: S603, S607
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout
