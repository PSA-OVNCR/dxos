# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Việc nền ``pii_detect``, bảng ``pii_scans`` và guard chờ dò xong (Plan 04 Task 4; S1; I5, P4-D2).

Dùng ``test-app`` với ``policies.pii.document_detect`` bật (bản manifest tạo trong test, không sửa tệp
fixture dùng chung). Số trong tệp mẫu đều hư cấu.
"""

import hashlib
import json
import re
from collections.abc import Mapping

import pytest
from dxos_core import worker
from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job
from dxos_core.objects.storage import ObjectStore
from dxos_core.pii.job import PII_JOB, process_pii_job
from dxos_core.registry.model import Manifest
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_core.settings import read_secret
from dxos_core.worker import MAX_ATTEMPTS
from dxos_core.workflow.guards import evaluate, load_guard_input
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.api import running_api, tok
from helpers.files import fixture
from helpers.make_pii_pdf import build_blank_pages_pdf
from helpers.manifests import P, load

pytestmark = pytest.mark.integration

URL = "/api/v1/apps/test-app/collections/item/records"
TYPES = ["CCCD", "PHONE", "BANK_ACCOUNT"]
MEMBER = tok("member1", "app:test-app:member")
REVIEWER = tok("rev1", "app:test-app:reviewer")


async def _install(conn, *, detect: list[str]) -> Manifest:
    raw = load("test-app")
    raw["policies"]["pii"]["document_detect"] = detect
    m = validate_manifest(raw)
    await save_manifest(conn, m, raw, "ACTIVE", "seed")
    return m


@pytest.fixture
async def env(s3_settings, core_conn, core_dsn, test_jwks):
    pool = await create_pool(core_dsn)
    try:
        async with running_api(s3_settings) as api:
            ctx = WorkerContext(pool=pool, store=ObjectStore(s3_settings), settings=s3_settings,
                                hmac_key=read_secret(s3_settings.actor_hmac_key_file).encode())
            yield api, ctx
    finally:
        await pool.close()


@pytest.fixture
async def detect_on(core_conn):
    return await _install(core_conn, detect=TYPES)


@pytest.fixture
def api(env):
    return env[0]


@pytest.fixture
def ctx(env):
    return env[1]


async def _upload(api, data: bytes, rid: str | None = None) -> tuple[str, str]:
    if rid is None:
        r = await api.post(URL, json={"title": "Hồ sơ"}, headers=MEMBER)
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
    r = await api.post(f"{URL}/{rid}/attachments", files={"file": ("a.pdf", data, "application/pdf")},
                       headers=MEMBER)
    assert r.status_code == 202, r.text
    return rid, hashlib.sha256(data).hexdigest()


async def _run_until_idle(ctx, *, limit: int = 10) -> int:
    """Chạy worker một vòng cho tới khi hết việc hoặc đủ ``limit`` việc; trả số việc đã chạy."""
    ran = 0
    while ran < limit and await worker.run_once(ctx):
        ran += 1
    return ran


def _no_long_digits(row: Mapping, *hex_values: str) -> bool:
    """Hàng không chứa chuỗi ≥ 8 chữ số liền nhau (sau khi bỏ các mã băm hex hợp lệ như sha256)."""
    text = str(dict(row))
    for h in hex_values:
        text = text.replace(h, "")
    return not re.search(r"\d{8,}", text)


async def _job_kinds(conn) -> list[str]:
    return [r["kind"] for r in await conn.fetch("SELECT kind FROM jobs ORDER BY id")]


async def test_clean_upload_enqueues_pii_job_only_when_manifest_asks(
        api, ctx, core_conn, detect_on):
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)                       # chỉ việc quét AV/kiểm PDF
    assert await _job_kinds(core_conn) == ["scan", PII_JOB]
    payload = await core_conn.fetchval("SELECT payload FROM jobs WHERE kind=$1", PII_JOB)
    assert json.loads(payload) == {"sha256": sha}          # R19: không còn types trong payload


async def test_manifest_without_document_detect_enqueues_nothing(api, ctx, core_conn):
    await _install(core_conn, detect=[])
    rid, _ = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx)
    await _review(api, rid)                          # :pii-review cũng không xếp việc khi manifest không khai
    assert await _job_kinds(core_conn) == ["scan"]
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans") == 0


async def _scan_pdf(api, ctx, data: bytes) -> str:
    _, sha = await _upload(api, data)
    await _run_until_idle(ctx)
    return sha


async def test_findings_rows_have_no_values(api, ctx, core_conn, detect_on):
    sha = await _scan_pdf(api, ctx, fixture("pii-fictional.pdf"))
    rows = await core_conn.fetch("SELECT * FROM pii_findings WHERE sha256=$1 ORDER BY id", sha)
    assert sorted((r["type"], r["page"]) for r in rows) == [("BANK_ACCOUNT", 2), ("CCCD", 1), ("PHONE", 1)]
    for r in rows:
        assert r["value_hmac"] is None
        boxes = r["bbox"] if isinstance(r["bbox"], list) else json.loads(r["bbox"])
        assert boxes and all(len(b) == 4 and all(isinstance(v, float) for v in b) for b in boxes)
        assert all(b[0] < b[2] and b[1] < b[3] for b in boxes)
        assert _no_long_digits(r, sha)                        # không chuỗi chữ số dài nào trong hàng
    scan = await core_conn.fetchrow("SELECT * FROM pii_scans WHERE sha256=$1", sha)
    assert (scan["status"], scan["findings"], scan["detector"]) == ("DONE", 3, "dxos-pii/1")
    assert _no_long_digits(scan, sha)
    # ledger: chỉ sha256, đếm theo loại và detector
    entry = await core_conn.fetchrow("SELECT * FROM ledger_entries WHERE type='pii.detected'")
    body = {"sha256": sha, "counts": {"CCCD": 1, "PHONE": 1, "BANK_ACCOUNT": 1}, "detector": "dxos-pii/1"}
    assert entry["subject"] == sha and entry["body_sha256"] == sha_hex(body)
    public = {k: v for k, v in dict(entry).items() if k != "leaf_hash"}      # leaf_hash là bytes băm
    assert _no_long_digits(public, sha, entry["body_sha256"])
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='pii.detected'") == 1


def sha_hex(body: dict) -> str:
    return sha256_hex(canonical_bytes(body))


async def test_rotated_page_box_is_inside_page(api, ctx, core_conn, detect_on):
    sha = await _scan_pdf(api, ctx, fixture("pii-fictional.pdf"))
    r = await core_conn.fetchrow(
        "SELECT page, bbox FROM pii_findings WHERE sha256=$1 AND type='BANK_ACCOUNT'", sha)
    assert r["page"] == 2
    boxes = r["bbox"] if isinstance(r["bbox"], list) else json.loads(r["bbox"])
    width, height = 792.0, 612.0                              # trang 2: mediabox 612x792 xoay 90°
    for left, bottom, right, top in boxes:
        assert 0 <= left < right <= width and 0 <= bottom < top <= height


async def test_too_many_pages(api, ctx, core_conn, detect_on):
    sha = await _scan_pdf(api, ctx, build_blank_pages_pdf(201))
    scan = await core_conn.fetchrow("SELECT status, findings FROM pii_scans WHERE sha256=$1", sha)
    assert (scan["status"], scan["findings"]) == ("TOO_LARGE", 0)
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings") == 0


async def test_pdfium_error_is_recorded_as_failed(api, ctx, core_conn, detect_on, monkeypatch):
    import pypdfium2 as pdfium
    from dxos_core.pii import job

    def boom(*a, **k):
        raise pdfium.PdfiumError("giả lập lỗi PDFium")

    monkeypatch.setattr(job, "extract_pages", boom)
    sha = await _scan_pdf(api, ctx, fixture("pii-fictional.pdf"))
    scan = await core_conn.fetchrow("SELECT status, findings FROM pii_scans WHERE sha256=$1", sha)
    assert (scan["status"], scan["findings"]) == ("FAILED", 0)
    assert await core_conn.fetchval("SELECT count(*) FROM jobs WHERE kind=$1 AND state='DONE'", PII_JOB) == 1


async def test_job_is_idempotent(api, ctx, core_conn, detect_on):
    sha = await _scan_pdf(api, ctx, fixture("pii-fictional.pdf"))
    job = await core_conn.fetchrow("SELECT id, kind, payload FROM jobs WHERE kind=$1", PII_JOB)
    again = Job(job["id"], job["kind"], json.loads(job["payload"]), 2)
    await process_pii_job(ctx, again)
    await process_pii_job(ctx, again)
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 1
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings WHERE sha256=$1", sha) == 3
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='pii.detected'") == 1


async def test_second_upload_of_scanned_file_does_not_enqueue_again(api, ctx, core_conn, detect_on):
    await _scan_pdf(api, ctx, fixture("pii-fictional.pdf"))
    await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx)
    assert await _job_kinds(core_conn) == ["scan", PII_JOB, "scan"]


async def _review(api, rid: str):
    etag = (await api.get(f"{URL}/{rid}", headers=REVIEWER)).headers["etag"]
    r = await api.post(f"{URL}/{rid}:pii-review", headers={**REVIEWER, "If-Match": etag})
    assert r.status_code == 200, r.text


async def _guard(conn, m: Manifest, rid: str):
    record = await conn.fetchrow("SELECT * FROM records WHERE id=$1::uuid", rid)
    async with conn.transaction():
        await conn.execute("SELECT 1 FROM core.records WHERE id=$1 FOR SHARE", record["id"])
        gi = await load_guard_input(conn, record=record, spec=m.collections["item"], m=m,
                                    p=P("rev1", ["app:test-app:reviewer"]), task_assignee=None)
    return evaluate(["pii_reviewed"], gi)


async def test_guard_waits_for_scan(api, ctx, core_conn, detect_on):
    rid, _ = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)                       # CLEAN, nhưng pii_detect chưa chạy
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans") == 0
    await _review(api, rid)                                   # vẫn ghi nhận được
    assert await core_conn.fetchval("SELECT count(*) FROM pii_reviews") == 1
    f = await _guard(core_conn, detect_on, rid)
    assert (f.guard, f.reason, f.status) == ("pii_reviewed", "pii_scan_pending", 409)
    await _run_until_idle(ctx)                                # dò xong
    f = await _guard(core_conn, detect_on, rid)
    assert f.reason == "pii_not_reviewed"        # xác nhận làm trước khi dò xong không còn giá trị
    await _review(api, rid)
    assert await _guard(core_conn, detect_on, rid) is None


async def test_failed_and_too_large_scans_still_require_a_fresh_review(api, ctx, core_conn, detect_on):
    rid, sha = await _upload(api, build_blank_pages_pdf(201))
    await _run_until_idle(ctx, limit=1)
    await _review(api, rid)                                   # xác nhận khi đang chờ
    await _run_until_idle(ctx)
    assert (await core_conn.fetchval("SELECT status FROM pii_scans WHERE sha256=$1", sha)) == "TOO_LARGE"
    assert (await _guard(core_conn, detect_on, rid)).reason == "pii_not_reviewed"
    await _review(api, rid)
    assert await _guard(core_conn, detect_on, rid) is None


async def _pii_jobs(conn) -> list[str]:
    return [r["state"] for r in await conn.fetch("SELECT state FROM jobs WHERE kind=$1 ORDER BY id", PII_JOB)]


async def test_review_requeues_a_missing_scan_once_and_guard_then_passes(api, ctx, core_conn, detect_on):
    """R16 (a): tệp CLEAN mà không có hàng pii_scans và không có việc nào (CLEAN từ trước tính năng)."""
    rid, _ = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)                       # CLEAN + việc pii_detect
    await core_conn.execute("DELETE FROM jobs WHERE kind=$1", PII_JOB)    # giả lập: chưa từng có việc
    assert await _pii_jobs(core_conn) == []
    await _review(api, rid)
    assert await _pii_jobs(core_conn) == ["QUEUED"]
    await _review(api, rid)                                   # gọi lần hai không xếp thêm
    assert await _pii_jobs(core_conn) == ["QUEUED"]
    assert (await _guard(core_conn, detect_on, rid)).reason == "pii_scan_pending"
    await _run_until_idle(ctx)
    assert await _pii_jobs(core_conn) == ["DONE"]
    assert (await _guard(core_conn, detect_on, rid)).reason == "pii_not_reviewed"
    await _review(api, rid)
    assert await _guard(core_conn, detect_on, rid) is None
    assert await _pii_jobs(core_conn) == ["DONE"]             # đã có hàng pii_scans: không xếp lại


async def test_last_failed_attempt_records_failed_scan_and_falls_back_to_manual_review(
        api, ctx, core_conn, detect_on, monkeypatch):
    """R16 (b): việc hết lượt thử thì ghi FAILED, bản ghi quay về rà tay thay vì chờ mãi."""
    rid, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)
    await _review(api, rid)                                   # làm khi việc dò còn chờ
    await core_conn.execute("UPDATE jobs SET attempts=$2 WHERE kind=$1", PII_JOB, MAX_ATTEMPTS - 1)

    def boom(_sha):
        raise OSError("giả lập S3 hỏng")

    monkeypatch.setattr(ctx.store, "read_object", boom)
    await _run_until_idle(ctx, limit=1)                       # lần thử thứ MAX_ATTEMPTS
    assert await _pii_jobs(core_conn) == ["FAILED"]
    scan = await core_conn.fetchrow("SELECT status, findings, detector FROM pii_scans WHERE sha256=$1", sha)
    assert (scan["status"], scan["findings"]) == ("FAILED", 0)
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings") == 0
    assert (await _guard(core_conn, detect_on, rid)).reason == "pii_not_reviewed"
    await _review(api, rid)
    assert await _guard(core_conn, detect_on, rid) is None


async def test_not_the_last_attempt_does_not_record_a_scan(api, ctx, core_conn, detect_on, monkeypatch):
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)

    def boom(_sha):
        raise OSError("giả lập S3 hỏng")

    monkeypatch.setattr(ctx.store, "read_object", boom)
    await _run_until_idle(ctx, limit=1)
    assert await _pii_jobs(core_conn) == ["QUEUED"]           # sẽ thử lại
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 0


async def test_concurrent_jobs_for_one_file_write_one_scan(api, ctx, core_conn, detect_on):
    """Nhánh ON CONFLICT: hai việc cùng sha chạy song song, chỉ một lần ghi thắng."""
    import asyncio
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run_until_idle(ctx, limit=1)
    row = await core_conn.fetchrow("SELECT id, kind, payload FROM jobs WHERE kind=$1", PII_JOB)
    payload = json.loads(row["payload"])
    await asyncio.gather(process_pii_job(ctx, Job(row["id"], row["kind"], payload, 1)),
                         process_pii_job(ctx, Job(row["id"], row["kind"], payload, 1)))
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 1
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings WHERE sha256=$1", sha) == 3
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='pii.detected'") == 1
