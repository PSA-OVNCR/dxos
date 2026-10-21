# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Tài liệu M2 (Plan 02 Task 15; spec 25.1, 25.2, 25.5): các câu chữ phải chép nguyên văn từ spec, mã lý do
xóa khớp CHECK của migration, danh mục guard và id dành riêng khớp mã lõi. Đổi spec hoặc mã mà quên tài liệu
thì đỏ."""

import re
from pathlib import Path

import pytest
from dxos_core.registry.bpmn import RESERVED_IDS
from dxos_core.registry.validator import GUARD_CATALOG

ROOT = Path(__file__).resolve().parents[2]
SPEC = (ROOT / "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md").read_text(encoding="utf-8")
FIRST_SENTENCE = "Diễn giải kỹ thuật của đội, không phải tư vấn pháp lý."
# spec 25.1, "Không nói"
FORBIDDEN = ["sẵn sàng để được chứng nhận", "có giá trị pháp lý", "tuân thủ Nghị định 30"]


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _spec_section(start: str, end: str) -> str:
    i = SPEC.index(start)
    return SPEC[i:SPEC.index(end, i)]


def _section(text: str, heading: str) -> str:
    """Nội dung từ dòng tiêu đề ``heading`` tới tiêu đề cùng cấp kế tiếp."""
    level = heading.split(" ", 1)[0]
    i = text.index("\n" + heading + "\n")
    nxt = re.compile(rf"^{level} ", re.M).search(text, i + len(heading) + 2)
    return text[i: nxt.start() if nxt else len(text)]


UNIFIED = next(line for line in _spec_section("### 25.1.", "**Căn cứ đã đối chiếu:**").splitlines()
               if line.startswith("> Niêm phong số là"))


# ---------------------------------------------------------------- docs/legal-mapping.md
def test_legal_mapping_first_sentence():
    first = next(line for line in _doc("docs/legal-mapping.md").splitlines() if line.strip())
    assert first.strip().strip("*") == FIRST_SENTENCE


@pytest.mark.parametrize("rel", ["docs/legal-mapping.md", "README.md"])
def test_unified_sentence_is_verbatim(rel):
    assert UNIFIED in _doc(rel).splitlines()


def test_legal_mapping_copies_the_basis_table_with_sources_and_date():
    doc = _doc("docs/legal-mapping.md")
    table = _spec_section("**Căn cứ đã đối chiếu:**", "**Ánh xạ 4 yêu cầu")
    rows = [r for r in table.splitlines() if r.startswith("| ") and not r.startswith("| Văn bản")]
    assert len(rows) == 10
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[2] in doc, cells[2]                      # cột "Nội dung dùng trong thiết kế", nguyên văn
    urls = re.findall(r"\((https://[^)]+)\)", SPEC[SPEC.index("### 25.6."):])   # 25.6 là mục cuối của spec
    assert len(urls) == 6
    for url in urls:
        assert url in doc, url
    assert "21/10/2026" in doc


def test_legal_mapping_copies_the_four_requirements_of_article_22_2():
    doc = _doc("docs/legal-mapping.md")
    items = re.findall(r"^- \(([a-d])\) (.+)$", _spec_section("**Ánh xạ 4 yêu cầu", "**Không nói:**"), re.M)
    assert [k for k, _ in items] == ["a", "b", "c", "d"]
    for _, text in items:
        assert text in doc, text


def test_legal_mapping_lists_what_is_not_achieved():
    sec = _section(_doc("docs/legal-mapping.md"), "## Không đạt")
    for phrase in ("chữ ký tay", "chữ ký số", "chứng nhận", "Nghị định 30/2020", "Điều 5", "vận dụng"):
        assert phrase in sec, phrase


def test_legal_mapping_personal_data_limits_copy_i5_out_of_scope():
    sec = _section(_doc("docs/legal-mapping.md"), "## Giới hạn về dữ liệu cá nhân")
    spec = _spec_section("**Phạm vi của I5:**", "- `comment` của `:complete`")
    bullets = re.findall(r"^  - (.+)$", spec, re.M)
    assert len(bullets) == 3
    for b in bullets:
        assert b in sec, b
    assert "1.0.3" in sec and "DISABLED" in sec


def test_legal_mapping_ends_with_reader_table_for_the_team():
    doc = _doc("docs/legal-mapping.md")
    sec = _section(doc, "## Thành viên đã đọc toàn văn")
    assert doc.rstrip().endswith(sec.rstrip())                 # là mục cuối tệp
    assert "| Văn bản, điều | Thành viên đã đọc | Ngày đọc |" in sec
    for art in ("Điều 22", "Điều 23", "Điều 25", "Nghị định 23/2025", "Nghị định 30/2020", "91/2025"):
        assert art in sec, art


@pytest.mark.parametrize("rel", ["docs/legal-mapping.md", "README.md", "docs/manifest-guide.md",
                                 "docs/runbook-pii-erasure.md"])
def test_no_overclaiming(rel):
    text = _doc(rel)
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase


# ---------------------------------------------------------------- README
def test_readme_legal_nature_section_links_the_mapping():
    sec = _section(_doc("README.md"), "## Bản chất pháp lý của niêm phong")
    assert UNIFIED in sec.splitlines() and "(docs/legal-mapping.md)" in sec


def test_readme_en_legal_nature_section_translates_and_links():
    sec = _section(_doc("README_EN.md"), "## Legal nature of the seal")
    for phrase in ("Article 22(1)(a)", "Law on Electronic Transactions 2023",
                   "not** equivalent to a handwritten",
                   "not** a digital signature", "Article 25(3)", "(docs/legal-mapping.md)"):
        assert phrase in sec, phrase


def test_readme_status_does_not_claim_the_release():
    sec = _section(_doc("README.md"), "## Trạng thái v0.2.0")
    assert "chưa gắn tag" in sec


# ---------------------------------------------------------------- docs/runbook-pii-erasure.md
def test_runbook_reason_codes_match_the_migration_check():
    sql = (ROOT / "core/migrations/003_workflow_seal.sql").read_text(encoding="utf-8")
    block = sql[sql.index("CREATE TABLE pii_erasures"):]
    codes = re.findall(r"'([a-z_]+)'", block[block.index("reason_code IN"):block.index(")),")])
    assert codes == ["data_subject_request", "purpose_completed", "retention_expired", "authority_decision",
                     "agreement"]
    doc = _doc("docs/runbook-pii-erasure.md")
    for c in codes:
        assert f"`{c}`" in doc, c
    assert "Điều 14 khoản 1" in doc


def test_runbook_covers_vacuum_backup_and_refusal_notice():
    doc = _doc("docs/runbook-pii-erasure.md")
    assert "VACUUM (ANALYZE) core.records, core.record_salts, core.uploads" in doc and "dxos_owner" in doc
    assert "backup" in doc.lower()
    assert "Điều 14 khoản 2" in doc and "Điều 19" in doc
    assert ":erase-pii" in doc and "If-Match" in doc


# ---------------------------------------------------------------- docs/manifest-guide.md
def test_manifest_guide_sections_and_core_facts():
    doc = _doc("docs/manifest-guide.md")
    for heading in ("## Trường công khai là công bố vĩnh viễn", "## Đánh số theo năm", "## Danh mục guard",
                    "## Luật BPMN", "## Vòng đời cài ứng dụng", "## Nâng phiên bản"):
        assert "\n" + heading + "\n" in doc, heading
    for g in GUARD_CATALOG:
        assert f"`{g}" in _section(doc, "## Danh mục guard"), g
    for rid in RESERVED_IDS:
        assert f"`{rid}`" in _section(doc, "## Luật BPMN"), rid
    for fact in ("id@version#hash16", "install-in-progress", "version-not-newer", "DXOS_TIMEZONE", "{n:0W}",
                 "test-flow", "assignee_is_caller", "incoming"):
        assert fact in doc, fact


# ---------------------------------------------------------------- BUILD, CHANGELOG, bằng chứng
def test_build_md_documents_m2_configuration():
    doc = _doc("BUILD.md")
    for var in ("DXOS_ORG_NAME", "DXOS_ORG_ID", "DXOS_SEAL_KEY_VALIDITY_DAYS", "DXOS_SEAL_PURPOSE",
                "DXOS_KEY_POLICY_URL", "DXOS_TIMEZONE", "DXOS_ALLOW_SELF_APPROVAL",
                "DXOS_INSTALLER_CLIENT_SECRET", "DXOS_TRUST_CORE_DIGEST", "org: down",
                "ops/keycloak_upgrade.py", "deploy/compose.release.yaml",
                "make openapi", "ops/e2e/install_apps.sh"):
        assert var in doc, var


def test_changelog_has_unreleased_020_section():
    doc = _doc("CHANGELOG.md")
    assert "\n## [0.2.0] - Chưa phát hành\n" in doc
    assert doc.index("## [0.2.0]") < doc.index("## [0.1.0]")


def test_evidence_readme_lists_m2_items_without_results():
    doc = _doc("docs/evidence/README.md")
    for item in ("at13-reuse.txt", "AT-19", "AT-20", "AT-18"):
        assert item in doc, item
