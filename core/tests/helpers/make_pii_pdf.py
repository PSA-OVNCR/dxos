# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dựng PDF mẫu cho test dò PII bằng pypdfium2 (không thêm phụ thuộc).

    python core/tests/helpers/make_pii_pdf.py        # ghi lại core/tests/fixtures/files/pii-fictional.pdf

Mọi số trong tệp mẫu đều **hư cấu** (tự bịa, không thuộc ai). Tệp sinh ra được commit; test
``test_fixture_is_reproducible`` dựng lại và so sha256 để biết tệp còn khớp mã dựng.

PDFium ghi ``/ID`` ngẫu nhiên và ``/CreationDate`` theo giờ hiện tại; hai giá trị này được thay bằng hằng
số cùng độ dài (nên bảng xref vẫn đúng) để kết quả tất định. Byte của tệp phụ thuộc bản PDFium đi kèm
pypdfium2: nâng pypdfium2 có thể làm test tái lập đỏ; khi đó chạy lại lệnh trên và commit tệp mới.
"""

import ctypes
import io
import math
import os
import re
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as raw

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "files" / "pii-fictional.pdf"

# Số hư cấu. CCCD: 079 là mã tỉnh trong khoảng 001-096 mà bộ dò chấp nhận.
CCCD = "079203012345"
PHONE = "0912 345 678"
ACCOUNT = "1234567890123"

_FIXED_ID = b"0123456789ABCDEF0123456789ABCDEF"
_FIXED_DATE = b"D:20260101000000+00'00'"


def add_text(doc: pdfium.PdfDocument, page: pdfium.PdfPage, text: str, x: float, y: float, *,
              size: float = 12, angle: float = 0) -> None:
    """Chèn một dòng chữ phông chuẩn Helvetica, gốc dòng ở (x, y) trong không gian trang chưa xoay."""
    obj = raw.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", size)
    buf = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
    raw.FPDFText_SetText(obj, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ushort)))
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    raw.FPDFPageObj_Transform(obj, c, s, -s, c, x, y)
    raw.FPDFPage_InsertObject(page.raw, obj)


def save(doc: pdfium.PdfDocument) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    out = buf.getvalue()
    out, n_id = re.subn(rb"/ID\[<[0-9A-F]{32}><[0-9A-F]{32}>\]",
                        b"/ID[<" + _FIXED_ID + b"><" + _FIXED_ID + b">]", out)
    out, n_date = re.subn(rb"/CreationDate\(D:\d{14}\+00'00'\)", b"/CreationDate(" + _FIXED_DATE + b")", out)
    if n_id != 1 or n_date != 1:
        raise RuntimeError("PDFium đổi cách ghi /ID hoặc /CreationDate; cập nhật make_pii_pdf.py")
    return out


def build_pii_pdf() -> bytes:
    """PDF 2 trang. Trang 1 (612x792): CCCD và số điện thoại. Trang 2 xoay 90° (hiển thị 792x612): số tài
    khoản sau nhãn "STK", đặt ở y=620 trong không gian chưa xoay (lớn hơn 612) để hộp chưa quy đổi
    xoay sẽ rơi ra ngoài trang hiển thị."""
    doc = pdfium.PdfDocument.new()
    try:
        p1 = doc.new_page(612, 792)
        add_text(doc, p1, "Ho so mau (du lieu hu cau)", 72, 720, size=14)
        add_text(doc, p1, f"CCCD: {CCCD} (hu cau)", 72, 690)
        add_text(doc, p1, f"Dien thoai: {PHONE} (hu cau)", 72, 670)
        raw.FPDFPage_GenerateContent(p1.raw)
        p2 = doc.new_page(612, 792)
        p2.set_rotation(90)
        # Quay chữ 90° ngược chiều kim đồng hồ để dòng chữ nằm ngang khi trang hiển thị đã xoay 90°.
        add_text(doc, p2, f"STK {ACCOUNT} (hu cau)", 100, 620, angle=90)
        raw.FPDFPage_GenerateContent(p2.raw)
        return save(doc)
    finally:
        doc.close()


def build_lines_pdf(lines: list[str]) -> bytes:
    """PDF một trang, mỗi phần tử ``lines`` một dòng chữ (dùng thử đếm phát hiện theo loại)."""
    doc = pdfium.PdfDocument.new()
    try:
        p = doc.new_page(612, 792)
        for i, line in enumerate(lines):
            add_text(doc, p, line, 72, 720 - 20 * i)
        raw.FPDFPage_GenerateContent(p.raw)
        return save(doc)
    finally:
        doc.close()


def build_blank_pages_pdf(pages: int) -> bytes:
    """PDF ``pages`` trang, mỗi trang một dòng chữ không có số (dùng thử giới hạn số trang)."""
    doc = pdfium.PdfDocument.new()
    try:
        for i in range(pages):
            p = doc.new_page(612, 792)
            add_text(doc, p, f"Trang mau so {i + 1}", 72, 720)
            raw.FPDFPage_GenerateContent(p.raw)
        return save(doc)
    finally:
        doc.close()


def build_noise_pages_pdf(pages: int, px: int, pt: int) -> bytes:
    """PDF viết tay ``pages`` trang ``pt`` x ``pt`` point, mọi trang dùng chung **một** ảnh nhiễu ngẫu nhiên
    ``px`` x ``px`` (nén không nổi) và một dòng chữ có số CCCD hư cấu. Tệp nhỏ (một ảnh) nhưng bản che của nó
    lớn tỉ lệ với số trang: dùng thử giới hạn dung lượng và RAM của ``redact_pdf``. Không tất định."""
    img = zlib.compress(os.urandom(px * px * 3), 6)
    objs: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: (b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB"
            b" /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (px, px, len(img)))
        + img + b"\nendstream",
    }
    kids, n = [], 5
    content = (b"q %d 0 0 %d 0 0 cm /Im0 Do Q BT /F1 12 Tf 72 72 Td (CCCD: 079203012345 hu cau) Tj ET"
               % (pt, pt))
    for _ in range(pages):
        objs[n] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        objs[n + 1] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /XObject"
                       b" << /Im0 4 0 R >> /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (pt, pt, n))
        kids.append(b"%d 0 R" % (n + 1))
        n += 2
    objs[2] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (pages, b" ".join(kids))
    out, offsets = io.BytesIO(), {}
    out.write(b"%PDF-1.7\n")
    for k in sorted(objs):
        offsets[k] = out.tell()
        out.write(b"%d 0 obj\n" % k + objs[k] + b"\nendobj\n")
    size, xref = max(objs) + 1, out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % size)
    for k in range(1, size):
        out.write(b"%010d 00000 n \n" % offsets[k])
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref))
    return out.getvalue()


if __name__ == "__main__":
    OUT.write_bytes(build_pii_pdf())
    print(f"đã ghi {OUT}")
