# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/deploy.sh`` (Plan 03 Task 12, S9.2, R-3; Plan 04 Task 11, S4: chỉ tag ký, tự quay lui) với
``git``, ``docker``, ``curl`` giả đặt đầu PATH và
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
# Khóa hư cấu: fake git không đọc nội dung, script chỉ cần thấy ít nhất một dòng không phải chú thích.
SIGNERS = "# chú thích\n\nrelease@example.test namespaces=\"git\" ssh-ed25519 AAAAFAKEKEYFORTESTS\n"
RESULT_FAILED = "\tresult=failed\t"
# Đúng nội dung release.yml ghi vào dist/trust-core-image-<X.Y.Z>.txt (có test đối chiếu bên dưới).
RELEASE_TXT = "ghcr.io/psa-ovncr/trust-core:{v}\nghcr.io/psa-ovncr/trust-core@sha256:{d}\n"

FAKE_GIT = r"""#!/bin/sh
echo "git $*" >> "$FAKE_LOG"
case "$*" in
  *verify-tag*)
    echo "$PWD" >> "$FAKE_LOG.pwd"
    for last; do :; done                    # FAKE_VERIFY_TAG_FAIL: "1" = mọi tag, hoặc danh sách tag
    last=${last#refs/tags/}
    case " ${FAKE_VERIFY_TAG_FAIL:-} " in
      *" 1 "* | *" $last "*) echo "error: no signature found" >&2; exit 1 ;;
    esac ;;
  "cat-file tag refs/tags/"*)
    t=${3#refs/tags/}; v=$(printf '%s' "$t" | tr . _)
    [ -z "${FAKE_LIGHTWEIGHT:-}" ] || { echo "fatal: bad object type" >&2; exit 128; }
    name=$(printenv "FAKE_TAG_NAME_$v" || true)      # FAKE_TAG_NAME_vX_Y_Z: tên trong thân tag
    printf 'object %s\ntype commit\ntag %s\ntagger x <x@e.test> 1 +0000\n\nm\n' \
      "$FAKE_COMMIT" "${name:-$t}" ;;
  "rev-parse -q --verify refs/tags/"*)
    v=$(printf '%s' "${4#refs/tags/}" | tr . _)
    had=$(printenv "FAKE_HAD_REF_$v" || true)
    [ -n "$had" ] && echo "$had" || exit 1 ;;
  "rev-parse refs/tags/"*"^{commit}")
    t=${2#refs/tags/}; t=${t%^\{commit\}}; v=$(printf '%s' "$t" | tr . _)
    c=$(printenv "FAKE_COMMIT_$v" || true)
    echo "${c:-$FAKE_COMMIT}" ;;
  "status --porcelain") printf '%s' "${FAKE_GIT_STATUS:-}" ;;
  fetch*) [ -z "${FAKE_FETCH_FAIL:-}" ] || { echo "! [rejected] would clobber existing tag" >&2; exit 1; } ;;
  "rev-parse HEAD") echo "${FAKE_COMMIT}" ;;
esac
exit 0
"""
# Tag đang triển khai = DXOS_RELEASE_TAG trong deploy/release.env (script ghi trước khi gọi compose).
# FAKE_BAD_TAGS (danh sách cách nhau bằng dấu cách; mặc định mọi tag) giới hạn các lỗi sức khỏe giả vào những
# tag đó, để quay lui về một tag khỏe mà vẫn mô phỏng được tag mới hỏng.
BAD_TAG_SNIPPET = r"""
cur=$(sed -n 's/^DXOS_RELEASE_TAG=//p' deploy/release.env 2>/dev/null)
is_bad() { case " ${FAKE_BAD_TAGS:-$cur} " in *" $cur "*) return 0 ;; *) return 1 ;; esac; }
"""
FAKE_CURL = r"""#!/bin/sh
echo "curl $*" >> "$FAKE_LOG"
""" + BAD_TAG_SNIPPET + r"""case "$*" in
  *trust-core-image-*)
    [ -z "${FAKE_CURL_FAIL:-}" ] || exit 22
    t=$(printf '%s' "$*" | sed -n 's|.*/download/\(v[0-9.]*\)/.*|\1|p' | tr . _)
    body=$(printenv "FAKE_DIGEST_$t" || true)       # digest riêng theo tag (kiểm quay lui lấy đúng digest)
    printf '%s' "${body:-$FAKE_DIGEST_BODY}" ;;
  *) [ -z "${FAKE_VERIFY_FAIL:-}" ] || ! is_bad || exit 22; echo '{"keys":[]}' ;;
esac
exit 0
"""
FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
if [ "$1" = compose ]; then
  echo "env digest=${DXOS_TRUST_CORE_DIGEST:-} tag=${DXOS_RELEASE_TAG:-}" >> "$FAKE_LOG.env"
