# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Neo STH vào repo git có bảo vệ và API quản trị neo (Plan 01 Task 16; AT-16, AT-18 phần mã)."""

import base64
import dataclasses
import json
import subprocess

import pytest
from dxos_core import worker
from dxos_core.db.pool import create_pool
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import enqueue
from dxos_core.ledger.anchor import AnchorError, ensure_clone, publish_sth, sth_path
from dxos_core.ledger.log import append
from dxos_core.ledger.sth import TreeHead, make_sth
from dxos_proof.canonical import canonical_bytes
from helpers.api import running_api, tok
from helpers.local_signer import LocalSigner

pytestmark = pytest.mark.integration
GIT_SSH = "ssh -o BatchMode=yes"          # không dùng tới với remote file://
KEY = b"changeme-test-hmac-key"


def git(cwd, *args) -> str:
    out = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def bare_remote(tmp_path):
    remote = tmp_path / "anchor-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


@pytest.fixture
async def tmp_bare_repo_clone(bare_remote, tmp_path):
    clone = tmp_path / "anchor-clone"
    await ensure_clone(f"file://{bare_remote}", clone, GIT_SSH)
    return clone


@pytest.fixture
def th():
    return TreeHead(tree_size=5, root_hash="cd" * 32, ts="2026-10-20T00:00:00Z", key_version=1,
                    signature="c2ln")


# ---------- Các test do Plan 01 Task 16 quy định ----------

async def test_publish_writes_file_and_commits(tmp_bare_repo_clone, th):
    sha = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert (tmp_bare_repo_clone / sth_path(th.tree_size)).is_file() and len(sha) == 40


async def test_publish_never_overwrites(tmp_bare_repo_clone, th):
    await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    with pytest.raises(AnchorError) as e:
        await publish_sth(dataclasses.replace(th, root_hash="ab" * 32), tmp_bare_repo_clone, GIT_SSH)
    assert e.value.code == "ANCHOR_CONFLICT"


async def test_anchor_run_requires_admin(api, tok_author):
    assert (await api.post("/admin/v1/anchor:run", headers=tok_author)).status_code == 403


# ---------- Bổ sung: publish_sth ----------

def test_sth_path():
    assert sth_path(42) == "sth/000000000042.json"


async def test_file_content_is_canonical_and_pushed(tmp_bare_repo_clone, bare_remote, th):
    sha = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert (tmp_bare_repo_clone / sth_path(5)).read_bytes() == canonical_bytes(dataclasses.asdict(th))
    assert git(bare_remote, "rev-parse", "main") == sha                          # đã lên remote
    assert git(bare_remote, "log", "-1", "--format=%s", "main") == "sth 5"


async def test_same_sth_twice_is_idempotent(tmp_bare_repo_clone, bare_remote, th):
    a = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    b = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert a == b and git(bare_remote, "rev-list", "--count", "main") == "1"


async def test_push_failure_then_retry_succeeds(tmp_bare_repo_clone, bare_remote, th, tmp_path):
    good_url = git(tmp_bare_repo_clone, "remote", "get-url", "origin")
    git(tmp_bare_repo_clone, "remote", "set-url", "origin", f"file://{tmp_path}/khong-co.git")
    with pytest.raises(AnchorError) as e:
        await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert e.value.code == "PUSH_FAILED"
    git(tmp_bare_repo_clone, "remote", "set-url", "origin", good_url)
    sha = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)                   # commit cục bộ được đẩy lên
    assert git(bare_remote, "rev-parse", "main") == sha


async def test_picks_up_commits_made_elsewhere(tmp_bare_repo_clone, bare_remote, th, tmp_path):
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", f"file://{bare_remote}", str(other)], check=True)
    (other / "README.md").write_text("repo neo\n", encoding="utf-8")
    git(other, "add", "README.md")
    git(other, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "readme")
    git(other, "push", "-q", "origin", "HEAD:main")
    await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert git(bare_remote, "rev-list", "--count", "main") == "2"


async def test_ensure_clone_is_idempotent(bare_remote, tmp_path):
    clone = tmp_path / "c"
    await ensure_clone(f"file://{bare_remote}", clone, GIT_SSH)
    await ensure_clone(f"file://{bare_remote}", clone, GIT_SSH)
    assert (clone / ".git").is_dir()


