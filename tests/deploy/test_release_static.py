# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tĩnh phần phát hành của Plan 02 Task 15: workflow ``release`` (image trust-core lên GHCR, digest trong
Release), overlay ``deploy/compose.release.yaml`` (image theo digest, không build) và cú pháp các script vận
hành.

Overlay được kiểm bằng ``docker compose config`` (chỉ cần CLI, không cần daemon); không có CLI thì bỏ qua."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"
DIGEST = "0123456789abcdef" * 4
IMAGE = f"ghcr.io/psa-ovncr/trust-core@sha256:{DIGEST}"
CORE = ("trust-core-api", "trust-core-worker")


def _is_action(uses: str, action: str) -> bool:
    """``uses`` là ``action`` ở dạng SHA 40 ký tự (ghim bằng ops/pin_actions.py)."""
    return re.fullmatch(re.escape(action) + r"@[0-9a-f]{40}", uses or "") is not None


def _wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(job: str) -> str:
    return "\n".join(json.dumps(s, ensure_ascii=False) for s in _wf()["jobs"][job]["steps"])


# ---------------------------------------------------------------- workflow release
def test_release_runs_only_on_version_tags_with_least_privilege():
    wf = _wf()
    assert wf[True] == {"push": {"tags": ["v*.*.*"]}}               # PyYAML đọc khóa `on` thành True
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    assert jobs["image"]["permissions"] == {"contents": "read", "packages": "write"}
    assert jobs["release"]["permissions"] == {"contents": "write"}
    assert "permissions" not in jobs["check"]
    assert jobs["image"]["needs"] == "check" and jobs["release"]["needs"] == "image"


def test_every_job_builds_from_the_tag_commit():
    for job in ("check", "image", "release"):
        checkout = _wf()["jobs"][job]["steps"][0]
        assert _is_action(checkout["uses"], "actions/checkout")
        assert checkout["with"]["ref"] == "${{ github.ref }}", job


def test_check_job_sets_up_python_before_running_ops_scripts():
    steps = _wf()["jobs"]["check"]["steps"]
    assert _is_action(steps[1]["uses"], "actions/setup-python")
    assert steps[1]["with"] == {"python-version": "3.12"}


def test_check_job_refuses_unreleased_changelog_and_version_mismatch():
    runs = "\n".join(s.get("run", "") for s in _wf()["jobs"]["check"]["steps"])
    assert 'python ops/changelog_section.py "$VERSION"' in runs
    # Mục "## [X.Y.Z] - Chưa phát hành" không khớp mẫu ngày nên job dừng trước khi đẩy image.
    assert '- [0-9]{4}-[0-9]{2}-[0-9]{2}\\$" CHANGELOG.md' in runs
    for f in ("libs/dxos-proof/pyproject.toml", "core/pyproject.toml", "witness/pyproject.toml",
              "cli/pyproject.toml",
              "core/src/dxos_core/__init__.py", "witness/src/dxos_witness/__init__.py",
              "cli/src/dxos_cli/__init__.py"):
        assert f in runs, f


