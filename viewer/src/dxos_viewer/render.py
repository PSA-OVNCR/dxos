# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dựng một trang PDF thành PNG, có watermark, hoàn toàn trong RAM (Plan 04 Task 7; S2; P4-D6, P4-D7).

Mỗi lần gọi: mở tài liệu từ ``bytes`` (PDFium giữ trong RAM), chèn watermark vào **bản trong bộ nhớ** của
trang (không bao giờ lưu lại), dựng đúng một trang thành bitmap rồi mã hóa PNG bằng ``zlib``. Không ghi đĩa
(test tĩnh ``test_no_disk.py``), không giữ trạng thái giữa hai lần gọi. Watermark **chỉ để răn đe**: ai cũng
chụp màn hình được; nó gắn danh tính và giờ xem vào ảnh để người xem biết là có dấu vết.

Watermark: dòng ``DX-OS <8 ký tự đầu của sub> <YYYY-MM-DD HH:MM> ICT`` (chỉ ASCII, phông Helvetica chuẩn nên
không dấu tiếng Việt), cỡ 18 point, xoay 30 độ, lặp lưới 3 x 4 trên **trang như người xem thấy** (đã tính
/Rotate và CropBox), xám 128 độ đục 45% (R27; thấy được cả trên nền sáng và nền tối).
Chữ được tô sau cùng nên nằm trên nội dung trang.

Chú thích (annotation) được dán phẳng vào nội dung trước khi chèn watermark và không dựng lại lần nữa
(``draw_annots=False``), nên không chú thích nào che được watermark.

Giới hạn: tối đa ``MAX_PAGES`` (200) trang; ảnh không quá ``MAX_PX`` (4000) điểm mỗi chiều (trang quá lớn thì
hạ dpi riêng cho trang đó, cỡ chữ watermark theo điểm ảnh được giữ); 110 dpi. Một trang một lúc: RAM đỉnh xấp
xỉ tệp + một bitmap + bản nén PNG (bitmap 4000 x 4000 là 48 MB; ``encode_png`` dựng thêm một bản đã lọc, tổng
khoảng 3 lần bitmap, nên ``app`` giới hạn số lần dựng song song).

