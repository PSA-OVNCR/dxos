# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test identity: kiểm JWT RS256 qua JWKS, vai trò theo app, 401 problem+json (Plan 01 Task 10)."""

import time

import httpx
import pytest
from dxos_core.identity.jwt import AuthError, IdpUnavailable, JwksVerifier, Principal, app_roles
from helpers.tokens import AUDIENCE, ISSUER, JWKS_URL, bearer, make_token


@pytest.fixture
def verifier(test_jwks):
    return JwksVerifier(JWKS_URL, ISSUER, AUDIENCE)


# ---------- Các test do Plan 01 Task 10 quy định ----------

async def test_valid_token(verifier):
    p = await verifier.verify(make_token("u1", ["app:phong-ho-so:giam_doc", "dxos-admin"]))
    assert p.sub == "u1" and p.is_admin and "app:phong-ho-so:giam_doc" in p.roles


@pytest.mark.parametrize("override", [{"aud": "other"}, {"iss": "https://evil/realms/dxos"},
                                      {"exp": 1}, {"alg": "HS256"}, {"alg": "none"}])
async def test_rejected_tokens(verifier, override):
    with pytest.raises(AuthError):
        await verifier.verify(make_token("u1", [], **override))


def test_app_roles_only_for_that_app():                                         # RF3 (phần 1)
    roles = {"app:phong-ho-so:giam_doc", "app:chung-nhan:truong_clb", "offline_access"}
    p = Principal("u", frozenset(roles), False)
    assert app_roles(p, "phong-ho-so") == {"giam_doc"}
    assert app_roles(p, "chung-nhan") == {"truong_clb"}
    assert app_roles(p, "test-app") == frozenset()


def test_endpoint_without_token_is_401(client):
    r = client.get("/api/v1/whoami")
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")


# ---------- Bổ sung ----------

@pytest.mark.parametrize("override", [
    {"nbf": int(time.time()) + 3600},       # chưa tới hiệu lực
    {"wrong_key": True},                    # chữ ký bằng khóa khác cùng kid
    {"kid": "khong-co"},                    # kid lạ
    {"sub": None},                          # thiếu sub
    {"exp": None},                          # thiếu exp
    {"aud": ["account"]},                   # aud không chứa dxos-api
])
async def test_more_rejected_tokens(verifier, override):
    with pytest.raises(AuthError):
        await verifier.verify(make_token("u1", [], **override))


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
async def test_garbage_rejected(verifier, garbage):
    with pytest.raises(AuthError):
        await verifier.verify(garbage)


async def test_audience_list_containing_dxos_api_accepted(verifier):
    p = await verifier.verify(make_token("u1", ["app:test-app:member"], aud=["account", "dxos-api"]))
    assert app_roles(p, "test-app") == {"member"} and not p.is_admin


async def test_non_admin_and_bad_roles_claim(verifier):
    p = await verifier.verify(make_token("u1", [], realm_access={"roles": "dxos-admin"}))
    assert p.roles == frozenset() and not p.is_admin


async def test_jwks_cached(verifier, test_jwks):
    await verifier.verify(make_token("u1", []))
    await verifier.verify(make_token("u2", []))
    assert test_jwks.calls.call_count == 1


async def test_unknown_kid_refetches_once_then_rejects(verifier, test_jwks):
    await verifier.verify(make_token("u1", []))
    with pytest.raises(AuthError):
        await verifier.verify(make_token("u1", [], kid="rotated"))
    with pytest.raises(AuthError):
        await verifier.verify(make_token("u1", [], kid="rotated"))
    assert test_jwks.calls.call_count == 2  # tải lại tối đa một lần trong khoảng chống dội


async def test_idp_down_is_distinct_error(respx_mock):
    respx_mock.get(JWKS_URL).mock(side_effect=httpx.ConnectError("down"))
    v = JwksVerifier(JWKS_URL, ISSUER, AUDIENCE)
    with pytest.raises(IdpUnavailable):
        await v.verify(make_token("u1", []))


def test_app_roles_ignores_malformed():
    roles = {"app:test-app", "app::x", "app:test-app:", "app:test-app:a:b", "app:test-app:ok"}
    p = Principal("u", frozenset(roles), False)
    assert app_roles(p, "test-app") == {"ok"}


def test_whoami_with_valid_token(client, test_jwks):
    r = client.get("/api/v1/whoami", headers=bearer(make_token("u9", ["app:test-app:member", "dxos-admin"])))
    assert r.status_code == 200
    assert r.json() == {"sub": "u9", "roles": ["app:test-app:member", "dxos-admin"], "is_admin": True}


def test_bad_token_401_problem_with_www_authenticate(client, test_jwks):
    r = client.get("/api/v1/whoami", headers=bearer(make_token("u1", [], aud="other")))
    assert r.status_code == 401
    assert r.json()["type"] == "https://dxos.dev/problems/unauthenticated"
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_non_bearer_scheme_401(client):
    r = client.get("/api/v1/whoami", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_idp_down_is_503(client, respx_mock):
    respx_mock.get(JWKS_URL).mock(side_effect=httpx.ConnectError("down"))
    r = client.get("/api/v1/whoami", headers=bearer(make_token("u1", [])))
    assert r.status_code == 503 and r.json()["type"].endswith("/idp-unavailable")
