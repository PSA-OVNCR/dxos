# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bản che dạng ảnh, ``variant=redacted``, khóa bản gốc và trạng thái PII trong danh sách tệp
(Plan 04 Task 5; S1; P4-D4, P4-D5; quyết định R17). Dùng ``test-app``; số trong tệp mẫu đều hư cấu.

Ba người dùng: ``member1`` (tải lên, chủ bản ghi), ``reader1`` chỉ ``read``, ``rev1`` có thêm ``reveal_pii``.
"""

import asyncio
import hashlib
import json

import pypdfium2 as pdfium
import pytest
from dxos_core import worker
from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job
from dxos_core.objects.storage import ObjectStore
from dxos_core.pii.job import PII_JOB, REDACT_JOB, process_pii_job
from dxos_core.registry.store import save_manifest
from dxos_core.registry.validator import validate_manifest
from dxos_core.settings import read_secret
from dxos_proof.canonical import canonical_bytes, sha256_hex
from helpers.api import running_api, tok
from helpers.files import fixture
from helpers.make_pii_pdf import build_blank_pages_pdf
from helpers.manifests import load

pytestmark = pytest.mark.integration

URL = "/api/v1/apps/test-app/collections/item/records"
TYPES = ["CCCD", "PHONE", "BANK_ACCOUNT"]
MEMBER = tok("member1", "app:test-app:member")
READER = tok("reader1", "app:test-app:reader")
REVIEWER = tok("rev1", "app:test-app:reviewer")
OUTSIDER = tok("member2", "app:test-app:member")           # có role nhưng không phải chủ bản ghi


async def _install(conn, *, detect: list[str], version: str = "0.1.0") -> None:
    raw = load("test-app")
    raw["app"]["version"] = version
    raw["roles"].append("reader")
    raw["collections"]["item"]["access"]["read"] = ["owner", "role:reviewer", "role:reader"]
    raw["policies"]["pii"]["document_detect"] = detect
    await save_manifest(conn, validate_manifest(raw), raw, "ACTIVE", "seed")


@pytest.fixture
async def env(s3_settings, core_conn, core_dsn, test_jwks):
    await _install(core_conn, detect=TYPES)
    pool = await create_pool(core_dsn)
    try:
        async with running_api(s3_settings) as api:
            ctx = WorkerContext(pool=pool, store=ObjectStore(s3_settings), settings=s3_settings,
                                hmac_key=read_secret(s3_settings.actor_hmac_key_file).encode())
            yield api, ctx
    finally:
        await pool.close()


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


async def _run(ctx, *, limit: int = 10) -> int:
    ran = 0
    while ran < limit and await worker.run_once(ctx):
        ran += 1
    return ran


async def _scanned(api, ctx, data: bytes, rid: str | None = None) -> tuple[str, str]:
    rid, sha = await _upload(api, data, rid)
    await _run(ctx)
    return rid, sha


def _get(api, sha: str, who: dict, variant: str | None = None):
    suffix = "" if variant is None else f"?variant={variant}"
    return api.get(f"/api/v1/objects/{sha}{suffix}", headers=who)


async def _last_denied(conn) -> str | None:
    """``reason`` của lá ``policy.denied`` mới nhất (đọc ngược qua ``body_sha256``)."""
    digest = await conn.fetchval(
        "SELECT body_sha256 FROM ledger_entries WHERE type='policy.denied' ORDER BY idx DESC LIMIT 1")
    for reason in ("pii_original", "not_in_access_list", "no_app_role"):
        for action, extra in (("reveal_pii", {}), ("read", {"collection": "item"})):
            if digest == sha256_hex(canonical_bytes({"action": action, "reason": reason, **extra})):
                return f"{action}:{reason}"
    return None


def _has_text(pdf: bytes) -> list[bool]:
    doc = pdfium.PdfDocument(pdf)
    try:
        return [bool(doc[i].get_textpage().get_text_range().strip()) for i in range(len(doc))]
    finally:
        doc.close()


async def _scan_row(conn, sha: str):
    return await conn.fetchrow(
        "SELECT s.status, s.findings, r.redacted_sha256 FROM pii_scans s"
        " LEFT JOIN pii_redactions r ON r.sha256 = s.sha256 WHERE s.sha256=$1", sha)


async def _redacted_of(conn, sha: str) -> str | None:
    return await conn.fetchval("SELECT redacted_sha256 FROM pii_redactions WHERE sha256=$1", sha)


async def _redacted_refs(conn, red: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT record_id::text AS r FROM object_refs WHERE sha256=$1 AND role='redacted'", red)
    return sorted(r["r"] for r in rows)


async def _review(api, rid: str) -> None:
    etag = (await api.get(f"{URL}/{rid}", headers=REVIEWER)).headers["etag"]
    r = await api.post(f"{URL}/{rid}:pii-review", headers={**REVIEWER, "If-Match": etag})
    assert r.status_code == 200, r.text


async def _pii(api, rid: str, who: dict = READER) -> list[dict | None]:
    r = await api.get(f"{URL}/{rid}/attachments", headers=who)
    assert r.status_code == 200, r.text
    return [item["pii"] for item in r.json()["items"]]


# ---------------------------------------------------------------- tải xuống

async def test_reader_gets_redacted_not_original(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    count = "SELECT count(*) FROM ledger_entries WHERE type='policy.denied'"
    denied = await core_conn.fetchval(count)
    r = await _get(api, sha, READER, "original")
    assert r.status_code == 404
    assert await core_conn.fetchval(count) == denied + 1
    assert await _last_denied(core_conn) == "reveal_pii:pii_original"
    for variant in (None, "original"):                       # mặc định cũng là original
        assert (await _get(api, sha, READER, variant)).status_code == 404
    r = await _get(api, sha, READER, "redacted")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.content[:5] == b"%PDF-"
    assert _has_text(r.content) == [False, False]
    assert r.content != fixture("pii-fictional.pdf")


async def test_reviewer_gets_both(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    original = await _get(api, sha, REVIEWER, "original")
    assert original.status_code == 200 and original.content == fixture("pii-fictional.pdf")
    redacted = await _get(api, sha, REVIEWER, "redacted")
    assert redacted.status_code == 200 and _has_text(redacted.content) == [False, False]
    assert await core_conn.fetchval("SELECT count(*) FROM ledger_entries WHERE type='object.read'") == 2


async def test_owner_without_reveal_pii_cannot_download_own_original(api, ctx):
    """P4-D4: người tải lên không có ``reveal_pii`` cũng không tải lại được bản gốc của mình."""
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert (await _get(api, sha, MEMBER, "original")).status_code == 404
    assert (await _get(api, sha, MEMBER, "redacted")).status_code == 200


async def test_no_findings_original_unchanged(api, ctx, core_conn):
    clean = fixture("clean-text.pdf")
    rid, sha = await _scanned(api, ctx, clean)
    scan = await _scan_row(core_conn, sha)
    assert (scan["status"], scan["findings"], scan["redacted_sha256"]) == ("DONE", 0, None)
    r = await _get(api, sha, READER, "original")
    assert r.status_code == 200 and r.content == clean
    assert (await _get(api, sha, READER)).status_code == 200
    assert (await _get(api, sha, READER, "redacted")).status_code == 404
    assert await core_conn.fetchval("SELECT count(*) FROM object_refs WHERE role='redacted'") == 0
    assert await _pii(api, rid) == [{"status": "DONE", "findings": 0, "redacted": False}]


async def test_unknown_variant_404(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    for variant in ("thumbnail", "Original", "REDACTED", "", "original,redacted", "../original"):
        for who in (READER, REVIEWER):
            assert (await _get(api, sha, who, variant)).status_code == 404, variant


async def test_redacted_needs_read_like_original(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert (await _get(api, sha, OUTSIDER, "redacted")).status_code == 404
    assert await _last_denied(core_conn) == "read:not_in_access_list"
    assert (await _get(api, sha, OUTSIDER, "original")).status_code == 404
    assert await _last_denied(core_conn) == "read:not_in_access_list"      # không phải pii_original


async def test_sha_of_the_redacted_copy_is_not_a_download_key(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    red = await _redacted_of(core_conn, sha)
    for variant in (None, "original", "redacted"):
        assert (await _get(api, red, REVIEWER, variant)).status_code == 404


# ---------------------------------------------------------------- R17: khóa khi chưa chắc không có PII

async def test_too_large_file_original_stays_locked(api, ctx, core_conn):
    rid, sha = await _scanned(api, ctx, build_blank_pages_pdf(201))
    assert (await core_conn.fetchval("SELECT status FROM pii_scans WHERE sha256=$1", sha)) == "TOO_LARGE"
    assert (await _get(api, sha, READER, "original")).status_code == 404
    assert await _last_denied(core_conn) == "reveal_pii:pii_original"
    assert (await _get(api, sha, READER, "redacted")).status_code == 404       # không dựng bản che
    assert (await _get(api, sha, REVIEWER, "original")).status_code == 200
    assert await _pii(api, rid) == [{"status": "TOO_LARGE", "findings": 0, "redacted": False}]


async def test_not_yet_scanned_original_stays_locked(api, ctx, core_conn):
    rid, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run(ctx, limit=1)                                  # CLEAN nhưng pii_detect chưa chạy
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans") == 0
    assert (await _get(api, sha, READER, "original")).status_code == 404
    assert await _last_denied(core_conn) == "reveal_pii:pii_original"
    assert (await _get(api, sha, READER, "redacted")).status_code == 404
    assert (await _get(api, sha, REVIEWER, "original")).status_code == 200
    assert await _pii(api, rid) == [{"status": "PENDING", "findings": 0, "redacted": False}]


async def test_failed_scan_original_stays_locked(api, ctx, core_conn, monkeypatch):
    from dxos_core.pii import job

    def boom(*a, **k):
        raise pdfium.PdfiumError("giả lập lỗi PDFium")

    monkeypatch.setattr(job, "extract_pages", boom)
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert (await core_conn.fetchval("SELECT status FROM pii_scans WHERE sha256=$1", sha)) == "FAILED"
    assert (await _get(api, sha, READER, "original")).status_code == 404
    assert (await _get(api, sha, READER, "redacted")).status_code == 404
    assert (await _get(api, sha, REVIEWER, "original")).status_code == 200
    assert await _pii(api, rid) == [{"status": "FAILED", "findings": 0, "redacted": False}]


async def _redact_jobs(conn) -> list[str]:
    rows = await conn.fetch("SELECT state FROM jobs WHERE kind=$1 ORDER BY id", REDACT_JOB)
    return [r["state"] for r in rows]


async def test_redaction_failure_keeps_original_locked_then_retry_job_repairs_it(
        api, ctx, core_conn, monkeypatch):
    """R18b: dựng bản che lỗi thì quét vẫn ghi DONE + phát hiện, bản gốc vẫn khóa, việc pii_redact thử lại."""
    from dxos_core.pii import job

    def boom(*a, **k):
        raise pdfium.PdfiumError("giả lập lỗi dựng bản che")

    monkeypatch.setattr(job, "redact_pdf", boom)
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    scan = await _scan_row(core_conn, sha)
    assert (scan["status"], scan["findings"], scan["redacted_sha256"]) == ("DONE", 3, None)
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings WHERE sha256=$1", sha) == 3
    row = await core_conn.fetchrow("SELECT state, attempts, last_error FROM jobs WHERE kind=$1", REDACT_JOB)
    assert (row["state"], row["attempts"]) == ("QUEUED", 1)     # worker đã thử một lần, lỗi, đang chờ backoff
    assert "PdfiumError" in row["last_error"]
    assert (await _get(api, sha, READER, "original")).status_code == 404
    assert (await _get(api, sha, READER, "redacted")).status_code == 404
    assert (await _get(api, sha, REVIEWER, "original")).status_code == 200
    assert await _pii(api, rid) == [{"status": "DONE", "findings": 3, "redacted": False}]
    assert await _redacted_of(core_conn, sha) is None
    monkeypatch.undo()                                          # hết lỗi
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", REDACT_JOB)
    await _run(ctx, limit=1)
    assert await _redact_jobs(core_conn) == ["DONE"]
    assert await _redacted_of(core_conn, sha)
    assert await _pii(api, rid) == [{"status": "DONE", "findings": 3, "redacted": True}]
    r = await _get(api, sha, READER, "redacted")
    assert r.status_code == 200 and _has_text(r.content) == [False, False]
    assert (await _get(api, sha, READER, "original")).status_code == 404       # vẫn khóa


async def test_redact_job_uses_stored_findings_not_a_new_scan(api, ctx, core_conn, monkeypatch):
    from dxos_core.pii import job

    monkeypatch.setattr(job, "redact_pdf", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    monkeypatch.undo()

    def no_scan(*a, **k):
        raise AssertionError("pii_redact không được dò lại")

    monkeypatch.setattr(job, "extract_pages", no_scan)
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", REDACT_JOB)
    await _run(ctx, limit=1)
    assert await _redacted_of(core_conn, sha)
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 1


async def test_pii_review_requeues_redaction_for_a_scan_without_one_exactly_once(
        api, ctx, core_conn, monkeypatch):
    """Hàng từ trước tính năng (DONE + phát hiện, không có bản che, không có việc) được :pii-review sửa."""
    from dxos_core.pii import job

    monkeypatch.setattr(job, "redact_pdf", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    monkeypatch.undo()
    await core_conn.execute("DELETE FROM jobs WHERE kind=$1", REDACT_JOB)          # mất việc / việc đã FAILED
    assert await _redact_jobs(core_conn) == []
    for _ in range(2):
        await _review(api, rid)
        assert await _redact_jobs(core_conn) == ["QUEUED"]                          # lần hai không xếp thêm
    await _run(ctx, limit=1)
    assert await _redacted_of(core_conn, sha)
    await _review(api, rid)
    assert await _redact_jobs(core_conn) == ["DONE"]                        # đã có bản che: không xếp lại


async def test_memory_error_in_redaction_is_not_swallowed(api, ctx, core_conn, monkeypatch):
    """R18b: MemoryError làm việc pii_detect lỗi để được thử lại, không ghi quét hay để lại thiếu bản che."""
    from dxos_core.pii import job

    def oom(*a, **k):
        raise MemoryError

    monkeypatch.setattr(job, "redact_pdf", oom)
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run(ctx, limit=2)
    row = await core_conn.fetchrow("SELECT state, attempts, last_error FROM jobs WHERE kind=$1", PII_JOB)
    assert (row["state"], row["attempts"]) == ("QUEUED", 1) and "MemoryError" in row["last_error"]
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 0
    assert await _redact_jobs(core_conn) == []
    monkeypatch.undo()
    await core_conn.execute("UPDATE jobs SET run_after=now() WHERE kind=$1", PII_JOB)
    await _run(ctx)
    assert await _redacted_of(core_conn, sha)


async def test_collection_without_document_detect_is_unchanged(api, ctx, core_conn):
    await _install(core_conn, detect=[], version="0.2.0")
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans") == 0
    r = await _get(api, sha, READER, "original")
    assert r.status_code == 200 and r.content == fixture("pii-fictional.pdf")
    assert (await _get(api, sha, READER, "redacted")).status_code == 404
    assert await _pii(api, rid) == [None]


async def test_manifest_with_only_undetectable_types_does_not_lock(api, ctx, core_conn):
    """EMAIL và NAME hợp lệ trong manifest nhưng chưa có bộ dò: không có lần dò nào, nên không khóa."""
    await _install(core_conn, detect=["EMAIL", "NAME"], version="0.2.0")
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert (await _get(api, sha, READER, "original")).status_code == 200
    assert await _pii(api, rid) == [None]


# ---------------------------------------------------------------- R19: luôn dò mọi loại

def _black_under(pdf: bytes, page_no: int, boxes: list[list[float]]) -> bool:
    doc = pdfium.PdfDocument(pdf)
    try:
        page = doc[page_no - 1]
        height = page.get_size()[1]
        bitmap = page.render(scale=150 / 72)
        buf, stride = bytes(bitmap.buffer), bitmap.stride
    finally:
        doc.close()
    for left, bottom, right, top in boxes:
        x0, x1 = int(left * 150 / 72) + 1, int(right * 150 / 72) - 1
        y0, y1 = int((height - top) * 150 / 72) + 1, int((height - bottom) * 150 / 72) - 1
        for y in range(y0, y1):
            for x in range(x0, x1):
                if max(buf[y * stride + 3 * x:y * stride + 3 * x + 3]) >= 16:
                    return False
    return True


async def test_scan_covers_every_type_whatever_the_manifest_asks(api, ctx, core_conn):
    """R19: manifest chỉ xin CCCD, tệp có CCCD + SĐT + STK: vẫn 3 phát hiện và bản che phủ cả ba."""
    await _install(core_conn, detect=["CCCD"], version="0.2.0")
    rid, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    payload = json.loads(await core_conn.fetchval("SELECT payload FROM jobs WHERE kind=$1", PII_JOB))
    assert payload == {"sha256": sha}
    rows = await core_conn.fetch("SELECT type, page, bbox FROM pii_findings WHERE sha256=$1", sha)
    assert sorted(r["type"] for r in rows) == ["BANK_ACCOUNT", "CCCD", "PHONE"]
    assert await _pii(api, rid) == [{"status": "DONE", "findings": 3, "redacted": True}]
    red = (await _get(api, sha, READER, "redacted")).content
    for r in rows:
        assert _black_under(red, r["page"], json.loads(r["bbox"])), r["type"]
    assert (await _get(api, sha, READER, "original")).status_code == 404


async def test_old_payload_with_types_is_accepted_and_ignored(api, ctx, core_conn):
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run(ctx, limit=1)
    row = await core_conn.fetchrow("SELECT id, kind FROM jobs WHERE kind=$1", PII_JOB)
    await process_pii_job(ctx, Job(row["id"], row["kind"], {"sha256": sha, "types": ["CCCD"]}, 1))
    assert await core_conn.fetchval("SELECT count(*) FROM pii_findings WHERE sha256=$1", sha) == 3


# ---------------------------------------------------------------- hàng dữ liệu của bản che

async def test_redacted_object_rows_and_refs_for_every_record(api, ctx, core_conn):
    rid1, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    rid2, _ = await _scanned(api, ctx, fixture("pii-fictional.pdf"))          # cùng tệp, bản ghi khác (CAS)
    assert rid1 != rid2
    red = await _redacted_of(core_conn, sha)
    assert red and red != sha
    obj = await core_conn.fetchrow(
        "SELECT status, scanner_version, mime_sniffed, size FROM objects WHERE sha256=$1", red)
    assert (obj["status"], obj["scanner_version"], obj["mime_sniffed"]) == (
        "CLEAN", "dxos-redact/1", "application/pdf")
    data = await asyncio.to_thread(ctx.store.read_object, red)                  # kho CAS, đã kiểm băm
    assert len(data) == obj["size"] and hashlib.sha256(data).hexdigest() == red
    assert await _redacted_refs(core_conn, red) == sorted([rid1, rid2])
    original_refs = "SELECT count(*) FROM object_refs WHERE sha256=$1 AND role='original'"
    assert await core_conn.fetchval(original_refs, red) == 0
    assert (await _get(api, sha, READER, "redacted")).status_code == 200


async def test_record_uploading_a_scanned_file_later_also_gets_the_redacted_ref(api, ctx, core_conn):
    rid1, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    red = await _redacted_of(core_conn, sha)
    rid2, _ = await _scanned(api, ctx, fixture("pii-fictional.pdf"))      # đã dò rồi: không có việc dò mới
    assert await core_conn.fetchval("SELECT count(*) FROM jobs WHERE kind=$1", PII_JOB) == 1
    assert await _redacted_refs(core_conn, red) == sorted([rid1, rid2])


async def test_concurrent_jobs_make_one_redacted_copy(api, ctx, core_conn):
    _, sha = await _upload(api, fixture("pii-fictional.pdf"))
    await _run(ctx, limit=1)
    row = await core_conn.fetchrow("SELECT id, kind, payload FROM jobs WHERE kind=$1", PII_JOB)
    payload = json.loads(row["payload"])
    await asyncio.gather(process_pii_job(ctx, Job(row["id"], row["kind"], payload, 1)),
                         process_pii_job(ctx, Job(row["id"], row["kind"], payload, 1)))
    assert await core_conn.fetchval("SELECT count(*) FROM pii_scans WHERE sha256=$1", sha) == 1
    assert await core_conn.fetchval("SELECT count(*) FROM objects WHERE scanner_version='dxos-redact/1'") == 1
    assert await core_conn.fetchval("SELECT count(*) FROM object_refs WHERE role='redacted'") == 1
    red = await _redacted_of(core_conn, sha)
    assert await core_conn.fetchval("SELECT sha256 FROM object_refs WHERE role='redacted'") == red


async def test_ledger_has_no_pii_and_redacted_read_is_marked(api, ctx, core_conn):
    _, sha = await _scanned(api, ctx, fixture("pii-fictional.pdf"))
    assert (await _get(api, sha, READER, "redacted")).status_code == 200
    entry = await core_conn.fetchrow("SELECT * FROM ledger_entries WHERE type='object.read'")
    rid = await core_conn.fetchval("SELECT record_id::text FROM object_refs WHERE role='original'")
    assert entry["subject"] == sha
    assert entry["body_sha256"] == sha256_hex(canonical_bytes(
        {"sha256": sha, "record_id": rid, "variant": "redacted"}))


# ---------------------------------------------------------------- danh sách tệp

async def test_attachment_list_shows_pii_state(api, ctx, core_conn):
    rid, sha = await _upload(api, fixture("pii-fictional.pdf"))
    r = await api.get(f"{URL}/{rid}/attachments", headers=READER)
    assert r.json()["items"][0]["status"] == "STAGING" and r.json()["items"][0]["pii"] is None
    await _run(ctx, limit=1)                                  # CLEAN, chưa dò
    assert await _pii(api, rid) == [{"status": "PENDING", "findings": 0, "redacted": False}]
    await _run(ctx)
    assert await _pii(api, rid) == [{"status": "DONE", "findings": 3, "redacted": True}]
    item = (await api.get(f"{URL}/{rid}/attachments", headers=READER)).json()["items"][0]
    assert item["sha256"] == sha and set(item["pii"]) == {"status", "findings", "redacted"}


async def test_rejected_upload_has_no_pii_state(api, ctx, core_conn):
    rid, _ = await _upload(api, b"khong phai pdf")
    await _run(ctx)
    items = (await api.get(f"{URL}/{rid}/attachments", headers=READER)).json()["items"]
    assert [(i["status"], i["pii"]) for i in items] == [("REJECTED", None)]
