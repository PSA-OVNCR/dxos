# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``load_guard_input``: mọi truy vấn DB của guard (Plan 02 Task 5). Người gọi giữ khóa hàng FOR SHARE."""

import pytest
from dxos_core.records.digest import data_digest
from dxos_core.workflow.guards import evaluate, load_guard_input, review_digest
from helpers.manifests import P

pytestmark = pytest.mark.integration


async def _load(conn, kw, **over):
    """Giữ ``FOR SHARE`` trên hàng bản ghi như người gọi thật (spec 25.2), rồi nạp GuardInput."""
    kw = {**kw, **over}
    async with conn.transaction():
        await conn.execute("SELECT 1 FROM core.records WHERE id=$1 FOR SHARE", kw["record"]["id"])
        return await load_guard_input(conn, **kw)


async def test_load_guard_input_counts_only_clean_refs(core_conn, flow_record_with_uploads):
    # 1 CLEAN, 1 INFECTED, 1 STAGING
    gi = await _load(core_conn, flow_record_with_uploads)
    assert gi.uploads_pending == 1 and len(gi.clean_attachments) == 1
    assert gi.clean_attachments == ("c" * 64,)


async def test_load_guard_input_basic_fields(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    gi = await _load(core_conn, kw, task_assignee="rev-1")
    assert (gi.caller_sub, gi.owner_sub, gi.seal_state, gi.task_assignee) == (
        "rev-1", "author-1", "NONE", "rev-1")
    assert gi.caller_roles == frozenset({"reviewer"})                  # đã bỏ tiền tố app:test-flow:
    assert gi.data == {"title": "Hồ sơ"}
    assert gi.attachments_min == 1                                       # doc.attachments.min = 1
    assert gi.pii_required is True                                       # doc có trường cccd (pii)
    assert gi.completions == () and gi.finding_ids == () and gi.last_review_digest is None


async def test_roles_of_other_apps_are_ignored(core_conn, flow_record_with_uploads):
    p = P("rev-1", ["app:other-app:approver", "app:test-flow:author", "dxos-admin"])
    gi = await _load(core_conn, flow_record_with_uploads, p=p)
    assert gi.caller_roles == frozenset({"author"})


async def test_attachments_min_zero_and_pii_not_required_without_pii(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    spec = kw["spec"].model_copy(update={
        "attachments": None,
        "fields": {k: v for k, v in kw["spec"].fields.items() if k != "cccd"}})
    gi = await _load(core_conn, kw, spec=spec)
    assert gi.attachments_min == 0 and gi.pii_required is False


async def test_pii_required_from_document_detect_alone(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    spec = kw["spec"].model_copy(update={
        "fields": {k: v for k, v in kw["spec"].fields.items() if k != "cccd"}})
    assert (await _load(core_conn, kw, spec=spec)).pii_required is False
    pol = kw["m"].policies.pii.model_copy(update={"document_detect": ["CCCD"]})
    m = kw["m"].model_copy(update={"policies": kw["m"].policies.model_copy(update={"pii": pol})})
    assert (await _load(core_conn, kw, spec=spec, m=m)).pii_required is True


async def test_completions_limited_to_current_instance(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    # instance cũ i-old (đã kết thúc) và instance hiện tại i-now; bản ghi trỏ vào i-now
    for n, (inst, key, actor) in enumerate([("i-old", "review", "old-rev"), ("i-now", "review", "rev-1"),
                                            ("i-now", "approve", "boss")]):
        intent = await core_conn.fetchval(
            "INSERT INTO task_intents(task_id, record_id, wf_instance_id, task_key, actor_sub, actor_roles,"
            " decision) VALUES ($1, $2, $3, $4, $5, '{x}', 'approve') RETURNING id",
            f"t{n}", rid, inst, key, actor)
        await core_conn.execute(
            "INSERT INTO task_intent_outcomes(intent_id, outcome) VALUES ($1, 'completed')", intent)
        await core_conn.execute(
            "INSERT INTO task_completions(task_id, intent_id, record_id, wf_instance_id, task_key, actor_sub,"
            " decision) VALUES ($1, $2, $3, $4, $5, $6, 'approve')", f"t{n}", intent, rid, inst, key, actor)
    # chưa có instance hiện tại: rỗng
    assert (await _load(core_conn, kw)).completions == ()
    await core_conn.execute("UPDATE records SET wf_instance_id='i-now' WHERE id=$1", rid)
    record = await core_conn.fetchrow("SELECT * FROM records WHERE id=$1", rid)
    gi = await _load(core_conn, kw, record=record)
    assert gi.completions == (("review", "rev-1"), ("approve", "boss"))
    assert evaluate(["not_same_actor:review"], gi).reason == "same_actor"    # rev-1 đã làm review
    await core_conn.execute("UPDATE records SET wf_instance_id='i-old' WHERE id=$1", rid)
    record = await core_conn.fetchrow("SELECT * FROM records WHERE id=$1", rid)
    assert (await _load(core_conn, kw, record=record)).completions == (("review", "old-rev"),)


async def test_finding_ids_only_from_clean_files(core_conn, flow_record_with_uploads):
    clean, infected = "c" * 64, "f" * 64
    ids = []
    for sha in (clean, infected, clean):
        ids.append(await core_conn.fetchval(
            "INSERT INTO pii_findings(sha256, type, page) VALUES ($1, 'CCCD', 0) RETURNING id", sha))
    gi = await _load(core_conn, flow_record_with_uploads)
    assert gi.finding_ids == tuple(sorted((ids[0], ids[2])))
    assert ids[1] not in gi.finding_ids


async def test_finding_ids_of_files_of_other_records_not_counted(core_conn, flow_record_with_uploads):
    other = "9" * 64
    await core_conn.execute(
        "INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
        " VALUES ($1, 1, 'application/pdf', 'CLEAN', 'k-other')", other)
    await core_conn.execute("INSERT INTO pii_findings(sha256, type, page) VALUES ($1, 'CCCD', 0)", other)
    assert (await _load(core_conn, flow_record_with_uploads)).finding_ids == ()


async def test_redacted_refs_and_non_clean_objects_not_attachments(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    red = "e" * 64
    await core_conn.execute(
        "INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
        " VALUES ($1, 1, 'application/pdf', 'CLEAN', 'k-red')", red)
    await core_conn.execute(
        "INSERT INTO object_refs(record_id, sha256, role) VALUES ($1, $2, 'redacted')", rid, red)
    assert (await _load(core_conn, kw)).clean_attachments == ("c" * 64,)


async def test_clean_attachments_sorted(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    for sha in ("b" * 64, "0" * 64):
        await core_conn.execute(
            "INSERT INTO objects(sha256, size, mime_sniffed, status, storage_key)"
            " VALUES ($1, 1, 'application/pdf', 'CLEAN', $2)", sha, f"k-{sha[:2]}")
        await core_conn.execute(
            "INSERT INTO object_refs(record_id, sha256, role) VALUES ($1, $2, 'original')", rid, sha)
    assert (await _load(core_conn, kw)).clean_attachments == ("0" * 64, "b" * 64, "c" * 64)


async def test_last_review_digest_picks_newest(core_conn, flow_record_with_uploads):
    rid = flow_record_with_uploads["record"]["id"]
    for d in ("1" * 64, "2" * 64, "3" * 64):
        await core_conn.execute(
            "INSERT INTO pii_reviews(record_id, review_digest, reviewed_by) VALUES ($1, $2, 'rev-1')", rid, d)
    assert (await _load(core_conn, flow_record_with_uploads)).last_review_digest == "3" * 64


async def test_pii_reviewed_end_to_end(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    gi = await _load(core_conn, kw)
    assert evaluate(["pii_reviewed"], gi).reason == "pii_not_reviewed"
    d = review_digest(gi.data_digest, gi.clean_attachments, gi.finding_ids)
    await core_conn.execute(
        "INSERT INTO pii_reviews(record_id, review_digest, reviewed_by) VALUES ($1, $2, 'rev-1')", rid, d)
    assert evaluate(["pii_reviewed"], await _load(core_conn, kw)) is None
    # phát hiện mới sau lần xác nhận -> phải rà lại
    await core_conn.execute("INSERT INTO pii_findings(sha256, type, page) VALUES ($1, 'CCCD', 0)", "c" * 64)
    assert evaluate(["pii_reviewed"], await _load(core_conn, kw)).reason == "pii_not_reviewed"


async def test_data_digest_is_salted_and_stable(core_conn, flow_record_with_uploads):
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    g1 = await _load(core_conn, kw)
    g2 = await _load(core_conn, kw)
    salt = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", rid)
    assert salt is not None
    assert g1.data_digest == g2.data_digest == data_digest({"title": "Hồ sơ"}, salt)


async def test_data_digest_recreates_erased_salt(core_conn, flow_record_with_uploads):
    """Salt đã bị xóa (xóa PII): ``ensure_salt`` tạo salt mới, digest đổi nhưng vẫn ổn định sau đó."""
    kw = flow_record_with_uploads
    rid = kw["record"]["id"]
    before = (await _load(core_conn, kw)).data_digest
    await core_conn.execute("DELETE FROM record_salts WHERE record_id=$1", rid)
    g1 = await _load(core_conn, kw)
    g2 = await _load(core_conn, kw)
    salt = await core_conn.fetchval("SELECT salt FROM record_salts WHERE record_id=$1", rid)
    assert g1.data_digest == g2.data_digest == data_digest({"title": "Hồ sơ"}, salt) != before
