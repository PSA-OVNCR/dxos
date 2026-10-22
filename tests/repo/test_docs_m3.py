# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tài liệu M3 (Plan 03 Task 15): README trỏ tới hướng dẫn và cổng đối soát, BUILD.md nêu đúng bộ công cụ web,
CHANGELOG có mục 0.3.0 chưa phát hành, README của SDK chỉ nhắc tên có thật trong mã, bản tổng kết tiến độ
liệt kê việc V27..V36 và không khẳng định điều chưa chạy."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


PROGRESS = "docs/progress/2026-10-21-tong-ket-tien-do.md"
PLAN00 = "docs/superpowers/plans/2026-10-20-dxos-00-ke-hoach-tong-the.md"


@pytest.mark.parametrize("rel", ["README.md", "README_EN.md"])
def test_readme_links_tutorial_and_verify_portal(rel):
    text = _doc(rel)
    assert "docs/tutorial-app-30-phut.md" in text
    assert "docs/at26-checklist.md" in text
    assert "/apps/verify/" in text
    assert "/apps/verify-lite/" in text
    assert "/apps/phong-ho-so/" in text
    assert "/apps/chung-nhan/" in text
    assert "make web-build" in text
    assert "sdk/js/README.md" in text


@pytest.mark.parametrize("rel", ["README.md", "README_EN.md", "sdk/js/README.md"])
def test_relative_links_exist(rel):
    base = (ROOT / rel).parent
    missing = []
    for target in re.findall(r"\]\(([^)\s]+)\)", _doc(rel)):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        path = target.split("#", 1)[0]
        if path and not (base / path).exists():
            missing.append(target)
    assert missing == []


def test_readme_status_does_not_claim_untested_web_stack():
    for rel in ("README.md", "README_EN.md"):
        text = _doc(rel)
        assert "V27" in text, rel  # trình duyệt thật + web-build chưa chạy: README nói thẳng


def test_readme_no_longer_says_apps_ui_is_future():
    text = _doc("README.md")
    assert "giao diện ở Plan 03" not in text
    assert "| SDK, SPA của App A/B, cổng Vue | Plan 03 |" not in text


def test_build_md_toolchain():
    text = _doc("BUILD.md")
    assert "npm@11.6.2" in text
    assert "npm ci" in text
    assert "make web-check" in text
    assert "make web-build" in text
    assert "Node.js 22" in text
    assert "engine-strict" in text
    assert "jsdom" in text and "29.1.1" in text
    assert "*(sắp có)*" not in text.split("## Build", 1)[0]
    pkg = json.loads(_doc("package.json"))
    assert pkg["packageManager"] == "npm@11.6.2"
    assert pkg["engines"]["npm"] == "11.6.2"


def test_changelog_has_unreleased_030_above_020():
    text = _doc("CHANGELOG.md")
    i030 = text.index("## [0.3.0] - Chưa phát hành")
    i020 = text.index("## [0.2.0] - ")
    assert i030 < i020
    sec = text[i030:i020]
    for h in ("### Added", "### Changed", "### Security", "### Known limitations"):
        assert h in sec, h
    for v in ("V27", "V28", "V29", "V32"):
        assert v in sec, v
    # Plan 03 đã chuyển khỏi [Unreleased]
    unreleased = text[text.index("## [Unreleased]"):i030]
    assert "vuot_rao" not in unreleased and "OpenTimestamps" not in unreleased


