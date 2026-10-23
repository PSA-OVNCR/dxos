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
import re
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


if __name__ == "__main__":
    OUT.write_bytes(build_pii_pdf())
    print(f"đã ghi {OUT}")
