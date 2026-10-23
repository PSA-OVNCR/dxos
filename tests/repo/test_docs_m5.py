# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tài liệu M5 (Plan 04 Task 16, bước 1 đến 3): kịch bản demo 15 phút, hồ sơ nộp bài, hướng dẫn dựng trên
máy Ubuntu 24.04 sạch, checklist AT-26 làm mới, việc V45 đến V50 và ruling R30, R31. Phiên bản vẫn 0.9.0
(ruling R30: đóng băng 1.0.0 làm ở M5, thủ tục nằm trong ``docs/nop-bai.md``)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md"
PROGRESS = "docs/progress/2026-10-21-tong-ket-tien-do.md"
KICH_BAN = "docs/demo/kich-ban.md"
NOP_BAI = "docs/nop-bai.md"
FORBIDDEN_VI = ("sẵn sàng để được chứng nhận", "có giá trị pháp lý", "tuân thủ Nghị định 30")
FORBIDDEN_EN = ("ready to be certified", "ready for certification", "legally valid", "legally binding",
                "complies with decree 30", "compliant with decree 30")
SUBJECT = "BÀI THI PMNM 2026 - [Tên Đội] - [Tên Trường]"
RECIPIENTS = ("olpvietnam@vaip.vn", "thuky@vfossa.vn")


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _unified_sentence() -> str:
    """Câu thống nhất của spec 25.1 (khối trích dẫn ngay sau '**Câu thống nhất**'), nguyên văn."""
    spec = _doc(SPEC)
    after = spec.split("### 25.1.", 1)[1].split("**Câu thống nhất**", 1)[1]
    quote = [ln for ln in after.splitlines() if ln.startswith("> ")][0]
    return quote[2:].strip()


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = re.search(r"^## ", text[start + len(heading):], re.M)
    return text[start: start + len(heading) + nxt.start()] if nxt else text[start:]


def _progress_14() -> str:
    text = _doc(PROGRESS)
    return text[text.index("\n## 14. Plan 04"):]


# ---------------------------------------------------------------- kịch bản demo
def test_demo_script_has_the_unified_sentence_verbatim():
    sentence = _unified_sentence()
    assert sentence.startswith("Niêm phong số là chữ ký điện tử chuyên dùng") and len(sentence) > 300
    assert sentence in _doc(KICH_BAN)


@pytest.mark.parametrize("rel", [KICH_BAN, NOP_BAI, "BUILD.md", "docs/at26-checklist.md"])
def test_no_forbidden_legal_phrase(rel):
    low = _doc(rel).lower()
    for phrase in FORBIDDEN_VI + FORBIDDEN_EN:
        assert phrase.lower() not in low, (rel, phrase)


def test_demo_script_watermark_is_deterrent_only():
    assert "chỉ để răn đe" in _doc(KICH_BAN)


def test_demo_script_timeline_is_contiguous_and_ends_at_15_minutes():
    rows = re.findall(r"^\| (\d+):(\d\d)–(\d+):(\d\d) \|", _doc(KICH_BAN), re.M)
    assert len(rows) >= 8
    spans = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in rows]
    assert spans[0][0] == 0 and spans[-1][1] == 15 * 60
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        assert end == start
    assert all(s < e for s, e in spans)


def test_demo_script_lists_six_backup_videos_v1_to_v6():
    text = _doc(KICH_BAN)
    sec = _section(text, "## Video dự phòng")
    for n in range(1, 7):
        assert re.search(rf"^\| V{n} \|", sec, re.M), f"thiếu video V{n}"
    assert "V7" not in sec
    assert "V47" in text                         # việc quay video là V47
    # không nhầm với 10 kịch bản của bảng thử vượt rào
    assert "vượt rào" in sec.lower()


def test_demo_script_covers_s1_to_s4_and_p8_limits():
    text = _doc(KICH_BAN)
    for token in ("CCCD", "bản che", "reveal_pii", "Viewer", "p16", "p8", "https://<DXOS_ADMIN_HOST>/ui/",
                  "tag đã ký", "backup.sh", "at21_drill.sh"):
        assert token in text, token
    low = text.lower()
    assert "không có viewer" in low or "viewer chỉ" in low      # S2 không có trên laptop p8


def test_demo_script_seed_order_and_preflight():
    text = _doc(KICH_BAN)
    assert 'make demo-seed ARGS="--only a"' in text and 'make demo-seed ARGS="--only b"' in text
    install = re.search(r"dxos [^`\n]*app install apps/chung-nhan", text)
    assert install and text.index('--only a"') < install.start() < text.index('--only b"')
    assert "ops/demo_preflight.sh" in text
    assert "docs/runbook-openbao.md" in text


def test_demo_script_pinned_portal_label_and_anchor_order():
    text = _doc(KICH_BAN)
    assert "Hợp lệ — chưa neo công khai" in text
    assert "anchor run" in text
    assert "CDN" in text and "5 phút" in text
    # anchor chạy trước bước quét QR của App B
    assert text.index("anchor run") < text.index("quét QR")


