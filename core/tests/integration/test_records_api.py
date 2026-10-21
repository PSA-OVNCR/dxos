# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test Records API chung (Plan 01 Task 13; AT-06, AT-09, AT-10, RF1)."""

import json
import unicodedata
import uuid

import pytest
from dxos_core.records.digest import data_digest
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.api import activate, last_event_type, running_api, tok
from helpers.manifests import raw

pytestmark = pytest.mark.integration

URL_F = "/api/v1/apps/test-flow/collections/doc/records"
URL_D = "/api/v1/apps/test-dated/collections/doc/records"       # biến thể của test-flow có trường kiểu date
URL_T = "/api/v1/apps/test-app/collections/item/records"


@pytest.fixture
async def api(make_settings, core_dsn, core_conn, test_jwks):
    await activate(core_conn)
    dated = raw("test-flow")                       # fixture chung không có trường date: tạo biến thể tại chỗ
    dated["app"]["id"] = "test-dated"
    dated["collections"]["doc"]["fields"]["held_on"] = {"type": "date"}
    await save_manifest(core_conn, validate_manifest(dated), dated, "ACTIVE", "seed")
    async with running_api(make_settings(database_url=core_dsn)) as client:
        yield client


@pytest.fixture
def tok_author():
    return tok("author1", "app:test-flow:author")


@pytest.fixture
def tok_dated():
    return tok("author1", "app:test-dated:author")


@pytest.fixture
def tok_owner_a():
    return tok("owner_a1", "app:test-app:member")


@pytest.fixture
def tok_owner_b():
    return tok("owner_b1", "app:test-app:member")


@pytest.fixture
def tok_reviewer():
    return tok("reviewer1", "app:test-app:reviewer")


@pytest.fixture
async def rid_t(api, tok_owner_a):
    return (await api.post(URL_T, json={"title": "t"}, headers=tok_owner_a)).json()["id"]


# ---------- Các test do Plan 01 Task 13 quy định ----------

async def test_create_assigns_sequence(api, tok_author):          # app test-flow ở trạng thái ACTIVE
    r1 = await api.post(URL_F, json={"title": "QĐ 1"}, headers=tok_author)
    r2 = await api.post(URL_F, json={"title": "QĐ 2"}, headers=tok_author)
    assert r1.status_code == 201 and r1.headers["etag"] == '"1"'
    assert (r1.json()["data"]["ref"], r2.json()["data"]["ref"]) == ("01/TF", "02/TF")


async def test_schema_violation_422(api, tok_author):
    r = await api.post(URL_F, json={}, headers=tok_author)    # thiếu title (bắt buộc)
    assert r.status_code == 422 and r.json()["type"].endswith("/schema")


async def test_idor_returns_404_and_logs(api, tok_owner_a, tok_owner_b, core_conn):   # AT-06
    rid = (await api.post(URL_T, json={"title": "t"}, headers=tok_owner_a)).json()["id"]
    r = await api.get(f"{URL_T}/{rid}", headers=tok_owner_b)
    assert r.status_code == 404
    assert await last_event_type(core_conn) == "policy.denied"


async def test_patch_requires_if_match(api, tok_owner_a, rid_t):
    assert (await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers=tok_owner_a)).status_code == 428


async def test_patch_version_conflict(api, tok_owner_a, rid_t):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_a, "If-Match": '"9"'})
    assert r.status_code == 409 and r.json()["type"].endswith("/version-conflict")


async def test_sealed_record_patch_409(api, tok_owner_a, rid_t, owner_conn):          # AT-09
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1::uuid", rid_t)
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 409 and r.json()["type"].endswith("/record-sealed")


async def test_pii_masked_and_reveal_logged(api, tok_owner_a, tok_reviewer, core_conn):  # AT-10
    rid = (await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"},
                          headers=tok_owner_a)).json()["id"]
    seen_by_owner = (await api.get(f"{URL_T}/{rid}", headers=tok_owner_a)).json()["data"]["secret_code"]
    seen_by_reviewer = (await api.get(f"{URL_T}/{rid}", headers=tok_reviewer)).json()["data"]["secret_code"]
    assert (seen_by_owner, seen_by_reviewer) == ("07********34", "079203001234")
    assert await last_event_type(core_conn) == "field.revealed"


async def test_nfd_input_stored_as_nfc(api, tok_owner_a, core_conn):                   # RF1
    nfd = unicodedata.normalize("NFD", "Nguyễn")
    r = await api.post(URL_T, json={"title": nfd}, headers=tok_owner_a)
    assert r.json()["data"]["title"] == "Nguyễn" and r.json()["data"]["title"] != nfd
    stored = await core_conn.fetchval("SELECT data->>'title' FROM records WHERE id=$1::uuid", r.json()["id"])
    assert stored == unicodedata.normalize("NFC", "Nguyễn")


