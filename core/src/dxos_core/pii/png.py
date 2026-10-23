# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Mã hóa PNG 8 bit RGB bằng ``zlib`` của thư viện chuẩn (Plan 04 Task 5; không thêm phụ thuộc, P4-D1).

Mã này được chép sang gói ``viewer`` (gói riêng, không import ``dxos_core``); hai bản và test của chúng
phải giống hệt nhau.
"""

import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IDAT_CHUNK = 1 << 20           # tối đa 1 MiB dữ liệu nén mỗi chunk IDAT


def _chunk(kind: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    """PNG không xen kẽ, 8 bit mỗi kênh, RGB. ``rgb`` là ``width * height * 3`` byte, hàng trên cùng trước.
    Ném ``ValueError`` (thông báo bắt đầu bằng "PNG") nếu kích thước không dương hoặc độ dài sai."""
    if width <= 0 or height <= 0 or len(rgb) != 3 * width * height:
        raise ValueError("PNG: kích thước ảnh không khớp dữ liệu")
    stride = 3 * width
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))      # bộ lọc "None"
    packed = zlib.compress(raw, 6)
    out = [_SIGNATURE, _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))]
    out += [_chunk(b"IDAT", packed[i:i + _IDAT_CHUNK]) for i in range(0, len(packed), _IDAT_CHUNK)]
    out.append(_chunk(b"IEND", b""))
    return b"".join(out)
