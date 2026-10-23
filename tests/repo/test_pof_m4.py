# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Chỗ trống PoF (Plan 04 Task 2): ARCHITECTURE.md, trang tài liệu (GitHub Pages), capacity.md,
target Makefile, cấu hình mẫu issue, mục "Thành viên đóng góp"."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md"


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_architecture_sections_and_pointer_to_spec():
    text = _doc("ARCHITECTURE.md")
    headings = (
        "## Ba tầng", "## Mạng", "## Luồng tải tệp", "## Niêm phong và sổ cái", "## Ranh giới tin cậy",
    )
    for heading in headings:
        assert re.search(rf"^{re.escape(heading)}\s*$", text, re.M), heading
    assert SPEC in text
    assert "```mermaid" in text
    assert len(text.splitlines()) < 250


def test_architecture_keeps_legal_wording_rules():
    text = _doc("ARCHITECTURE.md")
    # spec 25.1: không gọi niêm phong là "có giá trị pháp lý", không nói "sẵn sàng để được chứng nhận"
    assert not re.search(r"(niêm phong|Niêm phong)[^.\n]{0,40}có giá trị pháp lý(?! không)", text)
    assert "sẵn sàng để được chứng nhận" not in text
    assert "tuân thủ Nghị định 30" not in text


def test_architecture_relative_links_exist():
    for rel in ("ARCHITECTURE.md", "docs/index.md"):
        base = (ROOT / rel).parent
        missing = []
        for target in re.findall(r"\]\(([^)\s]+)\)", _doc(rel)):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            if path and not (base / path).exists():
                missing.append(target)
        assert missing == [], rel


def test_docs_site_config_excludes_internal_dirs():
    text = _doc("docs/_config.yml")
    assert re.search(r"^exclude:", text, re.M)
    for name in ("superpowers", "handoff", "spikes"):
        assert re.search(rf"^\s*-\s*{name}/?\s*$", text, re.M), name


def test_docs_index_links_main_documents():
    text = _doc("docs/index.md")
    blob = "https://github.com/PSA-OVNCR/dxos/blob/main/"
    # trang chỉ phát hành thư mục docs/, nên tệp ngoài docs/ phải là liên kết tuyệt đối tới GitHub
    for target in (blob + "ARCHITECTURE.md", blob + "BUILD.md", blob + "README.md", blob + "README_EN.md"):
        assert f"]({target}" in text, target
    for target in ("runbook-deploy.md", "tutorial-app-30-phut.md", "acceptance.md", "capacity.md"):
        assert f"]({target})" in text, target
    assert "](../" not in text
    for rel in re.findall(r"\]\(" + re.escape(blob) + r"([^)#\s]+)", text):
        assert (ROOT / rel).exists(), rel


def test_makefile_targets():
    text = _doc("Makefile")
    for target in ("build", "sbom", "release-check"):
        assert re.search(rf"^{target}:", text, re.M), target
    assert re.search(r"^build:.*\n\t(docker compose|\$\(COMPOSE\)).* build\s*$", text, re.M)


def test_sbom_uses_same_syft_image_as_release_workflow():
    image = re.search(r"anchore/syft:[\w.\-@:]+", _doc(".github/workflows/release.yml"))
    assert image
    assert image.group(0) in _doc("Makefile")


def test_issue_template_config():
    text = _doc(".github/ISSUE_TEMPLATE/config.yml")
    assert re.search(r"^blank_issues_enabled:\s*false\s*$", text, re.M)
    assert "https://github.com/PSA-OVNCR/dxos/discussions" in text