async def test_bulk_per_row_results(api, tok_author):
    rows = [{"title": "A"}, {"cccd": "079203001234"}]                                # dòng 2 thiếu title
    r = await api.post(URL_F + ":bulk", json=rows, headers=tok_author)
    assert [x["ok"] for x in r.json()["results"]] == [True, False]


async def test_inactive_app_404(api, tok_owner_a):
    r = await api.get("/api/v1/apps/khong-ton-tai/collections/x/records", headers=tok_owner_a)
    assert r.status_code == 404


# ---------- Bổ sung ----------

async def test_record_shape_hides_owner(api, tok_owner_a):
    r = await api.post(URL_T, json={"title": "t"}, headers=tok_owner_a)
    body = r.json()
    assert set(body) == {"id", "app_id", "collection", "data", "is_owner", "version", "seal_state",
                         "wf_state", "created_at", "updated_at"}            # wf_state: Plan 02 Task 6
    assert body["is_owner"] is True and body["version"] == 1 and body["seal_state"] == "NONE"
    assert "owner_a1" not in r.text


async def test_create_logs_record_created(api, tok_owner_a, core_conn):
    rid = (await api.post(URL_T, json={"title": "t"}, headers=tok_owner_a)).json()["id"]
    row = await core_conn.fetchrow(
        "SELECT type, subject, app_id FROM ledger_entries ORDER BY idx DESC LIMIT 1")
    assert tuple(row) == ("record.created", rid, "test-app")


async def test_create_forbidden_for_wrong_role(api, tok_reviewer, core_conn):
    r = await api.post(URL_T, json={"title": "t"}, headers=tok_reviewer)
    assert r.status_code == 403 and r.json()["type"].endswith("/forbidden")
    assert await last_event_type(core_conn) == "policy.denied"


async def test_role_of_other_app_cannot_list(api, tok_author, core_conn):                 # RF3
    r = await api.get(URL_T, headers=tok_author)
    assert r.status_code == 403
    assert await last_event_type(core_conn) == "policy.denied"


async def test_admin_without_app_role_cannot_read(api, tok_owner_a, rid_t):              # D4
    adm = tok("admin1", "dxos-admin")
    assert (await api.get(URL_T, headers=adm)).status_code == 403
    assert (await api.get(f"{URL_T}/{rid_t}", headers=adm)).status_code == 404


async def test_no_token_401(api):
    r = await api.get(URL_T)
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("rid", ["00000000-0000-0000-0000-000000000000", "khong-phai-uuid"])
async def test_missing_record_404_same_as_forbidden(api, tok_owner_a, rid):
    r = await api.get(f"{URL_T}/{rid}", headers=tok_owner_a)
    assert r.status_code == 404 and r.json()["type"].endswith("/not-found")


async def test_record_of_other_collection_not_reachable(api, tok_author, tok_owner_a):
    rid = (await api.post(URL_F, json={"title": "x"}, headers=tok_author)).json()["id"]
    assert (await api.get(f"{URL_T}/{rid}", headers=tok_owner_a)).status_code == 404


async def test_unknown_collection_404(api, tok_owner_a):
    r = await api.get("/api/v1/apps/test-app/collections/khong_co/records", headers=tok_owner_a)
    assert r.status_code == 404


@pytest.mark.parametrize("body", [
    {"title": "t", "la": 1},              # trường lạ
    {"title": 5},                         # sai kiểu
    ["không phải object"],
])
async def test_schema_errors(api, tok_owner_a, body):
    r = await api.post(URL_T, json=body, headers=tok_owner_a)
    assert r.status_code == 422 and r.json()["type"].endswith("/schema")


async def test_client_cannot_set_sequence(api, tok_author):
    r = await api.post(URL_F, json={"title": "x", "ref": "99/TF"}, headers=tok_author)
    assert r.status_code == 422 and r.json()["type"].endswith("/schema")


async def test_date_must_be_iso(api, tok_dated):
    r = await api.post(URL_D, json={"title": "A", "held_on": "20/11/2026"}, headers=tok_dated)
    assert r.status_code == 422
    ok = await api.post(URL_D, json={"title": "A", "held_on": "2026-11-20"}, headers=tok_dated)
    assert ok.status_code == 201 and ok.json()["data"]["held_on"] == "2026-11-20"