async def test_ensure_clone_refuses_a_clone_of_another_remote(bare_remote, tmp_path):
    """Đổi DXOS_ANCHOR_REMOTE mà giữ clone cũ thì worker không được lặng lẽ đẩy vào remote cũ."""
    clone = tmp_path / "c"
    await ensure_clone(f"file://{bare_remote}", clone, GIT_SSH)
    other = tmp_path / "other.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(other)], check=True)
    with pytest.raises(AnchorError) as ei:
        await ensure_clone(f"file://{other}", clone, GIT_SSH)
    assert ei.value.code == "PUSH_FAILED"
    assert "DXOS_ANCHOR_REPO_DIR" in str(ei.value)
    assert git(clone, "remote", "get-url", "origin") == f"file://{bare_remote}"   # clone cũ không bị sửa


# ---------- Bổ sung: job anchor_sth và API quản trị ----------

@pytest.fixture
def signer():
    return LocalSigner()


@pytest.fixture
def anchor_settings(make_settings, core_dsn, bare_remote, tmp_path):
    return make_settings(database_url=core_dsn, anchor_repo_dir=tmp_path / "worker-clone",
                         anchor_remote=f"file://{bare_remote}", anchor_git_ssh_command=GIT_SSH)


@pytest.fixture
async def wctx(anchor_settings, core_dsn, signer):
    pool = await create_pool(core_dsn)
    try:
        yield WorkerContext(pool=pool, store=None, settings=anchor_settings, hmac_key=KEY, signer=signer)
    finally:
        await pool.close()


@pytest.fixture
async def api(anchor_settings, signer, test_jwks):
    async with running_api(anchor_settings, signer=signer) as client:
        yield client


@pytest.fixture
def tok_author():
    return tok("author1", "app:test-flow:author")


@pytest.fixture
def tok_admin():
    return tok("admin1", "dxos-admin")


async def test_anchor_job_makes_sth_publishes_and_records(wctx, core_conn, bare_remote):
    await append(core_conn, type="object.read", subject="s", body={}, hmac_key=KEY)
    await enqueue(core_conn, "anchor_sth", {})
    assert await worker.run_once(wctx)
    row = await core_conn.fetchrow("SELECT * FROM anchors")
    assert row["tree_size"] == 2 and row["commit_sha"] == git(bare_remote, "rev-parse", "main")
    content = json.loads(git(bare_remote, "show", f"main:{sth_path(2)}"))
    assert content["tree_size"] == 2
    assert await core_conn.fetchval("SELECT state FROM jobs") == "DONE"


async def test_anchor_job_push_failure_retries(wctx, core_conn, tmp_path):
    broken = dataclasses.replace(wctx, settings=wctx.settings.model_copy(
        update={"anchor_remote": "ssh://git@127.0.0.1:1/khong-co.git", "anchor_repo_dir": tmp_path / "x"}))
    await enqueue(core_conn, "anchor_sth", {})
    assert await worker.run_once(broken)
    row = await core_conn.fetchrow("SELECT state, run_after > now() AS later, last_error FROM jobs")
    assert row["state"] == "QUEUED" and row["later"] and row["last_error"]


async def test_anchors_table_is_append_only(core_conn, owner_conn, signer):
    th_ = await make_sth(core_conn, signer)
    await core_conn.execute("INSERT INTO anchors(tree_size, repo, commit_sha) VALUES ($1, 'r', $2)",
                            th_.tree_size, "a" * 40)
    import asyncpg
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("UPDATE anchors SET commit_sha=$1", "b" * 40)
    with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
        await owner_conn.execute("DELETE FROM anchors")


async def test_admin_anchor_run_returns_sth_and_enqueues(api, tok_admin, core_conn):
    r = await api.post("/admin/v1/anchor:run", headers=tok_admin)
    assert r.status_code == 200
    body = r.json()
    assert body["tree_size"] >= 1 and body["anchor_job_id"] > 0
    job = await core_conn.fetchrow("SELECT kind, payload::text AS p FROM jobs WHERE id=$1",
                                   body["anchor_job_id"])
    assert job["kind"] == "anchor_sth" and json.loads(job["p"]) == {"tree_size": body["tree_size"]}


async def test_admin_ledger_status(api, tok_admin, wctx, core_conn):
    await api.post("/admin/v1/anchor:run", headers=tok_admin)
    assert await worker.run_once(wctx)
    s = (await api.get("/admin/v1/ledger/status", headers=tok_admin)).json()
    assert s["tree_size"] == s["latest_sth"]["tree_size"] == s["last_anchor"]["tree_size"]
    assert s["verify"] == {"ok": True, "first_bad_idx": None} and s["pending_anchor_jobs"] == 0
    assert not {"seal_pending", "seal_key", "org"} & s.keys()          # đã chuyển sang /admin/v1/health


