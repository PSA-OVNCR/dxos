# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Lỗi theo RFC 9457 (trước đây RFC 7807): ``application/problem+json``.

Mọi lỗi HTTP của lõi đều trả cùng một dạng ``{type, title, status, detail?, ...}``,
với ``type`` là ``https://dxos.dev/problems/<slug>``.
"""

import logging
import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE = "https://dxos.dev/problems/"
PROBLEM_MEDIA_TYPE = "application/problem+json"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# `instance` (RFC 9457 §3.1.5) được phép truyền qua extensions; các trường còn lại do tham số quy định.
_CORE_MEMBERS = frozenset({"type", "title", "status", "detail"})

log = logging.getLogger("dxos_core.errors")

# Slug mặc định cho lỗi HTTP chung (không do mô-đun nghiệp vụ nền tảng sinh ra).
HTTP_SLUGS: Mapping[int, str] = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    405: "method-not-allowed",
    406: "not-acceptable",
    409: "conflict",
    412: "precondition-failed",
    413: "payload-too-large",
    415: "unsupported-media-type",
    422: "invalid-request",
    428: "precondition-required",
    429: "rate-limited",
    500: "internal",
    503: "unavailable",
}


def problem_type(type_: str) -> str:
    """Chuẩn hóa ``type_`` (slug hoặc URL đầy đủ) thành URL ``https://dxos.dev/problems/<slug>``."""
    slug = type_[len(PROBLEM_BASE):] if type_.startswith(PROBLEM_BASE) else type_
    if not _SLUG.fullmatch(slug):
        raise ValueError(f"type của problem phải là slug [a-z0-9-] hoặc {PROBLEM_BASE}<slug>: {type_!r}")
    return PROBLEM_BASE + slug


def problem(
    status: int,
    type_: str,
    title: str,
    detail: str | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    """Tạo phản hồi ``application/problem+json``. ``extensions`` là trường mở rộng (RFC 9457 §3.2)."""
    clash = _CORE_MEMBERS & extensions.keys()
    if clash:
        raise ValueError(f"trường mở rộng trùng trường chuẩn: {sorted(clash)}")
    body: dict[str, Any] = {"type": problem_type(type_), "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    body.update(extensions)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=dict(headers or {}))


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


async def _http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    title = _phrase(exc.status_code)
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != title else None
    return problem(exc.status_code, HTTP_SLUGS.get(exc.status_code, "http-error"), title, detail,
                   headers=exc.headers)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
              for e in exc.errors()]
    return problem(422, "invalid-request", "Request validation failed", errors=errors)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("lỗi không xử lý", exc_info=exc)
    return problem(500, "internal", "Internal Server Error")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