async def test_patch_ok_increments_version_and_logs(api, tok_owner_a, rid_t, core_conn):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "mới"}, headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 200 and r.headers["etag"] == '"2"'
    assert r.json()["data"]["title"] == "mới" and r.json()["version"] == 2
    assert await last_event_type(core_conn) == "record.updated"
    again = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"},
                            headers={**tok_owner_a, "If-Match": '"1"'})
    assert again.status_code == 409


async def test_patch_null_removes_optional_field(api, tok_owner_a):
    rid = (await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"},
                          headers=tok_owner_a)).json()["id"]
    r = await api.patch(f"{URL_T}/{rid}", json={"secret_code": None},
                        headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 200 and "secret_code" not in r.json()["data"]


async def test_patch_by_non_owner_is_404(api, tok_owner_b, rid_t, core_conn):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_b, "If-Match": '"1"'})
    assert r.status_code == 404
    assert await last_event_type(core_conn) == "policy.denied"


async def test_malformed_if_match_400(api, tok_owner_a, rid_t):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_a, "If-Match": "abc"})
    assert r.status_code == 400


async def test_list_owner_scoped_and_reviewer_sees_all(api, tok_owner_a, tok_owner_b, tok_reviewer):
    for i in range(3):
        await api.post(URL_T, json={"title": f"a{i}"}, headers=tok_owner_a)
    await api.post(URL_T, json={"title": "b0"}, headers=tok_owner_b)
    mine = (await api.get(URL_T, headers=tok_owner_a)).json()["items"]
    assert sorted(x["data"]["title"] for x in mine) == ["a0", "a1", "a2"] and all(x["is_owner"] for x in mine)
    everyone = (await api.get(URL_T, headers=tok_reviewer)).json()["items"]
    assert len(everyone) == 4


async def test_list_keyset_pagination(api, tok_owner_a):
    for i in range(5):
        await api.post(URL_T, json={"title": f"t{i}"}, headers=tok_owner_a)
    seen, cursor = [], None
    while True:
        url = URL_T + "?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await api.get(url, headers=tok_owner_a)).json()
        seen += [x["data"]["title"] for x in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == ["t0", "t1", "t2", "t3", "t4"]


@pytest.mark.parametrize("q", ["?limit=0", "?limit=201", "?cursor=rac"])
async def test_list_bad_params(api, tok_owner_a, q):
    assert (await api.get(URL_T + q, headers=tok_owner_a)).status_code in (400, 422)


async def test_list_masks_and_logs_reveal(api, tok_owner_a, tok_reviewer, core_conn):
    await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"}, headers=tok_owner_a)
    items = (await api.get(URL_T, headers=tok_owner_a)).json()["items"]
    assert items[0]["data"]["secret_code"] == "07********34"
    items = (await api.get(URL_T, headers=tok_reviewer)).json()["items"]
    assert items[0]["data"]["secret_code"] == "079203001234"
    assert await last_event_type(core_conn) == "field.revealed"


async def test_bulk_assigns_sequences_and_logs_per_row(api, tok_author, core_conn):
    rows = [{"title": f"N{i}"} for i in range(3)]
    res = (await api.post(URL_F + ":bulk", json=rows, headers=tok_author)).json()["results"]
    assert all(x["ok"] for x in res)
    nums = await core_conn.fetch("SELECT data->>'ref' AS n FROM records ORDER BY data->>'title'")
    assert [r["n"] for r in nums] == ["01/TF", "02/TF", "03/TF"]
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='record.created'") == 3


async def test_bulk_error_row_shape_and_forbidden(api, tok_author, tok_owner_a):
    one_bad = [{"cccd": "079203001234"}]
    res = (await api.post(URL_F + ":bulk", json=one_bad, headers=tok_author)).json()["results"]
    assert res[0]["ok"] is False and res[0]["row"] == 0 and res[0]["error"]["type"].endswith("/schema")
    assert (await api.post(URL_F + ":bulk", json=[{}], headers=tok_owner_a)).status_code == 403


# ---------- Sửa sau rà soát độc lập ----------

async def test_patch_response_reveal_is_logged(api, tok_owner_a, core_conn, owner_conn):   # rà soát #3 (F4)
    rid = (await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"},
                          headers=tok_owner_a)).json()["id"]
    # chủ bản ghi đồng thời là reviewer (được xem bản rõ)
    both = tok("owner_a1", "app:test-app:member", "app:test-app:reviewer")
    before = await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='field.revealed'")
    r = await api.patch(f"{URL_T}/{rid}", json={"title": "mới"}, headers={**both, "If-Match": '"1"'})
    assert r.json()["data"]["secret_code"] == "079203001234"
    after = await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='field.revealed'")
    assert after == before + 1


