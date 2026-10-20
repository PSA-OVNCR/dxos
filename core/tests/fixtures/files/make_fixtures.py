# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Sinh lại các tệp mẫu cho test kiểm dịch/kiểm PDF (Plan 01 Task 14).

    python core/tests/fixtures/files/make_fixtures.py        # cần `pip install pypdf` (chỉ cho encrypted.pdf)

Tệp sinh ra được commit; không cần chạy lại trừ khi muốn đổi mẫu.
EICAR chỉ lưu ở dạng base64 (Global Constraints, Plan 01).
"""

import io
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _pdf(objects: list[bytes]) -> bytes:
    """Ghép một PDF tối giản với bảng xref đúng offset."""
    out = io.BytesIO()
    out.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def clean_text_pdf() -> bytes:
    content = b"BT /F1 18 Tf 72 720 Td (DX-OS Trust Core - van ban mau co lop chu) Tj ET"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ])


def image_only_pdf() -> bytes:
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0])  # ảnh 2x2 RGB
    content = b"q 200 0 0 200 72 500 cm /Im1 Do Q"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /XObject << /Im1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8"
        b" /Length %d >>\nstream\n" % len(pixels) + pixels + b"\nendstream",
    ])


def encrypted_pdf(clean: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter  # công cụ phát triển, không phải phụ thuộc của dxos-core

    w = PdfWriter(clone_from=PdfReader(io.BytesIO(clean)))
    w.encrypt(user_password="changeme-user", owner_password="changeme-owner", algorithm="AES-128")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def polyglot_bin() -> bytes:
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("payload.txt", "tệp đội lốt PDF")
    return b"%PDF-1.7\n" + z.getvalue()


def main() -> None:
    clean = clean_text_pdf()
    (HERE / "clean-text.pdf").write_bytes(clean)
    (HERE / "image-only.pdf").write_bytes(image_only_pdf())
    (HERE / "encrypted.pdf").write_bytes(encrypted_pdf(clean))
    (HERE / "polyglot.bin").write_bytes(polyglot_bin())
    (HERE / "eicar.b64").write_text(
        "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo=\n",
        encoding="ascii")


if __name__ == "__main__":
    main()
