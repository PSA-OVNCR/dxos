# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test client OpenBao transit với HTTP giả lập (respx)."""

import base64

import httpx
import pytest
from dxos_core.kms.base import KmsUnavailable
from dxos_core.kms.openbao import OpenBaoTransit

ADDR = "http://openbao.test:8200"


@pytest.fixture
def bao():
    return OpenBaoTransit(ADDR, "changeme-token")


async def test_sign_parses_vault_signature(bao, respx_mock):
    route = respx_mock.post(f"{ADDR}/v1/transit/sign/sth-key").respond(
        json={"data": {"signature": "vault:v3:" + base64.b64encode(b"sig").decode(), "key_version": 3}})
    r = await bao.sign("sth-key", b"hello")
    assert (r.signature, r.key_version) == (b"sig", 3)
    sent = route.calls.last.request
    assert sent.headers["x-vault-token"] == "changeme-token"
    assert b'"input":"aGVsbG8="' in sent.content.replace(b" ", b"")


async def test_sign_passes_key_version(bao, respx_mock):
    route = respx_mock.post(f"{ADDR}/v1/transit/sign/seal-key").respond(
        json={"data": {"signature": "vault:v1:" + base64.b64encode(b"s").decode()}})
    await bao.sign("seal-key", b"x", key_version=1)
    assert b'"key_version":1' in route.calls.last.request.content.replace(b" ", b"")


@pytest.mark.parametrize("status", [403, 500, 503])
async def test_errors_are_kms_unavailable(bao, respx_mock, status):
    respx_mock.post(f"{ADDR}/v1/transit/sign/sth-key").respond(status_code=status, json={"errors": ["x"]})
    with pytest.raises(KmsUnavailable):
        await bao.sign("sth-key", b"x")


async def test_connection_error_is_kms_unavailable(bao, respx_mock):
    respx_mock.post(f"{ADDR}/v1/transit/sign/sth-key").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(KmsUnavailable):
        await bao.sign("sth-key", b"x")


async def test_malformed_signature_is_kms_unavailable(bao, respx_mock):
    respx_mock.post(f"{ADDR}/v1/transit/sign/sth-key").respond(json={"data": {"signature": "rac"}})
    with pytest.raises(KmsUnavailable):
        await bao.sign("sth-key", b"x")


async def test_public_keys(bao, respx_mock):
    for name in ("seal-key", "sth-key"):
        respx_mock.get(f"{ADDR}/v1/transit/keys/{name}").respond(json={"data": {"type": "ed25519", "keys": {
            "1": {"public_key": base64.b64encode(b"a" * 32).decode()},
            "2": {"public_key": base64.b64encode(b"b" * 32).decode()}}}})
    keys = await bao.public_keys()
    assert keys == {"seal-key": {1: b"a" * 32, 2: b"b" * 32}, "sth-key": {1: b"a" * 32, 2: b"b" * 32}}


async def test_rejects_non_ed25519_key(bao, respx_mock):
    aes = {"data": {"type": "aes256-gcm96", "keys": {}}}
    respx_mock.get(f"{ADDR}/v1/transit/keys/seal-key").respond(json=aes)
    respx_mock.get(f"{ADDR}/v1/transit/keys/sth-key").respond(json={"data": {"type": "ed25519", "keys": {}}})
    with pytest.raises(KmsUnavailable):
        await bao.public_keys()


async def test_renew_self(bao, respx_mock):                                        # rà soát #5
    route = respx_mock.post(f"{ADDR}/v1/auth/token/renew-self").respond(
        json={"auth": {"lease_duration": 2764800}})
    assert await bao.renew_self() == 2764800
    assert route.calls.last.request.headers["x-vault-token"] == "changeme-token"


async def test_renew_self_failure(bao, respx_mock):
    respx_mock.post(f"{ADDR}/v1/auth/token/renew-self").respond(status_code=403)
    with pytest.raises(KmsUnavailable):
        await bao.renew_self()
