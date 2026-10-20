# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture E2E: gọi stack thật qua Caddy → APISIX → trust-core, token thật từ Keycloak (client dxos-test).

Biến môi trường:
- ``DXOS_E2E_BASE`` (mặc định ``https://localhost``) và ``DXOS_E2E_ADMIN_BASE`` (``https://admin.localhost``).
- ``SSL_CERT_FILE``: CA nội bộ của Caddy (ops/e2e/run_e2e.sh tự lấy).
- ``DXOS_E2E_ANCHOR_REMOTE``: repo neo để witness clone (mặc định bare repo trong volume của worker).
Chạy: ``ops/e2e/run_e2e.sh`` (trong container) hoặc ``pytest -m e2e tests/e2e`` khi tự chuẩn bị môi trường.
"""

import os

import httpx
import pytest

BASE = os.environ.get("DXOS_E2E_BASE", "https://localhost")
ADMIN_BASE = os.environ.get("DXOS_E2E_ADMIN_BASE", "https://admin.localhost")
PASSWORD = os.environ.get("DXOS_E2E_PASSWORD", "dev-only-password")


@pytest.fixture(scope="session")
def base() -> str:
    return BASE


@pytest.fixture(scope="session")
def admin_base() -> str:
    return ADMIN_BASE


@pytest.fixture(scope="session")
def kc_token():
    cache: dict[str, str] = {}

    def get(user: str) -> str:
        if user not in cache:
            r = httpx.post(f"{BASE}/auth/realms/dxos/protocol/openid-connect/token", timeout=20, data={
                "grant_type": "password", "client_id": "dxos-test", "username": user, "password": PASSWORD,
                "scope": "openid"})
            r.raise_for_status()
            cache[user] = r.json()["access_token"]
        return cache[user]
    return get
