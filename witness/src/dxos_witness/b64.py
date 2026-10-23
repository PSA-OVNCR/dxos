# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Giải mã base64 **chuẩn tắc** cho mọi trường base64 của gói bằng chứng (ruling R29, Plan 04 Task 14).

Chỉ nhận base64 chuẩn tắc theo RFC 4648 mục 4: bảng chữ chuẩn ``A-Za-z0-9+/``, độ dài chia hết
cho 4, ``=`` chỉ là phần đệm ở cuối (0 đến 2 dấu, đúng số byte còn thiếu), không khoảng trắng
hay xuống dòng. Mọi dạng khác (thừa ``=`` sau nhóm đủ, thiếu đệm, ký tự lạ, không phải ``str``)
bị từ chối tường minh **trước khi giải mã**, nên kết quả không còn phụ thuộc phiên bản CPython
(bản vá CVE-2026-3446 đổi cách ``b64decode(validate=True)`` xử lý thừa ``=``).

Bộ kiểm JS (``sdk/js/src/proof/hash.ts``) áp dụng cùng quy tắc và chạy chung vector
``b64/validate.json``. Trường base64 không chuẩn tắc trong gói là ``MALFORMED`` (hoặc khóa,
chữ ký không hợp lệ). Bit thừa ở cuối nhóm cuối không bị bắt buộc bằng 0.
"""

import base64
import re

_CANONICAL = re.compile(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")


def b64decode_canonical(value: object) -> bytes:
    """Giải mã base64 chuẩn tắc; sai dạng → ``ValueError`` (dạng không chuẩn tắc không bao giờ có kết quả)."""
    if not isinstance(value, str) or _CANONICAL.fullmatch(value) is None:
        raise ValueError("không phải base64 chuẩn tắc (RFC 4648 mục 4)")
    return base64.b64decode(value)