async def test_admin_api_needs_token_and_admin(api, tok_author):
    assert (await api.get("/admin/v1/ledger/status")).status_code == 401
    assert (await api.get("/admin/v1/ledger/status", headers=tok_author)).status_code == 403


async def test_anchor_run_503_when_kms_down(anchor_settings, tok_admin, test_jwks):
    from dxos_core.kms.base import KmsUnavailable

    class Down(LocalSigner):
        async def sign(self, *a, **k):
            raise KmsUnavailable("sealed")
    async with running_api(anchor_settings, signer=Down()) as api:
        r = await api.post("/admin/v1/anchor:run", headers=tok_admin)
    assert r.status_code == 503 and r.json()["type"].endswith("/kms-unavailable")


async def test_file_remote_bare_repo_created_when_missing(tmp_path, th):
    remote = tmp_path / "chua-co.git"
    clone = tmp_path / "clone"
    await ensure_clone(f"file://{remote}", clone, GIT_SSH)
    sha = await publish_sth(th, clone, GIT_SSH)
    assert git(remote, "rev-parse", "main") == sha


# ---------- Sửa sau rà soát độc lập ----------

async def test_failed_pushes_reuse_the_same_sth(wctx, core_conn, tmp_path):        # rà soát #6
    broken = dataclasses.replace(wctx, settings=wctx.settings.model_copy(
        update={"anchor_remote": "ssh://git@127.0.0.1:1/khong-co.git", "anchor_repo_dir": tmp_path / "x"}))
    await enqueue(core_conn, "anchor_sth", {})
    for _ in range(3):
        assert await worker.run_once(broken)
        await core_conn.execute("UPDATE jobs SET run_after=now()")
    assert await core_conn.fetchval("SELECT count(*) FROM tree_heads") == 1


async def test_hanging_git_times_out(tmp_path, th, monkeypatch):                  # rà soát #7
    from dxos_core.ledger import anchor

    monkeypatch.setattr(anchor, "GIT_TIMEOUT_S", 1.0)
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "remote", "add", "origin", "ssh://git@127.0.0.1:1/x.git")
    import time
    t0 = time.monotonic()
    with pytest.raises(AnchorError) as e:
        await publish_sth(th, repo, "sh -c 'sleep 30' --")
    assert e.value.code == "PUSH_FAILED" and time.monotonic() - t0 < 10


# ---------- Plan 02 Task 8: khóa công khai và tuyên bố khóa trong repo neo ----------

async def test_anchor_publishes_keys_and_detects_swap(anchor_env, local_signer):
    await anchor_env.anchor_once()
    pk = (await local_signer.public_keys())["seal-key"][1]
    assert (anchor_env.repo / "keys/seal-key/v1.pub").read_text().strip() == base64.b64encode(pk).decode()
    anchor_env.overwrite_remote("keys/seal-key/v1.pub", "AAAA\n")
    with pytest.raises(AnchorError, match="ANCHOR_CONFLICT"):
        await anchor_env.anchor_once()


# sealed_once: fixture mới, một niêm phong đã xong nên có hàng key_statements
async def test_anchor_publishes_key_statement(anchor_env, sealed_once):
    await anchor_env.anchor_once()
    doc = json.loads((anchor_env.repo / "keys/seal-key/v1.json").read_text(encoding="utf-8"))
    assert doc["serial"] == "seal-key/v1" and "signature" not in doc
    anchor_env.overwrite_remote("keys/seal-key/v1.json", "{}\n")
    with pytest.raises(AnchorError, match="ANCHOR_CONFLICT"):
        await anchor_env.anchor_once()


async def test_key_files_exact_bytes_and_same_commit_as_sth(anchor_env, local_signer, sealed_once, flow):
    await anchor_env.anchor_once()            # chạy cả job neo do lần niêm phong xếp, rồi job của lần này
    pub = await local_signer.public_keys()
    for name in ("seal-key", "sth-key"):
        assert anchor_env.remote_file(f"keys/{name}/v1.pub") == base64.b64encode(pub[name][1]) + b"\n"
    [stmt] = [s["statement"] for s in await flow.key_statements()]
    assert anchor_env.remote_file("keys/seal-key/v1.json") == canonical_bytes(stmt) + b"\n"
    first = git(anchor_env.remote, "log", "--format=%H", "--", "keys/seal-key/v1.pub").splitlines()
    assert len(first) == 1                                                      # tệp khóa chỉ ghi một lần
    files = set(git(anchor_env.remote, "show", "--name-only", "--format=", first[0]).splitlines())
    keys = {"keys/seal-key/v1.pub", "keys/sth-key/v1.pub", "keys/seal-key/v1.json"}
    assert keys < files and len([f for f in files - keys if f.startswith("sth/")]) == 1 == len(files - keys)
    # lần sau: tệp khóa trùng byte → không đổi, commit mới chỉ có STH mới
    size2 = await anchor_env.anchor_once()
    files2 = set(git(anchor_env.remote, "show", "--name-only", "--format=", "main").splitlines())
    assert files2 == {sth_path(size2)}


