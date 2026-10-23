# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tài liệu và phát hành M4 (Plan 04 Task 15): mọi phiên bản bằng 0.9.0, CHANGELOG có mục [0.9.0] đã ghi
ngày, README nêu S1..S4 kèm việc V chưa chạy, không câu cấm nào của spec 25.1, AT-21 trỏ test thật, mục 14
của bản tổng kết tiến độ đủ bảng task, V37..V44 và các ruling R1..R28, workflow ``release`` đưa Viewer (image
và wheel) vào Release cùng cách với ``trust-core`` (ruling R28)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.9.0"
PROGRESS = "docs/progress/2026-10-21-tong-ket-tien-do.md"
LEDGER = ROOT / ".superpowers/sdd/2026-10-22-dxos-04-should-release/progress.md"

PYPROJECTS = (
    "libs/dxos-proof/pyproject.toml", "core/pyproject.toml", "witness/pyproject.toml", "cli/pyproject.toml",
    "viewer/pyproject.toml",
)
INITS = (
    "core/src/dxos_core/__init__.py", "witness/src/dxos_witness/__init__.py", "cli/src/dxos_cli/__init__.py",
    "viewer/src/dxos_viewer/__init__.py",
)
PACKAGE_JSONS = (
    "package.json", "sdk/js/package.json", "verify-portal/app/package.json",
    "apps/phong-ho-so/web/package.json", "apps/chung-nhan/web/package.json",
    "examples/so-muon-sach/web/package.json", "admin-ui/package.json",
)
# spec 25.1, "Không nói" (tiếng Việt) và dạng tiếng Anh tương ứng cho README_EN
FORBIDDEN_VI = ("sẵn sàng để được chứng nhận", "có giá trị pháp lý", "tuân thủ Nghị định 30")
FORBIDDEN_EN = ("ready to be certified", "ready for certification", "legally valid", "legally binding",
                "complies with decree 30", "compliant with decree 30")


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _changelog_090() -> str:
    text = _doc("CHANGELOG.md")
    i = text.index(f"\n## [{VERSION}] - ")
    return text[i: text.index("\n## [0.3.0] - ", i)]


def _progress_14() -> str:
    text = _doc(PROGRESS)
    return text[text.index("\n## 14. Plan 04"):]


# ---------------------------------------------------------------- phiên bản
@pytest.mark.parametrize("rel", PYPROJECTS)
def test_python_pyproject_versions(rel):
    assert f'version = "{VERSION}"' in _doc(rel).splitlines(), rel


@pytest.mark.parametrize("rel", INITS)
def test_python_init_versions(rel):
    assert f'__version__ = "{VERSION}"' in _doc(rel).splitlines(), rel


@pytest.mark.parametrize("rel", PACKAGE_JSONS)
def test_npm_package_versions(rel):
    assert json.loads(_doc(rel))["version"] == VERSION, rel


def test_every_workspace_package_json_is_covered():
    """Không workspace nào bị sót: mọi package.json ngoài node_modules có trong danh sách trên."""
    found = {
        p.relative_to(ROOT).as_posix() for p in ROOT.rglob("package.json")
        if "node_modules" not in p.parts and ".venv" not in p.parts and "test-results" not in p.parts
    }
    assert found == set(PACKAGE_JSONS)


def test_package_lock_matches():
    lock = json.loads(_doc("package-lock.json"))
    assert lock["version"] == VERSION
    for key, entry in lock["packages"].items():
        if key == "" or ("node_modules" not in key and not entry.get("link")):
            assert entry["version"] == VERSION, key


def test_openapi_json_version():
    assert json.loads(_doc("docs/api/openapi.json"))["info"]["version"] == VERSION


def test_release_check_covers_the_viewer():
    sys.path.insert(0, str(ROOT / "ops"))
    try:
        import release_check as rc
    finally:
        sys.path.remove(str(ROOT / "ops"))
    assert "viewer/pyproject.toml" in rc.PYPROJECTS
    assert "viewer/src/dxos_viewer/__init__.py" in rc.INITS
    assert rc.check_versions(ROOT, VERSION) == []


def test_make_release_check_text_names_the_viewer():
    assert "viewer" in _doc("BUILD.md").split("## Phát hành", 1)[1]


