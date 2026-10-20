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
}


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _client(realm: dict, client_id: str) -> dict:
    return next(c for c in realm["clients"] if c["clientId"] == client_id)


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
    r = _load(PROD)
    assert not r.get("users")
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
