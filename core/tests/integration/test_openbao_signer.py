# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration với OpenBao thật (chế độ dev của deploy/compose.test.yaml): ký, khóa công khai, policy."""

import os
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_core.kms.base import KmsUnavailable
from dxos_core.kms.openbao import OpenBaoTransit

pytestmark = pytest.mark.integration

ADDR = os.environ.get("DXOS_TEST_OPENBAO_ADDR", "http://127.0.0.1:58200")
ROOT = os.environ.get("DXOS_TEST_OPENBAO_ROOT", "changeme-test-root")
POLICY = Path(__file__).resolve().parents[3] / "deploy/openbao/dxos-core-policy.hcl"


def _bao(method: str, path: str, token: str = ROOT, **kw) -> httpx.Response:
    return httpx.request(method, f"{ADDR}/v1/{path}", headers={"X-Vault-Token": token}, timeout=5, **kw)


@pytest.fixture(scope="module")
def core_token():
    """Dựng transit như deploy/openbao/init.sh rồi cấp token chỉ mang policy dxos-core."""
    try:
        _bao("GET", "sys/health")
    except httpx.HTTPError as exc:
        msg = f"cần OpenBao ở {ADDR} ({type(exc).__name__})"
        if os.environ.get("DXOS_TEST_REQUIRE_DB") == "1":
            pytest.fail(msg)
        pytest.skip(msg)
    if "transit/" not in _bao("GET", "sys/mounts").json().get("data", {}):
        _bao("POST", "sys/mounts/transit", json={"type": "transit"}).raise_for_status()
    for key in ("seal-key", "sth-key"):
        _bao("POST", f"transit/keys/{key}", json={"type": "ed25519", "exportable": False}).raise_for_status()
    policy = {"policy": POLICY.read_text(encoding="utf-8")}
    _bao("PUT", "sys/policies/acl/dxos-core", json=policy).raise_for_status()
    token_req = {"policies": ["dxos-core"], "no_default_policy": True, "ttl": "1h"}
    r = _bao("POST", "auth/token/create", json=token_req)
    r.raise_for_status()
    return r.json()["auth"]["client_token"]


@pytest.fixture
def openbao_signer(core_token):
    return OpenBaoTransit(ADDR, core_token)


async def test_openbao_sign_and_public_key(openbao_signer):           # cần OpenBao thật trong compose.test
    r = await openbao_signer.sign("sth-key", b"hello")
    pk = (await openbao_signer.public_keys())["sth-key"][r.key_version]
    Ed25519PublicKey.from_public_bytes(pk).verify(r.signature, b"hello")


async def test_policy_allows_only_sign_and_read(core_token):
    assert _bao("POST", "transit/sign/seal-key", core_token, json={"input": "aGk="}).status_code == 200
    forbidden = [
        ("DELETE", "transit/keys/sth-key"), ("POST", "transit/keys/sth-key/config"),
        ("GET", "transit/export/signing-key/sth-key"), ("POST", "transit/keys/new-key"),
        ("POST", "transit/keys/sth-key/rotate"), ("GET", "sys/mounts"), ("POST", "transit/sign/other-key"),
    ]
    for method, path in forbidden:
        assert _bao(method, path, core_token, json={}).status_code == 403, (method, path)


async def test_bad_token_is_kms_unavailable():
    with pytest.raises(KmsUnavailable):
        await OpenBaoTransit(ADDR, "changeme-sai-token").sign("sth-key", b"x")


async def test_core_token_can_renew_itself(core_token):                            # rà soát #5
    assert await OpenBaoTransit(ADDR, core_token).renew_self() > 0
