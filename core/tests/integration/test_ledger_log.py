# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test ghi ledger chỉ-thêm (Plan 01 Task 9, RF4, AT-15 phần DB)."""

import asyncio
import hmac
import json

import pytest
from dxos_core.ledger.log import VerifyResult, append, entries_bytes, entry_bytes, verify_log
from dxos_proof.canonical import canonical_bytes, sha256_hex
from dxos_proof.merkle import leaf_hash

pytestmark = pytest.mark.integration


@pytest.fixture
def key() -> bytes:
    return b"changeme-test-hmac-key"


# ---------- Các test do Plan 01 Task 9 quy định ----------

async def test_sequential_idx_from_zero(core_conn, key):
    a = await append(core_conn, type="record.created", subject="r1", body={}, hmac_key=key)
    b = await append(core_conn, type="record.updated", subject="r1", body={"v": 2}, hmac_key=key)
    assert (a.idx, b.idx) == (0, 1)


async def test_unknown_type_rejected(core_conn, key):
    with pytest.raises(ValueError):
        await append(core_conn, type="foo.bar", subject="x", body={}, hmac_key=key)


async def test_actor_ref_is_hmac_not_sub(core_conn, key):
    e = await append(core_conn, type="object.read", subject="o", body={}, hmac_key=key, actor_sub="user-123")
    assert e.actor_ref == hmac.new(key, b"user-123", "sha256").hexdigest() and "user-123" not in e.actor_ref


async def test_concurrent_appends_contiguous(core_pool, key):                     # RF4
    async def one(i):
        async with core_pool.acquire() as c:
            return (await append(c, type="object.read", subject=f"s{i}", body={}, hmac_key=key)).idx
    idxs = await asyncio.gather(*(one(i) for i in range(50)))
    assert sorted(idxs) == list(range(50))


async def test_leaf_hash_matches_entry_bytes(core_conn, key):
    e = await append(core_conn, type="record.created", subject="r", body={}, hmac_key=key)
    assert e.leaf_hash == leaf_hash(entry_bytes(e))


async def test_verify_detects_tamper(owner_conn, core_conn, key):                # AT-15 (phần DB)
    for i in range(5):
        await append(core_conn, type="object.read", subject=f"s{i}", body={}, hmac_key=key)
    await owner_conn.execute("ALTER TABLE ledger_entries DISABLE TRIGGER ledger_append_only")
    await owner_conn.execute("UPDATE ledger_entries SET subject='evil' WHERE idx=3")
    assert await verify_log(core_conn) == VerifyResult(ok=False, first_bad_idx=3)


# ---------- Bổ sung ----------

async def test_entry_fields_and_body_not_stored(core_conn, owner_conn, key):
    body = {"so_hieu": "12/QĐ-SM", "n": 3}
    e = await append(core_conn, type="record.created", subject="r9", body=body, hmac_key=key,
                     app_id="test-app")
    assert e.app_id == "test-app" and e.subject == "r9" and e.type == "record.created"
    assert e.body_sha256 == sha256_hex(canonical_bytes(body))
    assert e.ts.endswith("Z") and len(e.ts) == 20
    row = await owner_conn.fetchrow("SELECT * FROM ledger_entries WHERE idx=$1", e.idx)
    assert "12/QĐ-SM" not in json.dumps({k: str(v) for k, v in row.items()}, ensure_ascii=False)
    assert bytes(row["leaf_hash"]) == e.leaf_hash


async def test_subject_is_stored_nfc(core_conn, key):
    nfd = "Quyết"  # "Quyết" dạng NFD
    e = await append(core_conn, type="record.created", subject=nfd, body={}, hmac_key=key)
    assert e.subject == "Quyết"
    assert (await core_conn.fetchval("SELECT subject FROM ledger_entries WHERE idx=$1", e.idx)) == "Quyết"


async def test_entries_bytes_order_and_upto(core_conn, key):
    es = [await append(core_conn, type="object.read", subject=f"s{i}", body={}, hmac_key=key)
          for i in range(4)]
    assert await entries_bytes(core_conn) == [entry_bytes(e) for e in es]
    assert await entries_bytes(core_conn, upto=2) == [entry_bytes(e) for e in es[:2]]
    assert await entries_bytes(core_conn, upto=0) == []


async def test_verify_ok_on_clean_and_empty_log(core_conn, key):
    assert await verify_log(core_conn) == VerifyResult(ok=True, first_bad_idx=None)
    for i in range(3):
        await append(core_conn, type="object.read", subject=f"s{i}", body={}, hmac_key=key)
    assert await verify_log(core_conn) == VerifyResult(ok=True, first_bad_idx=None)


async def test_verify_detects_gap(owner_conn, core_conn, key):
    for i in range(4):
        await append(core_conn, type="object.read", subject=f"s{i}", body={}, hmac_key=key)
    await owner_conn.execute("ALTER TABLE ledger_entries DISABLE TRIGGER ledger_append_only")
    await owner_conn.execute("DELETE FROM ledger_entries WHERE idx=1")
    assert await verify_log(core_conn) == VerifyResult(ok=False, first_bad_idx=1)


async def test_append_rolled_back_with_caller_transaction(core_conn, key):
    await append(core_conn, type="object.read", subject="a", body={}, hmac_key=key)
    with pytest.raises(RuntimeError):
        async with core_conn.transaction():
            await append(core_conn, type="object.read", subject="b", body={}, hmac_key=key)
            raise RuntimeError("nghiệp vụ lỗi sau khi ghi ledger")
    c = await append(core_conn, type="object.read", subject="c", body={}, hmac_key=key)
    assert c.idx == 1  # không có lỗ hổng chỉ số
    assert await verify_log(core_conn) == VerifyResult(ok=True, first_bad_idx=None)


async def test_float_in_body_rejected(core_conn, key):
    with pytest.raises(ValueError):
        await append(core_conn, type="record.created", subject="r", body={"x": 1.5}, hmac_key=key)
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries") == 0
