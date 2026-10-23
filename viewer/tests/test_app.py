# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""API của Viewer với API Trust Core giả (httpx.MockTransport); Plan 04 Task 7, P4-D6."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from dxos_viewer import app as viewer_app
from dxos_viewer import render
from dxos_viewer.settings import Settings
from viewer_helpers import decode_png, make_pdf

SHA = "a" * 64
TOKEN = "Bearer eyJ.fake.token"
SUB = "0f1e2d3c-1111-4222-8333-444455556666"
NOW = datetime(2026, 12, 10, 9, 5, tzinfo=timezone(timedelta(hours=7)))
PROBLEM = "application/problem+json"


class FakeApi:
    """API Trust Core giả: ghi lại mọi yêu cầu; ``object_reply`` / ``whoami_reply`` quyết định phản hồi."""

    def __init__(self, pdf: bytes | None = None, *, object_status: int = 200, whoami_status: int = 200,
                 sub: str = SUB, raises: Exception | None = None, delay: float = 0.0,
                 headers: dict | None = None) -> None:
        self.pdf = make_pdf(pages=2) if pdf is None else pdf
        self.object_status, self.whoami_status, self.sub = object_status, whoami_status, sub
        self.raises, self.delay, self.headers = raises, delay, headers or {}
        self.calls: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises
        if request.url.path == "/api/v1/whoami":
            if self.whoami_status != 200:
                return httpx.Response(self.whoami_status, json={"title": "x"})
            return httpx.Response(200, json={"sub": self.sub, "roles": [], "is_admin": False})
        if request.url.path == f"/api/v1/objects/{SHA}":
            if self.object_status != 200:
                body = {"title": "Not Found", "status": self.object_status}
                return httpx.Response(self.object_status, json=body, headers={"content-type": PROBLEM})
            headers = {"content-type": "application/pdf", **self.headers}
            return httpx.Response(200, content=self.pdf, headers=headers)
        return httpx.Response(404, json={"title": "Not Found"})


def make_client(api: FakeApi, **overrides) -> httpx.AsyncClient:
    timeout_s = overrides.pop("timeout_s", 10.0)
    settings = Settings(api_base="http://apisix:9080", timeout_s=timeout_s, **overrides)
    app = viewer_app.create_app(settings, transport=httpx.MockTransport(api), clock=lambda: NOW)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://viewer")


def auth(token: str = TOKEN) -> dict:
    return {"Authorization": token}


async def test_healthz():
    async with make_client(FakeApi()) as client:
        reply = await client.get("/view/v1/healthz")
    assert reply.status_code == 200 and reply.json() == {"status": "ok"}


@pytest.mark.parametrize("path", [f"/view/v1/objects/{SHA}/info", f"/view/v1/objects/{SHA}/pages/1.png"])
@pytest.mark.parametrize("header", [None, {"Authorization": ""}, {"Authorization": "Basic dXNlcjpwYXNz"},
                                    {"Authorization": "Bearer "}])
async def test_no_token_401(path, header):
    api = FakeApi()
    async with make_client(api) as client:
        reply = await client.get(path, headers=header or {})
    assert reply.status_code == 401
    assert reply.headers["content-type"] == PROBLEM and reply.headers["www-authenticate"].startswith("Bearer")
    assert api.calls == []                                             # không gọi API


@pytest.mark.parametrize("path", [f"/view/v1/objects/{SHA}/info", f"/view/v1/objects/{SHA}/pages/1.png"])
@pytest.mark.parametrize("status", [404, 403, 400])
async def test_api_404_passthrough(path, status):
    api = FakeApi(object_status=status)
    async with make_client(api) as client:
        reply = await client.get(path, headers=auth())
    assert reply.status_code == 404
    assert reply.headers["content-type"] == PROBLEM
    assert reply.json()["type"] == "https://dxos.dev/problems/not-found"
    assert not reply.content.startswith(b"\x89PNG")
    assert [c.url.path for c in api.calls] == [f"/api/v1/objects/{SHA}"]    # không hỏi whoami khi chưa có tệp