def test_demo_script_uses_only_fictional_names_and_attack_names_exist():
    text = _doc(KICH_BAN)
    assert "Công ty TNHH Sao Mai" in text and "hư cấu" in text
    for target in re.findall(r"`(make [a-z-]+)", text):
        name = target.split()[1]
        assert re.search(rf"^{re.escape(name)}:", _doc("Makefile"), re.M), target
    for path in re.findall(r"`((?:ops|docs|demo)/[A-Za-z0-9_./-]+\.(?:sh|py|md|csv))`", text):
        assert (ROOT / path).is_file(), path


# ---------------------------------------------------------------- hồ sơ nộp bài
def test_submission_email_template_is_verbatim_from_the_de():
    text = _doc(NOP_BAI)
    assert f"Tiêu đề thư: {SUBJECT}" in text
    for addr in RECIPIENTS:
        assert addr in text, addr
    for line in ("Kính gửi BTC cuộc thi PMNM 2026,", "Thành viên đội",
                 "1. Tên thành viên 1, năm sinh, ngành đào tạo",
                 "3. Tên thành viên 3, năm sinh, ngành đào tạo",
                 "Người hướng dẫn: Tên Thầy/Cô - Khoa/Viện/Trường",
                 "Kho mã nguồn dự thi: [đường dẫn truy cập kho mã nguồn chứa đầy đủ nội dung kết quả dự thi]",
                 "Đội thi đã hoàn thành việc đăng kí dự thi theo đúng quy định của BTC thông qua "
                 "[Tên Trường]. "
                 "Chúng tôi cam kết toàn bộ bản quyền sử dụng đối với sản phẩm dự thi tuân thủ theo đúng các "
                 "quy tắc của phần mềm tự do nguồn mở."):
        assert line in text, line
    assert "Địa chỉ nhận bài: olpvietnam@vaip.vn, thuky@vfossa.vn" in text
    assert "Đề thi PMNM OLP 2026, mục 5" in text and "trang 6" in text


def test_submission_deadline_is_17h_06_12_2026_with_the_typo_noted():
    text = _doc(NOP_BAI)
    assert "17:00" in text and "06/12/2026" in text
    assert "G12" in text
    assert "06/12/2025" in text and "đánh máy" in text


def test_submission_filled_example_uses_team_name_and_leaves_personal_data_as_placeholders():
    text = _doc(NOP_BAI)
    assert "BÀI THI PMNM 2026 - PSA_OVNCR - [Tên Trường]" in text
    assert "https://github.com/PSA-OVNCR/dxos" in text
    assert "[Họ tên thành viên 1]" in text and "[năm sinh]" in text and "[ngành đào tạo]" in text
    assert "[Tên Thầy/Cô - Khoa/Viện/Trường]" in text
    # không có năm sinh cụ thể kiểu 2003/2004 cạnh chữ "năm sinh" (không bịa dữ liệu cá nhân)
    assert not re.search(r"năm sinh[^\n]{0,20}(19|20)\d\d", text)


def test_submission_checklist_has_the_tag_before_email_line_and_pof_items():
    text = _doc(NOP_BAI)
    assert re.search(r"^- \[ \] .*tag v1\.0\.0 trước khi gửi email", text, re.M)
    check = _section(text, "## 3. Checklist PoF")
    for token in ("OSI", "SPDX", "reuse lint", "LICENSE", "Release", "zip", "rar", "BUILD.md", "bug tracker",
                  "CHANGELOG", "README", "LICENSES-THIRD-PARTY.md", "SBOM", "Thể lệ", "tr.2"):
        assert token in check, token
    assert check.count("- [ ] ") >= 12


def test_submission_doc_gives_the_exact_1_0_0_procedure_and_does_not_do_it_now():
    text = _doc(NOP_BAI)
    proc = _section(text, "## 5. Thủ tục đóng băng 1.0.0")
    for token in ("libs/dxos-proof/pyproject.toml", "viewer/pyproject.toml", "__version__", "make openapi",
                  "CHANGELOG.md", "## [1.0.0]", "make check", "npm run check", "reuse lint",
                  "make release-check VERSION=1.0.0", "git tag -s v1.0.0", "verify-tag",
                  "git push origin v1.0.0", "chore(release): 1.0.0", "gh run list", "04/12", "R30"):
        assert token in proc, token
    assert "package-lock.json" in proc and "admin-ui/package.json" in proc
    # chưa đóng băng: phiên bản hiện tại vẫn 0.9.0
    assert 'version = "0.9.0"' in _doc("core/pyproject.toml").splitlines()
    assert "## [1.0.0]" not in _doc("CHANGELOG.md")


def test_submission_doc_orders_the_last_days():
    text = _doc(NOP_BAI)
    assert text.index("04/12") < text.index("06/12")
    assert "sáng 06/12" in text
    assert "07/12" in text and "10/12" in text           # lịch chấm kho mã và chung kết (Thể lệ)


# ---------------------------------------------------------------- BUILD.md: máy sạch
CLEAN = "## Máy Ubuntu 24.04 sạch, từng lệnh"


