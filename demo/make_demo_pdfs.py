#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dựng 3 PDF mẫu của "Công ty TNHH Sao Mai" cho ``make demo-seed`` (Plan 04 Task 13).

    python demo/make_demo_pdfs.py        # ghi lại demo/sao-mai/*.pdf

Dùng lại ``core/tests/helpers/make_pii_pdf.py`` (pypdfium2, phông Helvetica, chỉ ASCII nên không dấu). Mọi số
CCCD, điện thoại, tài khoản trong tệp đều **hư cấu** (tự bịa, không thuộc ai) và được ghi chú "(hu cau)" ngay
cạnh. Để bước dò PII (S1) có việc thật phải làm khi demo, mỗi tệp có ít nhất một CCCD và một số điện thoại.
Kết quả tất định; test ``test_demo_pdfs_are_reproducible`` dựng lại và so từng byte với tệp đã commit. Byte
phụ thuộc bản PDFium đi kèm pypdfium2: nâng pypdfium2 có thể làm test đỏ, khi đó chạy lại lệnh trên.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "sao-mai"
HELPER = ROOT / "core/tests/helpers/make_pii_pdf.py"

# tên tệp -> các dòng chữ (ASCII). Số hư cấu: CCCD mã tỉnh 001-096 để bộ dò nhận.
DOCUMENTS: dict[str, list[str]] = {
    "quy-che-chi-tieu.pdf": [
        "CONG TY TNHH SAO MAI (cong ty hu cau, tai lieu mau de demo)",
        "QUYET DINH ve viec ban hanh Quy che chi tieu noi bo nam 2027",
        "Moi so lieu trong tep nay deu hu cau, khong thuoc ai.",
        "Nguoi lien he: Tran Thi Mai (ten hu cau)",
        "CCCD: 079301234567 (hu cau)",
        "Dien thoai: 0987 654 321 (hu cau)",
    ],
    "hop-dong-ke-toan.pdf": [
        "CONG TY TNHH SAO MAI (cong ty hu cau, tai lieu mau de demo)",
        "HOP DONG cung cap dich vu ke toan thue nam 2027",
        "Moi so lieu trong tep nay deu hu cau, khong thuoc ai.",
        "Ben B: Le Van Binh (ten hu cau)",
        "CCCD: 001185012345 (hu cau)",
        "Dien thoai: 0903 112 233 (hu cau)",
        "STK 9704123456789 (hu cau)",
    ],
    "thong-bao-tuyen-dung.pdf": [
        "CONG TY TNHH SAO MAI (cong ty hu cau, tai lieu mau de demo)",
        "THONG BAO tuyen dung nhan vien hanh chinh quy I/2027",
        "Moi so lieu trong tep nay deu hu cau, khong thuoc ai.",
        "Ung vien tham khao: Pham Quoc Cuong (ten hu cau)",
        "CCCD: 048200098765 (hu cau)",
        "Dien thoai: 0356 789 012 (hu cau)",
    ],
}


def _helper():
    spec = importlib.util.spec_from_file_location("make_pii_pdf", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_all() -> dict[str, bytes]:
    build = _helper().build_lines_pdf
    return {name: build(lines) for name, lines in DOCUMENTS.items()}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf_name, data in build_all().items():
        (OUT / pdf_name).write_bytes(data)
        print(f"đã ghi {OUT / pdf_name}")