async def test_api_401_is_401_and_api_5xx_is_502():
    async with make_client(FakeApi(object_status=401)) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
    assert reply.status_code == 401 and reply.headers["content-type"] == PROBLEM
    async with make_client(FakeApi(object_status=500)) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
    assert reply.status_code == 502 and reply.headers["content-type"] == PROBLEM


async def test_whoami_failure_never_yields_an_image():
    for status, expected in [(401, 401), (403, 502), (500, 502)]:
        async with make_client(FakeApi(whoami_status=status)) as client:
            reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
        assert reply.status_code == expected and reply.headers["content-type"] == PROBLEM


async def test_api_timeout_504():
    api = FakeApi(raises=httpx.ReadTimeout("slow"))
    async with make_client(api) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
    assert reply.status_code == 504 and reply.headers["content-type"] == PROBLEM
    assert reply.json()["type"] == "https://dxos.dev/problems/upstream-timeout"


async def test_api_total_timeout_504_even_if_each_phase_is_fast():
    api = FakeApi(delay=1.0)
    async with make_client(api, timeout_s=0.05) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert reply.status_code == 504


async def test_api_connection_error_502():
    async with make_client(FakeApi(raises=httpx.ConnectError("refused"))) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert reply.status_code == 502 and reply.headers["content-type"] == PROBLEM


@pytest.mark.parametrize("number", ["0", "3", "-1", "x", "1000000000000000000000"])
async def test_page_out_of_range_404(number):
    async with make_client(FakeApi()) as client:                      # tệp có 2 trang
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/{number}.png", headers=auth())
    assert reply.status_code == 404 and reply.headers["content-type"] == PROBLEM


async def test_token_forwarded_unchanged():
    api = FakeApi()
    async with make_client(api) as client:
        await client.get(f"/view/v1/objects/{SHA}/pages/2.png", headers={**auth(), "Cookie": "a=b",
                                                                         "X-Forwarded-For": "1.2.3.4"})
        await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert len(api.calls) == 3                                         # tệp + whoami, rồi tệp
    assert {c.headers["authorization"] for c in api.calls} == {TOKEN}
    assert all("cookie" not in c.headers and "x-forwarded-for" not in c.headers for c in api.calls)
    assert {c.url.path for c in api.calls} == {f"/api/v1/objects/{SHA}", "/api/v1/whoami"}


async def test_variant_is_passed_through_unchanged():
    api = FakeApi()
    async with make_client(api) as client:
        await client.get(f"/view/v1/objects/{SHA}/info?variant=redacted", headers=auth())
        await client.get(f"/view/v1/objects/{SHA}/info?variant=original", headers=auth())
        await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert [c.url.params.get("variant") for c in api.calls] == ["redacted", "original", None]


@pytest.mark.parametrize("variant", ["x", "redacted&variant=original", "", "../original", "REDACTED"])
async def test_unknown_variant_is_refused_before_any_call(variant):
    api = FakeApi()
    async with make_client(api) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", params={"variant": variant}, headers=auth())
    assert reply.status_code == 422 and reply.headers["content-type"] == PROBLEM
    assert api.calls == []


@pytest.mark.parametrize("sha", ["abc", "A" * 64, "a" * 63, "a" * 65, "..%2f..%2fwhoami", "a" * 63 + "g"])
async def test_bad_sha_is_404_before_any_call(sha):
    api = FakeApi()
    async with make_client(api) as client:
        reply = await client.get(f"/view/v1/objects/{sha}/info", headers=auth())
    assert reply.status_code == 404 and reply.headers["content-type"] == PROBLEM
    assert api.calls == []


