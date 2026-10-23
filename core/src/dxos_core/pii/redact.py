# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bản che PII của PDF: mỗi trang là **một ảnh** đã tô đen, không còn lớp chữ (Plan 04 Task 5; S1; P4-D5).

Cách làm: dựng lại từng trang bằng PDFium (đã tính /Rotate và CropBox, như ``extract_pages``), tô đen các hộp
của phát hiện nở thêm ``pad_pt`` point trên chính điểm ảnh, nén ngay bằng ``zlib`` thành một image XObject rồi
giải phóng bitmap. PDF đầu ra được **viết tay, từng trang một** (PDF 1.7 tối thiểu: Catalog, Pages, mỗi trang
gồm ảnh, nội dung ``q W 0 0 H 0 0 cm /Im Do Q`` và trang; bảng xref và trailer ở cuối), không qua
``PdfDocument.save``: dựng tài liệu PDFium chứa mọi bitmap chưa nén thì RAM tăng theo số trang (đo được
+1,2 GB cho 200 trang Letter, hơn 10 GB cho 200 trang cỡ lớn, R18a). Nay đỉnh RAM xấp xỉ một bitmap cộng phần
đã nén. Vì chỉ còn ảnh nên số bị che không thể chép lại từ bản che. Đầu ra không có /Info, /ID, chú thích hay
tệp đính kèm của bản gốc. Chỉ dùng ``pypdfium2`` và thư viện chuẩn (không thêm phụ thuộc, P4-D1).

Hộp là PDF point trong không gian trang **đang hiển thị**, gốc dưới-trái (xem ``pii.job.extract_pages``);
trang ảnh có cùng khổ với trang hiển thị nên không cần xoay lại. Chú thích và trường biểu mẫu không được dò
(chữ trong đó vẫn hiện trong ảnh nếu có).

Giới hạn (chống cạn bộ nhớ): tối đa ``MAX_PAGES`` trang, ảnh mỗi trang không quá ``max_px`` điểm theo mỗi
chiều, tổng phần đã nén không quá ``MAX_OUT_BYTES`` (100 MiB; vượt thì ``RedactionTooLarge``, R20: trang ảnh
nhiễu nén không nổi nên cỡ bản che tỉ lệ với số trang). Trang lớn tới mức 150 dpi vượt ``max_px`` thì hạ dpi
riêng cho trang đó (khổ trang không đổi). Khóa PDFium dùng chung với ``pdfcheck``, giữ từng trang (dựng
và tô); nén chạy ngoài khóa.

