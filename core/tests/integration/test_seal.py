# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Niêm phong, thu hồi, xóa PII và tuyên bố khóa trên Flowable thật (Plan 02 Task 7; AT-09, AT-20b, AT-27,
AT-28; P2-D7, P2-D18, P2-D19, P2-D22..P2-D25).

Fixture ``flow`` (conftest): API thật + ``test-flow`` 0.1.0, ``SealHooks`` thật đã nối trong ``create_app``.
"""

import asyncio
import json
from base64 import b64decode
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_core.seal.keys import (
    LOCK_KEYSTMT,
    ORG_NAME_DEFAULT,
    KeyStatementInvalid,
    OrgNotConfigured,
    SealKeyExpired,
    build_statement,
    parse_rfc3339,
)
from dxos_core.seal.service import SealStateError, record_digest, seal_signing_bytes, sealed_leaf_body
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.flow import URL, headers_for
from helpers.local_signer import FailingSigner, UnreachableSigner

pytestmark = pytest.mark.integration


# ---------- Các test do Plan 02 Task 7 quy định ----------

async def test_seal_happy_path(flow, local_signer):
    rid = await flow.approved_record()                      # tới SEAL_PENDING; local_signer hoạt động
    row = await flow.seal_row(rid)
    pk = (await local_signer.public_keys())["seal-key"][row["key_version"]]
    Ed25519PublicKey.from_public_bytes(pk).verify(b64decode(row["signature"]),
                                                  seal_signing_bytes(row["payload"]))
    leaf = await flow.ledger_entry(row["leaf_index"])
    assert leaf.type == "record.sealed" and leaf.subject == row["seal_id"]
    assert leaf.body_sha256 == sha256_hex(canonical_bytes(sealed_leaf_body(row["payload"])))
    assert (await flow.get(rid))["seal_state"] == "SEALED"
    assert (await flow.patch(rid, {"title": "x"})).status_code == 409                       # AT-09


async def test_seal_covers_snapshot_not_later_state(flow, flaky_signer):                     # P2-D18
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer, kms_ok_for_probe=True)
    snap = await flow.seal_request(rid)
    await flow.force_extra_clean_ref(rid)  # mô phỏng ref xuất hiện muộn (owner_conn, bỏ qua trigger)
    flaky_signer.fail = False
    await flow.run_worker_until_idle(signer=flaky_signer)
    assert (await flow.seal_row(rid))["payload"]["attachments"] == snap["attachments"]


async def test_kms_fails_after_flowable_then_recovers(flow, flaky_signer):                     # AT-20b
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer, kms_ok_for_probe=True)  # thăm dò đạt, ký thật lỗi
    assert (await flow.get(rid))["seal_state"] == "SEAL_PENDING"
    assert await flow.count("seals", rid) == 0  # không có niêm phong thiếu chữ ký
    assert (await flow.patch(rid, {"title": "x"})).status_code == 409                       # đã khóa sửa
    flaky_signer.fail = False
    await flow.run_worker_until_idle(signer=flaky_signer)
    assert (await flow.get(rid))["seal_state"] == "SEALED"


async def test_seal_still_completes_after_app_disabled(flow, flaky_signer):                   # P2-D19
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer, kms_ok_for_probe=True)
    await flow.disable_app()
    flaky_signer.fail = False
    await flow.run_worker_until_idle(signer=flaky_signer)
    assert await flow.seal_state_db(rid) == "SEALED"


async def test_job_and_inline_seal_race_produce_one_seal(flow, local_signer):                 # Review Focus 3
    rid = await flow.pending_record()
    sid = await flow.seal_id_of(rid)
    _, claimed = await asyncio.gather(flow.seal_inline(rid), flow.run_worker_once())
    assert claimed and (await flow.seal_job(rid))["state"] == "DONE"          # job thật sự đã chạy (m5)
    assert await flow.count("seals", rid) == 1 and await flow.count_ledger("record.sealed", subject=sid) == 1


async def test_revoke_roles_and_terminal_state(flow):
    rid = await flow.sealed_record()
    assert (await flow.revoke(rid, as_="r1")).status_code == 404  # reviewer không có quyền
    assert (await flow.revoke(rid, as_="p1")).status_code == 200
    assert (await flow.revoke(rid, as_="p1")).status_code == 409
    assert await flow.seal_status(rid) == "REVOKED" and await flow.count("seal_revocations", rid) == 1


async def test_seal_triggers_anchor_job(flow):
    await flow.sealed_record()
    assert await flow.queued_jobs("anchor_sth") >= 1


# ---------- Bổ sung 21/10 (P2-D23, P2-D24, P2-D25) do plan quy định ----------

async def test_erase_pii_keeps_seal_valid_and_leaves_no_trace(flow, local_signer):            # AT-27
    rid = await flow.sealed_record(data={"title": "QĐ thử", "cccd": "001099012345"})
    sid, salt = await flow.seal_id_of(rid), await flow.salt_of(rid)
    r = await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")
    assert r.status_code == 200 and "cccd" not in await flow.raw_data(rid)
    # Hai khẳng định "niêm phong vẫn VALID" qua trang công khai và "gói bằng chứng vẫn kiểm được" của AT-27
    # cần API chưa có: GET /verify/v1/seals/{id} (Task 8) và gói bằng chứng + verify_bundle (Task 9 Step 3).
    # Ruling C5: thêm hai dòng đó ở Task 8/9. Ở đây kiểm phần DB: hàng seals không đổi.
    assert await flow.seal_status(rid) == "VALID" and (await flow.seal_row(rid))["seal_id"] == sid
    assert (await flow.ledger_verify()).ok
    dump = await flow.dump_core_tables()
    assert "001099012345" not in dump and salt not in dump
    assert await flow.count_ledger("pii.erased", subject=str(rid)) == 1


async def test_erase_pii_rules(flow):
    rid = await flow.sealed_record()
    # không thuộc erase_roles
    assert (await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="r1")).status_code == 404
    assert await flow.last_denied_reason() == "not_eraser"
    # không phải trường pii
    assert (await flow.erase_pii(rid, ["title"], "data_subject_request", as_="p1")).status_code == 422
    assert (await flow.erase_pii(rid, ["cccd"], "ly_do_la", as_="p1")).status_code == 422
    running = await flow.ready_record(author="a1")
    await flow.start(running, as_="a1")
    assert (await flow.erase_pii(running, ["cccd"], "data_subject_request", as_="p1")).status_code == 409


# rà soát bổ sung, #4
async def test_erase_rechecks_state_under_lock(flow, seal_pending_between_check_and_lock):
    rid = await flow.approved_record_before_seal()
    assert (await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")).status_code == 409
    assert await flow.count("pii_erasures", rid) == 0


async def test_no_unsalted_commitment_anywhere(flow):                                       # P2-D22, I5
    rid = await flow.sealed_record(data={"title": "QĐ thử", "cccd": "001099012345"})
    dump = await flow.dump_core_tables()
    for data in await flow.data_versions_sent(rid):
        plain = sha256_hex(canonical_bytes(data))
        assert plain not in dump
        for v in range(1, 10):
            legacy = {"collection": "doc", "version": v, "data_sha256": plain}
            assert not await flow.ledger_has_body_sha256(sha256_hex(canonical_bytes(legacy)))


async def test_revocation_note_is_erasable(flow):                                          # P2-D24
    rid = await flow.sealed_record()
    await flow.revoke(rid, as_="p1", reason_code="issued_in_error", note="Ghi chú có thể chứa tên người")
    assert await flow.count("seal_revocation_notes", rid) == 1
    await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")
    assert await flow.count("seal_revocation_notes", rid) == 0


async def test_key_statement_created_once_and_enforced(flow, local_signer):                 # AT-28
    await flow.sealed_record()
    await flow.sealed_record()
    [row] = await flow.key_statements()
    st = row["statement"]
    assert st["serial"] == "seal-key/v1" and st["issuer"]["name"] == flow.settings.org_name
    assert "signature" not in st and "subject" not in st  # spec 25.3: không tự ký
    assert st["valid_from"] == (await flow.first_seal_payload())["issued_at"]  # cùng chuỗi giây nguyên
    assert b64decode(st["public_key"]) == (await local_signer.public_keys())["seal-key"][1]
    [leaf] = await flow.ledger_entries("key.published")
    body = {"key": "seal-key", "version": 1, "statement_sha256": sha256_hex(canonical_bytes(st))}
    assert leaf.subject == "seal-key/v1" and leaf.body_sha256 == sha256_hex(canonical_bytes(body))
    late = parse_rfc3339(st["valid_until"]) + timedelta(seconds=1)
    rid = await flow.approved_record(seal_now=late)
    assert await flow.seal_state_db(rid) == "SEAL_PENDING"          # hết hạn: không ký, chờ xoay khóa


async def test_default_org_name_blocks_sealing(flow_factory):  # rà soát bổ sung, #5
    flow = await flow_factory(org_name=ORG_NAME_DEFAULT)
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    r = await flow.complete_task("approve", rid, "approve", as_="p1")
    assert r.status_code == 503 and r.json()["type"].endswith("/org-not-configured")
    assert await flow.count("key_statements") == 0


# ---------- Bổ sung của Task 7 ----------

async def test_seal_info_endpoint(flow):
    open_rid = await flow.new_record("a1")
    r = await flow.api.get(f"{URL}/{open_rid}/seal", headers=headers_for("a1"))
    assert r.status_code == 404                                   # chưa có yêu cầu niêm phong
    rid = await flow.sealed_record()
    r = await flow.api.get(f"{URL}/{rid}/seal", headers=headers_for("r1"))
    assert r.status_code == 200, r.text
    body, row = r.json(), await flow.seal_row(rid)
    assert set(body) == {"seal_id", "seal_state", "issued_at", "key_version", "public_fields", "verify_url"}
    assert body["seal_id"] == row["seal_id"] and body["seal_state"] == "SEALED"
    assert body["issued_at"] == row["payload"]["issued_at"] and body["key_version"] == row["key_version"]
    assert set(body["public_fields"]) == {"ref", "title"}             # chỉ trường public, không có cccd
    assert body["verify_url"] == f"https://localhost/apps/verify/#{row['seal_id']}"
    other = await flow.api.get(f"{URL}/{rid}/seal", headers=flow.token("x9", "author"))
    assert other.status_code == 404                               # không đọc được bản ghi → cùng 404


async def test_seal_info_of_pending_record_has_no_issued_at(flow, flaky_signer):
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer)
    body = (await flow.api.get(f"{URL}/{rid}/seal", headers=headers_for("p1"))).json()
    assert body["seal_state"] == "SEAL_PENDING" and body["issued_at"] is None and body["key_version"] is None
    assert body["seal_id"] == await flow.seal_id_of(rid)


async def test_snapshot_digest_is_salted_and_public_fields_present_only(flow):
    rid = await flow.approved_record(data={"title": "QĐ thử"})
    snap = await flow.seal_request(rid)
    data = await flow.raw_data(rid)
    assert snap["record_digest"] == record_digest(data, await flow.salt_of(rid))
    assert snap["public_fields"] == {"ref": data["ref"], "title": "QĐ thử"} and "salt" not in snap
    assert snap["app_version"] == "0.1.0" and len(snap["attachments"]) == 1


async def test_seal_job_backs_off_on_kms_and_never_fails(flow, flaky_signer):
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer)
    job = await flow.seal_job(rid)
    await flow.db.execute("UPDATE jobs SET attempts=30 WHERE id=$1", job["id"])  # quá MAX_ATTEMPTS của worker
    await flow.run_worker_until_idle(signer=FailingSigner())
    job = await flow.seal_job(rid)
    assert job["state"] == "QUEUED" and "KmsUnavailable" in job["last_error"]
    delay = (job["run_after"] - job["updated_at"]).total_seconds()
    assert 899 <= delay <= 901                                      # min(900, 30 * 2 ** min(attempts, 5))
    assert job["attempts"] <= 5                                     # KMS không ăn vào số lần thử của lỗi khác
    assert await flow.seal_state_db(rid) == "SEAL_PENDING"


async def test_admin_status_reports_seal_health(flow, flaky_signer):
    st = await flow.admin_status()
    assert (st["seal_pending"], st["seal_key"], st["org"]) == (0, "none", "ok")
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer)
    assert (await flow.admin_status())["seal_pending"] == 1
    flaky_signer.fail = False
    await flow.run_worker_until_idle(signer=flaky_signer)
    assert await flow.seal_state_db(rid) == "SEALED"
    st = await flow.admin_status()
    assert (st["seal_pending"], st["seal_key"], st["org"]) == (0, "ok", "ok")
    state = flow.api.app.state
    good = state.settings
    state.settings = good.model_copy(update={"org_name": ORG_NAME_DEFAULT})
    try:
        assert (await flow.admin_status())["org"] == "down: not configured"
    finally:
        state.settings = good


async def test_revoke_validates_body_and_needs_if_match(flow):
    rid = await flow.sealed_record()
    assert (await flow.revoke(rid, as_="p1", reason_code="vi_thich")).status_code == 422
    assert (await flow.revoke(rid, as_="p1", note="x" * 501)).status_code == 422
    assert (await flow.revoke(rid, as_="p1", note="")).status_code == 422
    r = await flow.api.post(f"{URL}/{rid}:revoke", json={"reason_code": "superseded"},
                            headers=headers_for("p1"))
    assert r.status_code == 428
    r = await flow.revoke(rid, as_="p1", reason_code="legal_order")
    assert r.status_code == 200 and r.json()["seal_state"] == "REVOKED"
    assert r.headers["ETag"] == f'"{r.json()["version"]}"'
    assert await flow.count_ledger("record.revoked", subject=await flow.seal_id_of(rid)) == 1


async def test_erase_open_record_then_edit_gets_new_salt(flow):
    rid = await flow.new_record("a1", {"title": "Hồ sơ", "cccd": "001099012345"})
    old = await flow.salt_of(rid)
    r = await flow.erase_pii(rid, ["cccd"], "purpose_completed", as_="p1")
    assert r.status_code == 200 and r.headers["ETag"] == f'"{r.json()["version"]}"'
    assert await flow.salt_of(rid) is None and "cccd" not in await flow.raw_data(rid)
    assert (await flow.patch(rid, {"title": "Hồ sơ sửa"}, as_="a1")).status_code == 200
    new = await flow.salt_of(rid)
    assert new is not None and new != old


async def test_erase_is_repeatable_and_needs_current_version(flow):
    rid = await flow.sealed_record(data={"title": "QĐ thử", "cccd": "001099012345"})
    assert (await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")).status_code == 200
    first = await flow.raw_data(rid)
    assert (await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")).status_code == 200
    assert await flow.raw_data(rid) == first and await flow.count("pii_erasures", rid) == 2
    stale = await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1",
                                 version=await flow.version(rid) - 1)
    assert stale.status_code == 409 and stale.json()["type"].endswith("/version-conflict")
    for bad in ([], ["cccd", "cccd"], "cccd"):
        assert (await flow.erase_pii(rid, bad, "data_subject_request", as_="p1")).status_code == 422


async def test_erase_on_seal_pending_is_409(flow, flaky_signer):
    flaky_signer.fail = True
    rid = await flow.approved_record(signer=flaky_signer, data={"title": "QĐ", "cccd": "001099012345"})
    r = await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")
    assert r.status_code == 409 and r.json()["type"].endswith("/seal-pending")


async def test_erase_on_disabled_app_is_404(flow):
    rid = await flow.sealed_record()
    await flow.disable_app()
    r = await flow.erase_pii(rid, ["cccd"], "data_subject_request", as_="p1")
    assert r.status_code == 404 and r.json()["type"].endswith("/app-not-active")


async def test_seal_record_is_idempotent_and_refuses_other_states(flow):
    rid = await flow.sealed_record()
    out = await flow.seal_inline(rid)
    assert out.state == "SEALED" and out.seal_id == await flow.seal_id_of(rid)
    assert await flow.count("seals", rid) == 1
    open_rid = await flow.new_record("a1")
    with pytest.raises(SealStateError):
        await flow.seal_inline(open_rid)


# ---------- Fix vòng 1 ----------

UNCONFIGURED = [ORG_NAME_DEFAULT, "", "  ", "changeme-ten-to-chuc", "ChangeMe x"]


@pytest.mark.parametrize("name", UNCONFIGURED)
async def test_unconfigured_org_name_blocks_r1_and_seal_record(flow, name):     # fix 1
    bad = flow.settings_with(org_name=name)
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    state = flow.api.app.state
    good, state.settings = state.settings, bad
    try:
        r = await flow.complete_task("approve", rid, "approve", as_="p1")
    finally:
        state.settings = good
    assert r.status_code == 503 and r.json()["type"].endswith("/org-not-configured")
    pending = await flow.pending_record()
    with pytest.raises(OrgNotConfigured):                     # bỏ qua R-1: bản ghi đã SEAL_PENDING
        await flow.seal_inline(pending, settings=bad)
    assert await flow.count("key_statements") == 0 and await flow.count("seals", pending) == 0
    state.settings = bad
    try:
        assert (await flow.admin_status())["org"] == "down: not configured"
    finally:
        state.settings = good


async def test_seal_record_raises_seal_key_expired(flow):                       # fix 2 (m1)
    await flow.sealed_record()
    [row] = await flow.key_statements()
    late = parse_rfc3339(row["statement"]["valid_until"]) + timedelta(seconds=1)
    rid = await flow.pending_record()
    with pytest.raises(SealKeyExpired):
        await flow.seal_inline(rid, now=late)
    assert await flow.seal_state_db(rid) == "SEAL_PENDING" and await flow.count("seals", rid) == 0


async def _assert_job_waits(flow, rid: str, exc_name: str) -> None:
    job = await flow.seal_job(rid)
    assert job["state"] == "QUEUED" and job["last_error"].startswith(exc_name), dict(job)
    assert job["run_after"] > datetime.now(UTC)
    assert await flow.seal_state_db(rid) == "SEAL_PENDING"


async def test_job_waits_on_expired_key_statement(flow, local_signer):          # fix 2 (m1)
    rid = await flow.pending_record()
    past = datetime.now(UTC) - timedelta(days=2)
    pk = (await local_signer.public_keys())["seal-key"][1]
    st = build_statement(flow.settings_with(seal_key_validity_days=1), version=1, public_key=pk,
                         valid_from=past.strftime("%Y-%m-%dT%H:%M:%SZ"))
    await flow.conn.execute("INSERT INTO key_statements(key, version, statement, statement_sha256)"
                            " VALUES ('seal-key', 1, $1, $2)",
                            json.dumps(st), sha256_hex(canonical_bytes(st)))
    await flow.run_worker_until_idle()
    await _assert_job_waits(flow, rid, "SealKeyExpired")


async def test_job_waits_on_unconfigured_org(flow):                              # fix 2 (m1)
    rid = await flow.pending_record()
    await flow.run_worker_until_idle(settings=flow.settings_with(org_name="changeme-ten-to-chuc"))
    await _assert_job_waits(flow, rid, "OrgNotConfigured")
    assert await flow.count("key_statements") == 0


class _LedgerLockProbe:
    """Signer bọc ``local_signer``: lúc ký thật, ghi lại có phiên nào đang giữ khóa advisory của ledger
    không."""

    def __init__(self, inner, pool) -> None:
        self.inner, self.pool, self.held_during_sign = inner, pool, []

    async def public_keys(self):
        return await self.inner.public_keys()

    async def sign(self, key, data, *, key_version=None):
        from dxos_core.ledger.log import LEDGER_LOCK_KEY

        self.held_during_sign.append(await self.pool.fetchval(
            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND objid=$1",
            LEDGER_LOCK_KEY))
        return await self.inner.sign(key, data, key_version=key_version)


async def test_key_published_after_signing_and_before_sealed_leaf(flow, local_signer):   # fix 3 (m2)
    rid = await flow.pending_record()
    probe = _LedgerLockProbe(local_signer, flow.db)
    assert (await flow.seal_inline(rid, signer=probe)).state == "SEALED"
    assert probe.held_during_sign == [0]                      # không giữ khóa ledger khi gọi KMS
    [published] = await flow.ledger_entries("key.published")
    row = await flow.seal_row(rid)
    assert published.idx + 1 == row["leaf_index"]             # key.published rồi ngay sau là record.sealed


async def test_concurrent_first_seal_is_not_misreported_expired(flow, local_signer):     # fix 4 (m3)
    """Bên tạo tuyên bố (valid_from = T1) commit trong lúc bên kia đã lấy thời điểm T0 < T1 và đang chờ
    LOCK_KEYSTMT: bên chờ phải lấy lại issued_at sau khi có tuyên bố, không được báo hết hạn."""
    rid = await flow.pending_record()
    pk = (await local_signer.public_keys())["seal-key"][1]
    async with flow.db.acquire() as holder:
        tx = holder.transaction()
        await tx.start()
        await holder.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEYSTMT)
        sealing = asyncio.create_task(flow.seal_inline(rid))
        for _ in range(500):                                  # chờ bên niêm phong xếp hàng ở khóa
            if await flow.db.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory'"
                                      " AND NOT granted AND objid=$1", LOCK_KEYSTMT):
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("bên niêm phong không chờ LOCK_KEYSTMT")
        await asyncio.sleep(1.2)                              # T1 muộn hơn T0 ít nhất một giây
        t1 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        st = build_statement(flow.settings, version=1, public_key=pk, valid_from=t1)
        await holder.execute("INSERT INTO key_statements(key, version, statement, statement_sha256)"
                             " VALUES ('seal-key', 1, $1, $2)",
                             json.dumps(st), sha256_hex(canonical_bytes(st)))
        await tx.commit()
    out = await sealing
    assert out.state == "SEALED"
    assert parse_rfc3339((await flow.seal_row(rid))["payload"]["issued_at"]) >= parse_rfc3339(t1)


async def test_revoke_fails_closed_when_sealed_manifest_is_missing(flow, monkeypatch):  # fix 5 (m4)
    from dxos_core.seal import service

    rid = await flow.sealed_record()

    async def missing(conn, app_id, version):
        return None

    monkeypatch.setattr(service, "get_version", missing)
    assert (await flow.revoke(rid, as_="p1")).status_code == 404
    assert await flow.last_denied_reason() == "not_revoker"
    assert await flow.seal_status(rid) == "VALID"


async def test_seal_key_status_follows_highest_kms_version(flow, local_signer):          # fix 7 (m7)
    await flow.sealed_record()
    assert (await flow.admin_status())["seal_key"] == "ok"
    local_signer.rotate("seal-key")                           # v2 chưa có tuyên bố
    assert (await flow.admin_status())["seal_key"] == "none"
    await flow.sealed_record()                                # lần niêm phong đầu bằng v2 tạo tuyên bố
    assert (await flow.admin_status())["seal_key"] == "ok"
    assert [r["version"] for r in await flow.key_statements()] == [1, 2]


# ---------- rà soát cuối Plan 02, m3/m5: tuyên bố khóa luôn đọc qua bước kiểm; health khi KMS lỗi ----------
async def _tampered_statement(flow, local_signer, version: int = 1) -> None:
    """Hàng ``key_statements`` đúng khóa công khai, còn hạn, nhưng ``statement_sha256`` sai (bị sửa)."""
    pk = (await local_signer.public_keys())["seal-key"][version]
    st = build_statement(flow.settings, version=version, public_key=pk,
                         valid_from=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    await flow.conn.execute("INSERT INTO key_statements(key, version, statement, statement_sha256)"
                            " VALUES ('seal-key', $1, $2, $3)", version, json.dumps(st), "0" * 64)


async def test_seal_refuses_a_tampered_key_statement(flow, local_signer, caplog):
    rid = await flow.pending_record()
    await _tampered_statement(flow, local_signer)
    with pytest.raises(KeyStatementInvalid):
        await flow.seal_inline(rid)
    caplog.clear()
    await flow.run_worker_until_idle()
    await _assert_job_waits(flow, rid, "KeyStatementInvalid")
    assert any(r.levelname == "ERROR" and "KeyStatementInvalid" in r.getMessage() for r in caplog.records)
    assert await flow.count("seals", rid) == 0 and await flow.count("key_statements") == 1   # không INSERT


async def test_r1_refuses_a_tampered_key_statement(flow, local_signer):
    rid = await flow.reviewed_record(author="a1", reviewer="r1")
    await _tampered_statement(flow, local_signer)
    r = await flow.complete_task("approve", rid, "approve", as_="p1")
    assert r.status_code == 503 and r.json()["type"].endswith("/key-statement-invalid"), r.text
    assert await flow.last_denied_reason() == "key_statement_invalid"
    assert await flow.task_exists("approve", rid)                              # Flowable chưa bị gọi


async def test_health_seal_key_invalid_and_unknown(flow, local_signer):
    await _tampered_statement(flow, local_signer)
    assert (await flow.admin_status())["seal_key"] == "invalid"
    await flow.owner_bypass("DELETE FROM core.key_statements")                # bảng chỉ-thêm: bỏ hàng giả
    await flow.sealed_record()                                                 # tuyên bố thật, còn hạn
    assert (await flow.admin_status())["seal_key"] == "ok"
    state = flow.api.app.state
    good = state.signer
    state.signer = UnreachableSigner()
    try:
        assert (await flow.admin_status())["seal_key"] == "unknown"           # không báo "ok" cũ
    finally:
        state.signer = good
