# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Realm Keycloak `dxos` (Plan 01 Task 5).

- Test tĩnh: kiểm tệp realm (không cần Keycloak chạy).
- Test sống (marker `infra`): lấy token thật từ Keycloak đang chạy.
  DXOS_KC_URL mặc định https://localhost/auth (qua Caddy).
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KC_DIR = ROOT / "deploy/keycloak"
PROD = KC_DIR / "realm-dxos.json"
DEV = KC_DIR / "realm-dxos-dev.json"

KC_URL = os.environ.get("DXOS_KC_URL", "https://localhost/auth")
DEV_PASSWORD = os.environ.get("DXOS_DEV_PASSWORD", "dev-only-password")

APP_ROLES = {
    "chuyen_vien1": "app:phong-ho-so:chuyen_vien",
    "truong_phong1": "app:phong-ho-so:truong_phong",
    "giam_doc1": "app:phong-ho-so:giam_doc",
    "van_thu1": "app:phong-ho-so:van_thu",
    "nhan_vien1": "app:phong-ho-so:nhan_vien",
    "can_bo_clb1": "app:chung-nhan:can_bo_clb",
    "truong_clb1": "app:chung-nhan:truong_clb",
    "owner_a1": "app:test-app:member",
    "owner_b1": "app:test-app:member",
    "admin1": "dxos-admin",
    "admin2": "dxos-admin",   # người duyệt thứ hai (bốn mắt, P2-D21)
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _client(realm: dict, client_id: str) -> dict:
    return next(c for c in realm["clients"] if c["clientId"] == client_id)


def realm() -> dict:
    """Realm production (deploy/keycloak/realm-dxos.json) đã parse; mỗi lần gọi đọc lại tệp."""
    return _load(PROD)


def client(client_id: str) -> dict:
    """Client ``client_id`` của realm production; StopIteration nếu không có."""
    return _client(realm(), client_id)


# ---------------- tĩnh ----------------

def test_production_realm_has_core_clients_role_and_scope():
    r = _load(PROD)
    assert r["realm"] == "dxos" and r["enabled"] is True
    assert {"dxos-admin"} == {x["name"] for x in r["roles"]["realm"]}  # lõi mù nghiệp vụ (I3)
    scope = next(s for s in r["clientScopes"] if s["name"] == "dxos-api-audience")
    mapper = scope["protocolMappers"][0]
    assert mapper["protocolMapper"] == "oidc-audience-mapper"
    assert mapper["config"]["included.custom.audience"] == "dxos-api"
    assert mapper["config"]["access.token.claim"] == "true"


def test_every_referenced_client_scope_is_defined():
    """Realm có khai báo clientScopes thì Keycloak KHÔNG tự tạo scope mặc định (đo 20/10/2026):
    mọi scope client tham chiếu phải được khai báo tường minh, nếu không token thiếu realm_access/sub."""
    for path in (PROD, DEV):
        r = _load(path)
        defined = {s["name"] for s in r["clientScopes"]}
        assert set(r["defaultDefaultClientScopes"]) <= defined, path.name
        for c in r["clients"]:
            missing = set(c.get("defaultClientScopes", [])) - defined
            assert not missing, (path.name, c["clientId"], missing)
        mappers = {m["protocolMapper"] for s in r["clientScopes"] for m in s.get("protocolMappers", [])}
        assert {"oidc-sub-mapper", "oidc-usermodel-realm-role-mapper"} <= mappers


def test_production_realm_has_no_users_no_test_client_no_literal_secret():
    """Realm production không có người dùng thật; ngoại lệ duy nhất là người dùng service account
    (có ``serviceAccountClientId``), và người dùng đó không có mật khẩu hay realm role
    (C10, Plan 02 Task 11)."""
    r = _load(PROD)
    for u in r.get("users", []):
        assert u.get("serviceAccountClientId"), u.get("username")
        assert not u.get("credentials") and not u.get("realmRoles"), u["username"]
    assert "dxos-test" not in {c["clientId"] for c in r["clients"]}
    for c in r["clients"]:
        if "secret" in c:
            assert c["secret"].startswith("${") and c["secret"].endswith("}"), c["clientId"]


def test_spa_is_public_pkce_s256_without_password_grant():
    spa = _client(_load(PROD), "dxos-spa")
    assert spa["publicClient"] is True
    assert spa["standardFlowEnabled"] is True
    assert spa["directAccessGrantsEnabled"] is False
    assert spa["implicitFlowEnabled"] is False
    assert spa["attributes"]["pkce.code.challenge.method"] == "S256"
    assert spa["redirectUris"] == ["https://${DXOS_DOMAIN}/apps/*"]
    assert "dxos-api-audience" in spa["defaultClientScopes"]


def test_installer_is_confidential_service_account_only():
    c = _client(_load(PROD), "dxos-installer")
    assert c["publicClient"] is False and c["serviceAccountsEnabled"] is True
    assert c["standardFlowEnabled"] is False and c["directAccessGrantsEnabled"] is False


def test_dev_realm_is_production_plus_dev_additions():
    prod, dev = _load(PROD), _load(DEV)
    spec = importlib.util.spec_from_file_location("bdr", ROOT / "ops/build_dev_realm.py")
    bdr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bdr)
    assert dev == bdr.build(prod, _load(KC_DIR / "dev-overlay.json")), \
        "realm-dxos-dev.json lệch: chạy `python ops/build_dev_realm.py`"
    users = {u["username"]: u for u in dev["users"]}
    for name, role in APP_ROLES.items():
        assert role in users[name]["realmRoles"], name
    assert _client(dev, "dxos-test")["directAccessGrantsEnabled"] is True


