# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tra sống trên stack đang chạy (marker `infra`, cần `make up`).

AT-01 bản đầu (phân vùng mạng) và AT-02 phía gateway (API đòi token).
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "deploy/network-matrix.yaml"
BASE = os.environ.get("DXOS_BASE_URL", "https://localhost")

_spec = importlib.util.spec_from_file_location("netcheck", ROOT / "ops/netcheck.py")
netcheck = importlib.util.module_from_spec(_spec)
sys.modules["netcheck"] = netcheck
_spec.loader.exec_module(netcheck)

pytestmark = pytest.mark.infra


def test_probes_match_matrix():  # AT-01 bản đầu
    bad = [r for r in netcheck.run_probes(MATRIX, "dxos") if r.expect != r.actual]
    assert bad == []


def test_api_requires_token():  # AT-02 (phía gateway)
    r = httpx.get(f"{BASE}/api/v1/healthz", verify=False)  # noqa: S501 - CA nội bộ của Caddy
    assert r.status_code == 401


def test_verify_is_anonymous_but_rate_limited_route_exists():
    r = httpx.get(f"{BASE}/verify/v1/healthz", verify=False)  # noqa: S501
    assert r.status_code not in (401, 502, 503)


def test_keycloak_admin_console_not_on_public_host():
    r = httpx.get(f"{BASE}/auth/admin/", verify=False, follow_redirects=False)  # noqa: S501
    assert r.status_code == 404


def test_keycloak_urls_keep_auth_prefix():
    r = httpx.get(f"{BASE}/auth/realms/master/.well-known/openid-configuration", verify=False)  # noqa: S501
    cfg = r.json()
    assert cfg["issuer"] == f"{BASE}/auth/realms/master"
    assert cfg["token_endpoint"].startswith(f"{BASE}/auth/realms/master/")