async def test_rotated_key_adds_file_and_keeps_old(anchor_env, local_signer):
    await anchor_env.anchor_once()
    v1 = anchor_env.remote_file("keys/seal-key/v1.pub")
    assert local_signer.rotate("seal-key") == 2
    await anchor_env.anchor_once()
    pub = await local_signer.public_keys()
    assert anchor_env.remote_file("keys/seal-key/v1.pub") == v1
    assert anchor_env.remote_file("keys/seal-key/v2.pub") == base64.b64encode(pub["seal-key"][2]) + b"\n"


async def test_conflicting_key_file_blocks_before_any_write(tmp_bare_repo_clone, bare_remote, th, tmp_path):
    other = tmp_path / "other-k"
    subprocess.run(["git", "clone", "-q", f"file://{bare_remote}", str(other)], check=True)
    (other / "keys/sth-key").mkdir(parents=True)
    (other / "keys/sth-key/v1.pub").write_text("AAAA\n", encoding="utf-8")
    git(other, "add", "keys")
    git(other, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "khóa lạ")
    git(other, "push", "-q", "origin", "HEAD:main")
    keys = {"seal-key": {1: b"\x01" * 32}, "sth-key": {1: b"\x02" * 32}}
    with pytest.raises(AnchorError) as e:
        await publish_sth(th, tmp_bare_repo_clone, GIT_SSH, keys=keys)
    assert e.value.code == "ANCHOR_CONFLICT"
    assert not (tmp_bare_repo_clone / sth_path(th.tree_size)).exists()
    assert not (tmp_bare_repo_clone / "keys/seal-key/v1.pub").exists()
    assert git(bare_remote, "rev-list", "--count", "main") == "1"


async def test_publish_without_keys_unchanged(tmp_bare_repo_clone, bare_remote, th):
    await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert not (tmp_bare_repo_clone / "keys").exists()


async def test_anchor_job_without_kms_on_pinned_retry_still_anchors(anchor_env, local_signer, kms_down):
    """Lần thử lại của một STH đã ký (``tree_size`` cố định) không cần KMS: neo STH, bỏ qua tệp khóa lần
    này."""
    async with anchor_env.ctx.pool.acquire() as c:
        th_ = await make_sth(c, local_signer)
        job_id = await enqueue(c, "anchor_sth", {"tree_size": th_.tree_size})
    kms_down()
    async with anchor_env.ctx.pool.acquire() as c:
        from dxos_core.jobs.queue import claim
        from dxos_core.ledger.anchor_job import process_anchor_job

        await process_anchor_job(anchor_env.ctx, await claim(c, ["anchor_sth"]))
        assert await c.fetchval("SELECT state FROM jobs WHERE id=$1", job_id) == "DONE"
    assert anchor_env.remote_file(sth_path(th_.tree_size))


async def test_statement_file_named_by_row_version_and_mismatch_refused(tmp_bare_repo_clone, bare_remote, th):
    """Fix vòng 1, #4."""
    from dxos_core.ledger.anchor import key_files

    st = {"format": "dxos-key-statement/1", "key": "seal-key", "version": 1, "serial": "seal-key/v1"}
    assert key_files(None, {1: st}) == [("keys/seal-key/v1.json", canonical_bytes(st) + b"\n")]
    with pytest.raises(AnchorError) as e:
        key_files(None, {2: st})
    assert e.value.code == "ANCHOR_CONFLICT"
    with pytest.raises(AnchorError):
        await publish_sth(th, tmp_bare_repo_clone, GIT_SSH, statements={2: st})
    assert not (tmp_bare_repo_clone / sth_path(th.tree_size)).exists()
    assert not (tmp_bare_repo_clone / "keys").exists()
    assert git(bare_remote, "rev-list", "--all", "--count") == "0"
