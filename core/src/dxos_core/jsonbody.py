# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đọc thân request JSON dùng chung (rà soát cuối Plan 02, m2).

``json.loads`` nhận cả những thứ lõi không xử lý được về sau: surrogate lẻ (``"\\ud800"``, không mã hóa UTF-8
được nên vỡ ở asyncpg hoặc ở băm chuẩn hóa → 500), U+0000 (``"\\u0000"``: PostgreSQL ``jsonb`` không biểu diễn
được nên INSERT vỡ → 500; review cuối Plan 03, I3) và cấu trúc lồng rất sâu (``RecursionError`` ngay khi đọc,
hoặc ở các hàm đệ quy sau đó). ``parse_json`` từ chối các trường hợp đó bằng ``JsonBodyError`` để route trả
422 thay vì 500; JSON hỏng thì ``malformed=True`` (route giữ mã lỗi cũ của mình cho trường hợp này).
"""

import json
from typing import Any

# Độ sâu lồng tối đa của object/mảng trong thân request. Manifest và dữ liệu bản ghi thật chỉ sâu vài mức.
MAX_JSON_DEPTH = 64
_TOO_DEEP = f"body is nested too deeply (max {MAX_JSON_DEPTH} levels)"
_SURROGATE = "body contains a lone surrogate (not encodable as UTF-8)"
_NUL = "body contains U+0000 (not representable in PostgreSQL jsonb)"


class JsonBodyError(ValueError):
    """Thân request không dùng được. ``malformed``: không phải JSON; ngược lại JSON đúng nhưng bị từ chối."""

    def __init__(self, detail: str, *, malformed: bool) -> None:
        super().__init__(detail)
        self.detail, self.malformed = detail, malformed


def check_json_value(value: Any) -> None:
    """Giá trị đã đọc: lồng không quá ``MAX_JSON_DEPTH`` mức, không có U+0000 (khóa lẫn giá trị) và mã hóa
    UTF-8 được (không surrogate lẻ)."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:                                   # không đệ quy: chính bước kiểm không được RecursionError
        v, depth = stack.pop()
        if isinstance(v, str):
            if "\x00" in v:
                raise JsonBodyError(_NUL, malformed=False)
        elif isinstance(v, dict | list):
            if depth > MAX_JSON_DEPTH:
                raise JsonBodyError(_TOO_DEEP, malformed=False)
            if isinstance(v, dict):
                stack.extend((k, depth) for k in v)                  # khóa: chỉ kiểm U+0000
                stack.extend((c, depth + 1) for c in v.values())
            else:
                stack.extend((c, depth + 1) for c in v)
    try:
        json.dumps(value, ensure_ascii=False).encode("utf-8")        # khóa và giá trị
    except UnicodeEncodeError:
        raise JsonBodyError(_SURROGATE, malformed=False) from None


def parse_json(raw: bytes | str) -> Any:
    """``json.loads`` + ``check_json_value``; mọi lỗi thành ``JsonBodyError``."""
    try:
        value = json.loads(raw)
    except RecursionError:
        raise JsonBodyError(_TOO_DEEP, malformed=False) from None
    except ValueError:                             # gồm UnicodeDecodeError, JSONDecodeError
        raise JsonBodyError("body must be JSON", malformed=True) from None
    check_json_value(value)
    return value