# ---------------------------------------------------------------- CHANGELOG
def test_changelog_090_is_dated_above_030():
    text = _doc("CHANGELOG.md")
    i090 = text.index(f"\n## [{VERSION}] - 2026-10-23\n")
    i030 = text.index("\n## [0.3.0] - ")
    assert text.index("## [Unreleased]") < i090 < i030
    sec = _changelog_090()
    for h in ("### Added", "### Changed", "### Fixed", "### Security", "### Known limitations"):
        assert h in sec, h
    assert "Chưa phát hành" not in sec
    # [Unreleased] đã chuyển hết vào [0.9.0]
    between = text[text.index("## [Unreleased]"): i090]
    assert "### " not in between, "còn mục trong [Unreleased]"


def test_changelog_section_tool_reads_090():
    out = subprocess.run([sys.executable, str(ROOT / "ops/changelog_section.py"), VERSION],
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert out.stdout.startswith(f"## [{VERSION}]")


def test_changelog_090_gathers_s1_to_s4_and_pof():
    sec = _changelog_090()
    for token in ("S1", "S2", "S3", "S4", "PoF"):
        assert token in sec, token
    # S1: phát hiện PII, bản che; S2: Viewer; S3: trang quản trị; S4: ký tag, quay lui, sao lưu
    for token in ("CCCD", "variant=redacted", "Viewer", "dxos-viewer", "admin-ui", "verify-tag", "tự quay",
                  "at21_drill", "demo-seed", "constraints.txt", "pin_actions", "release-check",
                  "ARCHITECTURE.md"):
        assert token in sec, token


def test_changelog_090_states_the_breaking_sdk_rename_and_limits():
    sec = _changelog_090()
    assert "BREAKING" in sec
    assert "client.download" in sec and "downloadObject" in sec
    assert "100 MiB" in sec                                       # trần bản che (ruling R20)
    for n in ("006", "007", "008", "009"):
        assert f"{n}_" in sec or f"migration {n}" in sec or n in sec, n
    for env in ("DXOS_ADMIN_HOST", "COMPOSE_PROFILES=viewer", "DXOS_VIEWER_API_BASE", "DXOS_VIEWER_MAX_BYTES",
                "DXOS_VIEWER_DIGEST"):
        assert env in sec, env


def test_changelog_090_known_limitations_list_every_unrun_v_item():
    sec = _changelog_090()
    limits = sec[sec.index("### Known limitations"):]
    for v in range(37, 45):
        assert f"V{v}" in limits, f"V{v}"
    # tên đúng các mục chưa chạy (Viewer, trang quản trị, ký tag, sao lưu, demo-seed)
    for token in ("Viewer", "trang quản trị", "AT-21", "demo-seed", "chưa chạy"):
        assert token in limits, token


# ---------------------------------------------------------------- README, câu cấm
@pytest.mark.parametrize("rel", ["README.md", "README_EN.md"])
def test_readme_states_s1_to_s4_with_unrun_v_items(rel):
    text = _doc(rel)
    assert "0.9.0" in text
    for token in ("S1", "S2", "S3", "S4"):
        assert token in text, (rel, token)
    for v in ("V37", "V38", "V39", "V40", "V41", "V42", "V43", "V44"):
        assert v in text, (rel, v)
    assert "docs/progress/2026-10-21-tong-ket-tien-do.md" in text


@pytest.mark.parametrize("rel", ["README.md", "README_EN.md"])
def test_readme_watermark_is_deterrent_only(rel):
    text = _doc(rel)
    assert ("chỉ để răn đe" if rel == "README.md" else "deterrent") in text
    if rel == "README_EN.md":
        assert "deterrent only" in text or "only a deterrent" in text


@pytest.mark.parametrize("rel", ["README.md", "README_EN.md", "docs/acceptance.md", "ARCHITECTURE.md",
                                 "viewer/README.md", "docs/runbook-deploy.md", "docs/runbook-backup.md"])
def test_no_forbidden_legal_phrase_in_docs(rel):
    low = _doc(rel).lower()
    for phrase in FORBIDDEN_VI + FORBIDDEN_EN:
        assert phrase.lower() not in low, (rel, phrase)


def test_no_forbidden_legal_phrase_in_changelog_090_and_progress_14():
    for name, text in (("CHANGELOG [0.9.0]", _changelog_090()), ("progress mục 14", _progress_14())):
        low = text.lower()
        for phrase in FORBIDDEN_VI + FORBIDDEN_EN:
            assert phrase.lower() not in low, (name, phrase)


def test_readme_no_longer_says_v030_is_the_current_state():
    text = _doc("README.md")
    assert "## Trạng thái v0.9.0" in text
    assert "## Trạng thái v0.3.0" not in text.split("## Trạng thái v0.9.0", 1)[0]


# ---------------------------------------------------------------- acceptance
def test_acceptance_at21_points_to_real_tests_and_the_manual_drill():
    row = next(ln for ln in _doc("docs/acceptance.md").splitlines() if ln.startswith("| AT-21 |"))
    assert "tests/ops/test_backup_restore.py" in row
    assert "V43" in row and "ops/at21_drill.sh" in row
    assert (ROOT / "tests/ops/test_backup_restore.py").is_file()
    # mọi tên test được dẫn có thật
    src = _doc("tests/ops/test_backup_restore.py")
    names = re.findall(r"tests/ops/test_backup_restore\.py::(\w+)", row)
    for name in names:
        assert f"def {name}" in src, name


# ---------------------------------------------------------------- bản tổng kết tiến độ, mục 14
def test_progress_14_has_task_table_numbers_and_v_items():
    sec = _progress_14()
    for n in range(1, 17):
        assert re.search(rf"^\| {n} \|", sec, re.M), f"thiếu hàng task {n}"
    for v in range(37, 45):
        assert re.search(rf"^\| V{v} \|", sec, re.M), f"thiếu V{v}"
    assert re.search(r"\d+ passed", sec)                          # số test cuối của lần chạy cổng
    assert "reuse lint" in sec and "CI" in sec
    assert "verify_page_checks.js" in sec and "ignoreHTTPSErrors" in sec     # nợ của Task 14 (bộ riêng)
    assert "chưa chạy" in sec


def test_progress_14_lists_every_ruling_of_the_ledger():
    ledger = LEDGER.read_text(encoding="utf-8") if LEDGER.is_file() else ""
    numbers = sorted({int(n) for n in re.findall(r"^(?:- )?Ruling R(\d+)[: ]", ledger, re.M)})
    sec = _progress_14()
    assert "### 14.4" in sec or "Rulings" in sec
    wanted = numbers or list(range(1, 29))
    assert wanted == list(range(1, 29)), "sổ điều phối phải có R1..R28"
    for n in wanted:
        assert re.search(rf"^\| R{n} \|", sec, re.M), f"thiếu R{n}"
    assert "Nếu sai" in sec or "nếu sai" in sec


def test_progress_milestone_row_m4_mentions_the_code_state():
    row = next(ln for ln in _doc(PROGRESS).splitlines() if ln.startswith("| M4 |"))
    assert "Chưa bắt đầu" not in row and "tag" in row


# ------------------------------------------------------- release.yml: Viewer cùng cách với trust-core
def _wf() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))


