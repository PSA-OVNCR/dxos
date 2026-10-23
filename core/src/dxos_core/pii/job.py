# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Việc nền ``pii_detect``: dò PII trong một tệp PDF đã CLEAN (Plan 04 Task 4, S1; I5, P4-D2).

Luồng: đọc object từ kho → ``extract_pages`` (văn bản và hộp từng ký tự, PDFium dưới khóa chung của
``pdfcheck``) → ``detect_text`` từng trang → trong **một** transaction: ``pii_scans`` + ``pii_findings`` +
ledger ``pii.detected``, rồi đánh dấu việc xong.

* Kết quả không chứa giá trị PII hay mã băm của nó: ``pii_findings`` chỉ có loại, trang (từ 1) và hộp;
  ``pii.detected`` chỉ có ``sha256``, đếm theo loại và ``detector``. Thông báo log chỉ ghi tên lớp lỗi.
* Quá ``MAX_PAGES`` trang → ``TOO_LARGE`` (không dò). Lỗi PDFium hoặc lỗi bộ dò trên tệp này → ``FAILED``.
  Hai trạng thái này không có phát hiện nhưng guard ``pii_reviewed`` vẫn đòi người rà xác nhận.
* Idempotent: ``pii_scans.sha256`` là khóa chính; ``INSERT … ON CONFLICT DO NOTHING``, chỉ lần chèn
  thắng mới ghi ``pii_findings`` và ledger. Chạy lại (worker chết giữa chừng, hai upload cùng tệp) không
  nhân đôi hàng.
* Lỗi tạm thời (kho S3, DB) cho ném ra ngoài để worker thử lại với backoff. Lỗi của chính tệp (PDFium) là
  tất định nên ghi ``FAILED`` luôn, không thử lại: nếu không guard sẽ chờ mãi một lần dò không bao giờ có.
* Không để guard chờ mãi (R16): ``enqueue_missing_scans`` (gọi từ ``:pii-review``) xếp lại việc cho tệp CLEAN
  chưa có hàng ``pii_scans`` và chưa có việc đang chờ/chạy; ``record_failed_scan`` (worker gọi khi việc hết
  lượt thử) ghi ``FAILED`` để bản ghi quay về rà tay.