def test_build_has_the_clean_machine_section_with_the_unrun_marker():
    text = _doc("BUILD.md")
    assert CLEAN in text
    sec = _section(text, CLEAN)
    assert "chưa chạy trên máy sạch — kiểm ở AT-23 (V45)" in sec
    for token in ("ops/doctor.sh", "apt", "docker", "git clone", "python3 -m venv", "make dev-install",
                  "cp .env.example .env", "make pin-images", "make up PROFILE=p8", "make up PROFILE=p16",
                  "make web-build", "make netcheck", "operator unseal", "ops/demo_preflight.sh",
                  "usermod -aG docker", "DXOS_ORG_NAME", "https://localhost"):
        assert token in sec, token


def test_build_clean_machine_commands_refer_to_real_targets_and_files():
    sec = _section(_doc("BUILD.md"), CLEAN)
    makefile = _doc("Makefile")
    for name in set(re.findall(r"^\s*make ([a-z][a-z-]*)", sec, re.M)):
        assert re.search(rf"^{re.escape(name)}:", makefile, re.M), f"make {name}"
    for path in set(re.findall(r"\b((?:ops|docs|deploy)/[A-Za-z0-9_./-]+\.(?:sh|py|md|yaml|env))\b", sec)):
        assert (ROOT / path).exists(), path
    assert (ROOT / ".env.example").is_file()


def test_build_clean_machine_does_not_ask_for_node_or_hide_docker_group_logout():
    sec = _section(_doc("BUILD.md"), CLEAN)
    assert "đăng nhập lại" in sec                       # nhóm docker chỉ có hiệu lực sau khi đăng nhập lại
    assert "newgrp docker" in sec or "đăng xuất" in sec
    assert "Node" in sec and "make web-build" in sec     # dựng web trong container: Node là tùy chọn


def test_build_front_matter_points_to_clean_machine_section():
    head = _doc("BUILD.md").split("## Yêu cầu", 1)[0]
    assert "Máy Ubuntu 24.04 sạch" in head


# ---------------------------------------------------------------- AT-26 làm mới
def test_at26_checklist_is_refreshed_for_v46():
    text = _doc("docs/at26-checklist.md")
    assert "V46" in text and "V31" in text
    assert "thay V31" in text
    assert "M5" in text
    assert "ops/doctor.sh" in text
    assert "v1.0.0" in text                              # thử trên đúng bản sẽ nộp
    assert "Ubuntu 24.04" in text


# ---------------------------------------------------------------- mục 14 của bản tổng kết
def test_progress_has_v45_to_v50_rows():
    sec = _progress_14()
    for v in range(45, 51):
        assert re.search(rf"^\| V{v} \|", sec, re.M), f"thiếu V{v}"


def _row(prefix: str) -> str:
    return next(ln for ln in _progress_14().splitlines() if ln.startswith(prefix))


def test_v45_to_v48_content():
    assert "BUILD.md" in _row("| V45 |") and "AT-23" in _row("| V45 |") and "ops/doctor.sh" in _row("| V45 |")
    assert "tutorial-app-30-phut.md" in _row("| V46 |") and "AT-26" in _row("| V46 |")
    assert "V31" in _row("| V46 |")
    v47 = _row("| V47 |")
    assert "6 video" in v47 and "docs/demo/kich-ban.md" in v47
    v48 = _row("| V48 |")
    assert "5 lần" in v48 and "ops/demo_preflight.sh" in v48


def test_v49_is_recorded_as_decided_not_an_open_action():
    row = _row("| V49 |")
    assert "trưởng nhóm quyết 22/10: không cần" in row
    assert "R4" in row


def test_v50_has_the_tag_and_email_procedure():
    row = _row("| V50 |")
    for token in ("v1.0.0", "04/12", "06/12", "docs/nop-bai.md", "make release-check VERSION=1.0.0",
                  "git tag -s v1.0.0", "R30"):
        assert token in row, token


def test_task_16_row_and_milestone_reflect_the_state():
    row = _row("| 16 |")
    assert "Chưa làm" not in row and "R30" in row and "test_docs_m5.py" in row
    m5 = next(ln for ln in _doc(PROGRESS).splitlines() if ln.startswith("| M5 |"))
    assert "Chưa bắt đầu" not in m5 and "chưa đóng băng" in m5.lower()


def test_rulings_r30_r31_are_in_14_6_with_cost_if_wrong():
    sec = _progress_14()
    for n in (30, 31):
        row = next(ln for ln in sec.splitlines() if ln.startswith(f"| R{n} |"))
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 4 and cells[1] == "16" and cells[2] and cells[3], row
    assert "R1 đến R34" in sec
    assert "G12" in next(ln for ln in sec.splitlines() if ln.startswith("| R31 |"))


def test_progress_14_new_text_has_no_forbidden_phrase():
    low = _progress_14().lower()
    for phrase in FORBIDDEN_VI + FORBIDDEN_EN:
        assert phrase.lower() not in low, phrase


# ---------------------------------------------------------------- ops/README
def test_ops_readme_lists_the_two_new_scripts():
    text = _doc("ops/README.md")
    assert "doctor.sh" in text and "demo_preflight.sh" in text
    assert "V45" in text and "V48" in text
