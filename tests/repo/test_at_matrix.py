# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``docs/acceptance.md`` (Plan 03 Task 11): ma trận AT-01..AT-28 phải đủ, không dẫn test không tồn tại.

Quy tắc:
- đủ 28 dòng AT-01..AT-28, mỗi AT đúng một dòng, khớp danh sách trong spec mục 19;
- mọi ``đường_dẫn::tên_test`` có tệp, và trong tệp có ``def <tên>(`` (Python) hoặc ``test('<tên>'`` /
  ``it('<tên>'`` (JS, TS);
- chỉ AT-18, AT-21, AT-22, AT-23, AT-26 được ghi ``Thủ công`` (ruling của controller); mỗi dòng đó dẫn một tài
  liệu bằng chứng có thật hoặc ghi "chưa có — V<số>" (S<số> cho việc của Plan 04);
- tài liệu bằng chứng nào được dẫn (ngoài các dòng "chưa có") cũng phải có thật;
- mọi dòng còn lại phải dẫn ít nhất một test.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/acceptance.md"
SPEC = ROOT / "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md"
MANUAL_ALLOWED = {"AT-18", "AT-21", "AT-22", "AT-23", "AT-26"}
HEADER = ["AT", "Nội dung", "Tự động bằng", "Chạy ở đâu", "Bằng chứng gần nhất"]
REF = re.compile(r"`([^`]+?)::([^`]+?)`")
PATH_TOKEN = re.compile(r"`([A-Za-z0-9_.\-/]+\.(?:md|txt|png|xml|json|py|sh|ts|yaml|yml))`")
PENDING = re.compile(r"chưa có — [VS]\d+")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _rows() -> dict[str, list[str]]:
    lines = MATRIX.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if _cells(ln) == HEADER)
    rows: dict[str, list[str]] = {}
    for ln in lines[start + 2:]:                           # bỏ dòng ngăn |---|
        if not ln.startswith("|"):
            break
        cells = _cells(ln)
        assert len(cells) == len(HEADER), f"dòng sai số cột: {ln[:80]}"
        assert cells[0] not in rows, f"{cells[0]} xuất hiện hai lần"
        rows[cells[0]] = cells
    return rows


ROWS = _rows()


def _has_test(path: Path, name: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return re.search(rf"^\s*(?:async\s+)?def {re.escape(name)}\(", text, re.M) is not None
    return any(f"{kw}({q}{name}{q}" in text for kw in ("test", "it") for q in ("'", '"', "`"))


def test_has_exactly_the_28_acceptance_tests():
    assert list(ROWS) == [f"AT-{i:02d}" for i in range(1, 29)]


def test_rows_match_the_spec_numbering():
    """Mỗi AT trong spec mục 19 có đúng một dòng (spec thêm AT thì ma trận phải thêm theo)."""
    spec = SPEC.read_text(encoding="utf-8")
    section = spec[spec.index("## 19. Tiêu chí nghiệm thu"):spec.index("## 20.")]
    in_spec = re.findall(r"^\| (AT-\d{2}) \|", section, re.M)
    assert in_spec == list(ROWS)


@pytest.mark.parametrize("at", ROWS)
def test_every_row_is_automated_or_an_allowed_manual_one(at):
    how = ROWS[at][2]
    if how == "Thủ công":
        assert at in MANUAL_ALLOWED, f"{at} không được để Thủ công (chỉ {sorted(MANUAL_ALLOWED)})"
        return
    assert REF.search(how), f"{at}: cột 'Tự động bằng' phải là `đường_dẫn::tên_test` hoặc Thủ công"
    assert "Thủ công" not in how, f"{at}: trộn Thủ công với test; tách ra cột bằng chứng"


def test_only_the_allowed_ats_are_manual():
    manual = {at for at, cells in ROWS.items() if cells[2] == "Thủ công"}
    assert manual == MANUAL_ALLOWED


@pytest.mark.parametrize("at", ROWS)
def test_every_referenced_test_exists(at):
    for path_text, name in REF.findall(ROWS[at][2]):
        path = ROOT / path_text
        assert path.is_file(), f"{at}: không có tệp {path_text}"
        assert _has_test(path, name), f"{at}: {path_text} không có test '{name}'"


@pytest.mark.parametrize("at", sorted(MANUAL_ALLOWED))
def test_manual_rows_point_to_evidence_or_say_not_yet(at):
    evidence = ROWS[at][4]
    if PENDING.search(evidence):
        return
    paths = PATH_TOKEN.findall(evidence)
    assert paths, f"{at}: dòng Thủ công phải dẫn tài liệu bằng chứng hoặc ghi 'chưa có — V<số>'"


@pytest.mark.parametrize("at", ROWS)
def test_cited_evidence_documents_exist(at):
    evidence = ROWS[at][4]
    if PENDING.search(evidence):                 # ví dụ ảnh chưa chụp: đã nói rõ là chưa có
        return
    for rel in PATH_TOKEN.findall(evidence):
        assert (ROOT / rel).is_file(), f"{at}: tài liệu bằng chứng không tồn tại: {rel}"


def test_checker_rejects_a_missing_test_name(tmp_path):
    """Chính bộ kiểm phải bắt được dẫn sai (tránh bộ kiểm luôn xanh)."""
    py = tmp_path / "test_x.py"
    py.write_text("async def test_real(x):\n    pass\n", encoding="utf-8")
    ts = tmp_path / "a.spec.ts"
    ts.write_text("test('AT-25: ok {\"a\"}', async () => {})\nit(\"khac\", () => {})\n", encoding="utf-8")
    assert _has_test(py, "test_real") and not _has_test(py, "test_fake") and not _has_test(py, "test_re")
    assert _has_test(ts, 'AT-25: ok {"a"}')                 # tên có dấu nháy kép trong chuỗi nháy đơn
    assert _has_test(ts, "khac") and not _has_test(ts, "missing")