async def test_create_response_always_masked(api):
    both = tok("u", "app:test-app:member", "app:test-app:reviewer")
    r = await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"}, headers=both)
    assert r.json()["data"]["secret_code"] == "07********34"


@pytest.mark.parametrize("d", ["2026-W01-1", "20261120", "2026-13-01", "2026-02-30"])
async def test_strict_dates(api, tok_dated, d):
    r = await api.post(URL_D, json={"title": "A", "held_on": d}, headers=tok_dated)
    assert r.status_code == 422


# ---------- Plan 02 Task 2: cam kết có salt (P2-D22), đánh số theo năm (P2-D26) ----------

async def test_record_events_commit_to_salted_digest(api, tok_owner_a, core_conn):
    r = await api.post(URL_T, json={"title": "t", "secret_code": "001099012345"}, headers=tok_owner_a)
    rid = r.json()["id"]
    data = json.loads(await core_conn.fetchval("SELECT data::text FROM records WHERE id=$1", uuid.UUID(rid)))
    salt = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", uuid.UUID(rid))
    got = await core_conn.fetchval(
        "SELECT body_sha256 FROM ledger_entries WHERE type='record.created' AND subject=$1", rid)
    expected = {"collection": "item", "version": 1, "data_digest": data_digest(data, salt)}
    legacy = {"collection": "item", "version": 1, "data_sha256": sha256_hex(canonical_bytes(data))}
    assert got == sha256_hex(canonical_bytes(expected)) and got != sha256_hex(canonical_bytes(legacy))


async def test_record_updated_commits_to_salted_digest(api, tok_owner_a, rid_t, core_conn):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"secret_code": "001099012345"},
                        headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 200
    data = json.loads(await core_conn.fetchval("SELECT data::text FROM records WHERE id=$1",
                                               uuid.UUID(rid_t)))
    salt = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", uuid.UUID(rid_t))
    got = await core_conn.fetchval(
        "SELECT body_sha256 FROM ledger_entries WHERE type='record.updated' AND subject=$1", rid_t)
    assert got == sha256_hex(canonical_bytes({"collection": "item", "version": 2,
                                              "data_digest": data_digest(data, salt)}))


async def test_patch_recreates_erased_salt(api, tok_owner_a, rid_t, owner_conn, core_conn):
    """Sau khi salt bị xóa (P2-D23), lần sửa kế tiếp tạo salt mới bằng ``ensure_salt``."""
    old = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", uuid.UUID(rid_t))
    await owner_conn.execute("DELETE FROM record_salts WHERE record_id=$1", uuid.UUID(rid_t))
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "y"}, headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 200
    new = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", uuid.UUID(rid_t))
    assert new and new != old


async def test_yearly_sequence_field_uses_zero_padded_format(make_settings, core_dsn, core_conn, test_jwks):
    await activate(core_conn, ("test-flow",))
    url = "/api/v1/apps/test-flow/collections/doc/records"
    author = tok("author1", "app:test-flow:author")
    async with running_api(make_settings(database_url=core_dsn, timezone="Asia/Ho_Chi_Minh")) as client:
        refs = [(await client.post(url, json={"title": f"d{i}"}, headers=author)).json()["data"]["ref"]
                for i in range(2)]
    assert refs == ["01/TF", "02/TF"]
    names = [r["name"] for r in await core_conn.fetch("SELECT name FROM sequences WHERE app_id='test-flow'")]
    assert len(names) == 1 and names[0].startswith("doc.ref@20")


# ---------- rà soát cuối Plan 02, m2: thân JSON không mã hóa được / lồng quá sâu → 422, không 500 ----------
@pytest.mark.parametrize("body", [
    b'{"title": "x\\ud800y"}',                          # surrogate lẻ: json.loads nhận, UTF-8 thì không
    b'{"title": ' + b"[" * 100 + b"]" * 100 + b"}",              # quá trần độ sâu
    b'{"title": ' + b"[" * 200_000 + b"]" * 200_000 + b"}",      # json.loads ném RecursionError
], ids=["surrogate", "depth-100", "depth-200000"])
async def test_unencodable_or_deep_body_is_422(api, tok_author, body):
    headers = {**tok_author, "content-type": "application/json"}
    for r in (await api.post(URL_F, content=body, headers=headers),
              await api.post(URL_F + ":bulk", content=body, headers=headers)):
        assert r.status_code == 422 and r.json()["type"].endswith("/invalid-request"), r.text
