# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper cho cổng đối soát công khai và repo neo (Plan 02 Task 8).

- ``VerifyClient``: gọi ``/verify/v1/*`` của API thật, **không** kèm token.
- ``AnchorEnv``: bare repo ``file://`` + clone của worker + Settings, chạy đúng đường của job ``anchor_sth``.
"""

import json
import subprocess
import uuid
from collections.abc import AsyncIterator, Coroutine, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import claim, enqueue
from dxos_core.ledger.anchor import AnchorError
from dxos_core.ledger.anchor_job import ANCHOR_JOB, process_anchor_job

PREFIX = "/verify/v1/"


class VerifyClient:
    """Client ẩn danh của các route công khai ``/verify/v1/``."""

    def __init__(self, api: httpx.AsyncClient) -> None:
        self._api = api

    @staticmethod
    def _check(path: str) -> str:
        assert path.startswith(PREFIX), f"chỉ dùng cho route công khai {PREFIX}: {path}"
        return path

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        return await self._api.get(self._check(path), **kw)

    async def post(self, path: str, **kw: Any) -> httpx.Response:
        return await self._api.post(self._check(path), **kw)

    def stream_post(self, path: str, chunks: Sequence[bytes], *,
                    content_type: str = "application/json") -> Coroutine[Any, Any, httpx.Response]:
        """POST thân request kiểu chunked (không có Content-Length), từng phần ``chunks``."""
        async def body() -> AsyncIterator[bytes]:
            for c in chunks:
                yield c

        return self._api.post(self._check(path), content=body(), headers={"content-type": content_type})


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return out.stdout.strip()


@dataclass
class AnchorEnv:
    remote: Path              # bare repo (đóng vai repo neo trên GitHub)
    repo: Path                # clone của worker (settings.anchor_repo_dir)
    ctx: WorkerContext
    scratch: Path

    @property
    def settings(self):
        return self.ctx.settings

    async def anchor_once(self) -> int:
        """Xếp một job ``anchor_sth`` rồi chạy mọi job neo tới hạn bằng ``process_anchor_job`` thật. Job của
        lần này ``FAILED``/thử lại → ``AnchorError`` (mã lấy từ ``last_error``); xong → trả ``tree_size``."""
        async with self.ctx.pool.acquire() as conn:
            job_id = await enqueue(conn, ANCHOR_JOB, {})
            while (job := await claim(conn, [ANCHOR_JOB])) is not None:
                await process_anchor_job(self.ctx, job)
            row = await conn.fetchrow("SELECT state, last_error, payload FROM jobs WHERE id=$1", job_id)
        if row["state"] != "DONE":
            err = row["last_error"] or ""
            code = "ANCHOR_CONFLICT" if err.startswith("ANCHOR_CONFLICT") else "PUSH_FAILED"
            raise AnchorError(code, err)
        payload = row["payload"]
        return (json.loads(payload) if isinstance(payload, str) else payload)["tree_size"]

    def overwrite_remote(self, rel: str, text: str) -> None:
        """Một bên khác (có quyền push) ghi đè tệp ``rel`` trên remote bằng ``text`` và đẩy lên."""
        other = self.scratch / f"other-{uuid.uuid4().hex[:8]}"
        subprocess.run(["git", "clone", "-q", f"file://{self.remote}", str(other)], check=True)
        path = other / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(other, "add", rel)
        git(other, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", f"ghi đè {rel}")
        git(other, "push", "-q", "origin", "HEAD:main")

    def remote_file(self, rel: str) -> bytes:
        return subprocess.run(["git", "-C", str(self.remote), "show", f"main:{rel}"], check=True,
                              capture_output=True).stdout
