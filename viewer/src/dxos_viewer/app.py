# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Viewer (Plan 04 Task 7; S2; P4-D6): dịch vụ không trạng thái, chỉ RAM, vẽ từng trang PDF thành PNG.

Đặt sau APISIX (tiền tố ``/view``). Viewer không có khóa, không chạm kho lưu trữ, Flowable hay OpenBao: nó
lấy tệp qua APISIX bằng **chính token của người gọi** (``Authorization`` chuyển nguyên văn, không thêm gì
khác), nên mọi quyền (kể cả chặn bản gốc khi tệp có PII, ``reveal_pii``) do API quyết định. Danh tính
watermark lấy từ ``GET /api/v1/whoami`` (``sub``). API không trả 200 thì Viewer không trả ảnh nào.

    GET /view/v1/healthz
    GET /view/v1/objects/{sha256}/info?variant=original|redacted        -> {"pages": n}
    GET /view/v1/objects/{sha256}/pages/{n}.png?variant=original|redacted   -> image/png (n từ 1)

Mọi phản hồi có ``Cache-Control: no-store`` và ``X-Content-Type-Options: nosniff``. Lỗi theo RFC 9457
(``application/problem+json``, ``type`` = ``https://dxos.dev/problems/<slug>``). Watermark chỉ để răn đe.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from dxos_viewer import render
from dxos_viewer.settings import Settings

PROBLEM_BASE = "https://dxos.dev/problems/"
PROBLEM_MEDIA_TYPE = "application/problem+json"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PAGE = re.compile(r"[0-9]{1,9}")
_VARIANTS = frozenset({"original", "redacted"})
MAX_CONCURRENT_RENDERS = 2          # mỗi lần dựng tốn vài lần một bitmap (xem render.py): giữ RAM có trần
_WWW_AUTH = {"WWW-Authenticate": "Bearer"}


class ProblemError(Exception):
    def __init__(self, status: int, slug: str, title: str, detail: str | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(f"{status} {slug}")
        self.status, self.slug, self.title, self.detail, self.headers = status, slug, title, detail, headers


def _problem(status: int, slug: str, title: str, detail: str | None = None,
             headers: dict[str, str] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"type": PROBLEM_BASE + slug, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def _authorization(request: Request) -> str:
    """``Authorization`` nguyên văn; thiếu hoặc không phải ``Bearer <token>`` thì 401 (chưa gọi API)."""
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ProblemError(401, "unauthorized", "Unauthorized", "bearer token required", _WWW_AUTH)
    return value


def _check_sha(sha256: str) -> None:
    if not _SHA256.fullmatch(sha256):
        raise ProblemError(404, "not-found", "Not Found")


def _variant(request: Request) -> dict[str, str]:
    """Tham số ``variant`` chuyển nguyên văn cho API (chỉ nhận ``original`` / ``redacted``)."""
    values = request.query_params.getlist("variant")
    if not values:
        return {}
    if len(values) != 1 or values[0] not in _VARIANTS:
        raise ProblemError(422, "invalid-request", "Invalid Request", "variant must be original or redacted")
    return {"variant": values[0]}


class _Upstream:
    """Gọi API Trust Core qua APISIX bằng token của người gọi; tổng thời gian mỗi lần gọi bị chặn."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client, self.settings = client, settings

    async def _call(self, path: str, authorization: str, params: dict[str, str], limit: int | None
                    ) -> tuple[int, bytes]:
        async def run() -> tuple[int, bytes]:
            async with self.client.stream("GET", path, params=params,
                                          headers={"Authorization": authorization}) as reply:
                if reply.status_code != 200:
                    return reply.status_code, b""
                declared = reply.headers.get("content-length", "")
                if limit is not None and declared.isdigit() and int(declared) > limit:
                    raise ProblemError(413, "file-too-large", "File Too Large")
                body = bytearray()
                async for chunk in reply.aiter_bytes():
                    body += chunk
                    if limit is not None and len(body) > limit:
                        raise ProblemError(413, "file-too-large", "File Too Large")
                return 200, bytes(body)

        try:
            async with asyncio.timeout(self.settings.timeout_s):
                return await run()
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProblemError(504, "upstream-timeout", "Upstream Timeout") from exc
        except httpx.HTTPError as exc:
            raise ProblemError(502, "upstream-error", "Bad Gateway") from exc

    async def fetch_pdf(self, sha256: str, authorization: str, params: dict[str, str]) -> bytes:
        status, body = await self._call(f"/api/v1/objects/{sha256}", authorization, params,
                                        self.settings.max_bytes)
        if status == 401:
            raise ProblemError(401, "unauthorized", "Unauthorized", "token rejected", _WWW_AUTH)
        if status >= 500:
            raise ProblemError(502, "upstream-error", "Bad Gateway")
        if status != 200:
            raise ProblemError(404, "not-found", "Not Found")          # 404, 403, ...: không lộ lý do
        if not body.startswith(b"%PDF-"):
            raise ProblemError(415, "unsupported-media-type", "Unsupported Media Type",
                               "only PDF can be viewed")
        return body

    async def whoami_sub(self, authorization: str) -> str:
        status, body = await self._call("/api/v1/whoami", authorization, {}, 64 * 1024)
        if status == 401:
            raise ProblemError(401, "unauthorized", "Unauthorized", "token rejected", _WWW_AUTH)
        sub = None
        if status == 200:
            try:
                sub = httpx.Response(200, content=body).json().get("sub")
            except (ValueError, AttributeError):
                sub = None
        if not isinstance(sub, str) or not sub:
            raise ProblemError(502, "upstream-error", "Bad Gateway", "identity unavailable")
        return sub


def _render_error(exc: render.RenderError) -> ProblemError:
    if isinstance(exc, render.PageOutOfRange):
        return ProblemError(404, "not-found", "Not Found", "page out of range")
    if isinstance(exc, render.TooManyPages):
        return ProblemError(422, "too-many-pages", "Too Many Pages", f"at most {render.MAX_PAGES} pages")
    return ProblemError(422, "unreadable-document", "Unreadable Document")      # không kèm chi tiết của tệp


def create_app(settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
               clock: Callable[[], datetime] | None = None) -> FastAPI:
    """``transport`` và ``clock`` để test thay API và giờ. Chạy thật:
    ``uvicorn dxos_viewer.app:create_app --factory``."""
    settings = settings or Settings.from_env()
    now = clock or (lambda: datetime.now(UTC))
    client = httpx.AsyncClient(base_url=settings.api_base, transport=transport, follow_redirects=False,
                               timeout=settings.timeout_s)
    upstream = _Upstream(client, settings)
    gate = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="DX-OS Viewer", version="0.9.0", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)

    @app.middleware("http")
    async def no_store(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ProblemError)
    async def _on_problem(_: Request, exc: ProblemError) -> JSONResponse:
        return _problem(exc.status, exc.slug, exc.title, exc.detail, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _on_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(exc.status_code, "not-found" if exc.status_code == 404 else "http-error",
                        "Not Found" if exc.status_code == 404 else "Error")

    @app.exception_handler(RequestValidationError)
    async def _on_invalid(_: Request, __: RequestValidationError) -> JSONResponse:
        return _problem(422, "invalid-request", "Invalid Request")

    @app.get("/view/v1/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/view/v1/objects/{sha256}/info")
    async def info(sha256: str, request: Request) -> dict[str, int]:
        authorization = _authorization(request)
        _check_sha(sha256)
        params = _variant(request)
        async with gate:
            data = await upstream.fetch_pdf(sha256, authorization, params)
            try:
                pages = await asyncio.to_thread(render.page_count, data)
            except render.RenderError as exc:
                raise _render_error(exc) from exc
        return {"pages": pages}

    @app.get("/view/v1/objects/{sha256}/pages/{page}.png")
    async def page_png(sha256: str, page: str, request: Request) -> Response:
        authorization = _authorization(request)
        _check_sha(sha256)
        params = _variant(request)
        if not _PAGE.fullmatch(page) or int(page) < 1:
            raise ProblemError(404, "not-found", "Not Found", "page out of range")
        async with gate:
            data = await upstream.fetch_pdf(sha256, authorization, params)
            sub = await upstream.whoami_sub(authorization)
            try:
                png = await asyncio.to_thread(render.render_page, data, int(page), sub, now())
            except render.RenderError as exc:
                raise _render_error(exc) from exc
        return Response(png, media_type="image/png")

    return app