Hàm đồng bộ, chặn: bên gọi chạy trong ``asyncio.to_thread``. Không bao giờ ghi nội dung phát hiện vào
thông báo lỗi.
"""

import io
import math
import zlib
from collections.abc import Sequence

import pypdfium2 as pdfium

from dxos_core.objects import pdfcheck
from dxos_core.pii.detect import Box, Finding

MAX_PAGES = 200
MAX_OUT_BYTES = 100 * 1024 * 1024         # trần dung lượng bản che (R20)
_BLACK = (0, 0, 0, 255)


class RedactionTooLarge(Exception):
    """Bản che vượt ``max_out_bytes``: kết cục cố định của tệp này, thử lại không giúp gì."""


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


def _num(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _compress_rgb(bitmap: pdfium.PdfBitmap) -> bytes:
    """Nén các điểm ảnh RGB của bitmap (bỏ phần đệm cuối mỗi hàng nếu có), không sao chép cả bitmap."""
    view = memoryview(bitmap.buffer).cast("B")
    row = 3 * bitmap.width
    comp = zlib.compressobj(6)
    if bitmap.stride == row:
        step = 1 << 20
        out = [comp.compress(view[i:i + step]) for i in range(0, row * bitmap.height, step)]
    else:
        out = [comp.compress(view[y * bitmap.stride:y * bitmap.stride + row]) for y in range(bitmap.height)]
    out.append(comp.flush())
    return b"".join(out)


class _PdfWriter:
    """Ghi PDF tuần tự: đối tượng nào xong vào bộ đệm ngay (chỉ giữ dữ liệu đã nén), nhớ offset cho xref."""

    def __init__(self) -> None:
        self.buf = io.BytesIO()
        self.buf.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        self.offsets: dict[int, int] = {}

    @property
    def size(self) -> int:
        return self.buf.tell()

    def obj(self, num: int, body: bytes, stream: bytes | None = None) -> None:
        self.offsets[num] = self.buf.tell()
        self.buf.write(b"%d 0 obj\n" % num)
        if stream is None:
            self.buf.write(body + b"\nendobj\n")
        else:
            self.buf.write(body.replace(b"@LEN@", b"%d" % len(stream)) + b"\nstream\n" + stream +
                           b"\nendstream\nendobj\n")

    def finish(self, root: int) -> bytes:
        size = max(self.offsets) + 1
        start = self.buf.tell()
        self.buf.write(b"xref\n0 %d\n0000000000 65535 f \n" % size)
        for n in range(1, size):
            self.buf.write(b"%010d 00000 n \n" % self.offsets[n])
        self.buf.write(b"trailer\n<< /Size %d /Root %d 0 R >>\n" % (size, root))
        self.buf.write(b"startxref\n%d\n%%%%EOF\n" % start)
        return self.buf.getvalue()


def redact_pdf(data: bytes, findings: Sequence[Finding], dpi: int = 150, pad_pt: float = 2.0,
               max_px: int = 4000, max_pages: int = MAX_PAGES, max_out_bytes: int = MAX_OUT_BYTES) -> bytes:
    """PDF chỉ có ảnh: mỗi trang của ``data`` thành một ảnh (``dpi``, hạ nếu quá ``max_px``) với mọi hộp của
    ``findings`` tô đen (nở ``pad_pt`` point). Ném ``ValueError`` nếu tệp quá ``max_pages`` trang hoặc một
    phát hiện nằm ngoài tệp; ``pdfium.PdfiumError`` nếu tệp không mở được; ``RedactionTooLarge`` ngay khi phần
    đã nén vượt ``max_out_bytes`` (trang nhiễu nén không nổi: cỡ ra xấp xỉ cỡ thô). RAM đỉnh xấp xỉ một bitmap
    cộng tối đa ``max_out_bytes`` đã nén."""
    with pdfcheck._LOCK:
        src = pdfium.PdfDocument(data)
        count = len(src)
    try:
        if count > max_pages:
            raise ValueError(f"tệp quá {max_pages} trang")
        by_page = _boxes_by_page(findings, count)
        writer = _PdfWriter()
        kids = []
        for number in range(1, count + 1):
            with pdfcheck._LOCK:
                page = src[number - 1]
                try:
                    width, height = page.get_size()                 # khổ hiển thị: đã xoay và cắt
                    bitmap = page.render(scale=_scale_for(width, height, dpi, max_px), rev_byteorder=True)
                finally:
                    page.close()
                try:
                    _blackout(bitmap, width, height, by_page.get(number, ()), pad_pt)
                except BaseException:
                    bitmap.close()
                    raise
            try:
                pixels = _compress_rgb(bitmap)
                px_w, px_h = bitmap.width, bitmap.height
            finally:
                with pdfcheck._LOCK:
                    bitmap.close()
            if writer.size + len(pixels) > max_out_bytes:
                raise RedactionTooLarge(f"bản che vượt {max_out_bytes} byte ở trang {number}")
            img, content, page_obj = 3 + 3 * (number - 1), 4 + 3 * (number - 1), 5 + 3 * (number - 1)
            writer.obj(img, b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB"
                       b" /BitsPerComponent 8 /Filter /FlateDecode /Length @LEN@ >>" % (px_w, px_h), pixels)
            del pixels
            w, h = _num(width), _num(height)
            writer.obj(content, b"<< /Length @LEN@ >>", f"q {w} 0 0 {h} 0 0 cm /Im0 Do Q".encode())
            resources = f"/Resources << /XObject << /Im0 {img} 0 R >> >>"
            writer.obj(page_obj, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] {resources}"
                                  f" /Contents {content} 0 R >>").encode())
            kids.append(b"%d 0 R" % page_obj)
        writer.obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        writer.obj(2, b"<< /Type /Pages /Count %d /Kids [%s] >>" % (count, b" ".join(kids)))
        return writer.finish(root=1)
    finally:
        with pdfcheck._LOCK:
            src.close()
