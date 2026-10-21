# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Neo STH vào repo git công khai có bảo vệ nhánh (spec 11.3; Plan 01 Task 16).

- Mỗi STH là một tệp ``sth/<tree_size 12 chữ số>.json`` chứa JSON chuẩn hóa của STH.
- **Không bao giờ ghi đè**: tệp đã có với nội dung khác → ``ANCHOR_CONFLICT`` (dấu hiệu viết lại lịch sử).
- Mạng lỗi, remote từ chối → ``PUSH_FAILED``; commit cục bộ được đẩy lại ở lần sau.
- Bảo vệ nhánh (cấm force-push, cấm xóa, lịch sử tuyến tính) nằm **ở GitHub**, ngoài tầm với của VPS (AT-18).
- Plan 02 Task 8 (spec 11.6, 25.3): cùng commit với STH còn có khóa công khai ``keys/<khóa>/v<n>.pub``
  (base64 khóa ed25519 thô + ``\n``, cho ``seal-key`` và ``sth-key``) và tuyên bố khóa
  ``keys/seal-key/v<n>.json`` (``canonical_bytes(tuyên bố)`` + ``\n``). Cùng luật không ghi đè: tệp đã có mà
  khác byte → ``ANCHOR_CONFLICT``; trùng byte → bỏ qua. Mọi tệp được so **trước** khi ghi tệp nào.
"""

import asyncio
import base64
import dataclasses
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from dxos_proof.canonical import canonical_bytes

from dxos_core.ledger.sth import TreeHead

BRANCH = "main"
GIT_TIMEOUT_S = 120.0     # một lệnh git (kể cả push qua SSH) không được treo worker
_AUTHOR = ["-c", "user.name=dxos-anchor", "-c", "user.email=anchor@dxos.invalid"]


class AnchorError(Exception):
    def __init__(self, code: Literal["ANCHOR_CONFLICT", "PUSH_FAILED"], message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def sth_path(tree_size: int) -> str:
    return f"sth/{tree_size:012d}.json"


_KEY_FILES = ("seal-key", "sth-key")


def key_files(keys: Mapping[str, Mapping[int, bytes]] | None,
              statements: Iterable[Mapping[str, Any]] = ()) -> list[tuple[str, bytes]]:
    """Các tệp khóa cần có trong repo neo: ``(đường dẫn, nội dung)``, theo thứ tự cố định."""
    out: list[tuple[str, bytes]] = []
    for name in _KEY_FILES:
        for v, raw in sorted((keys or {}).get(name, {}).items()):
            out.append((f"keys/{name}/v{int(v)}.pub", base64.b64encode(raw) + b"\n"))
    for st in sorted(statements, key=lambda x: int(x["version"])):
        if st.get("key") != "seal-key":
            raise ValueError(f"tuyên bố khóa lạ: {st.get('key')!r}")
        out.append((f"keys/seal-key/v{int(st['version'])}.json", canonical_bytes(dict(st)) + b"\n"))
    return out


async def _git(repo: Path, git_ssh_command: str, *args: str, check: bool = True) -> tuple[int, str]:
    env = {**os.environ, "GIT_SSH_COMMAND": git_ssh_command, "GIT_TERMINAL_PROMPT": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), *args, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), GIT_TIMEOUT_S)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise AnchorError("PUSH_FAILED", f"git {args[0]} quá {GIT_TIMEOUT_S:.0f}s") from exc
    text = out.decode("utf-8", "replace").strip()
    if check and proc.returncode != 0:
        raise AnchorError("PUSH_FAILED", f"git {args[0]}: {text[-300:]}")
    return proc.returncode, text


async def ensure_clone(remote: str, repo_dir: Path, git_ssh_command: str) -> None:
    """Clone ``remote`` vào ``repo_dir`` nếu chưa có; repo rỗng thì đặt nhánh ``main``."""
    if (repo_dir / ".git").is_dir():
        return
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if remote.startswith("file://"):            # chỉ cho môi trường thử (compose.e2e.yaml): tự tạo bare repo
        bare = Path(remote[len("file://"):])
        if not bare.exists():
            await _git(repo_dir.parent, git_ssh_command, "init", "-q", "--bare", "-b", BRANCH, str(bare))
    await _git(repo_dir.parent, git_ssh_command, "clone", "-q", remote, str(repo_dir))
    await _git(repo_dir, git_ssh_command, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")


async def _remote_has_branch(repo: Path, ssh: str) -> bool:
    code, out = await _git(repo, ssh, "ls-remote", "--heads", "origin", BRANCH, check=False)
    if code != 0:
        raise AnchorError("PUSH_FAILED", f"không liên lạc được remote: {out[-300:]}")
    return bool(out.strip())


async def publish_sth(th: TreeHead, repo_dir: Path, git_ssh_command: str, *,
                      keys: Mapping[str, Mapping[int, bytes]] | None = None,
                      statements: Iterable[Mapping[str, Any]] = ()) -> str:
    """Ghi, commit và đẩy STH (cùng tệp khóa/tuyên bố còn thiếu) lên ``origin main``; trả về sha của commit
    chứa tệp STH."""
    ssh = git_ssh_command
    if await _remote_has_branch(repo_dir, ssh):
        await _git(repo_dir, ssh, *_AUTHOR, "pull", "-q", "--rebase", "origin", BRANCH)
    rel = sth_path(th.tree_size)
    files = [(rel, canonical_bytes(dataclasses.asdict(th))), *key_files(keys, statements)]
    # So hết trước khi ghi: xung đột ở bất kỳ tệp nào thì không ghi tệp nào.
    for f, content in files:
        path = repo_dir / f
        if path.exists() and path.read_bytes() != content:
            raise AnchorError("ANCHOR_CONFLICT", f"{f} đã có với nội dung khác")
    sth_is_new = not (repo_dir / rel).exists()
    for f, content in files:
        path = repo_dir / f
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    await _git(repo_dir, ssh, "add", "--", *(f for f, _ in files))
    staged, _ = await _git(repo_dir, ssh, "diff", "--cached", "--quiet", check=False)
    if staged != 0:     # có tệp mới (STH và/hoặc khóa) → một commit
        message = f"sth {th.tree_size}" if sth_is_new else "keys"
        await _git(repo_dir, ssh, *_AUTHOR, "commit", "-q", "-m", message)
    await _git(repo_dir, ssh, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
    return (await _git(repo_dir, ssh, "log", "-1", "--format=%H", "--", rel))[1]
