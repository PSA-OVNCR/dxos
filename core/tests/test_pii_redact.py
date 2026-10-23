# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bản che dạng ảnh của PDF có PII (Plan 04 Task 5, S1; P4-D5). Số trong tệp mẫu đều hư cấu."""

import math

import pypdfium2 as pdfium
import pypdfium2.raw as raw
import pytest
from dxos_core.pii.detect import DETECTABLE, Box, Finding, detect_text
from dxos_core.pii.job import extract_pages
from dxos_core.pii.redact import redact_pdf
from helpers.files import fixture
from helpers.make_pii_pdf import add_text, build_blank_pages_pdf, save

DPI = 150
SCALE = DPI / 72


def _findings(data: bytes) -> list[Finding]:
    out: list[Finding] = []
    for text, boxes in extract_pages(data):
        out.extend(detect_text(text, boxes, DETECTABLE))
    return out


def _render(data: bytes, page_no: int, scale: float = SCALE):
    doc = pdfium.PdfDocument(data)
    try:
        bitmap = doc[page_no - 1].render(scale=scale)
        return bitmap.width, bitmap.height, bitmap.stride, bytes(bitmap.buffer)       # BGR, 3 byte/điểm
    finally:
        doc.close()


def _black(pixels, stride, x0, y0, x1, y1) -> tuple[int, int]:
    """(số điểm đen (mọi kênh < 16), tổng số điểm) trong khối [x0, x1) x [y0, y1)."""
    n = dark = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            n += 1
            dark += max(pixels[y * stride + 3 * x:y * stride + 3 * x + 3]) < 16
    return dark, n


def _inner_px(box: Box, page_h: float) -> tuple[int, int, int, int]:
    """Khối điểm ảnh nằm trọn trong hộp (co 1 điểm để tránh biên bị làm mượt)."""
    return (int(box.left * SCALE) + 1, int((page_h - box.top) * SCALE) + 1,
            int(box.right * SCALE) - 1, int((page_h - box.bottom) * SCALE) - 1)


def test_redacted_pdf_has_no_text_layer():
    src = fixture("pii-fictional.pdf")
    out = redact_pdf(src, _findings(src))
    orig, doc = pdfium.PdfDocument(src), pdfium.PdfDocument(out)
    try:
        assert len(doc) == len(orig) == 2
        assert all(orig[i].get_textpage().get_text_range().strip() for i in range(2))     # bản gốc có chữ
        for i in range(len(doc)):
            assert doc[i].get_textpage().get_text_range().strip() == ""
    finally:
        doc.close()
        orig.close()


def test_redacted_pixels_black_under_box():
    src = fixture("pii-fictional.pdf")
    findings = _findings(src)
    out = redact_pdf(src, findings)
    _, _, stride, pixels = _render(out, 1)
    boxes = [b for f in findings if f.type in ("CCCD", "PHONE") for b in f.boxes]
    assert len(boxes) == 2
    for box in boxes:
        dark, n = _black(pixels, stride, *_inner_px(box, 792.0))
        assert n > 100 and dark == n


def test_rotated_page_pixels_black_under_box():
    """Trang 2 xoay 90° (hiển thị 792x612): hộp theo không gian trang đang hiển thị."""
    src = fixture("pii-fictional.pdf")
    findings = _findings(src)
    out = redact_pdf(src, findings)
    w, h, stride, pixels = _render(out, 2)
    assert (w, h) == (math.ceil(792 * SCALE), math.ceil(612 * SCALE))
    (finding,) = [f for f in findings if f.page == 2]
    for box in finding.boxes:
        dark, n = _black(pixels, stride, *_inner_px(box, 612.0))
        assert n > 100 and dark == n


def test_text_outside_the_boxes_stays_readable():
    src = fixture("pii-fictional.pdf")
    out = redact_pdf(src, _findings(src))
    _, _, stride, pixels = _render(out, 1)
    (text, boxes), = extract_pages(src)[:1]
    start = text.index("Ho so mau")
    title = Box(1, min(b.left for b in boxes[start:start + 9]), min(b.bottom for b in boxes[start:start + 9]),
                max(b.right for b in boxes[start:start + 9]), max(b.top for b in boxes[start:start + 9]))
    dark, n = _black(pixels, stride, *_inner_px(title, 792.0))
    assert 0 < dark < n // 2                       # có nét chữ, nhưng không bị phủ đen cả khối


def test_box_is_padded_by_pad_pt():
    src = fixture("pii-fictional.pdf")
    findings = _findings(src)
    (cccd,) = [f for f in findings if f.type == "CCCD"]
    box = cccd.boxes[0]
    y0, y1 = int((792 - box.top) * SCALE) + 2, int((792 - box.bottom) * SCALE) - 2
    x = int((box.left - 1.0) * SCALE)               # 1 pt bên trái hộp, nằm trong vùng nở 2 pt
    for pad, expected in ((2.0, True), (0.0, False)):
        out = redact_pdf(src, findings, pad_pt=pad)
        _, _, stride, pixels = _render(out, 1)
        dark, n = _black(pixels, stride, x, y0, x + 1, y1)
        assert (dark == n) is expected


def test_page_size_and_pixels_follow_dpi():
    src = fixture("pii-fictional.pdf")
    out = redact_pdf(src, _findings(src), dpi=72)
    doc = pdfium.PdfDocument(out)
    try:
        assert doc[0].get_size() == (612.0, 792.0) and doc[1].get_size() == (792.0, 612.0)
        (img,) = list(doc[0].get_objects())
        assert img.get_px_size() == (612, 792)
    finally:
        doc.close()


def _page_5000_pdf() -> bytes:
    doc = pdfium.PdfDocument.new()
    try:
        page = doc.new_page(5000, 5000)
        add_text(doc, page, "CCCD: 079203012345 (hu cau)", 100, 4000, size=60)
        raw.FPDFPage_GenerateContent(page.raw)
        return save(doc)
    finally:
        doc.close()


def test_huge_page_lowers_dpi():
    src = _page_5000_pdf()
    findings = _findings(src)
    assert [f.type for f in findings] == ["CCCD"]
    out = redact_pdf(src, findings)
    doc = pdfium.PdfDocument(out)
    try:
        assert doc[0].get_size() == (5000.0, 5000.0)     # khổ trang không đổi, chỉ ảnh bị hạ độ phân giải
        (img,) = list(doc[0].get_objects())
        w, h = img.get_px_size()
        assert 3000 < max(w, h) <= 4000 and w <= 4000 and h <= 4000
    finally:
        doc.close()


def test_huge_page_still_blacks_out_the_box():
    src = _page_5000_pdf()
    findings = _findings(src)
    out = redact_pdf(src, findings)
    scale = 4000 / 5000
    w, h, stride, pixels = _render(out, 1, scale=scale)
    box = findings[0].boxes[0]
    dark, n = _black(pixels, stride, int(box.left * scale) + 1, int((5000 - box.top) * scale) + 1,
                     int(box.right * scale) - 1, int((5000 - box.bottom) * scale) - 1)
    assert n > 50 and dark == n


def test_more_than_200_pages_is_refused():
    with pytest.raises(ValueError, match="200"):
        redact_pdf(build_blank_pages_pdf(201), [])


def test_finding_outside_the_document_is_refused():
    src = fixture("pii-fictional.pdf")
    bad = Finding("CCCD", 3, (Box(3, 0, 0, 10, 10),))
    with pytest.raises(ValueError, match="trang"):
        redact_pdf(src, [bad])