fi
""" + BAD_TAG_SNIPPET + r"""case "$*" in
  *"exec -T trust-core-api"*)
    if [ -n "${FAKE_READYZ_PRINT:-}" ]; then echo "$FAKE_READYZ_PRINT"; exit 0; fi
    if [ "${FAKE_READYZ:-200}" = 200 ] || ! is_bad; then echo 200; exit 0; fi
    echo "urllib.error.HTTPError: HTTP Error ${FAKE_READYZ}: Service Unavailable" >&2; exit 1 ;;
  *" pull "*) [ -z "${FAKE_PULL_FAIL:-}" ] || ! is_bad || { echo "pull access denied" >&2; exit 1; } ;;
  *" up "*) [ -z "${FAKE_UP_FAIL:-}" ] || ! is_bad || { echo "container x is unhealthy" >&2; exit 1; } ;;
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
        self.previous_ok_tag: str | None = None      # dòng KIỂU CŨ (cột 5 = OK, không có cột signed)
        self.digests: dict[str, str] = {}            # digest riêng theo tag (mặc định DIGEST)
        self.cwd: Path | None = None                 # thư mục gọi script (mặc định: gốc repo tạm)
        self.commits: dict[str, str] = {}            # commit riêng theo tag (mặc định COMMIT)
        self.signers: str | None = SIGNERS           # nội dung deploy/allowed_signers (None = không có tệp)
        self.readyz = "200"
        self.extra: dict[str, str] = {}

    def environ(self, tag: str) -> dict[str, str]:
        body = self.digest_body if self.digest_body is not None else RELEASE_TXT.format(v=tag[1:], d=DIGEST)
        env = {"FAKE_GIT_STATUS": self.git_status, "FAKE_COMMIT": COMMIT, "FAKE_DIGEST_BODY": body,
               "FAKE_READYZ": self.readyz}
        for t, c in self.commits.items():
            env["FAKE_COMMIT_" + t.replace(".", "_")] = c
        for t, d in self.digests.items():
            env["FAKE_DIGEST_" + t.replace(".", "_")] = RELEASE_TXT.format(v=t[1:], d=d)
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
        signers = repo / "deploy/allowed_signers"
        signers.unlink(missing_ok=True)
        if stubs.signers is not None:
            signers.write_text(stubs.signers, encoding="utf-8")
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
                              capture_output=True, text=True, check=False, timeout=60,
                              cwd=stubs.cwd or repo)
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
        "verify-tag refs/tags/v0.3.0",
        "git rev-parse refs/tags/v0.3.0^{commit}",
        f"git -c advice.detachedHead=false checkout --detach {COMMIT}",
        "curl -fsSL https://github.com/PSA-OVNCR/dxos/releases/download/v0.3.0/trust-core-image-0.3.0.txt",
        " pull --ignore-buildable",
        "web_build_docker.sh",
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