"""

import asyncio
import ctypes
import json
import logging
import re
from collections import Counter
from collections.abc import Collection, Iterable, Sequence

import asyncpg
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, complete, enqueue
from dxos_core.ledger.log import append
from dxos_core.objects import pdfcheck
from dxos_core.pii.detect import DETECTABLE, Box, Finding, detect_text

log = logging.getLogger("dxos_core.pii.job")

PII_JOB = "pii_detect"
DETECTOR = "dxos-pii/1"
MAX_PAGES = 200
PAGE_BREAK = "\f"                       # ký tự ngăn trang trong ``extract`` (không có hộp)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCALE = 1000                           # FPDF_PageToDevice trả số nguyên: nhân 1000 để giữ 0,001 pt


def detectable(types: Collection[str]) -> list[str]:
    """Phần của ``policies.pii.document_detect`` mà bộ dò hỗ trợ (EMAIL, NAME hợp lệ trong manifest nhưng
    chưa có bộ dò), giữ thứ tự khai báo. Rỗng nghĩa là không dò và guard không phải chờ."""
    return [t for t in types if t in DETECTABLE]


def _page_to_display(page: pdfium.PdfPage, width: float, height: float):
    """Phép biến đổi (x, y) trong không gian trang của PDFium sang không gian trang **hiển thị**: gốc ở góc
    dưới-trái của trang đã xoay (/Rotate) và đã cắt theo CropBox, đơn vị PDF point, ``width`` x ``height``
    là ``page.get_size()``. Lấy từ ``FPDF_PageToDevice`` (đã tính xoay, MediaBox, CropBox), dựng ma trận
    từ ba điểm mẫu."""
    size_x, size_y = round(width * _SCALE), round(height * _SCALE)

    def device(px: float, py: float) -> tuple[float, float]:
        dx, dy = ctypes.c_int(), ctypes.c_int()
        pdfium_raw.FPDF_PageToDevice(page.raw, 0, 0, size_x, size_y, 0, px, py, dx, dy)
        return dx.value / _SCALE, height - dy.value / _SCALE        # thiết bị: gốc trên-trái, y xuống

    unit = 1000.0
    o, ex, ey = device(0, 0), device(unit, 0), device(0, unit)
    a, b = (ex[0] - o[0]) / unit, (ex[1] - o[1]) / unit
    c, d = (ey[0] - o[0]) / unit, (ey[1] - o[1]) / unit

    def apply(x: float, y: float) -> tuple[float, float]:
        return a * x + c * y + o[0], b * x + d * y + o[1]

    return apply


def _page_text(textpage: pdfium.PdfTextPage, n: int) -> str:
    """Đúng ``n`` ký tự, ký tự thứ i ứng với chỉ số i của PDFium (để khớp ``get_charbox``)."""
    text = textpage.get_text_range(0, n) if n else ""
    if len(text) == n:
        return text
    # Ký tự ngoài BMP hay ký tự hỏng làm độ dài lệch: dựng từng ký tự, ký tự không biểu diễn được → U+FFFD.
    out = []
    for i in range(n):
        code = pdfium_raw.FPDFText_GetUnicode(textpage.raw, i)
        out.append("�" if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF else chr(code))
    return "".join(out)


def _extract_page(page: pdfium.PdfPage, number: int) -> tuple[str, list[Box | None]]:
    width, height = page.get_size()
    to_display = _page_to_display(page, width, height)
    textpage = page.get_textpage()
    try:
        n = textpage.count_chars()
        text = _page_text(textpage, n)
        boxes: list[Box | None] = []
        for i in range(n):
            if pdfium_raw.FPDFText_IsGenerated(textpage.raw, i) > 0:    # "\r\n" do PDFium chèn thêm
                boxes.append(None)
                continue
            left, bottom, right, top = textpage.get_charbox(i)
            (x0, y0), (x1, y1) = to_display(left, bottom), to_display(right, top)
            boxes.append(Box(number, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        return text, boxes
    finally:
        textpage.close()


def extract_pages(data: bytes, max_pages: int = MAX_PAGES) -> list[tuple[str, list[Box | None]]] | None:
    """Văn bản và hộp từng ký tự của **từng trang** (``len(text) == len(boxes)``), trang đánh số từ 1.

    Hộp tính bằng PDF point trong không gian trang đang hiển thị: gốc ở góc dưới-trái của trang sau khi xoay
    (/Rotate) và cắt (CropBox), kích thước ``page.get_size()``. Ký tự do PDFium chèn thêm (xuống dòng) có hộp
    ``None``. Trả ``None`` nếu quá ``max_pages`` trang. Ném ``pdfium.PdfiumError`` nếu tệp không mở được.
    Mọi lệnh gọi PDFium nằm dưới ``pdfcheck._LOCK`` (khóa được giữ từng trang, không giữ suốt tệp).
    """
    with pdfcheck._LOCK:
        doc = pdfium.PdfDocument(data)
        count = len(doc)
    try:
        if count > max_pages:
            return None
        pages = []
        for index in range(count):
            with pdfcheck._LOCK:
                page = doc[index]
                try:
                    pages.append(_extract_page(page, index + 1))
                finally:
                    page.close()
        return pages
    finally:
        with pdfcheck._LOCK:
            doc.close()


def extract(data: bytes, max_pages: int = MAX_PAGES) -> tuple[str, list[Box | None]] | None:
    """Như ``extract_pages`` nhưng nối cả tệp thành một chuỗi, các trang ngăn bằng ``PAGE_BREAK`` (hộp
    ``None``). ``None`` khi quá ``max_pages`` trang. Việc nền dò từng trang riêng, không dùng hàm này."""
    pages = extract_pages(data, max_pages)
    if pages is None:
        return None
    text: list[str] = []
    boxes: list[Box | None] = []
    for i, (page_text, page_boxes) in enumerate(pages):
        if i:
            text.append(PAGE_BREAK)
            boxes.append(None)
        text.append(page_text)
        boxes.extend(page_boxes)
    return "".join(text), boxes


def _scan(data: bytes, types: Sequence[str]) -> tuple[str, list[Finding]]:
    """(status, findings) cho một tệp. Chạy trong thread (PDFium và regex đều chặn event loop)."""
    try:
        pages = extract_pages(data)
        if pages is None:
            return "TOO_LARGE", []
        findings: list[Finding] = []
        for text, boxes in pages:
            findings.extend(detect_text(text, boxes, types))     # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 (lỗi tất định của tệp này: ghi FAILED, không thử lại)
        log.warning("không dò được PII (%s); ghi FAILED", type(exc).__name__)    # không ghi nội dung lỗi
        return "FAILED", []
    return "DONE", findings


def _bbox_json(finding: Finding) -> str:
    return json.dumps([[round(b.left, 3), round(b.bottom, 3), round(b.right, 3), round(b.top, 3)]
                       for b in finding.boxes])


async def process_pii_job(ctx: WorkerContext, job: Job) -> None:
    sha = job.payload["sha256"]
    types = job.payload["types"]
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise ValueError("payload pii_detect: sha256 không hợp lệ")
    if not isinstance(types, list) or not types or not set(types) <= set(DETECTABLE):
        raise ValueError("payload pii_detect: types không hợp lệ")
    async with ctx.pool.acquire() as conn:
        if await conn.fetchval("SELECT 1 FROM pii_scans WHERE sha256=$1", sha):      # đã dò (chạy lại)
            await complete(conn, job.id)
            return
        status = await conn.fetchval("SELECT status FROM objects WHERE sha256=$1", sha)
    if status != "CLEAN":
        raise ValueError("pii_detect: object không tồn tại hoặc không CLEAN")
    data = await asyncio.to_thread(ctx.store.read_object, sha)
    scan_status, findings = await asyncio.to_thread(_scan, data, types)
    async with ctx.pool.acquire() as conn, conn.transaction():
        inserted = await conn.fetchval(
            "INSERT INTO pii_scans(sha256, status, findings, detector) VALUES ($1, $2, $3, $4)"
            " ON CONFLICT (sha256) DO NOTHING RETURNING sha256",
            sha, scan_status, len(findings), DETECTOR)
        if inserted is not None:
            await conn.executemany(
                "INSERT INTO pii_findings(sha256, type, page, bbox) VALUES ($1, $2, $3, $4::jsonb)",
                [(sha, f.type, f.page, _bbox_json(f)) for f in findings])
            if scan_status == "DONE":
                await append(conn, type="pii.detected", subject=sha, hmac_key=ctx.hmac_key,
                             body={"sha256": sha, "counts": dict(Counter(f.type for f in findings)),
                                   "detector": DETECTOR})
        await complete(conn, job.id)


async def enqueue_missing_scans(conn: asyncpg.Connection, shas: Iterable[str], types: Collection[str]) -> int:
    """Xếp việc ``pii_detect`` cho tệp CLEAN chưa có hàng ``pii_scans`` và chưa có việc ``QUEUED``/``RUNNING``
    cho sha đó (tệp CLEAN từ trước khi có tính năng, hoặc CLEAN lúc manifest chưa khai ``document_detect``).
    ``types`` lấy từ manifest mà guard đang dùng; không có loại hỗ trợ thì không làm gì. Trả số việc đã xếp.
    Gọi trong transaction của bên gọi."""
    wanted = detectable(types)
    if not wanted:
        return 0
    queued = 0
    for sha in sorted(set(shas)):
        if await conn.fetchval("SELECT 1 FROM pii_scans WHERE sha256=$1", sha):
            continue
        if await conn.fetchval(
                "SELECT 1 FROM jobs WHERE kind=$1 AND state IN ('QUEUED', 'RUNNING')"
                " AND payload->>'sha256'=$2", PII_JOB, sha):
            continue
        await enqueue(conn, PII_JOB, {"sha256": sha, "types": wanted})
        queued += 1
    return queued


async def record_failed_scan(conn: asyncpg.Connection, job: Job) -> None:
    """Lần thử cuối của việc ``pii_detect`` thất bại: ghi ``FAILED`` (findings 0) để guard không chờ mãi mà
    đòi rà tay. Không ghi gì nếu payload không có sha256 hợp lệ hoặc object không tồn tại (không có khóa)."""
    sha = job.payload.get("sha256")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        return
    await conn.execute(
        "INSERT INTO pii_scans(sha256, status, findings, detector)"
        " SELECT $1::text::sha256_hex, 'FAILED', 0, $2"
        " WHERE EXISTS (SELECT 1 FROM objects WHERE sha256::text = $1::text)"
        " ON CONFLICT (sha256) DO NOTHING", sha, DETECTOR)
