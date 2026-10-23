# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dựng trang PDF thành PNG có watermark (Plan 04 Task 7; S2; P4-D7). Watermark chỉ để răn đe."""

from datetime import UTC, datetime, timedelta, timezone

import pypdfium2 as pdfium
import pytest
from dxos_viewer import render
from viewer_helpers import decode_png, grey_pixels, make_pdf

ICT = timezone(timedelta(hours=7))
NOW = datetime(2026, 12, 10, 9, 5, tzinfo=ICT)
SUB = "0f1e2d3c-1111-4222-8333-444455556666"


def test_watermark_text_format():
    assert render.watermark_text(SUB, NOW) == "DX-OS 0f1e2d3c 2026-12-10 09:05 ICT"


def test_watermark_text_converts_other_zones_to_ict():
    assert render.watermark_text(SUB, datetime(2026, 12, 10, 2, 5, tzinfo=UTC)) == \
        "DX-OS 0f1e2d3c 2026-12-10 09:05 ICT"


@pytest.mark.parametrize("sub", ["ab", "Nguyễn-Văn-Á-1234", "../../etc/passwd", "a b\n\x00c-1-2-3"])
def test_watermark_text_is_ascii_whatever_the_subject(sub):
    text = render.watermark_text(sub, NOW)
    assert text.isascii() and text.isprintable()
    assert text.startswith("DX-OS ") and text.endswith(" 2026-12-10 09:05 ICT")
    assert len(text.split(" ")[1]) <= 8


def test_png_has_watermark_pixels():
    png = render.render_page(make_pdf(), 1, SUB, NOW)
    width, height, rgb = decode_png(png)
    assert (width, height) == (935, 1210)                             # Letter ở 110 dpi
    assert grey_pixels(width, height, rgb, (0.25, 0.25, 0.75, 0.75)) > 300     # vùng giữa ảnh có điểm xám
    # nền trắng thật: phần lớn ảnh là 255, và watermark chỉ có sắc xám (không màu)
    assert rgb.count(b"\xff\xff\xff") > 0.5 * width * height
    assert all(rgb[i] == rgb[i + 1] == rgb[i + 2] for i in range(0, len(rgb), 3 * 97))


def test_watermark_is_a_text_object_with_the_exact_string():
    doc = pdfium.PdfDocument(make_pdf())
    page = doc[0]
    try:
        render.apply_watermark(doc, page, render.watermark_text(SUB, NOW), 612, 792, 110 / 72)
        text = page.get_textpage().get_text_range()
    finally:
        page.close()
        doc.close()
    assert text.count("DX-OS 0f1e2d3c 2026-12-10 09:05 ICT") == 12      # lưới 3 x 4


def test_watermark_is_drawn_over_page_content():
    plain = decode_png(render.render_page(make_pdf(text="Hop dong so 01"), 1, SUB, NOW))
    assert plain[0] == 935 and grey_pixels(*plain) > 1000
    assert plain[2].count(b"\x00\x00\x00") > 100                            # chữ đen của trang vẫn còn


def test_rotated_page_gets_an_upright_watermark():
    """Trang MediaBox 792x612 có /Rotate 90 hiển thị như trang 612x792: ảnh phải giống trang thường."""
    base = decode_png(render.render_page(make_pdf(size=(612, 792)), 1, SUB, NOW))
    for rotate, size in [(90, (792, 612)), (180, (612, 792)), (270, (792, 612))]:
        got = decode_png(render.render_page(make_pdf(size=size, rotate=rotate), 1, SUB, NOW))
        assert got[:2] == base[:2], rotate
        different = sum(a != b for a, b in zip(got[2][::3], base[2][::3], strict=True))
        assert different < 0.01 * got[0] * got[1], rotate


def test_cropbox_is_respected_like_a_page_of_that_size():
    data = make_pdf(size=(612, 792), cropbox=(100, 100, 400, 500))
    cropped = decode_png(render.render_page(data, 1, SUB, NOW))
    plain = decode_png(render.render_page(make_pdf(size=(300, 400)), 1, SUB, NOW))
    assert cropped[:2] == plain[:2] == (459, 612)
    different = sum(a != b for a, b in zip(cropped[2][::3], plain[2][::3], strict=True))
    assert different < 0.01 * plain[0] * plain[1]


def test_huge_page_capped():
    width, height, rgb = decode_png(render.render_page(make_pdf(size=(14400, 7200)), 1, SUB, NOW))
    assert width <= 4000 and height <= 4000
    assert width >= 3990                                                    # hạ dpi vừa đủ, không nhỏ hơn cần
    assert len(rgb) == 3 * width * height
    assert grey_pixels(width, height, rgb) > 0                              # watermark vẫn thấy được


def test_dpi_and_cap_are_parameters():
    width, height, _ = decode_png(render.render_page(make_pdf(), 1, SUB, NOW, dpi=72, max_px=300))
    assert (width, height) == (232, 300)


def test_page_numbers_are_one_based_and_bounded():
    data = make_pdf(pages=3)
    assert render.page_count(data) == 3
    render.render_page(data, 3, SUB, NOW)
    for bad in (0, -1, 4):
        with pytest.raises(render.PageOutOfRange):
            render.render_page(data, bad, SUB, NOW)


def test_more_than_200_pages_refused():
    data = make_pdf(pages=201, size=(50, 50))
    with pytest.raises(render.TooManyPages):
        render.page_count(data)
    with pytest.raises(render.TooManyPages):
        render.render_page(data, 1, SUB, NOW)
    assert render.page_count(make_pdf(pages=200, size=(50, 50))) == 200


@pytest.mark.parametrize("data", [b"", b"not a pdf", b"%PDF-1.7\ngarbage", make_pdf()[:300]])
def test_unreadable_document_is_a_clean_error(data):
    with pytest.raises(render.BadDocument) as err:
        render.render_page(data, 1, SUB, NOW)
    assert "garbage" not in str(err.value)


def test_many_renders_do_not_grow_memory():
    import resource
    data = make_pdf(text="x")
    for _ in range(5):
        render.render_page(data, 1, SUB, NOW)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for _ in range(60):
        render.render_page(data, 1, SUB, NOW)
    grown_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) / 1024
    assert grown_mb < 40, grown_mb