def test_release_workflow_has_a_viewer_image_job_like_trust_core():
    jobs = _wf()["jobs"]
    assert "image-viewer" in jobs
    job = jobs["image-viewer"]
    assert job["needs"] == "check"
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    assert job["outputs"] == {"digest": "${{ steps.push.outputs.digest }}"}
    text = json.dumps(job["steps"], ensure_ascii=False)
    assert "docker build -f viewer/Dockerfile" in text
    assert "ghcr.io/psa-ovncr/viewer:${VERSION}" in text
    assert "docker push" in text and "--password-stdin" in text
    assert "ghcr.io/psa-ovncr/trust-core" not in text
    assert set(jobs["release"]["needs"]) == {"image", "image-viewer"}


def test_release_workflow_publishes_viewer_digest_and_wheel():
    steps = _wf()["jobs"]["release"]["steps"]
    text = json.dumps(steps, ensure_ascii=False)
    assert "dist/viewer-image-${VERSION}.txt" in text
    assert "ghcr.io/psa-ovncr/viewer@sha256:${VIEWER_DIGEST}" in text
    assert "DXOS_VIEWER_DIGEST=${VIEWER_DIGEST}" in text
    notes = next(s for s in steps if s.get("name", "").startswith("Ghi chú phát hành"))
    assert notes["env"]["VIEWER_DIGEST"] == "${{ needs.image-viewer.outputs.digest }}"
    assert "for pkg in libs/dxos-proof core witness cli viewer; do" in text


def test_release_check_job_verifies_the_viewer_version():
    runs = "\n".join(s.get("run", "") for s in _wf()["jobs"]["check"]["steps"])
    assert "viewer/pyproject.toml" in runs
    assert "viewer/src/dxos_viewer/__init__.py" in runs


def test_release_workflow_header_mentions_the_viewer():
    head = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8").split("name: release", 1)[0]
    assert "viewer" in head and "dxos-viewer" in head
