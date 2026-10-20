# SPDX-FileCopyrightText: 2026 DX-OS Trust Core contributors
# SPDX-License-Identifier: Apache-2.0
"""JSON chuẩn hóa (canonical JSON) cho dữ liệu cần băm và ký.

Quy tắc (spec 11.1): UTF-8, khóa sắp xếp, không khoảng trắng, cấm số thực,
thời gian là chuỗi RFC 3339 UTC. Bổ sung: mọi chuỗi (khóa và giá trị) được
chuẩn hóa Unicode NFC để chữ tiếng Việt gõ ở dạng NFD hay NFC cho cùng kết quả.

Thứ tự khóa theo code point của Python; có thể khác JCS (RFC 8785) với ký tự
ngoài BMP. Dự án không dùng ký tự ngoài BMP làm khóa.
"""

import hashlib
import json
import unicodedata
from datetime import UTC, datetime


class CanonicalError(ValueError):
    """Giá trị không biểu diễn được ở dạng JSON chuẩn hóa."""


def _normalize(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"khóa phải là chuỗi, nhận {type(key).__name__}")
            out[unicodedata.normalize("NFC", key)] = _normalize(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise CanonicalError(f"kiểu không được phép: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    """Trả về biểu diễn JSON chuẩn hóa dạng UTF-8 của ``value``."""
    return json.dumps(
        _normalize(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")


def rfc3339_utc(dt: datetime) -> str:
    """Chuyển thời điểm có múi giờ sang chuỗi RFC 3339 UTC, ví dụ ``2026-10-20T00:30:00Z``."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise CanonicalError("datetime phải có múi giờ")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(data: bytes) -> str:
    """SHA-256 dạng hex thường."""
    return hashlib.sha256(data).hexdigest()
