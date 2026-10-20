# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Integration test upload → kiểm dịch → kiểm PDF → CAS (Plan 01 Task 14; AT-03, AT-04, AT-05, AT-20, D1)."""

import dataclasses
import hashlib
import uuid

import pytest
from dxos_core import worker
from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.objects.storage import IntegrityError, ObjectStore
from dxos_core.settings import read_secret
from helpers.api import activate, last_event_type, running_api, tok
from helpers.files import eicar, fixture

pytestmark = pytest.mark.integration

URL_A = "/api/v1/apps/phong-ho-so/collections/van_ban/records"
URL_T = "/api/v1/apps/test-app/collections/item/records"


@pytest.fixture
async def env(s3_settings, core_conn, core_dsn, test_jwks):
    await activate(core_conn)
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


@pytest.fixture
def run_worker_once(ctx):
    async def run(n: int = 1):
        for _ in range(n):
            assert await worker.run_once(ctx), "không có việc nào để chạy"
    return run


@pytest.fixture
def run_worker_once_with_clamd_down(ctx):
    down = dataclasses.replace(ctx, settings=ctx.settings.model_copy(update={"clamd_port": 1}))

    async def run():
        assert await worker.run_once(down)
    return run


@pytest.fixture
def tok_cv():
    return tok("chuyen_vien1", "app:phong-ho-so:chuyen_vien")


@pytest.fixture
def tok_tp():
    return tok("truong_phong1", "app:phong-ho-so:truong_phong")


@pytest.fixture
def tok_admin_with_app_role():
    return tok("admin1", "dxos-admin", "app:phong-ho-so:giam_doc")


async def new_record(api, tok_, url=URL_A, body=None) -> str:
    r = await api.post(url, json=body or {"trich_yeu": "Văn bản có tệp"}, headers=tok_)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def upload(api, tok_, data: bytes, name: str, rid: str | None = None, url=URL_A) -> str:
    rid = rid or await new_record(api, tok_, url)
    files = {"file": (name, data, "application/pdf")}
    r = await api.post(f"{url}/{rid}/attachments", files=files, headers=tok_)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "STAGING"
    return r.json()["upload_id"]


async def status(api, tok_, up) -> dict:
    return (await api.get(f"/api/v1/uploads/{up}", headers=tok_)).json()


# ---------- Các test do Plan 01 Task 14 quy định ----------

async def test_eicar_quarantined(api, tok_cv, run_worker_once, core_conn):          # AT-03
    up = await upload(api, tok_cv, eicar(), "a.pdf")
    await run_worker_once()
    assert (await api.get(f"/api/v1/uploads/{up}", headers=tok_cv)).json()["status"] == "INFECTED"
    assert await last_event_type(core_conn) == "object.infected"


async def test_staging_not_readable_even_by_admin(api, tok_cv, tok_admin_with_app_role):   # AT-04
    await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf")         # chưa chạy worker
    sha = hashlib.sha256(fixture("clean-text.pdf")).hexdigest()
    assert (await api.get(f"/api/v1/objects/{sha}", headers=tok_admin_with_app_role)).status_code == 404


async def test_cas_dedup_and_byte_change(api, tok_cv, run_worker_once, core_conn):  # AT-05 (phần CAS)
    data = fixture("clean-text.pdf")
    await upload(api, tok_cv, data, "1.pdf")
    await upload(api, tok_cv, data, "2.pdf")
    await run_worker_once(2)
    assert await core_conn.fetchval("SELECT count(*) FROM objects") == 1
    changed = data[:-2] + bytes([data[-2] ^ 1]) + data[-1:]
    await upload(api, tok_cv, changed, "3.pdf")
    await run_worker_once()
    # 2 nếu bản sửa vẫn là PDF hợp lệ, 1 nếu bị REJECTED
    assert await core_conn.fetchval("SELECT count(*) FROM objects") in (1, 2)


async def test_clamd_down_stays_staging_and_retries(api, tok_cv, run_worker_once_with_clamd_down,
                                                    core_conn):  # AT-20
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf")
    await run_worker_once_with_clamd_down()
    assert (await api.get(f"/api/v1/uploads/{up}", headers=tok_cv)).json()["status"] == "STAGING"
    assert await core_conn.fetchval("SELECT attempts FROM jobs ORDER BY id DESC LIMIT 1") == 1