def test_changelog_section_tool_reads_030():
    import subprocess
    import sys

    out = subprocess.run([sys.executable, str(ROOT / "ops/changelog_section.py"), "0.3.0"],
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert out.stdout.startswith("## [0.3.0]")


def _exports() -> set[str]:
    names: set[str] = set()
    for rel in ("sdk/js/src/index.ts", "sdk/js/src/vue/index.ts"):
        for m in re.finditer(r"export\s+(?:type\s+)?(?:\{([^}]*)\}|\*)", _doc(rel)):
            for part in (m.group(1) or "").split(","):
                part = part.strip()
                if part:
                    names.add(part.split(" as ")[-1].replace("default as ", "").strip())
    names |= set(re.findall(r"^export (?:async )?(?:function|const|class|interface|type) (\w+)",
                            _doc("sdk/js/src/testing.ts"), re.M))
    return names


def test_sdk_readme_mentions_only_real_api():
    text = _doc("sdk/js/README.md")
    exports = _exports()
    for name in ("createAuth", "DxosClient", "verifyBundle", "rawAnchor", "QuarantineStatus", "SealQr",
                 "VerifyLink", "RecordForm", "ProblemMessage", "messageFor", "fakeClient", "fakeFetch",
                 "AppShell", "boot", "SealPanel", "PiiPanel"):
        assert name in text, name
        assert name in exports, f"{name} không được SDK export"
    # Mọi phương thức DxosClient nêu trong README có thật trong client.ts
    client = _doc("sdk/js/src/client.ts")
    for m in re.findall(r"client\.(\w+)\(", text):
        assert re.search(rf"^\s+(?:async )?{m}[(<]", client, re.M), f"client.{m}() không có"
    assert "dxos-sdk-js/testing" in text and "dxos-sdk-js/vue" in text and "dxos-sdk-js/style.css" in text
    assert "chưa" in text  # phần giới hạn: không có bản npm công bố, chưa chạy trên trình duyệt thật


def test_progress_has_plan03_table_and_v_items():
    text = _doc(PROGRESS)
    sec = text[text.index("## 13. Plan 03"):]
    for n in range(1, 16):
        assert re.search(rf"^\| {n} \|", sec, re.M), f"thiếu hàng task {n}"
    for v in range(27, 37):
        assert re.search(rf"^\| V{v} \|", sec, re.M), f"thiếu V{v}"
    assert "40d6d64" in sec  # sửa mở khóa AT-20 (V36)
    assert "NODE_IMAGE" in sec and "PLAYWRIGHT_IMAGE" in sec
    assert "| M3 |" in text and "tag" in text.split("| M3 |", 1)[1].split("\n", 1)[0]


def test_progress_records_real_counts_and_flags_unrun():
    sec = _doc(PROGRESS)
    sec = sec[sec.index("## 13. Plan 03"):]
    assert re.search(r"\d+ passed", sec)
    assert "chưa chạy" in sec


def test_plan00_row_03_updated():
    row = next(ln for ln in _doc(PLAN00).splitlines() if ln.startswith("| 03 |"))
    assert "15/15" in row
    assert "chờ duyệt" not in row


_REVIEW_CLAIMS = ("mỗi task đã qua review", "mỗi task qua review")
ALL_REVIEWED = "15/15 task đã qua review"


def test_no_all_tasks_reviewed_claim_while_a_task_is_unreviewed():
    """Còn task "Chưa review" thì không được nói "mỗi task qua review" (progress mục 13, plan 00)."""
    progress = _doc(PROGRESS)
    sec = progress[progress.index("## 13. Plan 03"):]
    m3_row = next(ln for ln in progress.splitlines() if ln.startswith("| M3 |"))
    plan_row = next(ln for ln in _doc(PLAN00).splitlines() if ln.startswith("| 03 |"))
    for name, text in (("progress mục 13", sec), ("progress hàng M3", m3_row), ("plan 00 hàng 03", plan_row)):
        for claim in _REVIEW_CLAIMS:
            assert claim not in text, f"{name}: '{claim}'"
    places = (("progress mục 13", sec), ("progress hàng M3", m3_row), ("plan 00 hàng 03", plan_row))
    if "Chưa review" in sec:
        # Còn task chờ review: không nơi nào được nói đủ 15/15 task đã qua review
        for name, text in places:
            assert ALL_REVIEWED not in text, name
            assert "đang chờ review" in text, name
    else:
        # Mọi task đã review (review cuối Plan 03): cả ba nơi nói cùng một câu, kèm commit sửa review cuối
        done = ALL_REVIEWED + r"; review cuối toàn nhánh: 4 Important đã sửa ở `[0-9a-f]{7,40}`"
        for name, text in places:
            assert re.search(done, text), name


def test_build_md_web_section_states_pin_and_where_it_ran():
    """V35 và V27 đã chạy trên máy Windows 22/10/2026: BUILD.md nói rõ đã chạy ở đâu và chưa chạy ở đâu."""
    text = _doc("BUILD.md")
    sec = text[text.index("## Dựng SPA Tầng 2"):]
    assert "V35" in sec and "V27" in sec and "make pin-images" in sec
    assert "docs/progress/2026-10-22-web-live.md" in sec
    assert "Chưa chạy trên Linux hay VPS" in sec


def test_web_live_evidence_doc_matches_files():
    doc = _doc("docs/progress/2026-10-22-web-live.md")
    assert "10 passed" in doc and "10/10" in doc and "14 passed" in doc
    shots = ROOT / "docs" / "evidence" / "web-live-2026-10-22"
    for name in re.findall(r"`([a-z0-9-]+\.png)`", doc):
        assert (shots / name).is_file(), name
    junit = (shots / "web-live-junit.xml").read_text(encoding="utf-8")
    assert 'tests="10" failures="0" skipped="0" errors="0"' in junit


def test_verify_parity_gap_is_disclosed():
    for rel in ("sdk/js/README.md", "CHANGELOG.md"):
        text = _doc(rel)
        assert "4300" in text, rel
    assert "4300" in _doc(PROGRESS)
