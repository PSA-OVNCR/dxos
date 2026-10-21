# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test client Admin API Keycloak của installer (HTTP giả lập bằng respx). Plan 02 Task 11.

Đường dẫn và mã trả về đã đối chiếu với Keycloak 26.3.0 thật: xem test ``infra`` trong
``tests/infra/test_keycloak_realm.py`` (``test_installer_token_can_create_role_live``...).
"""

import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from dxos_core.registry.keycloak_admin import IdpAdminUnavailable, KeycloakAdmin, keycloak_admin_from_settings

TOKEN = "http://keycloak.test:8080/auth/realms/dxos/protocol/openid-connect/token"
ADMIN = "http://keycloak.test:8080/auth/admin/realms/dxos"
SECRET = "changeme-installer-secret-xyz"
ACCESS = "eyJ.changeme-access-token.sig"


@pytest.fixture
def kc() -> KeycloakAdmin:
    """KeycloakAdmin trỏ vào TOKEN/ADMIN giả (respx chặn mọi request); secret là SECRET."""
    return KeycloakAdmin(TOKEN, ADMIN, "dxos-installer", SECRET)


def token_ok(expires_in: int = 60) -> httpx.Response:
    return httpx.Response(200, json={"access_token": ACCESS, "expires_in": expires_in,
                                     "token_type": "Bearer"})


# ---------------------------------------------------------------- ensure_app_roles

@respx.mock
async def test_ensure_roles_builds_names_and_ignores_existing(kc):
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 60}))
    created = respx.post(f"{ADMIN}/roles").mock(side_effect=[httpx.Response(201), httpx.Response(409)])
    assert await kc.ensure_app_roles("test-flow", ["reviewer", "approver"]) == ["app:test-flow:reviewer"]
    assert json.loads(created.calls[0].request.content) == {"name": "app:test-flow:reviewer"}


async def test_bad_role_name_never_hits_network(kc):
    with pytest.raises(ValueError):
        await kc.ensure_app_roles("test-flow", ["Bad:Role"])


@pytest.mark.parametrize(("app_id", "roles"), [
    ("test-flow", ["ok", "Bad"]),          # một tên sai -> không gọi mạng cho cả tên đúng
    ("test-flow", ["../x"]),
    ("test-flow", ["reviewer:x"]),
    ("test-flow", [""]),
    ("Test-Flow", ["reviewer"]),
    ("t", ["reviewer"]),                   # app id quá ngắn theo mẫu của lõi
    ("test-flow/../x", ["reviewer"]),
    ("test-flow", ["app:test-flow:reviewer"]),   # client tự dựng tiền tố, không nhận tên đầy đủ
])
@respx.mock(assert_all_called=False)
async def test_invalid_names_raise_before_any_request(kc, app_id, roles):
    token = respx.post(TOKEN).mock(return_value=token_ok())
    with pytest.raises(ValueError):
        await kc.ensure_app_roles(app_id, roles)
    assert token.call_count == 0 and len(respx.calls) == 0


@respx.mock
async def test_non_string_role_is_rejected(kc):
    with pytest.raises((ValueError, TypeError)):
        await kc.ensure_app_roles("test-flow", [1])   # type: ignore[list-item]
    assert len(respx.calls) == 0


@respx.mock
async def test_role_request_uses_bearer_token_and_dedupes(kc):
    token = respx.post(TOKEN).mock(return_value=token_ok())
    created = respx.post(f"{ADMIN}/roles").mock(return_value=httpx.Response(201))
    assert await kc.ensure_app_roles("test-flow", ["reviewer", "reviewer", "approver"]) == [
        "app:test-flow:reviewer", "app:test-flow:approver"]
    assert created.call_count == 2
    assert all(c.request.headers["Authorization"] == f"Bearer {ACCESS}" for c in created.calls)
    form = parse_qs(token.calls[0].request.content.decode())
    assert form == {"grant_type": ["client_credentials"], "client_id": ["dxos-installer"],
                    "client_secret": [SECRET]}


@respx.mock
async def test_empty_role_list_makes_no_request(kc):
    assert await kc.ensure_app_roles("test-flow", []) == []
    assert len(respx.calls) == 0


@respx.mock
async def test_token_is_cached_until_shortly_before_expiry(kc):
    token = respx.post(TOKEN).mock(return_value=token_ok(expires_in=300))
    respx.post(f"{ADMIN}/roles").mock(return_value=httpx.Response(409))
    await kc.ensure_app_roles("test-flow", ["a"])
    await kc.ensure_app_roles("test-flow", ["b"])
    assert token.call_count == 1


@respx.mock
async def test_token_close_to_expiry_is_refreshed(kc):
    token = respx.post(TOKEN).mock(return_value=token_ok(expires_in=5))   # dưới biên an toàn -> không cache
    respx.post(f"{ADMIN}/roles").mock(return_value=httpx.Response(409))
    await kc.ensure_app_roles("test-flow", ["a"])
    await kc.ensure_app_roles("test-flow", ["b"])
    assert token.call_count == 2


@respx.mock
async def test_401_on_admin_call_drops_cached_token(kc):
    token = respx.post(TOKEN).mock(return_value=token_ok(expires_in=300))
    respx.post(f"{ADMIN}/roles").mock(side_effect=[httpx.Response(401), httpx.Response(201)])
    with pytest.raises(IdpAdminUnavailable):
        await kc.ensure_app_roles("test-flow", ["a"])
    assert await kc.ensure_app_roles("test-flow", ["a"]) == ["app:test-flow:a"]
    assert token.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
@respx.mock
async def test_token_failure_is_unavailable_without_leaking_secret(kc, status, caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(TOKEN).mock(return_value=httpx.Response(status, json={"error": "x", "secret": SECRET}))
    with pytest.raises(IdpAdminUnavailable) as exc:
        await kc.ensure_app_roles("test-flow", ["reviewer"])
    assert SECRET not in str(exc.value) and SECRET not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 404, 500, 502])
@respx.mock
async def test_role_create_failure_is_unavailable_without_leaking_token(kc, status, caplog):
    caplog.set_level(logging.DEBUG)
    respx.post(TOKEN).mock(return_value=token_ok())
    respx.post(f"{ADMIN}/roles").mock(return_value=httpx.Response(status, text=f"echo {ACCESS}"))
    with pytest.raises(IdpAdminUnavailable) as exc:
        await kc.ensure_app_roles("test-flow", ["reviewer"])
    text = str(exc.value) + repr(exc.value) + caplog.text
    assert ACCESS not in text and SECRET not in text


@respx.mock
async def test_network_error_is_unavailable(kc):
    respx.post(TOKEN).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(IdpAdminUnavailable):
        await kc.ensure_app_roles("test-flow", ["reviewer"])


@pytest.mark.parametrize("body", [
    {"expires_in": 60},                              # thiếu access_token
    {"access_token": "", "expires_in": 60},
    {"access_token": "t", "expires_in": "soon"},
    ["not", "a", "dict"],
])
@respx.mock
async def test_malformed_token_response_is_unavailable(kc, body):
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(IdpAdminUnavailable):
        await kc.ensure_app_roles("test-flow", ["reviewer"])


def test_repr_hides_secret(kc):
    assert SECRET not in repr(kc) and SECRET not in str(kc)


def test_admin_url_must_not_carry_credentials():
    with pytest.raises(ValueError):
        KeycloakAdmin(TOKEN, "http://u:p@keycloak.test/auth/admin/realms/dxos", "dxos-installer", SECRET)


# ---------------------------------------------------------------- default_role_composites

@respx.mock
async def test_default_role_composites_lists_names(kc):
    respx.post(TOKEN).mock(return_value=token_ok())
    respx.get(ADMIN).mock(return_value=httpx.Response(200, json={
        "realm": "dxos",
        "defaultRole": {"id": "0f1e2d3c-aaaa-bbbb-cccc-1234567890ab", "name": "default-roles-dxos"}}))
    respx.get(f"{ADMIN}/roles-by-id/0f1e2d3c-aaaa-bbbb-cccc-1234567890ab/composites").mock(
        return_value=httpx.Response(200, json=[
            {"name": "offline_access", "clientRole": False},
            {"name": "uma_authorization", "clientRole": False},
            {"name": "view-profile", "clientRole": True}]))
    assert await kc.default_role_composites() == ["offline_access", "uma_authorization", "view-profile"]


@pytest.mark.parametrize("realm_json", [
    {"realm": "dxos"},                                          # không có defaultRole
    {"realm": "dxos", "defaultRole": {"id": "../users"}},       # id lạ không được vào đường dẫn
    {"realm": "dxos", "defaultRole": "x"},
])
@respx.mock
async def test_default_role_composites_rejects_unusable_realm(kc, realm_json):
    respx.post(TOKEN).mock(return_value=token_ok())
    respx.get(ADMIN).mock(return_value=httpx.Response(200, json=realm_json))
    with pytest.raises(IdpAdminUnavailable):
        await kc.default_role_composites()
    assert len(respx.calls) == 2   # token + realm, không gọi thêm


@respx.mock
async def test_default_role_composites_malformed_list_is_unavailable(kc):
    respx.post(TOKEN).mock(return_value=token_ok())
    respx.get(ADMIN).mock(return_value=httpx.Response(200, json={"defaultRole": {"id": "abc-123"}}))
    respx.get(f"{ADMIN}/roles-by-id/abc-123/composites").mock(return_value=httpx.Response(200, json={"x": 1}))
    with pytest.raises(IdpAdminUnavailable):
        await kc.default_role_composites()


# ---------------------------------------------------------------- Settings

def test_settings_defaults_for_installer(make_settings):
    s = make_settings()
    assert s.keycloak_token_url == "http://keycloak:8080/auth/realms/dxos/protocol/openid-connect/token"
    assert s.keycloak_admin_url == "http://keycloak:8080/auth/admin/realms/dxos"
    assert s.installer_client_id == "dxos-installer"
    assert s.installer_client_secret_file is None


def test_factory_returns_none_without_secret_file(make_settings):
    assert keycloak_admin_from_settings(make_settings()) is None


def test_factory_reads_secret_at_use_time(make_settings, tmp_path):
    f = tmp_path / "installer-client-secret"
    f.write_text(SECRET + "\n", encoding="utf-8")
    kc = keycloak_admin_from_settings(make_settings(installer_client_secret_file=f))
    assert isinstance(kc, KeycloakAdmin) and SECRET not in repr(kc)


@pytest.mark.parametrize("content", [None, ""])
def test_factory_unreadable_or_empty_secret_is_unavailable(make_settings, tmp_path, content):
    f = tmp_path / "installer-client-secret"
    if content is not None:
        f.write_text(content, encoding="utf-8")
    with pytest.raises(IdpAdminUnavailable) as exc:
        keycloak_admin_from_settings(make_settings(installer_client_secret_file=f))
    assert str(f) not in str(exc.value)


def test_source_keeps_one_client_until_secret_changes(make_settings, tmp_path):     # Plan 02 Task 12
    from dxos_core.registry.keycloak_admin import KeycloakAdminSource

    src = KeycloakAdminSource()
    assert src.get(make_settings()) is None                          # chưa đặt secret → duyệt app 503
    secret = tmp_path / "installer-secret"
    secret.write_text("s1\n", encoding="utf-8")
    settings = make_settings(installer_client_secret_file=secret)
    first = src.get(settings)
    assert isinstance(first, KeycloakAdmin) and src.get(settings) is first
    secret.write_text("s2\n", encoding="utf-8")
    assert src.get(settings) is not first
    secret.unlink()
    with pytest.raises(IdpAdminUnavailable):
        src.get(settings)
    fake = object()
    assert KeycloakAdminSource.fixed(fake).get(settings) is fake
