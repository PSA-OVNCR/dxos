# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture dùng chung cho test của trust-core."""

from pathlib import Path

import pytest
import respx
from dxos_core.app import create_app
from dxos_core.settings import Settings
from fastapi.testclient import TestClient
from helpers.tokens import JWKS_URL, jwks

CORE_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS = CORE_DIR / "migrations"

# Cổng 1 trên loopback: không có dịch vụ nào, kết nối bị từ chối ngay.
UNREACHABLE_DSN = "postgresql://dxos_core:changeme@127.0.0.1:1/dxos"


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    path = tmp_path / "secret"
    path.write_text("changeme-test-secret\n", encoding="utf-8")
    return path


@pytest.fixture
def make_settings(tmp_path: Path, secret_file: Path):
    def _make(**overrides) -> Settings:
        values = {
            "database_url": UNREACHABLE_DSN,
            "s3_endpoint": "http://seaweedfs.invalid:8333",
            "s3_access_key_file": secret_file,
            "s3_secret_key_file": secret_file,
            "openbao_token_file": secret_file,
            "keycloak_issuer": "https://localhost/auth/realms/dxos",
            "keycloak_jwks_url": "http://keycloak.invalid/auth/realms/dxos/protocol/openid-connect/certs",
            "actor_hmac_key_file": secret_file,
            "anchor_repo_dir": tmp_path / "anchor-repo",
        }
        values.update(overrides)
        return Settings(**values)

    return _make


@pytest.fixture
def settings(make_settings) -> Settings:
    return make_settings()


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def test_jwks():
    """Giả lập JWKS của Keycloak; các request httpx khác (OpenBao...) đi thẳng."""
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as m:
        route = m.get(JWKS_URL).respond(json=jwks())
        m.route().pass_through()
        yield route


@pytest.fixture
async def fake_clamd():
    """clamd giả (deploy/fake-av) chạy trong tiến trình test; trả (host, port)."""
    from helpers.files import load_fake_av

    server = await load_fake_av().serve("127.0.0.1", 0)
    try:
        yield "127.0.0.1", server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


def pytest_addoption(parser):
    parser.addoption("--real-clamav", action="store_true", default=False,
                     help="chạy test kiểm dịch với ClamAV thật ở DXOS_TEST_CLAMD (host:port)")