PDFium không an toàn đa luồng: mọi lời gọi PDFium đi qua ``_LOCK``; mã hóa PNG chạy ngoài khóa. Hàm đồng bộ,
chặn: bên gọi chạy trong ``asyncio.to_thread``. Thông báo lỗi không bao giờ chứa nội dung tệp.
"""

import ctypes
import math
import re
import threading
from datetime import datetime, timedelta, timezone

import pypdfium2 as pdfium

from dxos_viewer.png import encode_png

MAX_PAGES = 200
MAX_PX = 4000
DPI = 110
FONT_PT = 18.0
ANGLE_DEG = 30.0
GRID_COLS, GRID_ROWS = 3, 4
GREY = 128                                # xám trung bình: thấy được cả trên vùng sáng lẫn vùng tối
ALPHA = round(0.45 * 255)                 # độ đục 45%: trên nền trắng ra ~198, trên nền đen ra ~58
ICT = timezone(timedelta(hours=7))        # Việt Nam không có giờ mùa hè; không cần dữ liệu múi giờ (tzdata)

_LOCK = threading.Lock()
_SUB_BAD = re.compile(r"[^A-Za-z0-9_-]")


class RenderError(Exception):
    """Gốc các lỗi dựng trang; thông báo không chứa nội dung tệp."""


class BadDocument(RenderError):
    """Tệp không mở/dựng được như một PDF."""


class TooManyPages(RenderError):
    """Tệp quá ``MAX_PAGES`` trang."""


class PageOutOfRange(RenderError):
    """Số trang ngoài ``1..n``."""


def watermark_text(sub: str, now: datetime) -> str:
    """``DX-OS <8 ký tự đầu của sub> <YYYY-MM-DD HH:MM> ICT``; chỉ ASCII (ký tự lạ trong sub thành ``_``)."""
    who = _SUB_BAD.sub("_", sub[:8]) or "_"
    return f"DX-OS {who} {now.astimezone(ICT):%Y-%m-%d %H:%M} ICT"


def _scale_for(width: float, height: float, dpi: int, max_px: int) -> float:
    """Hệ số điểm ảnh/point của một trang: ``dpi``, hạ xuống nếu ảnh vượt ``max_px`` mỗi chiều."""
    scale = dpi / 72
    longest = max(width, height)
    if longest * scale > max_px:
        scale = max_px / longest
    while scale > 0 and (math.ceil(width * scale) > max_px or math.ceil(height * scale) > max_px):
        scale *= 0.999                          # sai số dấu phẩy động: ceil() có thể vượt max_px 1 điểm
    return scale


Box = tuple[float, float, float, float]


def _to_user_space(rot: int, box: Box, x: float, y: float) -> tuple[float, float]:
    """Điểm (x, y) trên trang **hiển thị** (gốc dưới-trái) -> toạ độ không gian người dùng của trang."""
    x0, y0, x1, y1 = box
    wu, hu = x1 - x0, y1 - y0
    u, v = {0: (x, y), 90: (wu - y, x), 180: (wu - x, hu - y), 270: (y, hu - x)}[rot]
    return x0 + u, y0 + v


def apply_watermark(doc: pdfium.PdfDocument, page: pdfium.PdfPage, text: str, width: float, height: float,
                    scale: float, dpi: int = DPI) -> None:
    """Chèn lưới watermark vào ``page`` (chỉ bản trong bộ nhớ). ``width`` x ``height``: khổ hiển thị (point),
    ``scale`` là điểm ảnh/point sẽ dựng. Người gọi giữ ``_LOCK``."""
    rot = page.get_rotation() % 360
    box = page.get_bbox()
    # cỡ chữ theo điểm ảnh không đổi khi dpi bị hạ vì trang quá lớn
    size = FONT_PT * max(1.0, (dpi / 72) / scale)
    font = pdfium.raw.FPDFText_LoadStandardFont(doc.raw, b"Helvetica")
    if not font:
        raise BadDocument("không nạp được phông Helvetica")
    phi = math.radians(ANGLE_DEG + rot)               # góc trong không gian người dùng
    cos, sin = math.cos(phi), math.sin(phi)
    codes = [ord(c) for c in text]
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            obj = pdfium.raw.FPDFPageObj_CreateTextObj(doc.raw, font, size)
            if not obj:
                raise BadDocument("không tạo được đối tượng chữ")
            buf = (ctypes.c_ushort * (len(codes) + 1))(*codes)
            pdfium.raw.FPDFText_SetText(obj, buf)
            left, bottom, right, top = (ctypes.c_float() for _ in range(4))
            pdfium.raw.FPDFPageObj_GetBounds(obj, left, bottom, right, top)
            cx, cy = (left.value + right.value) / 2, (bottom.value + top.value) / 2
            u, v = _to_user_space(rot, box, width * (col + 0.5) / GRID_COLS, height * (row + 0.5) / GRID_ROWS)
            pdfium.raw.FPDFPageObj_SetFillColor(obj, GREY, GREY, GREY, ALPHA)
            # xoay quanh tâm dòng chữ rồi dời tâm đó tới (u, v)
            pdfium.raw.FPDFPageObj_Transform(obj, cos, sin, -sin, cos,
                                             u - (cos * cx - sin * cy), v - (sin * cx + cos * cy))
            pdfium.raw.FPDFPage_InsertObject(page.raw, obj)      # trang nắm giữ đối tượng
    pdfium.raw.FPDFPage_GenerateContent(page.raw)


def _flattened_page(doc: pdfium.PdfDocument, index: int) -> pdfium.PdfPage:
    """Trang ``index`` sau khi dán phẳng chú thích vào nội dung. Chú thích được vẽ **sau** nội dung trang nên
    một chú thích có hình đục (AP) che được watermark; dán phẳng trước khi chèn watermark thì watermark nằm
    trên cùng. Sau khi dán phẳng phải mở lại trang (đối tượng trang cũ không còn khớp). Người gọi giữ
    ``_LOCK``."""
    page = doc[index]
    try:
        # lỗi hoặc không có gì để dán: bỏ qua
        pdfium.raw.FPDFPage_Flatten(page.raw, pdfium.raw.FLAT_NORMALDISPLAY)
    finally:
        page.close()
    return doc[index]


def _open(data: bytes) -> pdfium.PdfDocument:
    with _LOCK:
        try:
            return pdfium.PdfDocument(data)
        except (pdfium.PdfiumError, ValueError, OSError) as exc:
            raise BadDocument("không mở được tệp PDF") from exc


def _close(doc: pdfium.PdfDocument) -> None:
    with _LOCK:
        doc.close()


def page_count(data: bytes, max_pages: int = MAX_PAGES) -> int:
    """Số trang của ``data``. ``BadDocument`` nếu không mở được, ``TooManyPages`` nếu quá ``max_pages``."""
    doc = _open(data)
    try:
        with _LOCK:
            count = len(doc)
    finally:
        _close(doc)
    if count > max_pages:
        raise TooManyPages(f"tệp quá {max_pages} trang")
    if count == 0:
        raise BadDocument("tệp không có trang")
    return count


def _compact_rgb(bitmap: pdfium.PdfBitmap) -> memoryview | bytes:
    """Điểm ảnh RGB không đệm cuối hàng; không sao chép khi stride đã khít."""
    row = 3 * bitmap.width
    view = memoryview(bitmap.buffer).cast("B")
    if bitmap.stride == row:
        return view[:row * bitmap.height]
    return b"".join(view[y * bitmap.stride:y * bitmap.stride + row] for y in range(bitmap.height))


def render_page(data: bytes, number: int, sub: str, now: datetime, *, dpi: int = DPI, max_px: int = MAX_PX,
                max_pages: int = MAX_PAGES) -> bytes:
    """PNG của trang ``number`` (từ 1) của ``data``, có watermark của ``sub`` lúc ``now``."""
    text = watermark_text(sub, now)
    doc = _open(data)
    try:
        with _LOCK:
            count = len(doc)
        if count > max_pages:
            raise TooManyPages(f"tệp quá {max_pages} trang")
        if not 1 <= number <= count:
            raise PageOutOfRange(f"trang {number} ngoài 1..{count}")
        with _LOCK:
            try:
                page = _flattened_page(doc, number - 1)
                try:
                    width, height = page.get_size()                 # khổ hiển thị: đã xoay và cắt
                    if not (width > 0 and height > 0 and math.isfinite(width) and math.isfinite(height)):
                        raise BadDocument("khổ trang không hợp lệ")
                    scale = _scale_for(width, height, dpi, max_px)
                    apply_watermark(doc, page, text, width, height, scale, dpi)
                    bitmap = page.render(scale=scale, rev_byteorder=True, draw_annots=False)
                finally:
                    page.close()
            except pdfium.PdfiumError as exc:
                raise BadDocument("không dựng được trang") from exc
        try:
            if bitmap.n_channels != 3:
                raise BadDocument("định dạng bitmap không mong đợi")
            return encode_png(bitmap.width, bitmap.height, _compact_rgb(bitmap))
        finally:
            with _LOCK:
                bitmap.close()
    finally:
        _close(doc)
