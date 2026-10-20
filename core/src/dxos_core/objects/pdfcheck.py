# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tệp PDF **sau** khi đã quét AV sạch (D1): đúng magic, mở được, không mã hóa, có lớp chữ.

Dùng PDFium qua pypdfium2. PDFium không an toàn đa luồng nên mọi lần gọi đi qua một khóa.
"""

import threading
from dataclasses import dataclass
from typing import Literal

import pypdfium2 as pdfium

Reason = Literal["OK", "EMPTY", "TOO_LARGE", "BAD_MAGIC", "ENCRYPTED", "PARSE_ERROR", "NO_TEXT_LAYER"]
MAX_PAGES_SCANNED = 50
_LOCK = threading.Lock()


@dataclass
class PdfCheck:
    ok: bool
    reason: Reason


def _result(reason: Reason) -> PdfCheck:
    return PdfCheck(reason == "OK", reason)


def check_pdf(data: bytes, max_bytes: int) -> PdfCheck:
    if not data:
        return _result("EMPTY")
    if len(data) > max_bytes:
        return _result("TOO_LARGE")
    if not data.startswith(b"%PDF-"):
        return _result("BAD_MAGIC")
    with _LOCK:
        try:
            doc = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            return _result("ENCRYPTED" if "password" in str(exc).lower() else "PARSE_ERROR")
        try:
            if pdfium.raw.FPDF_GetSecurityHandlerRevision(doc.raw) != -1:   # mã hóa chỉ bằng owner password
                return _result("ENCRYPTED")
            n = len(doc)
            if n == 0:
                return _result("PARSE_ERROR")
            for i in range(min(n, MAX_PAGES_SCANNED)):
                page = doc[i]
                try:
                    text = page.get_textpage()
                    try:
                        if text.get_text_range().strip():
                            return _result("OK")
                    finally:
                        text.close()
                finally:
                    page.close()
            return _result("NO_TEXT_LAYER")
        except pdfium.PdfiumError:
            return _result("PARSE_ERROR")
        finally:
            doc.close()
