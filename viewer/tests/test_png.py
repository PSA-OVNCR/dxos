# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bộ mã hóa PNG bằng zlib (Plan 04 Task 5). Chép từ core/tests/test_pii_png.py, chỉ khác dòng import."""

import struct
import zlib

import pytest
from dxos_viewer.png import encode_png

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunks(png: bytes) -> list[tuple[bytes, bytes, int]]:
    assert png[:8] == SIGNATURE
    pos, out = 8, []
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        kind, body = png[pos + 4:pos + 8], png[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length:pos + 12 + length])
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF, kind
        out.append((kind, body, crc))
        pos += 12 + length
    assert pos == len(png)
    return out


def test_png_roundtrip_header_and_crc():
    width, height = 5, 3
    rgb = bytes((x * 40 + y * 7 + c) % 256 for y in range(height) for x in range(width) for c in range(3))
    chunks = _chunks(encode_png(width, height, rgb))
    assert [c[0] for c in chunks][0] == b"IHDR" and chunks[-1][0] == b"IEND" and chunks[-1][1] == b""
    w, h, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
    assert (w, h, depth, color, comp, filt, interlace) == (width, height, 8, 2, 0, 0, 0)
    raw = zlib.decompress(b"".join(body for kind, body, _ in chunks if kind == b"IDAT"))
    assert len(raw) == (1 + 3 * width) * height
    for y in range(height):
        row = raw[y * (1 + 3 * width):(y + 1) * (1 + 3 * width)]
        assert row[0] == 0                                   # bộ lọc "None"
        assert row[1:] == rgb[y * 3 * width:(y + 1) * 3 * width]


@pytest.mark.parametrize(("width", "height", "size"),
                         [(2, 2, 11), (2, 2, 13), (0, 2, 0), (2, 0, 0), (-1, 1, 3)])
def test_png_rejects_inconsistent_input(width, height, size):
    with pytest.raises(ValueError, match="PNG"):
        encode_png(width, height, bytes(size))


def test_png_one_pixel_is_the_smallest_valid_image():
    chunks = _chunks(encode_png(1, 1, b"\x00\x10\xff"))
    assert zlib.decompress(chunks[1][1]) == b"\x00\x00\x10\xff"