def test_installer_service_account_has_only_manage_realm():
    sa = next(u for u in realm()["users"] if u.get("serviceAccountClientId") == "dxos-installer")
    assert sa["clientRoles"] == {"realm-management": ["manage-realm"]} and not sa.get("realmRoles")
    assert sa["username"] == "service-account-dxos-installer" and sa["enabled"] is True
    assert not sa.get("credentials") and not sa.get("groups")


def test_cli_client_is_public_device_flow_only():
    c = client("dxos-cli")
    assert c["publicClient"] and not c["standardFlowEnabled"] and not c["directAccessGrantsEnabled"]
    assert c["attributes"]["oauth2.device.authorization.grant.enabled"] == "true"
    assert {"basic", "roles", "dxos-api-audience"} <= set(c["defaultClientScopes"])
    assert realm()["adminEventsEnabled"] is True


def test_cli_client_has_no_other_flow_and_realm_records_admin_event_details():
    c = client("dxos-cli")
    assert c["implicitFlowEnabled"] is False and c["serviceAccountsEnabled"] is False
    assert "secret" not in c and not c.get("redirectUris")
    assert c["attributes"].get("oauth2.device.authorization.grant.enabled") == "true"
    assert c["attributes"].get("oidc.ciba.grant.enabled", "false") == "false"
    assert realm()["adminEventsDetailsEnabled"] is True


def test_dev_realm_keeps_production_service_account_and_adds_admin2():
    dev = _load(DEV)
    users = {u["username"]: u for u in dev["users"]}
    assert users["service-account-dxos-installer"]["clientRoles"] == {"realm-management": ["manage-realm"]}
    assert users["admin2"]["realmRoles"] == ["dxos-admin"]
    assert _client(dev, "dxos-cli")["directAccessGrantsEnabled"] is False


# ---------------- sống ----------------

httpx = pytest.importorskip("httpx")
jwt = pytest.importorskip("jwt")


def _token_response(client_id: str, username: str):
    return httpx.post(
        f"{KC_URL}/realms/dxos/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": client_id,
              "username": username, "password": DEV_PASSWORD, "scope": "openid"},
        verify=False,  # noqa: S501 - CA nội bộ của Caddy
    )


def password_grant(client_id: str, username: str) -> str:
    r = _token_response(client_id, username)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def password_grant_status(client_id: str, username: str) -> int:
    return _token_response(client_id, username).status_code


@pytest.mark.infra
def test_token_has_dxos_api_audience_and_issuer():
    tok = password_grant("dxos-test", "chuyen_vien1")
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert "dxos-api" in (claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]])
    assert claims["iss"].endswith("/realms/dxos")
    assert "app:phong-ho-so:chuyen_vien" in claims["realm_access"]["roles"]


@pytest.mark.infra
def test_spa_client_disallows_password_grant():
    assert password_grant_status("dxos-spa", "chuyen_vien1") == 400  # unauthorized_client


@pytest.mark.infra
@pytest.mark.parametrize(("username", "role"), sorted(APP_ROLES.items()))
def test_every_dev_user_gets_its_role(username, role):
    claims = jwt.decode(password_grant("dxos-test", username), options={"verify_signature": False})
    assert role in claims["realm_access"]["roles"]


# ---------------- sống: service account installer, dxos-cli (Plan 02 Task 11) ----------------

# Mặc định gọi qua Caddy: token ở host công khai, Admin API chỉ mở trên host admin (Caddyfile).
KC_ADMIN_URL = os.environ.get("DXOS_KC_ADMIN_URL", "https://admin.localhost/auth")
INSTALLER_SECRET = os.environ.get("DXOS_INSTALLER_CLIENT_SECRET", "changeme-installer")
# CA nội bộ của Caddy: đặt DXOS_KC_CA=<đường dẫn root.crt> để kiểm chứng chỉ; mặc định không kiểm
# (như các test sống ở trên).
KC_VERIFY: bool | str = os.environ.get("DXOS_KC_CA") or False
TOKEN_URL = f"{KC_URL}/realms/dxos/protocol/openid-connect/token"
ADMIN_REALM_URL = f"{KC_ADMIN_URL}/admin/realms/dxos"


