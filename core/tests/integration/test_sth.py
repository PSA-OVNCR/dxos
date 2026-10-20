# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""STH ký và endpoint xác minh công khai (Plan 01 Task 15; AT-15, AT-17 phần STH, F8)."""

import base64
import dataclasses

import pytest
from dxos_core.kms.base import KmsUnavailable
from dxos_core.ledger.log import append, entries_bytes
from dxos_core.ledger.sth import latest_sth, make_sth, sth_signing_bytes, verify_sth
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import root, verify_consistency
from helpers.api import running_api
from helpers.local_signer import FailingSigner, LocalSigner

pytestmark = pytest.mark.integration
KEY = b"changeme-test-hmac-key"


@pytest.fixture
def local_signer():
    return LocalSigner()


@pytest.fixture
def failing_signer():
    return FailingSigner()


async def add_entries(conn, n: int) -> None:
    for i in range(n):
        await append(conn, type="object.read", subject=f"s{i}", body={"i": i}, hmac_key=KEY)


@pytest.fixture
async def seeded_entries(core_conn):
    await add_entries(core_conn, 7)


@pytest.fixture
async def api(make_settings, core_dsn, local_signer):
    async with running_api(make_settings(database_url=core_dsn), signer=local_signer) as client:
        yield client


# ---------- Các test do Plan 01 Task 15 quy định ----------

async def test_sth_root_matches_proof_lib(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    leaves = await entries_bytes(core_conn)
    assert th.root_hash == root(leaves).hex() and th.tree_size == len(leaves)


async def test_sth_signature_verifies_and_tamper_fails(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    pk = (await local_signer.public_keys())["sth-key"][th.key_version]
    assert verify_sth(th, pk)
    assert not verify_sth(dataclasses.replace(th, root_hash="00" * 32), pk)


async def test_kms_unavailable_inserts_nothing(core_conn, failing_signer, seeded_entries):     # F8
    before = await core_conn.fetchval("SELECT count(*) FROM tree_heads")
    with pytest.raises(KmsUnavailable):
        await make_sth(core_conn, failing_signer)
    assert await core_conn.fetchval("SELECT count(*) FROM tree_heads") == before


async def test_consistency_endpoint_verifies(api, core_conn, local_signer):     # AT-17 (phần STH)
    a = await make_sth(core_conn, local_signer)
    await add_entries(core_conn, 5)
    b = await make_sth(core_conn, local_signer)
    url = f"/verify/v1/sth/consistency?first={a.tree_size}&second={b.tree_size}"
    p = (await api.get(url)).json()["proof"]
    assert verify_consistency(a.tree_size, b.tree_size, bytes.fromhex(a.root_hash),
                              bytes.fromhex(b.root_hash), [bytes.fromhex(x) for x in p])


async def test_consistency_bad_range_400(api):
    assert (await api.get("/verify/v1/sth/consistency?first=9&second=3")).status_code == 400


# ---------- Bổ sung ----------

async def test_sth_covers_its_own_publication_leaf(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    assert th.tree_size == 8                                   # 7 lá + lá sth.published
    last = await core_conn.fetchrow("SELECT type FROM ledger_entries ORDER BY idx DESC LIMIT 1")
    assert last["type"] == "sth.published"
    row = await core_conn.fetchrow("SELECT * FROM tree_heads WHERE tree_size=$1", th.tree_size)
    assert (row["root_hash"], row["ts"], row["key_version"], row["signature"]) == (
        th.root_hash, th.ts, th.key_version, th.signature)


async def test_kms_failure_rolls_back_publication_leaf(core_conn, failing_signer, seeded_entries):
    with pytest.raises(KmsUnavailable):
        await make_sth(core_conn, failing_signer)
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='sth.published'") == 0
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries") == 7


def test_signing_bytes_are_canonical():
    assert sth_signing_bytes(3, "ab" * 32, "2026-10-20T00:00:00Z", 1) == canonical_bytes(
        {"tree_size": 3, "root_hash": "ab" * 32, "ts": "2026-10-20T00:00:00Z", "key_version": 1})


async def test_wrong_key_fails_and_bad_signature_is_false(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    other = (await LocalSigner().public_keys())["sth-key"][1]
    assert not verify_sth(th, other)
    assert not verify_sth(dataclasses.replace(th, signature="không-phải-base64"), other)
    assert not verify_sth(th, b"\x00" * 31)


async def test_key_rotation_signs_with_latest_version(core_conn, local_signer, seeded_entries):
    v2 = local_signer.rotate("sth-key")
    th = await make_sth(core_conn, local_signer)
    keys = await local_signer.public_keys()
    assert th.key_version == v2 and verify_sth(th, keys["sth-key"][v2])
    assert not verify_sth(th, keys["sth-key"][1])


async def test_sth_on_empty_log(core_conn, local_signer):
    th = await make_sth(core_conn, local_signer)
    assert th.tree_size == 1                                   # chỉ có lá sth.published


async def test_latest_endpoint_and_keys(api, core_conn, local_signer, seeded_entries):
    assert (await api.get("/verify/v1/sth/latest")).status_code == 404
    await make_sth(core_conn, local_signer)
    th = await make_sth(core_conn, local_signer)
    body = (await api.get("/verify/v1/sth/latest")).json()
    assert body == dataclasses.asdict(th)
    assert dataclasses.asdict(await latest_sth(core_conn)) == body
    keys = (await api.get("/verify/v1/keys")).json()
    pk = base64.b64decode(keys["sth-key"][str(th.key_version)])
    assert set(keys) == {"seal-key", "sth-key"} and verify_sth(th, pk)


@pytest.mark.parametrize("q", ["first=0&second=1", "first=1&second=999", "first=a&second=b", "second=3"])
async def test_consistency_bad_params(api, core_conn, local_signer, seeded_entries, q):
    await make_sth(core_conn, local_signer)
    assert (await api.get(f"/verify/v1/sth/consistency?{q}")).status_code in (400, 422)


async def test_consistency_same_size_empty_proof(api, core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    r = await api.get(f"/verify/v1/sth/consistency?first={th.tree_size}&second={th.tree_size}")
    assert r.json() == {"first": th.tree_size, "second": th.tree_size, "proof": []}


async def test_verify_api_is_public(api, core_conn, local_signer, seeded_entries):
    await make_sth(core_conn, local_signer)
    for path in ("/verify/v1/sth/latest", "/verify/v1/keys"):
        assert (await api.get(path)).status_code == 200      # không cần token


async def test_keys_503_when_kms_down(make_settings, core_dsn):
    class Down(LocalSigner):
        async def public_keys(self):
            raise KmsUnavailable("down")
    async with running_api(make_settings(database_url=core_dsn), signer=Down()) as api:
        r = await api.get("/verify/v1/keys")
    assert r.status_code == 503 and r.json()["type"].endswith("/kms-unavailable")
