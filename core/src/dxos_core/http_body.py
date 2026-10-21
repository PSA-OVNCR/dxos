# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đọc thân request với trần cứng, dùng chung cho cổng đối soát (``seal/verify_router.py``) và API quản trị
(``admin/apps.py``).

Thứ tự: Content-Type (415), ``Content-Length`` khai báo vượt trần (413, không đọc gì) hoặc sai dạng (400), rồi
đọc theo luồng và trả 413 **ngay** khi vượt trần (không đọc thêm; đúng cả với thân chunked không có
Content-Length).
"""

from fastapi import Request

from dxos_core.errors import ProblemError


async def read_capped_body(request: Request, limit: int, *, content_type: str = "application/json",
                           unsupported_detail: str | None = None) -> bytes:
    """Bytes của thân request (tối đa ``limit`` byte) nếu media type đúng ``content_type``."""
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media != content_type:
        raise ProblemError(415, "unsupported-media-type", "Unsupported Media Type",
                           unsupported_detail or f"only {content_type}")
    too_large = ProblemError(413, "payload-too-large", "Payload Too Large", f"body limit is {limit} bytes")
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise too_large
        except ValueError as exc:
            raise ProblemError(400, "bad-request", "Bad Request", "invalid Content-Length") from exc
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise too_large
    return bytes(buf)