def installer_token() -> str:
    r = httpx.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": "dxos-installer",
                                    "client_secret": INSTALLER_SECRET}, verify=KC_VERIFY)
    assert r.status_code == 200, r.status_code
    return r.json()["access_token"]


class _LiveInstaller:
    """Điều khiển Keycloak thật bằng service account dxos-installer: tạo role qua KeycloakAdmin của lõi,
    rồi đọc lại danh sách realm role bằng token của chính service account đó."""

    def __init__(self) -> None:
        from dxos_core.registry.keycloak_admin import KeycloakAdmin

        self.admin = KeycloakAdmin(TOKEN_URL, ADMIN_REALM_URL, "dxos-installer", INSTALLER_SECRET,
                                   verify=KC_VERIFY)

    def create_and_list(self, app_id: str, roles: list[str]) -> list[str]:
        import asyncio

        asyncio.run(self.admin.ensure_app_roles(app_id, roles))
        r = httpx.get(f"{ADMIN_REALM_URL}/roles", params={"max": 1000},
                      headers={"Authorization": f"Bearer {installer_token()}"}, verify=KC_VERIFY)
        assert r.status_code == 200, r.status_code
        return [x["name"] for x in r.json()]

    def default_role_composites(self) -> list[str]:
        import asyncio

        return asyncio.run(self.admin.default_role_composites())


@pytest.fixture
def kc_live() -> _LiveInstaller:
    """Installer thật trên Keycloak đang chạy (DXOS_KC_URL, DXOS_KC_ADMIN_URL, DXOS_INSTALLER_CLIENT_SECRET);
    chỉ chạy với marker ``infra``."""
    return _LiveInstaller()


@pytest.mark.infra
def test_installer_token_can_create_role_live(kc_live):    # Keycloak 26.3.0 thật (như Plan 01 Task 5)
    assert "app:test-flow:reviewer" in kc_live.create_and_list("test-flow", ["reviewer"])
    # Lần hai: role đã có (409) không phải lỗi, danh sách không đổi.
    assert "app:test-flow:reviewer" in kc_live.create_and_list("test-flow", ["reviewer"])


@pytest.mark.infra
def test_installer_token_carries_only_manage_realm_live():
    claims = jwt.decode(installer_token(), options={"verify_signature": False})
    assert claims["resource_access"] == {"realm-management": {"roles": ["manage-realm"]}}
    realm_roles = set((claims.get("realm_access") or {}).get("roles", []))
    assert "dxos-admin" not in realm_roles and not {r for r in realm_roles if r.startswith("app:")}


@pytest.mark.infra
def test_installer_cannot_read_users_live():
    """manage-realm không gồm view-users: service account không đọc được danh sách người dùng."""
    r = httpx.get(f"{ADMIN_REALM_URL}/users", headers={"Authorization": f"Bearer {installer_token()}"},
                  verify=KC_VERIFY)
    assert r.status_code == 403


@pytest.mark.infra
def test_realm_admin_events_enabled_and_default_roles_clean_live(kc_live):
    r = httpx.get(ADMIN_REALM_URL, headers={"Authorization": f"Bearer {installer_token()}"}, verify=KC_VERIFY)
    assert r.status_code == 200
    assert r.json()["adminEventsEnabled"] is True and r.json()["adminEventsDetailsEnabled"] is True
    composites = kc_live.default_role_composites()
    assert "offline_access" in composites
    assert "dxos-admin" not in composites and not [x for x in composites if x.startswith("app:")]


@pytest.mark.infra
def test_cli_client_allows_device_flow_only_live():
    dev = httpx.post(f"{KC_URL}/realms/dxos/protocol/openid-connect/auth/device",
                     data={"client_id": "dxos-cli", "scope": "openid"}, verify=KC_VERIFY)
    assert dev.status_code == 200, dev.text
    assert dev.json()["device_code"] and dev.json()["verification_uri"]
    assert password_grant_status("dxos-cli", "chuyen_vien1") == 400   # unauthorized_client
    code = httpx.get(f"{KC_URL}/realms/dxos/protocol/openid-connect/auth",
                     params={"client_id": "dxos-cli", "response_type": "code", "scope": "openid",
                             "redirect_uri": "http://127.0.0.1/cb"}, verify=KC_VERIFY)
    assert code.status_code == 400   # client không bật standard flow
