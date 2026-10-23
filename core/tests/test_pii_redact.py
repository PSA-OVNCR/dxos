# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bản che dạng ảnh của PDF có PII (Plan 04 Task 5, S1; P4-D5). Số trong tệp mẫu đều hư cấu."""

import math
import subprocess
import sys
import textwrap

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


def test_memory_stays_flat_with_many_large_pages():
    """R18a: dựng nhiều trang lớn không được giữ bitmap của mọi trang (bản cũ +400 MB cho 60 trang; bản
    viết tay từng trang: một bitmap cộng phần đã nén). Đo trong tiến trình con để ``ru_maxrss`` sạch."""
    script = textwrap.dedent("""
        import io, resource, sys
        import pypdfium2 as pdfium
        from dxos_core.pii.detect import Box, Finding
        from dxos_core.pii.redact import redact_pdf
        doc = pdfium.PdfDocument.new()
        for _ in range(60):
            doc.new_page(1500, 1500)
        buf = io.BytesIO(); doc.save(buf); doc.close()
        base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out = redact_pdf(buf.getvalue(), [Finding("CCCD", 1, (Box(1, 100, 100, 300, 120),))], max_px=1500)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print((peak - base) // 1024, len(out))
    """)
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120,
                          check=True)
    delta_mb, size = (int(x) for x in done.stdout.split())
    assert delta_mb < 100, f"RAM tăng {delta_mb} MB cho 60 trang 1500x1500"
    assert size > 0


def test_output_is_a_minimal_valid_pdf_with_one_image_per_page():
    src = fixture("pii-fictional.pdf")
    out = redact_pdf(src, _findings(src))
    assert out.startswith(b"%PDF-1.7\n") and out.rstrip().endswith(b"%%EOF")
    assert b"/Info" not in out and b"/ID" not in out and b"/Annots" not in out and b"/Font" not in out
    doc = pdfium.PdfDocument(out)
    try:
        for i in range(len(doc)):
            objs = list(doc[i].get_objects())
            assert len(objs) == 1 and objs[0].type == raw.FPDF_PAGEOBJ_IMAGE
    finally:
        doc.close()
    xref = int(out[out.rindex(b"startxref") + 10:].split()[0])
    assert out[xref:xref + 4] == b"xref"                     # startxref trỏ đúng bảng xref


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_cropbox_with_nonzero_origin_and_rotation(rotation):
    """CropBox không bắt đầu ở gốc, kèm /Rotate: hộp (không gian trang hiển thị) vẫn trùng chữ bị che."""
    doc = pdfium.PdfDocument.new()
    try:
        page = doc.new_page(612, 792)
        page.set_cropbox(100, 150, 500, 450)                       # 400 x 300, lệch gốc
        page.set_rotation(rotation)
        add_text(doc, page, "CCCD: 079203012345 (hu cau)", 130, 300)
        add_text(doc, page, "Dien thoai: 0912 345 678 (hu cau)", 130, 270)
        raw.FPDFPage_GenerateContent(page.raw)
        src = save(doc)
    finally:
        doc.close()
    findings = _findings(src)
    assert sorted(f.type for f in findings) == ["CCCD", "PHONE"]
    out = redact_pdf(src, findings)
    width, height = (400.0, 300.0) if rotation in (0, 180) else (300.0, 400.0)
    out_doc = pdfium.PdfDocument(out)
    try:
        assert out_doc[0].get_size() == (width, height)
    finally:
        out_doc.close()
    w, h, stride, pixels = _render(out, 1)
    assert (w, h) == (math.ceil(width * SCALE), math.ceil(height * SCALE))
    boxes = [b for f in findings for b in f.boxes]
    assert boxes and all(0 <= b.left < b.right <= width and 0 <= b.bottom < b.top <= height for b in boxes)
    for box in boxes:
        x0, y0, x1, y1 = _inner_px(box, height)
        if x1 > x0 and y1 > y0:
            dark, n = _black(pixels, stride, x0, y0, x1, y1)
            assert dark == n
