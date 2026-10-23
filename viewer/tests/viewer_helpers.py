# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đồ dùng cho test của viewer (viewer/tests nằm trong pythonpath): dựng PDF trong RAM, giải mã PNG."""

import ctypes
import io
import struct
import zlib

import pypdfium2 as pdfium

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_pdf(pages: int = 1, size: tuple[float, float] = (612, 792), rotate: int = 0,
             cropbox: tuple[float, float, float, float] | None = None, text: str | None = None,
             black: bool = False) -> bytes:
    """PDF trắng (giữ trong RAM, không ghi đĩa). ``text`` thêm một dòng chữ đen để có lớp chữ."""
    doc = pdfium.PdfDocument.new()
    try:
        for _ in range(pages):
            page = doc.new_page(*size)
            if rotate:
                page.set_rotation(rotate)
            if cropbox:
                page.set_cropbox(*cropbox)
            if black:                                    # nền đen kín trang
                rect = pdfium.raw.FPDFPageObj_CreateNewRect(0, 0, size[0], size[1])
                pdfium.raw.FPDFPageObj_SetFillColor(rect, 0, 0, 0, 255)
                pdfium.raw.FPDFPath_SetDrawMode(rect, 1, 0)
                pdfium.raw.FPDFPage_InsertObject(page.raw, rect)
                pdfium.raw.FPDFPage_GenerateContent(page.raw)
            if text:
                font = pdfium.raw.FPDFText_LoadStandardFont(doc.raw, b"Helvetica")
                obj = pdfium.raw.FPDFPageObj_CreateTextObj(doc.raw, font, 24.0)
                buf = (ctypes.c_ushort * (len(text) + 1))(*[ord(c) for c in text])
                pdfium.raw.FPDFText_SetText(obj, buf)
                pdfium.raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 72, 400)
                pdfium.raw.FPDFPage_InsertObject(page.raw, obj)
                pdfium.raw.FPDFPage_GenerateContent(page.raw)
            page.close()
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


def decode_png(png: bytes) -> tuple[int, int, bytes]:
    """(rộng, cao, RGB) của PNG do ``encode_png`` sinh ra (8 bit RGB, bộ lọc None)."""
    assert png[:8] == SIGNATURE
    pos, idat, width, height = 8, [], 0, 0
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        kind, body = png[pos + 4:pos + 8], png[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            idat.append(body)
        pos += 12 + length
    raw = zlib.decompress(b"".join(idat))
    stride = 3 * width
    assert len(raw) == (stride + 1) * height
    rgb = b"".join(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)] for y in range(height))
    return width, height, rgb


def grey_pixels(width: int, height: int, rgb: bytes, box: tuple[float, float, float, float] = (0, 0, 1, 1)
                ) -> int:
    """Số điểm ảnh xám (R=G=B trong 100..230) trong ``box`` (phân số của ảnh: x0, y0, x1, y1)."""
    x0, y0, x1, y1 = int(box[0] * width), int(box[1] * height), int(box[2] * width), int(box[3] * height)
    count = 0
    for y in range(y0, y1):
        row = rgb[(y * width + x0) * 3:(y * width + x1) * 3]
        for i in range(0, len(row), 3):
            if row[i] == row[i + 1] == row[i + 2] and 100 <= row[i] <= 230:
                count += 1
    return count


def annotated_pdf(overlay: bytes = b"1 1 1 rg 0 0 612 792 re f 0 0 0 rg 100 400 200 20 re f") -> bytes:
    """PDF 1 trang 612x792 có một chú thích /Square phủ kín trang, hình (AP /N) là ``overlay`` (mặc định: nền
    trắng đục kèm một thanh đen). Chú thích được vẽ sau nội dung nên nếu không dán phẳng thì che mọi thứ."""
    ap = overlay
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Annots [5 0 R] >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
        b"<< /Type /Annot /Subtype /Square /Rect [0 0 612 792] /F 4 /AP << /N 6 0 R >> >>",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Length %d >>\nstream\n" % len(ap) + ap
        + b"\nendstream",
    ]
    out, offsets = bytearray(b"%PDF-1.7\n"), []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, start)
    return bytes(out)
