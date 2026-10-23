# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bản che PII của PDF: mỗi trang là **một ảnh** đã tô đen, không còn lớp chữ (Plan 04 Task 5; S1; P4-D5).

Cách làm: dựng lại từng trang bằng PDFium (đã tính /Rotate và CropBox, như ``extract_pages``), tô đen các hộp
của phát hiện nở thêm ``pad_pt`` point trên chính điểm ảnh, rồi đặt ảnh đó thành trang của một PDF mới. Vì
chỉ còn ảnh nên số bị che không thể chép lại từ bản che. PDF mới không mang metadata, chú thích hay tệp
đính kèm của bản gốc. Chỉ dùng ``pypdfium2`` (không thêm phụ thuộc, P4-D1).

Hộp là PDF point trong không gian trang **đang hiển thị**, gốc dưới-trái (xem ``pii.job.extract_pages``);
trang ảnh có cùng khổ với trang hiển thị nên không cần xoay lại.

Giới hạn (chống cạn bộ nhớ): tối đa ``MAX_PAGES`` trang, ảnh mỗi trang không quá ``max_px`` điểm theo mỗi
chiều. Trang lớn tới mức 150 dpi vượt ``max_px`` thì hạ dpi riêng cho trang đó (khổ trang không đổi).
Khóa PDFium dùng chung với ``pdfcheck`` và được giữ từng trang, không giữ suốt tệp.

Hàm đồng bộ, chặn: bên gọi chạy trong ``asyncio.to_thread``. Không bao giờ ghi nội dung phát hiện vào
thông báo lỗi.
"""

import io
import math
from collections.abc import Sequence

import pypdfium2 as pdfium

from dxos_core.objects import pdfcheck
from dxos_core.pii.detect import Box, Finding

MAX_PAGES = 200
_BLACK = (0, 0, 0, 255)


def _scale_for(width: float, height: float, dpi: int, max_px: int) -> float:
    """Hệ số điểm ảnh/point cho một trang: ``dpi``, hạ xuống nếu ảnh vượt ``max_px`` mỗi chiều."""
    scale = dpi / 72
    longest = max(width, height)
    if longest * scale > max_px:
        scale = max_px / longest
    while scale > 0 and (math.ceil(width * scale) > max_px or math.ceil(height * scale) > max_px):
        scale *= 0.999                          # sai số dấu phẩy động: ceil() có thể vượt max_px 1 điểm
    return scale


def _boxes_by_page(findings: Sequence[Finding], count: int) -> dict[int, list[Box]]:
    out: dict[int, list[Box]] = {}
    for finding in findings:
        for box in finding.boxes:
            if not 1 <= box.page <= count:
                raise ValueError(f"phát hiện nằm ngoài tệp: tệp có {count} trang")
            out.setdefault(box.page, []).append(box)
    return out


def _blackout(bitmap: pdfium.PdfBitmap, width: float, height: float, boxes: Sequence[Box],
              pad_pt: float) -> None:
    """Tô đen các hộp (point, gốc dưới-trái, nở ``pad_pt``) trên bitmap có gốc trên-trái."""
    sx, sy = bitmap.width / width, bitmap.height / height
    for b in boxes:
        x0 = max(0, math.floor((b.left - pad_pt) * sx))
        x1 = min(bitmap.width, math.ceil((b.right + pad_pt) * sx))
        y0 = max(0, math.floor((height - b.top - pad_pt) * sy))
        y1 = min(bitmap.height, math.ceil((height - b.bottom + pad_pt) * sy))
        if x1 > x0 and y1 > y0:
            bitmap.fill_rect(_BLACK, x0, y0, x1 - x0, y1 - y0)


def redact_pdf(data: bytes, findings: Sequence[Finding], dpi: int = 150, pad_pt: float = 2.0,
               max_px: int = 4000, max_pages: int = MAX_PAGES) -> bytes:
    """PDF chỉ có ảnh: mỗi trang của ``data`` thành một ảnh (``dpi``, hạ nếu quá ``max_px``) với mọi hộp của
    ``findings`` tô đen (nở ``pad_pt`` point). Ném ``ValueError`` nếu tệp quá ``max_pages`` trang hoặc một
    phát hiện nằm ngoài tệp; ``pdfium.PdfiumError`` nếu tệp không mở được."""
    with pdfcheck._LOCK:
        src = pdfium.PdfDocument(data)
        count = len(src)
    out = None
    try:
        if count > max_pages:
            raise ValueError(f"tệp quá {max_pages} trang")
        by_page = _boxes_by_page(findings, count)
        with pdfcheck._LOCK:
            out = pdfium.PdfDocument.new()
        for number in range(1, count + 1):
            with pdfcheck._LOCK:
                page = src[number - 1]
                try:
                    width, height = page.get_size()                 # khổ hiển thị: đã xoay và cắt
                    bitmap = page.render(scale=_scale_for(width, height, dpi, max_px))
                finally:
                    page.close()
                try:
                    _blackout(bitmap, width, height, by_page.get(number, ()), pad_pt)
                    image = pdfium.PdfImage.new(out)
                    image.set_bitmap(bitmap)
                    image.set_matrix(pdfium.PdfMatrix().scale(width, height))
                    new_page = out.new_page(width, height)
                    new_page.insert_obj(image)
                    new_page.gen_content()
                    new_page.close()
                finally:
                    bitmap.close()
        with pdfcheck._LOCK:
            buf = io.BytesIO()
            out.save(buf)
        return buf.getvalue()
    finally:
        with pdfcheck._LOCK:
            if out is not None:
                out.close()
            src.close()
