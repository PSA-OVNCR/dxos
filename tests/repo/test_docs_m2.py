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
    rows = {key: next(line for line in doc.splitlines() if line.startswith("| " + key))
            for key in ("E2E mốc M2", "AT-13", "AT-19", "AT-20", "Cổng năng suất M2")}
    e2e = rows.pop("E2E mốc M2").rstrip(" |").split("|")[-1].strip()
    # E2E đã chạy trên Docker Desktop 22/10 (review cuối Plan 03, m2): ghi kết quả kèm nguồn, nói rõ chưa chạy
    # trên VPS
    assert e2e.startswith("Có") and "chưa chạy trên VPS" in e2e
    assert "2026-10-22-e2e-m2-docker-desktop.md" in e2e
    for key, row in rows.items():
        # chưa chạy: cột trạng thái không được ghi kết quả
        assert row.rstrip(" |").split("|")[-1].strip().startswith("Chưa có"), key


def test_vps_dev_user_warning_points_to_removal_commands():
    for rel in ("BUILD.md", "ops/at13_reuse.sh"):
        text = _doc(rel)
        assert "mật khẩu" in text and "docs/evidence/README.md" in text, rel
    ev = _section(_doc("docs/evidence/README.md"),
                  "## Người dùng dev tạm trên VPS (quyết định của trưởng nhóm)")
    assert "mật khẩu" in ev and "kcadm.sh" in ev and "read -rs KC_CLI_PASSWORD" in ev
    assert "delete users" in ev and "delete clients" in ev


def test_docs_never_put_openbao_secrets_on_the_command_line():
    for rel in ("docs/runbook-openbao.md", "BUILD.md", "docs/evidence/README.md", "deploy/openbao/init.sh"):
        text = _doc(rel)
        assert "BAO_TOKEN=<" not in text and "unseal <" not in text, rel


# ---------------------------------------------------------------- mã lỗi và lý do từ chối (fix vòng 1)
CORE = ROOT / "core/src/dxos_core"
SLUG_PATTERNS = [r'\b(?:ProblemError|problem)\([^"()]*?"([a-z][a-z0-9-]*)"',
                 r'\b_conflict\(\s*"([a-z][a-z0-9-]*)"',
                 r'\brefuse\(\s*"[a-z_]+",\s*"([a-z][a-z0-9-]*)"']


def _core_sources() -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted(CORE.rglob("*.py"))]


def _first_column(section: str, sub: str) -> set[str]:
    """Các mã trong cột đầu (``| `x` |``) của bảng ngay dưới tiêu đề ``sub``."""
    part = _section(section, sub)
    return set(re.findall(r"^\| `([^`]+)` \|", part, re.M))


def _deny_reasons() -> set[str]:
    out: set[str] = set()
    for t in _core_sources():
        for call in re.findall(r"\bdeny\((.*?)\)\n", t, re.S):
            out |= set(re.findall(r'reason="([a-z_]+)"', call))
            if 'reason=f"guard:{failure.guard}:{failure.reason}"' in call:
                out.add("guard:<guard>:<lý do>")
        out |= set(re.findall(r'\brefuse\(\s*"([a-z_]+)"', t))
        for a, b in re.findall(r'reason="([a-z_]+)" if [\w.]+\.is_admin else "([a-z_]+)"', t):
            out |= {a, b}
    return out


def _deny_actions() -> set[str]:
    return {a for t in _core_sources() for a in re.findall(r'\bdeny\([^()]*?action="([a-z_]+)"', t, re.S)}


def _slugs() -> set[str]:
    return {s for t in _core_sources() for p in SLUG_PATTERNS for s in re.findall(p, t)}


def test_deny_reasons_documented_exactly():
    sec = _section(_doc("docs/manifest-guide.md"), "## Mã lỗi và lý do từ chối")
    reasons = _deny_reasons()
    assert {"self_approval", "not_task_role", "kms_unavailable", "guard:<guard>:<lý do>"} <= reasons
    assert _first_column(sec, "### Lý do từ chối (`reason` trong `policy.denied`)") == reasons | {
        "unknown_collection", "not_in_access_list"}


def test_enforce_reasons_and_guard_reasons_documented():
    sec = _section(_doc("docs/manifest-guide.md"), "## Mã lỗi và lý do từ chối")
    pdp = (CORE / "policy/pdp.py").read_text(encoding="utf-8")
    for r in re.findall(r'Decision\(False, "([a-z_]+)"', pdp) + ["admin_no_data_access", "no_app_role"]:
        assert f"| `{r}` |" in sec, r
    guards_src = (CORE / "workflow/guards.py").read_text(encoding="utf-8")
    for r in re.findall(r'_fail\(guard, "([a-z_]+)"', guards_src):
        assert f"`{r}`" in sec, r


def test_deny_actions_documented():
    sec = _section(_doc("docs/manifest-guide.md"), "## Mã lỗi và lý do từ chối")
    actions = _deny_actions()
    assert actions == {"approve", "complete", "erase_pii", "list_tasks", "pii_review", "read_manifest",
                       "revoke"}
    for a in actions | {"list", "read", "create", "update"}:
        assert f"`{a}`" in sec, a


def test_problem_slugs_documented_exactly():
    from dxos_core.errors import HTTP_SLUGS

    sec = _section(_doc("docs/manifest-guide.md"), "## Mã lỗi và lý do từ chối")
    slugs = _slugs()
    assert {"guard-failed", "install-in-progress", "workflow-model-mismatch", "keys-unavailable"} <= slugs
    assert _first_column(sec, "### Problem type (`type` của lỗi)") == slugs
    for s in [*HTTP_SLUGS.values(), "http-error"]:
        assert f"`{s}`" in sec, s