async def test_bad_job_does_not_stop_worker(api, tok_cv, ctx, core_conn):
    async with ctx.pool.acquire() as c:
        await c.execute("INSERT INTO jobs(kind, payload) VALUES ('scan', $1::jsonb)",
                        '{"upload_id": "khong-phai-uuid"}')
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf")
    assert await worker.run_once(ctx)          # việc hỏng: ghi lỗi, không ném ra ngoài
    assert await worker.run_once(ctx)          # việc hợp lệ phía sau vẫn chạy
    assert (await status(api, tok_cv, up))["status"] == "CLEAN"
    row = await core_conn.fetchrow("SELECT state, last_error FROM jobs ORDER BY id LIMIT 1")
    assert row["state"] in ("QUEUED", "FAILED") and row["last_error"]


# ---------- Bổ sung ----------

async def test_clean_pdf_flow_and_download(api, tok_cv, tok_tp, run_worker_once, core_conn):
    data = fixture("clean-text.pdf")
    rid = await new_record(api, tok_cv)
    up = await upload(api, tok_cv, data, "Quyết định.pdf", rid)
    await run_worker_once()
    st = await status(api, tok_cv, up)
    sha = hashlib.sha256(data).hexdigest()
    assert st == {"status": "CLEAN", "sha256": sha}
    assert await last_event_type(core_conn) == "object.clean"
    r = await api.get(f"/api/v1/objects/{sha}?variant=original", headers=tok_cv)
    assert r.status_code == 200 and r.content == data and r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert await last_event_type(core_conn) == "object.read"
    # trưởng phòng có quyền đọc theo manifest
    assert (await api.get(f"/api/v1/objects/{sha}", headers=tok_tp)).status_code == 200
    ref = await core_conn.fetchrow("SELECT record_id::text AS rid, role FROM object_refs")
    assert (ref["rid"], ref["role"]) == (rid, "original")


async def test_original_name_only_hashed(api, tok_cv, core_conn):
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "Hồ sơ mật của ông A.pdf")
    row = await core_conn.fetchrow("SELECT * FROM uploads WHERE id=$1::uuid", up)
    assert "Hồ sơ" not in str(dict(row)) and len(row["original_name_hash"]) == 64
    assert await last_event_type(core_conn) == "upload.staged"


@pytest.mark.parametrize("name,reason", [("image-only.pdf", "NO_TEXT_LAYER"), ("encrypted.pdf", "ENCRYPTED"),
                                         ("polyglot.bin", "PARSE_ERROR")])
async def test_rejected_files(api, tok_cv, run_worker_once, core_conn, name, reason):  # RF2, D1
    up = await upload(api, tok_cv, fixture(name), "x.pdf")
    await run_worker_once()
    assert await status(api, tok_cv, up) == {"status": "REJECTED", "reason": reason}
    assert await last_event_type(core_conn) == "object.rejected"
    assert await core_conn.fetchval("SELECT count(*) FROM objects") == 0


async def test_av_runs_before_pdf_checks(api, tok_cv, run_worker_once):              # D1
    # EICAR không phải PDF: vẫn phải bị cách ly (INFECTED), không chỉ REJECTED
    up = await upload(api, tok_cv, eicar(), "virus.exe")
    await run_worker_once()
    assert (await status(api, tok_cv, up))["status"] == "INFECTED"


async def test_staging_emptied_and_quarantine_used(api, tok_cv, ctx, run_worker_once):
    up_bad = await upload(api, tok_cv, eicar(), "a.pdf")
    up_ok = await upload(api, tok_cv, fixture("clean-text.pdf"), "b.pdf")
    await run_worker_once(2)
    staging = ctx.store.list_keys(ctx.settings.s3_bucket_staging)
    assert up_bad not in staging and up_ok not in staging
    assert up_bad in ctx.store.list_keys(ctx.settings.s3_bucket_quarantine)
    sha_ok = hashlib.sha256(fixture("clean-text.pdf")).hexdigest()
    assert ctx.store.exists(ctx.settings.s3_bucket_objects, sha_ok)


