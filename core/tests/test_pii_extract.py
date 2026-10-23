# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``pii.job.extract``: văn bản và hộp từng ký tự của PDF (Plan 04 Task 4; số trang tính từ 1, R1)."""

import hashlib

import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest
from dxos_core.objects import pdfcheck
from dxos_core.pii import detect_text
from dxos_core.pii.job import extract, extract_pages
from helpers.files import FILES, fixture
from helpers.make_pii_pdf import ACCOUNT, add_text, build_blank_pages_pdf, build_pii_pdf, save


def test_fixture_is_reproducible():
    built = build_pii_pdf()
    assert hashlib.sha256(built).hexdigest() == hashlib.sha256(fixture("pii-fictional.pdf")).hexdigest()
    assert built == (FILES / "pii-fictional.pdf").read_bytes()


def test_extract_pages_lengths_match_and_pages_are_one_based():
    pages = extract_pages(fixture("pii-fictional.pdf"))
    assert pages is not None and len(pages) == 2
    for number, (text, boxes) in enumerate(pages, start=1):
        assert len(text) == len(boxes) > 0
        assert {b.page for b in boxes if b is not None} == {number}


def test_generated_line_breaks_have_no_box():
    text, boxes = extract_pages(fixture("pii-fictional.pdf"))[0]
    breaks = [i for i, ch in enumerate(text) if ch in "\r\n"]
    assert breaks, "PDFium phải chèn xuống dòng giữa các dòng của trang 1"
    assert all(boxes[i] is None for i in breaks)
    assert all(b is not None for ch, b in zip(text, boxes, strict=True) if ch not in "\r\n")


def test_extract_whole_document_joins_pages_with_form_feed():
    pages = extract_pages(fixture("pii-fictional.pdf"))
    text, boxes = extract(fixture("pii-fictional.pdf"))
    assert len(text) == len(boxes)
    assert text == "\f".join(t for t, _ in pages)
    assert boxes[len(pages[0][0])] is None            # ký tự ngăn trang không có hộp


def test_extract_returns_none_beyond_max_pages():
    data = build_blank_pages_pdf(4)
    assert extract_pages(data, max_pages=3) is None and extract(data, max_pages=3) is None
    assert len(extract_pages(data, max_pages=4)) == 4


def test_rotated_page_boxes_are_in_displayed_page_space():
    data = fixture("pii-fictional.pdf")
    doc = pdfium.PdfDocument(data)
    try:
        width, height = doc[1].get_size()
    finally:
        doc.close()
    assert (width, height) == (792.0, 612.0)          # trang 2 hiển thị ngang
    text, boxes = extract_pages(data)[1]
    real = [b for b in boxes if b is not None]
    assert all(0 <= b.left < b.right <= width and 0 <= b.bottom < b.top <= height for b in real)
    # chữ nằm ngang trên trang hiển thị: các hộp trải theo trục x, cao theo trục y bằng cỡ chữ
    assert max(b.right for b in real) - min(b.left for b in real) > 100
    assert max(b.top for b in real) - min(b.bottom for b in real) < 20


def _ink(data: bytes, index: int):
    """Hàm đếm điểm ảnh tối trong một hình chữ nhật (gốc dưới-trái, PDF point) của trang ``index`` (dựng ở
    scale 1) và tổng số điểm tối của trang."""
    doc = pdfium.PdfDocument(data)
    try:
        bitmap = doc[index].render(scale=1.0)
        width, height = bitmap.width, bitmap.height
        pixels, stride, channels = bytes(bitmap.buffer), bitmap.stride, bitmap.n_channels
    finally:
        doc.close()

    def dark(x0: float, y0: float, x1: float, y1: float) -> int:
        return sum(1 for yy in range(max(0, int(height - y1)), min(height, int(height - y0) + 1))
                   for xx in range(max(0, int(x0)), min(width, int(x1) + 1))
                   if pixels[yy * stride + xx * channels] < 128)

    return dark, (width, height)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("origin", [(0, 0), (50, 30)], ids=["origin0", "mediabox-offset"])
def test_boxes_cover_the_rendered_glyphs_for_every_rotation(rotation, origin):
    """Hộp phải nằm đúng chỗ chữ được vẽ ra khi dựng trang (xoay 0/90/180/270, MediaBox lệch gốc)."""
    ox, oy = origin
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(612, 792)
    page.set_rotation(rotation)
    if origin != (0, 0):
        page.set_mediabox(ox, oy, ox + 612, oy + 792)
    add_text(doc, page, f"STK {ACCOUNT}", ox + 300, oy + 400, size=14, angle=rotation)
    raw.FPDFPage_GenerateContent(page.raw)
    data = save(doc)
    doc.close()
    findings = _detect(data)
    assert [f.type for f in findings] == ["BANK_ACCOUNT"]
    dark, (width, height) = _ink(data, 0)
    box = findings[0].boxes[0]
    assert 0 <= box.left < box.right <= width and 0 <= box.bottom < box.top <= height
    inside, total = dark(box.left, box.bottom, box.right, box.top), dark(0, 0, width, height)
    assert inside > 30 and inside >= 0.6 * total, (inside, total)


def _detect(data: bytes):
    out = []
    for text, boxes in extract_pages(data):
        out.extend(detect_text(text, boxes, ["CCCD", "PHONE", "BANK_ACCOUNT"]))
    return out


def test_fixture_yields_one_finding_per_type_on_the_right_page():
    got = sorted((f.type, f.page) for f in _detect(fixture("pii-fictional.pdf")))
    assert got == [("BANK_ACCOUNT", 2), ("CCCD", 1), ("PHONE", 1)]


def test_extract_holds_the_pdfium_lock(monkeypatch):
    """PDFium không an toàn đa luồng: extract phải đi qua khóa của pdfcheck."""
    seen = []
    real = pdfcheck._LOCK

    class Spy:
        def __enter__(self):
            seen.append(True)
            return real.__enter__()

        def __exit__(self, *a):
            return real.__exit__(*a)

    monkeypatch.setattr(pdfcheck, "_LOCK", Spy())
    extract_pages(fixture("pii-fictional.pdf"))
    assert seen


def test_extract_rejects_non_pdf():
    with pytest.raises(pdfium.PdfiumError):
        extract_pages(b"not a pdf")