def test_capacity_table_has_p8_p16_and_every_number_has_a_source():
    text = _doc("docs/capacity.md")
    rows = [r for r in text.splitlines() if r.startswith("|")]
    header = next(r for r in rows if "Nguồn đo" in r)
    cols = [c.strip() for c in header.strip("|").split("|")]
    src = cols.index("Nguồn đo")
    body = [r for r in rows if r is not header and not re.match(r"^\|[\s:|-]+\|$", r)]
    p8 = next(r for r in body if re.match(r"\|\s*p8\b", r))
    p16 = next(r for r in body if re.match(r"\|\s*p16\b", r))
    assert "chưa đo (V13)" in p16
    for row in body:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == len(cols), row
        values = [c for i, c in enumerate(cells) if i not in (0, src)]
        has_number = any(re.search(r"\d", re.sub(r"V\d+", "", c)) for c in values)
        if has_number:
            assert re.search(r"docs/progress/\S+\.md", cells[src]), row
    assert "docs/progress/2026-10-22-p8-ram-laptop.md" in p8
    assert "5 080" in p8 and "62%" in p8
    # không có số liệu nào ngoài bảng mà không kèm nguồn: dòng văn xuôi có số MiB/GB phải nêu nguồn
    for line in text.splitlines():
        if line.startswith("|") or line.startswith("#"):
            continue
        if re.search(r"\d[\d  ]*\s?(MiB|GiB|MB|GB|%)", line):
            assert "docs/progress/" in line, line


def test_contributors_section_lists_three_accounts_only():
    text = _doc("CONTRIBUTING.md")
    section = text.split("## Thành viên đóng góp", 1)[1]
    for account in ("UI-UX-USHP", "Levminh", "kirito99152"):
        assert account in section
    assert "@gmail" not in section and "Cao Thanh Phong" not in section


@pytest.mark.parametrize("rel", ["README.md", "README_EN.md"])
def test_readme_links_architecture_and_docs_site(rel):
    text = _doc(rel)
    assert "](ARCHITECTURE.md)" in text
    assert "https://psa-ovncr.github.io/dxos/" in text


def _release_check(version: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "ops/release_check.py"), version, "--no-fetch"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def _load_release_check():
    spec = importlib.util.spec_from_file_location("release_check", ROOT / "ops/release_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_release_check_rejects_wrong_version_and_is_read_only():
    def state():
        run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout  # noqa: E731
        return run("status", "--porcelain"), run("tag"), run("rev-parse", "HEAD")

    before = state()
    r = _release_check("9.9.9")
    assert r.returncode == 1
    assert "9.9.9" in r.stderr and "CHANGELOG.md" in r.stderr
    assert _release_check("not-a-version").returncode == 2
    assert state() == before


def test_release_check_passes_on_matching_repo_and_flags_each_gap(tmp_path):
    rc = _load_release_check()
    for rel in rc.PYPROJECTS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    for rel in rc.INITS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    draft = "## [Unreleased]\n\n## [1.2.3] - Chưa phát hành\n"
    (tmp_path / "CHANGELOG.md").write_text(draft, encoding="utf-8")
    assert rc.check_versions(tmp_path, "1.2.3") == []
    assert len(rc.check_versions(tmp_path, "1.2.4")) == 7
    assert len(rc.check_changelog(tmp_path, "1.2.3")) == 1
    (tmp_path / "CHANGELOG.md").write_text("## [1.2.3] - 2026-10-23\n", encoding="utf-8")
    assert rc.check_changelog(tmp_path, "1.2.3") == []

    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git = lambda cwd, *a: subprocess.run(  # noqa: E731
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
        cwd=cwd, check=True, capture_output=True,
    )
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(tmp_path, "init", "-b", "main", str(work))
    (work / "a.txt").write_text("x", encoding="utf-8")
    git(work, "add", "a.txt")
    git(work, "commit", "-m", "one")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "origin", "main")
    assert rc.check_git(work, fetch=True) == []
    (work / "a.txt").write_text("y", encoding="utf-8")
    assert any("chưa sạch" in p for p in rc.check_git(work, fetch=False))
    git(work, "commit", "-am", "two")
    assert any("HEAD" in p and "origin/main" in p for p in rc.check_git(work, fetch=False))
    tags = subprocess.run(["git", "tag"], cwd=work, capture_output=True, text=True).stdout.split()
    assert tags == []


def test_release_check_source_never_tags():
    src = _doc("ops/release_check.py")
    assert '"tag"' not in src and "'tag'" not in src and "push" not in src.replace("không đẩy gì", "")