async def test_info_returns_page_count():
    async with make_client(FakeApi(make_pdf(pages=5, size=(100, 100)))) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert reply.status_code == 200 and reply.json() == {"pages": 5}


async def test_page_png_headers_and_watermark_from_whoami_sub(monkeypatch):
    seen = {}
    real = render.render_page

    def spy(data, number, sub, now, **kw):
        seen.update(number=number, sub=sub, now=now)
        return real(data, number, sub, now, **kw)

    monkeypatch.setattr(viewer_app.render, "render_page", spy)
    async with make_client(FakeApi()) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/2.png", headers=auth())
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "image/png"
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert seen == {"number": 2, "sub": SUB, "now": NOW}
    width, height, _ = decode_png(reply.content)
    assert (width, height) == (935, 1210)


async def test_every_response_is_no_store_and_nosniff():
    async with make_client(FakeApi(object_status=404)) as client:
        replies = [await client.get("/view/v1/healthz"),
                   await client.get(f"/view/v1/objects/{SHA}/info", headers=auth()),
                   await client.get(f"/view/v1/objects/{SHA}/info"),
                   await client.get("/nope")]
    assert [r.status_code for r in replies] == [200, 404, 401, 404]
    for reply in replies:
        assert reply.headers["cache-control"] == "no-store"
        assert reply.headers["x-content-type-options"] == "nosniff"
    assert replies[3].headers["content-type"] == PROBLEM


async def test_not_a_pdf_is_415():
    async with make_client(FakeApi(b"\x89PNG\r\n\x1a\n not a pdf")) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
    assert reply.status_code == 415 and reply.headers["content-type"] == PROBLEM


async def test_corrupt_pdf_is_422_without_details():
    async with make_client(FakeApi(b"%PDF-1.7\nSECRET-garbage")) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())
    assert reply.status_code == 422 and reply.headers["content-type"] == PROBLEM
    assert b"SECRET" not in reply.content


async def test_too_many_pages_422():
    async with make_client(FakeApi(make_pdf(pages=201, size=(50, 50)))) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert reply.status_code == 422 and reply.json()["type"].endswith("/too-many-pages")


async def test_oversized_download_is_stopped():
    big = b"%PDF-1.7\n" + b"0" * 5000
    async with make_client(FakeApi(big), max_bytes=1000) as client:
        reply = await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())
    assert reply.status_code == 413 and reply.headers["content-type"] == PROBLEM


async def test_nothing_is_cached_between_requests():
    """Không giữ trạng thái: API đổi nội dung thì phản hồi theo ngay, và 404 sau 200 vẫn là 404."""
    api = FakeApi(make_pdf(pages=2, size=(100, 100)))
    async with make_client(api) as client:
        assert (await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())).json() == {"pages": 2}
        api.pdf = make_pdf(pages=4, size=(100, 100))
        assert (await client.get(f"/view/v1/objects/{SHA}/info", headers=auth())).json() == {"pages": 4}
        api.object_status = 404
        assert (await client.get(f"/view/v1/objects/{SHA}/pages/1.png", headers=auth())).status_code == 404


def test_settings_from_env(monkeypatch):
    monkeypatch.delenv("DXOS_VIEWER_API_BASE", raising=False)
    monkeypatch.delenv("DXOS_VIEWER_TIMEOUT_S", raising=False)
    default = Settings.from_env()
    assert (default.api_base, default.timeout_s) == ("http://apisix:9080", 10.0)
    monkeypatch.setenv("DXOS_VIEWER_API_BASE", "http://x:1/")
    monkeypatch.setenv("DXOS_VIEWER_TIMEOUT_S", "2.5")
    custom = Settings.from_env()
    assert (custom.api_base, custom.timeout_s) == ("http://x:1", 2.5)
    monkeypatch.setenv("DXOS_VIEWER_TIMEOUT_S", "0")
    with pytest.raises(ValueError, match="DXOS_VIEWER_TIMEOUT_S"):
        Settings.from_env()