def test_fetch_failure_exits_3_and_logs_failed(run, stubs):
    stubs.extra["FAKE_FETCH_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 3
    assert not any("checkout" in c or "docker" in c or "curl" in c or "verify-tag" in c for c in r.calls)
    assert RESULT_FAILED in r.log_last() and "Triển khai v0.3.0 hỏng." in r.stdout


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


def test_pull_failure_exits_3_logs_failed_and_changes_nothing_that_runs(run, stubs):
    stubs.extra["FAKE_PULL_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 3 and not any(" up " in c for c in r.calls)
    assert "web_build" not in r.text                            # SPA chưa bị dựng lại vào volume đang phục vụ
    assert RESULT_FAILED in r.log_last() and "Triển khai v0.3.0 hỏng." in r.stdout


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
    ts, tag, commit, digest, result, signed = r.log_last().split("\t")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)
    assert (tag, commit, digest, result, signed) == ("v0.3.0", COMMIT, DIGEST, "result=ok", "signed=yes")
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
    assert r.returncode == 3 and "docker compose" not in r.text and "web_build" not in r.text
    assert not (r.repo / "deploy/release.env").exists()
    assert RESULT_FAILED in r.log_last()


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
    assert r.returncode == 3 and "docker compose" not in r.text and RESULT_FAILED in r.log_last()


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
    assert r.returncode == 3 and not any(" up " in c for c in r.calls)
    assert "make pin-images" in r.stdout + r.stderr and "chưa ghim" in r.stdout + r.stderr
    assert RESULT_FAILED in r.log_last() and "Triển khai v0.3.0 hỏng." in r.stdout


def test_web_build_other_failure_stops_before_compose(run, stubs):
    stubs.extra["FAKE_WEB_RC"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 3 and not any(" up " in c for c in r.calls)


# ---------- chuẩn bị trước khi chuyển: thoát 3, không quay lui ----------

def test_pre_switch_failure_prints_previous_tag_hint(run, stubs):
    stubs.previous_ok_tag = "v0.2.0"
    stubs.digest_body = "not-hex"
    r = run("v0.3.0")
    assert r.returncode == 3
    assert "Triển khai v0.3.0 hỏng. Quay lại bằng: ops/deploy.sh v0.2.0" in r.stdout
    assert RESULT_FAILED in r.log_last() and r.log_last().split("\t")[1] == "v0.3.0"
    assert not any("docker" in c for c in r.calls)            # chưa chạm stack, nên không quay lui


def test_pre_switch_failure_with_no_previous_prints_none(run, stubs):
    stubs.digest_body = "not-hex"
    r = run("v0.3.0")
    assert "Quay lại bằng: ops/deploy.sh none" in r.stdout and "chưa có bản nào chạy tốt" in r.stdout


# ---------- hỏng sức khỏe và tự quay lui (S4) ----------

def test_health_fail_rolls_back_to_last_ok(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"
    stubs.extra["FAKE_BAD_TAGS"] = "v1.0.0"
    stubs.digests = {"v0.9.0": "9" * 64, "v1.0.0": "1" * 64}
    stubs.commits = {"v0.9.0": "9" * 40, "v1.0.0": "1" * 40}
    r = run("v1.0.0")
    assert r.returncode == 4, r.stdout + r.stderr
    # chuỗi triển khai chạy lại đầy đủ cho v0.9.0, sau khi v1.0.0 đã hỏng
    assert r.order([
        "git fetch origin refs/tags/v1.0.0:refs/tags/v1.0.0", f"checkout --detach {'1' * 40}",
        "web_build_docker.sh", " up -d --wait", "exec -T trust-core-api",
        "git fetch origin refs/tags/v0.9.0:refs/tags/v0.9.0", f"checkout --detach {'9' * 40}",
        "releases/download/v0.9.0/trust-core-image-0.9.0.txt",
        " pull --ignore-buildable", "web_build_docker.sh", " up -d --wait", "exec -T trust-core-api",
        "/verify/v1/keys",
    ]), r.text
    assert r.file("deploy/release.env") == f"DXOS_TRUST_CORE_DIGEST={'9' * 64}\nDXOS_RELEASE_TAG=v0.9.0\n"
    seen = r.log_lines()
    assert seen[-1].split("\t")[1:] == ["v1.0.0", "1" * 40, "1" * 64, "result=rolled-back", "signed=yes"]
    assert seen[-2].split("\t")[1:] == ["v0.9.0", "9" * 40, "9" * 64, "result=ok", "signed=yes"]
    assert "quay lui về v0.9.0" in r.stdout and "Đã quay lui về v0.9.0" in r.stdout


def test_rollback_does_not_recurse(run, stubs):
    stubs.log_before = (f"2026-10-01T00:00:00Z\tv0.8.0\t{'b' * 40}\t{'c' * 64}\tresult=ok\tsigned=yes\n"
                        f"2026-10-02T00:00:00Z\tv0.9.0\t{'b' * 40}\t{'c' * 64}\tresult=ok\tsigned=yes\n")
    stubs.readyz = "503"                                       # mọi tag hỏng, kể cả v0.9.0
    r = run("v1.0.0")
    assert r.returncode == 5
    ups = [c for c in r.calls if " up " in c]
    assert len(ups) == 2                                       # v1.0.0 rồi v0.9.0; không thử v0.8.0
    assert not any("refs/tags/v0.8.0" in c for c in r.calls)


def test_first_deploy_health_fail_no_previous(run, stubs):
    stubs.readyz = "503"
    r = run("v1.0.0")
    assert r.returncode == 5
    assert "Khôi phục tay" in r.stdout and "docker compose -p dxos ps" in r.stdout
    assert "ops/deploy.sh <tag>" in r.stdout and "runbook-deploy.md" in r.stdout
    assert len([c for c in r.calls if " up " in c]) == 1       # không có gì để quay lui
    assert not any("refs/tags/v0" in c for c in r.calls)
    assert RESULT_FAILED in r.log_last() and r.log_last().split("\t")[1] == "v1.0.0"
    assert len(r.log_lines()) == 1


def test_rollback_also_fails_exit_5(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"                                       # cả v1.0.0 lẫn v0.9.0 đều không khỏe
    r = run("v1.0.0")
    assert r.returncode == 5
    assert "quay lui về v0.9.0 cũng hỏng" in r.stdout and "Khôi phục tay" in r.stdout
    tail = [ln.split("\t") for ln in r.log_lines()[-2:]]
    assert [(t[1], t[4]) for t in tail] == [("v0.9.0", "result=failed"), ("v1.0.0", "result=failed")]


def test_rollback_failing_before_compose_also_exit_5(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"
    stubs.extra["FAKE_BAD_TAGS"] = "v1.0.0"
    stubs.extra["FAKE_DIGEST_v0_9_0"] = "<html>404</html>"      # Release của bản cũ đã bị xóa
    r = run("v1.0.0")
    assert r.returncode == 5 and "Khôi phục tay" in r.stdout
    assert len([c for c in r.calls if " up " in c]) == 1


def test_compose_up_wait_failure_is_a_health_failure_and_rolls_back(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.extra.update({"FAKE_UP_FAIL": "1", "FAKE_BAD_TAGS": "v1.0.0"})
    r = run("v1.0.0")
    assert r.returncode == 4 and "exec -T" in r.text           # chỉ bản quay lui mới tới bước readyz
    assert "result=rolled-back" in r.log_last()


def test_unexpected_readyz_output_rolls_back_or_exit_5(run, stubs):
    stubs.extra["FAKE_READYZ_PRINT"] = "204"                   # exec thoát 0 nhưng không in đúng 200
    r = run("v0.3.0")
    assert r.returncode == 5 and "/verify/v1/keys" not in r.text and RESULT_FAILED in r.log_last()


def test_verify_keys_failure_rolls_back(run, stubs):
    stubs.previous_ok_tag = "v0.2.0"
    stubs.extra.update({"FAKE_VERIFY_FAIL": "1", "FAKE_BAD_TAGS": "v0.3.0"})
    r = run("v0.3.0")
    assert r.returncode == 4 and "result=rolled-back" in r.log_last()


def test_health_failure_stops_at_readyz_before_verify_keys(run, stubs):
    stubs.readyz = "503"
    r = run("v0.3.0")
    assert r.returncode == 5 and "/verify/v1/keys" not in r.text


def test_previous_is_last_ok_line_not_a_failed_one_nor_the_tag_itself(run, stubs):
    def row(day, tag, result):
        return f"2026-10-{day}T00:00:00Z\t{tag}\t{'b' * 40}\t{'c' * 64}\t{result}\n"

    stubs.log_before = (row("01", "v0.1.0", "OK") + row("02", "v0.2.0", "result=ok\tsigned=yes")
                        + row("03", "v0.2.5", "result=failed\tsigned=yes")
                        + row("04", "v0.2.6", "result=rolled-back\tsigned=no")
                        + row("05", "v0.3.0", "result=ok\tsigned=yes") + row("06", "v0.1.5", "FAIL"))
    stubs.readyz = "503"
    stubs.extra["FAKE_BAD_TAGS"] = "v0.3.0"
    stubs.commits = {"v0.2.0": "2" * 40, "v0.1.5": "5" * 40}
    r = run("v0.3.0")                       # redeploy v0.3.0: chính nó không được là đích quay lui
    assert r.returncode == 4
    assert f"checkout --detach {'2' * 40}" in r.text and f"checkout --detach {'5' * 40}" not in r.text


def test_old_format_log_lines_still_parse_for_last_ok(run, stubs):
    stubs.previous_ok_tag = "v0.2.0"                             # dòng kiểu cũ: ..., OK (không có cột signed)
    stubs.digest_body = "not-hex"
    r = run("v0.3.0")
    assert "Quay lại bằng: ops/deploy.sh v0.2.0" in r.stdout
    assert len(r.log_lines()) == 2 and r.log_lines()[0].endswith("\tOK")   # dòng cũ giữ nguyên, dòng mới nối
    assert RESULT_FAILED in r.log_last()
    stubs.log_before = f"2026-10-01T00:00:00Z\tv0.1.0\t{'b' * 40}\t{'c' * 64}\tFAIL\n"
    stubs.previous_ok_tag = None
    assert "Quay lại bằng: ops/deploy.sh none" in run("v0.3.0").stdout     # FAIL kiểu cũ không phải bản tốt


def test_log_with_garbage_previous_tag_is_ignored(run, stubs):
    row = ["2026-10-01T00:00:00Z", "$(touch pwned)", "b" * 40, "c" * 64, "result=ok", "signed=yes"]
    stubs.log_before = "\t".join(row) + "\n"
    stubs.readyz = "503"
    r = run("v0.3.0")
    assert r.returncode == 5 and not any("pwned" in c for c in r.calls)


# ---------- chữ ký tag (S4) ----------

VERIFY = "git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/"


def test_unsigned_tag_refused_before_any_change(run, stubs):
    stubs.extra["FAKE_VERIFY_TAG_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 2
    assert not any(c.startswith(("docker", "curl", "web_build")) for c in r.calls)
    assert not any("checkout" in c for c in r.calls)
    assert not (r.repo / "deploy/release.env").exists() and r.log_lines() == []
    assert "chưa ký" in r.stderr and "allowed_signers" in r.stderr
    assert "hỏng" not in r.stdout                               # không phải một lần triển khai hỏng


def test_signed_tag_verified_with_allowed_signers(run):
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{VERIFY}v0.3.0" in r.calls
    assert r.order([f"{VERIFY}v0.3.0", f"checkout --detach {COMMIT}"])
    assert not any("checkout --detach v" in c for c in r.calls)   # checkout theo OID, không theo tên
    assert r.order(["git fetch", f"{VERIFY}v0.3.0"])           # tag phải có ở máy trước khi kiểm
    assert r.calls.index(f"{VERIFY}v0.3.0") < min(i for i, c in enumerate(r.calls) if c.startswith("docker"))
    assert r.log_last().endswith("\tresult=ok\tsigned=yes")


def test_verify_resolves_allowed_signers_from_the_repo_root_wherever_invoked(run, stubs, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    stubs.cwd = elsewhere
    r = run("v0.3.0")
    assert r.returncode == 0, r.stdout + r.stderr
    pwd = (tmp_path / "calls.log.pwd").read_text(encoding="utf-8").strip()
    assert Path(pwd).resolve() == r.repo.resolve()      # deploy/allowed_signers tương đối: đúng gốc repo


def test_allow_unsigned_logs_warning(run):
    r = run("v0.3.0", "--allow-unsigned")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.log_last().endswith("\tresult=ok\tsigned=no")
    assert "CẢNH BÁO" in r.stderr and "--allow-unsigned" in r.stderr
    assert not any("verify-tag" in c for c in r.calls)


def test_allow_unsigned_accepts_a_tag_that_fails_verification_and_option_order_is_free(run, stubs):
    stubs.extra["FAKE_VERIFY_TAG_FAIL"] = "1"
    r = run("--allow-unsigned", "v0.3.0", "--profile", "p8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "signed=no" in r.log_last()


def test_rollback_keeps_the_signature_policy(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"
    stubs.extra["FAKE_BAD_TAGS"] = "v1.0.0"
    r = run("v1.0.0")
    assert r.returncode == 4
    assert f"{VERIFY}v1.0.0" in r.calls and f"{VERIFY}v0.9.0" in r.calls
    r = run("v1.0.0", "--allow-unsigned")
    assert r.returncode == 4 and not any("verify-tag" in c for c in r.calls)
    assert r.log_lines()[-1].endswith("\tresult=rolled-back\tsigned=no")


def test_rollback_target_failing_signature_is_exit_5(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"
    stubs.extra.update({"FAKE_BAD_TAGS": "v1.0.0", "FAKE_VERIFY_TAG_FAIL": "v0.9.0"})
    stubs.commits = {"v0.9.0": "9" * 40}
    r = run("v1.0.0")
    assert r.returncode == 5 and "Khôi phục tay" in r.stdout
    assert not any("checkout --detach " + "9" * 40 in c for c in r.calls)   # tag không đạt chữ ký


# ---------- tên tag bị đổi (replay), tag nhẹ, allowed_signers rỗng ----------

def test_renamed_signed_tag_is_refused_before_any_change(run, stubs):
    stubs.extra["FAKE_TAG_NAME_v1_1_0"] = "v1.0.0"      # thân tag ký của v1.0.0 đẩy lên dưới tên v1.1.0
    r = run("v1.1.0")
    assert r.returncode == 2, r.stdout + r.stderr
    assert f"{VERIFY}v1.1.0" in r.calls                         # chữ ký thì hợp lệ: chính tên mới là vấn đề
    assert not any(c.startswith(("docker", "curl", "web_build")) for c in r.calls)
    assert not any("checkout" in c for c in r.calls)
    assert "không khớp" in r.stderr and "v1.0.0" in r.stderr
    assert not (r.repo / "deploy/release.env").exists() and r.log_lines() == []


def test_refused_tag_drops_the_ref_it_fetched_but_keeps_a_preexisting_one(run, stubs):
    stubs.extra["FAKE_TAG_NAME_v1_1_0"] = "v1.0.0"
    r = run("v1.1.0")
    assert "git update-ref -d refs/tags/v1.1.0" in r.calls
    stubs.extra["FAKE_HAD_REF_v1_1_0"] = "d" * 40               # tag cục bộ đã có từ trước: không đụng
    r = run("v1.1.0")
    assert r.returncode == 2 and not any("update-ref" in c for c in r.calls)
    stubs.extra.pop("FAKE_HAD_REF_v1_1_0")
    stubs.extra["FAKE_VERIFY_TAG_FAIL"] = "1"                   # chữ ký hỏng cũng dọn ref vừa fetch
    assert "git update-ref -d refs/tags/v1.1.0" in run("v1.1.0").calls


def test_lightweight_tag_without_a_tag_object_is_refused(run, stubs):
    stubs.extra["FAKE_LIGHTWEIGHT"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 2 and not any(c.startswith("docker") or "checkout" in c for c in r.calls)


def test_rollback_target_with_renamed_tag_is_exit_5(run, stubs):
    stubs.previous_ok_tag = "v0.9.0"
    stubs.readyz = "503"
    stubs.extra.update({"FAKE_BAD_TAGS": "v1.0.0", "FAKE_TAG_NAME_v0_9_0": "v0.8.0"})
    stubs.commits = {"v0.9.0": "9" * 40}
    r = run("v1.0.0")
    assert r.returncode == 5 and "Khôi phục tay" in r.stdout
    assert not any("checkout --detach " + "9" * 40 in c for c in r.calls)


def test_empty_or_missing_allowed_signers_refuses_before_fetch(run, stubs):
    for content in ("", "# chỉ chú thích\n\n   \n# V42\n", None):
        stubs.signers = content
        r = run("v0.3.0")
        assert r.returncode == 2, content
        assert r.calls == ["git status --porcelain"], r.calls      # chưa fetch, chưa verify
        assert "V42" in r.stderr and "không có khóa nào" in r.stderr
        assert r.log_lines() == []


def test_allow_unsigned_does_not_need_allowed_signers(run, stubs):
    stubs.signers = None
    r = run("v0.3.0", "--allow-unsigned")
    assert r.returncode == 0, r.stdout + r.stderr


def test_fetch_failure_message_tells_how_to_drop_a_stale_local_tag(run, stubs):
    stubs.extra["FAKE_FETCH_FAIL"] = "1"
    r = run("v0.3.0")
    assert r.returncode == 3 and "git tag -d v0.3.0" in r.stderr


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


def test_allowed_signers_is_comment_only_until_the_real_key_exists():
    lines = (ROOT / "deploy/allowed_signers").read_text(encoding="utf-8").splitlines()
    assert lines and all(ln.startswith("#") or not ln.strip() for ln in lines)   # khóa thật là việc V42
    assert any("SPDX-" + "License-Identifier: Apache-2.0" in ln for ln in lines)


def test_runbook_documents_signing_exit_codes_and_the_unsigned_caveat():
    text = (ROOT / "docs/runbook-deploy.md").read_text(encoding="utf-8")
    for needle in ("git config gpg.format ssh", "user.signingkey", "git tag -s", "deploy/allowed_signers",
                   "--allow-unsigned", "signed=no", "result=rolled-back", "V42"):
        assert needle in text, needle
    table = text[text.index("### 2.1. Mã thoát"):text.index("### 2.2.")]
    assert all(f"| {code} |" in table for code in range(6) if code != 1)


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