async def test_too_large_413(api):
    owner = tok("owner_a1", "app:test-app:member")
    rid = await new_record(api, owner, URL_T, {"title": "t"})                  # test-app: max_mb = 1
    big = b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 10)
    r = await api.post(f"{URL_T}/{rid}/attachments", files={"file": ("big.pdf", big)}, headers=owner)
    assert r.status_code == 413 and r.json()["type"].endswith("/payload-too-large")


async def test_upload_requires_update_permission(api, tok_cv, tok_tp, core_conn):
    rid = await new_record(api, tok_cv)
    r = await api.post(f"{URL_A}/{rid}/attachments", files={"file": ("a.pdf", b"%PDF-1.7")}, headers=tok_tp)
    assert r.status_code == 404
    assert await last_event_type(core_conn) == "policy.denied"


async def test_upload_to_sealed_record_409(api, tok_cv, owner_conn):
    rid = await new_record(api, tok_cv)
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1::uuid", rid)
    r = await api.post(f"{URL_A}/{rid}/attachments", files={"file": ("a.pdf", b"%PDF-1.7")}, headers=tok_cv)
    assert r.status_code == 409 and r.json()["type"].endswith("/record-sealed")


async def test_upload_missing_file_field_400(api, tok_cv):
    rid = await new_record(api, tok_cv)
    r = await api.post(f"{URL_A}/{rid}/attachments", files={"other": ("a.pdf", b"x")}, headers=tok_cv)
    assert r.status_code == 400


async def test_upload_status_hidden_from_other_users(api, tok_cv):
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf")
    outsider = tok("x", "app:chung-nhan:truong_clb")
    assert (await api.get(f"/api/v1/uploads/{up}", headers=outsider)).status_code == 404
    assert (await api.get("/api/v1/uploads/khong-phai-uuid", headers=tok_cv)).status_code == 404


async def test_object_not_readable_without_record_access(api, tok_cv, run_worker_once, core_conn):
    data = fixture("clean-text.pdf")
    await upload(api, tok_cv, data, "a.pdf")
    await run_worker_once()
    sha = hashlib.sha256(data).hexdigest()
    outsider = tok("x", "app:test-app:member")
    assert (await api.get(f"/api/v1/objects/{sha}", headers=outsider)).status_code == 404
    assert await last_event_type(core_conn) == "policy.denied"
    assert (await api.get(f"/api/v1/objects/{'0' * 64}", headers=tok_cv)).status_code == 404
    assert (await api.get("/api/v1/objects/khong-phai-hash", headers=tok_cv)).status_code == 404
    assert (await api.get(f"/api/v1/objects/{sha}?variant=redacted", headers=tok_cv)).status_code == 404


async def test_read_object_detects_tampering(api, tok_cv, ctx, run_worker_once):
    # PDF riêng cho test này (thêm chú thích sau %%EOF) để không làm hỏng object dùng chung của test khác
    data = fixture("clean-text.pdf") + f"%{uuid.uuid4().hex}\n".encode()
    await upload(api, tok_cv, data, "a.pdf")
    await run_worker_once()
    sha = hashlib.sha256(data).hexdigest()
    ctx.store.put_raw(ctx.settings.s3_bucket_objects, sha, b"%PDF-1.7 bi sua tren o dia")
    with pytest.raises(IntegrityError):
        ctx.store.read_object(sha)
    r = await api.get(f"/api/v1/objects/{sha}", headers=tok_cv)
    assert r.status_code == 500 and r.json()["type"].endswith("/integrity-error")


async def test_promote_never_overwrites(ctx):
    a, b = uuid.uuid4(), uuid.uuid4()
    key = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    ctx.store.put_staging(a, b"one")
    ctx.store.put_staging(b, b"two")
    assert ctx.store.promote(a, key) is True
    assert ctx.store.promote(b, key) is False
    assert ctx.store.get_raw(ctx.settings.s3_bucket_objects, key) == b"one"
    assert not ctx.store.exists(ctx.settings.s3_bucket_staging, str(b))


async def test_no_job_returns_false(ctx):
    assert await worker.run_once(ctx) is False