def test_image_job_pushes_trust_core_to_ghcr_with_github_token_and_outputs_digest():
    job = _wf()["jobs"]["image"]
    steps = _steps("image")
    assert 'docker build -f core/Dockerfile -t \\"ghcr.io/psa-ovncr/trust-core:${VERSION}\\"' in steps
    assert "docker push \\\"ghcr.io/psa-ovncr/trust-core:${VERSION}\\\"" in steps
    push = next(s for s in job["steps"] if s.get("id") == "push")
    assert push["env"] == {"GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}
    assert "--password-stdin" in push["run"] and "$GH_TOKEN" not in push["run"].split("|", 1)[1]
    assert job["outputs"] == {"digest": "${{ steps.push.outputs.digest }}"}


def test_release_notes_carry_the_digest_and_assets_include_four_wheels():
    job = _wf()["jobs"]["release"]
    notes = next(s for s in job["steps"] if s.get("name", "").startswith("Ghi chú phát hành"))
    assert notes["env"] == {"DIGEST": "${{ needs.image.outputs.digest }}"}
    assert "ghcr.io/psa-ovncr/trust-core@sha256:${DIGEST}" in notes["run"]
    assert "DXOS_TRUST_CORE_DIGEST=${DIGEST}" in notes["run"]
    steps = _steps("release")
    assert "for pkg in libs/dxos-proof core witness cli; do" in steps
    assert "anchore/syft:v1.18.1" in steps and "git archive --format=tar.gz" in steps
    assert "gh release create" in steps and "--verify-tag" in steps


def test_release_attaches_the_web_build_as_a_tarball():
    """Plan 03 Task 12: ``ops/build_web.sh`` trong môi trường Node 22 + npm 11.6.2, đóng gói thành
    ``dxos-web-<X.Y.Z>.tar.gz`` trong ``dist/`` (cùng các tệp đính kèm khác); thư mục build nằm ngoài
    ``dist/``."""
    steps = _wf()["jobs"]["release"]["steps"]
    node = next(i for i, s in enumerate(steps) if _is_action(s.get("uses"), "actions/setup-node"))
    assert steps[node]["with"] == {"node-version": "22"}
    web = next(i for i, s in enumerate(steps) if "ops/build_web.sh" in s.get("run", ""))
    run = steps[web]["run"]
    assert node < web
    assert run.index("npm i -g npm@11.6.2") < run.index("sh ops/build_web.sh build-web")
    assert 'tar -czf "dist/dxos-web-${VERSION}.tar.gz" -C build-web .' in run
    assert "dist/web" not in run                         # dist/* được đính kèm: không để thư mục trong đó
    release = next(i for i, s in enumerate(steps) if "gh release create" in s.get("run", ""))
    assert web < release
    sbom = next(i for i, s in enumerate(steps) if "anchore/syft" in s.get("run", ""))
    assert sbom < web                                    # syft không quét node_modules của bước dựng web


# ---------------------------------------------------------------- compose.release.yaml
def _config(*overlays: str, digest: str | None) -> subprocess.CompletedProcess:
    if shutil.which("docker") is None:
        pytest.skip("cần CLI docker compose")
    cmd = ["docker", "compose", "-p", "dxos", "--env-file", str(ROOT / ".env.example")]
    for o in overlays:
        cmd += ["-f", str(ROOT / "deploy" / o)]
    env = {k: v for k, v in os.environ.items() if k != "DXOS_TRUST_CORE_DIGEST"}
    if digest is not None:
        env["DXOS_TRUST_CORE_DIGEST"] = digest
    proc = subprocess.run([*cmd, "config", "--format", "json"], capture_output=True, text=True,  # noqa: S603
                          check=False, env=env)
    if proc.returncode != 0 and "is not a docker command" in proc.stderr:
        pytest.skip("cần plugin docker compose v2")
    return proc


@pytest.mark.parametrize("profile", ["p16", "p8"])
def test_release_overlay_only_swaps_build_for_the_released_image(profile):
    base = json.loads(_config("compose.yaml", f"compose.{profile}.yaml", digest=None).stdout)
    rel = _config("compose.yaml", f"compose.{profile}.yaml", "compose.release.yaml", digest=DIGEST)
    assert rel.returncode == 0, rel.stderr
    rel = json.loads(rel.stdout)
    for svc in CORE:
        assert "build" in base["services"][svc]
        r = rel["services"][svc]
        assert r["image"] == IMAGE and "build" not in r, svc
        assert r["pull_policy"] == "missing"
        strip = {"image", "build", "pull_policy"}
        assert {k: v for k, v in r.items() if k not in strip} == \
               {k: v for k, v in base["services"][svc].items() if k not in strip}, svc
    others = set(base["services"]) - set(CORE)
    assert {s: rel["services"][s] for s in others} == {s: base["services"][s] for s in others}


def test_release_overlay_requires_the_digest():
    proc = _config("compose.yaml", "compose.p16.yaml", "compose.release.yaml", digest=None)
    assert proc.returncode != 0 and "DXOS_TRUST_CORE_DIGEST" in proc.stderr


# ---------------------------------------------------------------- script vận hành
SCRIPTS = [ROOT / "ops/at13_reuse.sh", ROOT / "ops/e2e/install_apps.sh", ROOT / "ops/e2e/run_e2e.sh"]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_ops_scripts_parse_and_are_executable(script):
    shell = "bash" if script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash") else "sh"
    if shutil.which(shell) is None:
        pytest.skip(f"cần {shell}")
    proc = subprocess.run([shell, "-n", str(script)], capture_output=True, text=True, check=False)  # noqa: S603
    assert proc.returncode == 0, proc.stderr
    assert os.access(script, os.X_OK)
    spdx = "SPDX-" + "License-Identifier: Apache-2.0"         # tách chuỗi để reuse lint không đọc nhầm
    assert spdx in script.read_text(encoding="utf-8")


def test_run_e2e_installs_apps_with_the_cli_not_the_seed_script():
    text = (ROOT / "ops/e2e/run_e2e.sh").read_text(encoding="utf-8")
    assert "install_apps.sh" in text
    # mỗi token một dòng: lấy token lỗi thì set -e dừng ngay
    assert "\nADMIN1_TOKEN=$(token admin1)\nADMIN2_TOKEN=$(token admin2)\n" in text
    assert "DXOS_TOKEN=$ADMIN1_TOKEN DXOS_APPROVER_TOKEN=$ADMIN2_TOKEN" in text
    assert "python -m dxos_core.registry.seed" not in text and "python ops/seed_manifests.py" not in text
    assert "DXOS_ALLOW_SELF_APPROVAL" not in text


def test_seed_script_is_marked_core_tests_only():
    assert "**Chỉ dùng cho test lõi.**" in (ROOT / "ops/seed_manifests.py").read_text(encoding="utf-8")
