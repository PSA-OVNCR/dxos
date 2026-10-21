# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Hướng dẫn "Viết app DX-OS trong 30 phút" và checklist AT-26 (Plan 03 Task 13, H13).

Kiểm: đủ năm bước có mốc thời gian; mọi lệnh `dxos` và `make` trong hướng dẫn có thật; đoạn manifest
trong hướng dẫn là đúng nội dung tệp ví dụ (không lệch); lệnh chưa chạy được ở cloud được đánh dấu; có mục
"Kiểm lại P1"; README trỏ tới hướng dẫn.
"""

import re
import shlex
from pathlib import Path

import pytest
from dxos_cli.main import build_parser

ROOT = Path(__file__).resolve().parents[2]
TUTORIAL = ROOT / "docs/tutorial-app-30-phut.md"
CHECKLIST = ROOT / "docs/at26-checklist.md"
UNVERIFIED = "chưa kiểm ở cloud — kiểm trong AT-26"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code_blocks(text: str) -> list[tuple[str, str]]:
    return re.findall(r"^```(\w*)\n(.*?)^```", text, re.S | re.M)


def _shell_lines(text: str) -> list[str]:
    out = []
    for lang, body in _code_blocks(text):
        if lang in {"bash", "sh", "console"}:
            out += [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return out


def test_tutorial_has_the_five_timed_steps_in_order():
    heads = re.findall(r"^## (.+)$", _text(TUTORIAL), re.M)
    stamps = [re.match(r"\((\d+)[–-](\d+)'\)", h) for h in heads]
    assert [(m.group(1), m.group(2)) for m in stamps if m] == [
        ("0", "5"), ("5", "15"), ("15", "20"), ("20", "25"), ("25", "30")]


def test_tutorial_sections_cover_the_required_content():
    t = _text(TUTORIAL)
    for needle in ("make up PROFILE=dev-lite", "dxos login", "dxos app install examples/so-muon-sach",
                   "dxos app diff so-muon-sach 1.0.0", "dxos app approve so-muon-sach 1.0.0",
                   "app:so-muon-sach:ban_doc", "app:so-muon-sach:thu_thu", "make web-build",
                   "/apps/so-muon-sach/",
                   "FLOOR_WEAKENED", "spec 9.2", "Kiểm lại P1", "git diff --stat", "-- core/",
                   "console Keycloak", "admin.", "not_same_actor:creator"):
        assert needle in t, needle


def test_every_dxos_command_in_the_tutorial_parses_with_the_real_cli():
    lines = [ln for ln in _shell_lines(_text(TUTORIAL)) if re.match(r"(DXOS_\w+=\S+ )*dxos ", ln)]
    assert len(lines) >= 5
    parser = build_parser()
    for ln in lines:
        line = re.sub(r"^(DXOS_\w+=\S+ )*", "", ln.replace("<miền>", "example.vn"))
        argv = shlex.split(line.split(" #")[0])[1:]
        parser.parse_args(argv)                                         # SystemExit nếu lệnh hay đối số sai


def test_every_make_target_in_the_tutorial_exists():
    makefile = _text(ROOT / "Makefile")
    targets = set(re.findall(r"^([a-z][\w-]*):", makefile, re.M))
    used = {m.group(1) for ln in _shell_lines(_text(TUTORIAL)) if (m := re.match(r"make (\w[\w-]*)", ln))}
    assert {"up", "web-build"} <= used
    assert used <= targets, used - targets


def test_manifest_and_bpmn_in_the_tutorial_are_the_example_files():
    t = _text(TUTORIAL)
    blocks = [body for _, body in _code_blocks(t)]
    yaml_body = _text(ROOT / "examples/so-muon-sach/manifest.yaml").split("\n", 3)[3]  # sau 3 dòng đầu
    assert any(yaml_body.strip() in b for b in blocks), "đoạn manifest trong hướng dẫn lệch tệp ví dụ"
    bpmn = _text(ROOT / "examples/so-muon-sach/bpmn/duyet-muon.bpmn")
    process = re.search(r"<process .*?</process>", bpmn, re.S).group(0)
    assert any(process in b for b in blocks), "đoạn BPMN trong hướng dẫn lệch duyet-muon.bpmn"


def test_commands_not_run_in_the_cloud_are_marked_unverified():
    t = _text(TUTORIAL)
    assert t.count(UNVERIFIED) >= 5
    assert "đã kiểm" in t                                           # có phần ghi rõ lệnh đã chạy thật
    for section in re.split(r"^## ", t, flags=re.M)[1:]:
        if re.match(r"\((15|20|25)[–-]", section):                   # các bước cần stack thật
            assert UNVERIFIED in section, section.splitlines()[0]


def test_p1_recheck_section_has_the_empty_diff_command_and_floor_example():
    t = _text(TUTORIAL)
    assert re.search(r"git diff --stat <commit[^>]*> -- core/", t)
    assert re.search(r"FLOOR_WEAKENED.*quarantine", t, re.S)


def test_checklist_covers_the_at26_procedure():
    c = _text(CHECKLIST)
    for needle in ("AT-26", "V31", "docs/tutorial-app-30-phut.md", "docs/progress/", "core/",
                   "git diff --stat", "30 phút", "Vướng", "Biên bản"):
        assert needle in c, needle
    assert re.search(r"(?i)(8 GB|16 GB)", c) and "Docker" in c
    assert "Mẫu biên bản" in c


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md"])
def test_readmes_link_the_tutorial(readme):
    assert "docs/tutorial-app-30-phut.md" in _text(ROOT / readme)


def test_example_readme_exists_and_points_to_the_tutorial():
    r = _text(ROOT / "examples/so-muon-sach/README.md")
    assert "docs/tutorial-app-30-phut.md" in r and "manifest.yaml" in r
