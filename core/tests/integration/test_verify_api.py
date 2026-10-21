# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cổng đối soát công khai và gói bằng chứng (Plan 02 Task 8; spec 11.5, 12.2, 25.3; AT-05, AT-19, AT-25 phần
API, AT-27 phần trang công khai; P2-D7, P2-D16, P2-D25, P2-D26).

Fixture ``flow``/``verify``/``kms_down`` ở conftest. ``test-flow`` 0.1.0 có ``verify: {public: true,
require_file: true}``, ``public_fields: [ref, title]``, chỉ ``title`` có ``label``.
"""

import asyncio
import base64
import hashlib
import json
from datetime import datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_core.ledger.sth import TreeHead, make_sth, verify_sth
from dxos_core.seal.keys import statement_for
from dxos_core.seal.service import seal_signing_bytes, sealed_leaf_body
from dxos_proof.canonical import canonical_bytes, sha256_hex
from dxos_proof.merkle import leaf_hash, verify_consistency, verify_inclusion

pytestmark = pytest.mark.integration

# 2 khóa cuối: bổ sung 21/10
ALLOWED = {"seal_id", "status", "app_id", "issued_at", "key_version", "public_fields", "require_file",
           "attachments_count", "signature_valid", "inclusion", "issuer", "public_labels"}
ENTRY_FIELDS = {"idx", "ts", "type", "app_id", "subject", "actor_ref", "body_sha256"}
REPO = "file:///repo-neo-thu.git"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _make_sth(flow, signer) -> TreeHead:
    async with flow.db.acquire() as c:
        return await make_sth(c, signer)


async def _anchor_row(flow, th: TreeHead, commit: str = "a" * 40) -> None:
    await flow.db.execute("INSERT INTO anchors(tree_size, repo, commit_sha) VALUES ($1, $2, $3)",
                          th.tree_size, REPO, commit)


async def _file_bundle(verify, sid: str, original: bytes) -> dict:
    r = await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": _sha(original)})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Các test do Plan 02 Task 8 quy định ----------

async def test_public_view_has_only_allowed_keys(flow, verify):          # AT-19 (nội dung), Review Focus 4
    sid, rid = await flow.sealed_ids()
    body = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    text = json.dumps(body)
    assert set(body) == ALLOWED and body["status"] == "VALID" and body["signature_valid"]
    assert set(body["public_fields"]) <= {"ref", "title"}
    assert str(rid) not in text and all(h not in text for h in await flow.attachment_hashes(sid))


async def test_pending_seal_shows_pending(flow, verify):
    sid = await flow.pending_seal_id()
    assert (await verify.get(f"/verify/v1/seals/{sid}")).json() == {"seal_id": sid, "status": "SEAL_PENDING"}


async def test_non_public_app_hides_even_pending(flow, verify):
    sid = await flow.pending_seal_id(verify_public=False)
    assert (await verify.get(f"/verify/v1/seals/{sid}")).status_code == 404


async def test_check_matches_original_not_modified_file(flow, verify):                  # AT-05
    sid, original = await flow.sealed_with_file()
    modified = bytearray(original)
    modified[-10] ^= 1
    for data, expect in ((original, True), (bytes(modified), False)):
        r = await verify.post(f"/verify/v1/seals/{sid}:check",
                              json={"sha256": hashlib.sha256(data).hexdigest()})
        assert r.json() == {"match": expect}


async def test_check_refuses_files_and_large_bodies(flow, verify):        # AT-25 (phần API), R-2
    sid, original = await flow.sealed_with_file()
    assert (await verify.post(f"/verify/v1/seals/{sid}:check",
                              files={"file": ("a.pdf", original)})).status_code == 415
    big = b'{"sha256": "' + b"a" * 300 + b'"}'
    assert (await verify.post(f"/verify/v1/seals/{sid}:check", content=big,
                              headers={"content-type": "application/json"})).status_code == 413
    chunked = verify.stream_post(f"/verify/v1/seals/{sid}:check", chunks=[b"{", b" " * 300, b"}"])
    assert (await chunked).status_code == 413


async def test_bundle_for_file_seal_only_via_post_with_matching_hash(flow, verify):     # P2-D16
    sid, original = await flow.sealed_with_file()
    assert (await verify.get(f"/verify/v1/seals/{sid}/bundle")).status_code == 404
    assert (await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": "0" * 64})).status_code == 404
    ok = await verify.post(f"/verify/v1/seals/{sid}:bundle",
                           json={"sha256": hashlib.sha256(original).hexdigest()})
    assert ok.status_code == 200 and ok.json()["format"] == "dxos-seal-bundle/1"


async def test_bundle_never_contains_unsalted_digest(flow, verify):                    # P2-D7
    sid, original = await flow.sealed_with_file()
    b = (await verify.post(f"/verify/v1/seals/{sid}:bundle",
                           json={"sha256": hashlib.sha256(original).hexdigest()})).json()
    data = await flow.record_data_of(sid)
    assert b["payload"]["record_digest"] != sha256_hex(canonical_bytes(data)) and "salt" not in json.dumps(b)


async def test_public_view_works_while_openbao_sealed(flow, verify, kms_down):
    sid, _ = await flow.sealed_ids()
    await verify.get(f"/verify/v1/seals/{sid}")                       # khởi tạo cache
    kms_down()
    assert (await verify.get(f"/verify/v1/seals/{sid}")).json()["signature_valid"]


async def test_revoked_status_is_public(flow, verify):
    sid = await flow.revoked_seal_id()
    assert (await verify.get(f"/verify/v1/seals/{sid}")).json()["status"] == "REVOKED"


# ---------- Bổ sung 21/10 (P2-D25, P2-D26) do plan quy định ----------

async def test_public_view_shows_issuer_and_labels(flow, verify):
    sid, _ = await flow.sealed_ids()
    body = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert body["issuer"] == {"name": flow.settings.org_name, "id": flow.settings.org_id}
    assert body["public_labels"] == {"title": "Tiêu đề"}            # "ref" không có label


# ---------- Ruling C5: AT-27, phần trang công khai ----------

async def test_public_view_still_valid_after_erase_pii(flow, verify):                  # AT-27
    rid = await flow.sealed_record(data={"title": "QĐ thử", "cccd": "001099012345"})
    sid, salt = await flow.seal_id_of(rid), await flow.salt_of(rid)
    assert salt
    r = await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")
    assert r.status_code == 200, r.text
    resp = await verify.get(f"/verify/v1/seals/{sid}")
    body, text = resp.json(), resp.text
    assert body["status"] == "VALID" and body["signature_valid"] is True
    assert "001099012345" not in text and salt not in text


# ---------- Bổ sung của Task 8 ----------

async def test_hidden_unknown_and_malformed_ids_look_the_same(flow, verify):
    """Thứ tự kiểm chung: sai dạng / không có / app không công khai đều cùng một 404, ở cả bốn route."""
    hidden_pending = await flow.pending_seal_id(verify_public=False)       # phiên bản 0.2.0, public: false
    hidden_sealed, _ = await flow.sealed_ids()                              # cũng ghim 0.2.0
    ids = ["abc", "a" * 26, "A" * 27, "A" * 26, hidden_pending, hidden_sealed]
    bodies = set()
    for sid in ids:
        for r in (await verify.get(f"/verify/v1/seals/{sid}"),
                  await verify.get(f"/verify/v1/seals/{sid}/bundle"),
                  await verify.post(f"/verify/v1/seals/{sid}:check", json={"sha256": "0" * 64}),
                  await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": "0" * 64})):
            assert r.status_code == 404, (sid, r.request.url, r.text)
            bodies.add(r.text)
    assert len(bodies) == 1


async def test_cold_key_cache_with_kms_down_is_503_not_invalid(flow, verify, kms_down):
    sid, original = await flow.sealed_with_file()
    kms_down()                                                              # cache chưa có khóa nào
    for r in (await verify.get(f"/verify/v1/seals/{sid}"),
              await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": _sha(original)})):
        assert r.status_code == 503 and r.json()["type"].endswith("/keys-unavailable")
    # :check không cần khóa
    assert (await verify.post(f"/verify/v1/seals/{sid}:check", json={"sha256": _sha(original)})).json() == {
        "match": True}


async def test_check_body_rules(flow, verify):
    sid, original = await flow.sealed_with_file()
    url = f"/verify/v1/seals/{sid}:check"
    good = json.dumps({"sha256": _sha(original)}).encode()
    assert (await verify.post(url, content=good)).status_code == 415          # thiếu content-type
    assert (await verify.post(url, content=good, headers={"content-type": "text/plain"})).status_code == 415
    r = await verify.post(url, content=good, headers={"content-type": "application/json; charset=utf-8"})
    assert r.json() == {"match": True}
    exact = good[:-1] + b" " * (256 - len(good)) + b"}"
    assert len(exact) == 256
    js = {"content-type": "application/json"}
    assert (await verify.post(url, content=exact, headers=js)).status_code == 200
    over = good[:-1] + b" " * (257 - len(good)) + b"}"
    assert (await verify.post(url, content=over, headers=js)).status_code == 413
    assert (await verify.stream_post(url, [good[:10], good[10:]])).json() == {"match": True}   # chunked, nhỏ
    for bad in (b"{", b"[]", b'{"sha256": 1}', json.dumps({"sha256": _sha(original).upper()}).encode(),
                json.dumps({"sha256": "0" * 63}).encode(), json.dumps({"sha256": "0" * 64, "x": 1}).encode(),
                b'{"sha256": "' + b"0" * 64 + b'", "sha256": "' + b"1" * 64 + b'"}', b"\xff"):
        r = await verify.post(url, content=bad, headers={"content-type": "application/json"})
        assert r.status_code == 422, (bad, r.text)


async def test_body_cap_stops_reading_at_the_limit(flow, verify):
    """413 ngay khi vượt 256 byte: phần thân sau đó không bao giờ tới (client treo) mà vẫn có phản hồi."""
    sid, _ = await flow.sealed_with_file()

    async def endless():
        yield b"{" + b" " * 300
        await asyncio.Event().wait()                    # không bao giờ gửi tiếp

    for path in (f"/verify/v1/seals/{sid}:check", f"/verify/v1/seals/{sid}:bundle"):
        r = await asyncio.wait_for(flow.api.post(path, content=endless(),
                                                 headers={"content-type": "application/json"}), 10)
        assert r.status_code == 413


async def test_check_and_bundle_while_pending(flow, verify):
    sid = await flow.pending_seal_id()
    r = await verify.post(f"/verify/v1/seals/{sid}:check", json={"sha256": "0" * 64})
    assert r.json() == {"match": False, "status": "SEAL_PENDING"}
    r = await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": "0" * 64})
    assert r.json() == {"seal_id": sid, "status": "SEAL_PENDING"}


async def test_bundle_get_for_seal_without_file_requirement(flow, verify):
    await flow.install_verify_policy("0.2.0", require_file=False)
    sid, _ = await flow.sealed_ids()
    view = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert view["require_file"] is False and view["attachments_count"] == 1
    r = await verify.get(f"/verify/v1/seals/{sid}/bundle")
    assert r.status_code == 200 and r.json()["payload"]["seal_id"] == sid
    hashes = await flow.attachment_hashes(sid)
    r = await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": hashes[0]})
    assert r.status_code == 404


async def test_bundle_is_self_consistent_and_entry_reproduces_leaf(flow, verify, local_signer):
    sid, original = await flow.sealed_with_file()
    th = await _make_sth(flow, local_signer)
    await _anchor_row(flow, th)
    b = await _file_bundle(verify, sid, original)
    assert b["status"] == "VALID" and b["format"] == "dxos-seal-bundle/1"
    datetime.fromisoformat(b["generated_at"].replace("Z", "+00:00"))
    # chữ ký niêm phong bằng khóa trong gói = khóa KMS
    pk = (await local_signer.public_keys())["seal-key"][b["payload"]["key_version"]]
    assert base64.b64decode(b["seal_key"]["public_key"]) == pk and b["seal_key"]["version"] == 1
    Ed25519PublicKey.from_public_bytes(pk).verify(base64.b64decode(b["signature"]),
                                                  seal_signing_bytes(b["payload"]))
    async with flow.db.acquire() as c:
        assert b["seal_key"]["statement"] == await statement_for(c, 1)
    # lá ledger: đúng 7 trường, băm lại ra đúng leaf_hash đã lưu
    entry = b["ledger"]["entry"]
    assert set(entry) == ENTRY_FIELDS and entry["idx"] == b["inclusion"]["leaf_index"]
    stored = await flow.db.fetchval("SELECT leaf_hash FROM ledger_entries WHERE idx=$1", entry["idx"])
    assert leaf_hash(canonical_bytes(entry)) == bytes(stored)
    assert b["ledger"]["body"] == sealed_leaf_body(b["payload"])
    assert entry["body_sha256"] == sha256_hex(canonical_bytes(b["ledger"]["body"]))
    # inclusion + STH + neo
    sth = b["sth"]
    assert sth == {"tree_size": th.tree_size, "root_hash": th.root_hash, "ts": th.ts,
                   "key_version": th.key_version, "signature": th.signature}
    assert b["inclusion"]["tree_size"] == th.tree_size
    assert verify_inclusion(leaf_hash(canonical_bytes(entry)), entry["idx"], sth["tree_size"],
                            [bytes.fromhex(p) for p in b["inclusion"]["proof"]],
                            bytes.fromhex(sth["root_hash"]))
    sth_pk = base64.b64decode(b["sth_keys"][str(th.key_version)])
    assert verify_sth(TreeHead(**sth), sth_pk)
    assert b["anchored"] == {"sth": sth, "repo": REPO, "commit_sha": "a" * 40, "consistency": []}


async def test_sth_selection(flow, verify, local_signer):
    """Chưa có STH → không kiểm được; có STH chưa neo → dùng nó; đã neo phủ lá → ưu tiên STH đã neo."""
    sid, original = await flow.sealed_with_file()
    view = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert view["inclusion"]["tree_size"] is None and view["inclusion"]["verified"] is False
    assert view["inclusion"]["anchored"] is None and view["signature_valid"] is True
    b = await _file_bundle(verify, sid, original)
    assert b["sth"] is None and b["anchored"] is None
    assert b["inclusion"] == {"leaf_index": b["ledger"]["entry"]["idx"], "tree_size": None, "proof": []}

    s1 = await _make_sth(flow, local_signer)
    view = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert view["inclusion"]["tree_size"] == s1.tree_size and view["inclusion"]["verified"] is True
    assert view["inclusion"]["anchored"] is None
    assert (await _file_bundle(verify, sid, original))["anchored"] is None

    await _anchor_row(flow, s1)
    s2 = await _make_sth(flow, local_signer)                       # mới hơn nhưng chưa neo
    assert s2.tree_size > s1.tree_size
    view = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert view["inclusion"] == {"leaf_index": view["inclusion"]["leaf_index"], "tree_size": s1.tree_size,
                                 "verified": True,
                                 "anchored": {"tree_size": s1.tree_size, "repo": REPO,
                                              "commit_sha": "a" * 40}}
    b = await _file_bundle(verify, sid, original)
    assert b["sth"]["tree_size"] == s1.tree_size and b["anchored"]["sth"] == b["sth"]
    assert b["anchored"]["consistency"] == []


async def test_anchored_sth_older_than_leaf_comes_with_consistency(flow, verify, local_signer):
    s0 = await _make_sth(flow, local_signer)                       # trước khi niêm phong
    await _anchor_row(flow, s0)
    sid, original = await flow.sealed_with_file()
    s1 = await _make_sth(flow, local_signer)
    b = await _file_bundle(verify, sid, original)
    assert b["sth"]["tree_size"] == s1.tree_size and b["anchored"]["sth"]["tree_size"] == s0.tree_size
    assert b["anchored"]["sth"]["tree_size"] <= b["inclusion"]["leaf_index"]          # neo chưa phủ lá (C8)
    assert verify_consistency(s0.tree_size, s1.tree_size, bytes.fromhex(s0.root_hash),
                              bytes.fromhex(s1.root_hash),
                              [bytes.fromhex(p) for p in b["anchored"]["consistency"]])
    view = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert view["inclusion"]["tree_size"] == s1.tree_size and view["inclusion"]["verified"] is True
    assert view["inclusion"]["anchored"]["tree_size"] == s0.tree_size


async def test_verify_routes_never_write(flow, verify, local_signer):
    sid, original = await flow.sealed_with_file()
    await _make_sth(flow, local_signer)

    async def counts():
        return [await flow.db.fetchval(f"SELECT count(*) FROM {t}")  # noqa: S608
                for t in ("ledger_entries", "tree_heads", "anchors", "jobs")]

    before = await counts()
    await verify.get(f"/verify/v1/seals/{sid}")
    await verify.post(f"/verify/v1/seals/{sid}:check", json={"sha256": _sha(original)})
    await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": _sha(original)})
    await verify.post(f"/verify/v1/seals/{sid}:bundle", json={"sha256": "0" * 64})
    await verify.get("/verify/v1/keys")
    assert await counts() == before


async def test_tampered_payload_is_reported_not_hidden(flow, verify, local_signer):         # X1 (quyền SQL)
    sid, _ = await flow.sealed_ids()
    await _make_sth(flow, local_signer)
    await flow.owner.execute(
        "UPDATE seals SET payload = jsonb_set(payload, '{public_fields,title}', '\"Giả mạo\"')"
        " WHERE seal_id=$1",
        sid)
    body = (await verify.get(f"/verify/v1/seals/{sid}")).json()
    assert body["signature_valid"] is False and body["inclusion"]["verified"] is False


async def test_keys_include_statements_and_survive_kms_outage(flow, verify, local_signer, kms_down):
    await flow.sealed_ids()
    keys = (await verify.get("/verify/v1/keys")).json()
    assert set(keys) == {"seal-key", "sth-key", "statements"}
    pub = await local_signer.public_keys()
    assert keys["sth-key"] == {"1": base64.b64encode(pub["sth-key"][1]).decode()}
    async with flow.db.acquire() as c:
        assert keys["statements"] == {"seal-key": {"1": await statement_for(c, 1)}}
    kms_down()
    assert (await verify.get("/verify/v1/keys")).json() == keys            # khóa bất biến: phục vụ từ cache
