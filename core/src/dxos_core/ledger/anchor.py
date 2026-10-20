# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Neo STH vào repo git công khai có bảo vệ nhánh (spec 11.3; Plan 01 Task 16).

- Mỗi STH là một tệp ``sth/<tree_size 12 chữ số>.json`` chứa JSON chuẩn hóa của STH.
- **Không bao giờ ghi đè**: tệp đã có với nội dung khác → ``ANCHOR_CONFLICT`` (dấu hiệu viết lại lịch sử).
- Mạng lỗi, remote từ chối → ``PUSH_FAILED``; commit cục bộ được đẩy lại ở lần sau.
- Bảo vệ nhánh (cấm force-push, cấm xóa, lịch sử tuyến tính) nằm **ở GitHub**, ngoài tầm với của VPS (AT-18).
"""

import asyncio
import dataclasses
import os
from pathlib import Path
from typing import Literal

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


async def publish_sth(th: TreeHead, repo_dir: Path, git_ssh_command: str) -> str:
    """Ghi, commit và đẩy STH lên ``origin main``; trả về sha của commit chứa tệp."""
    ssh = git_ssh_command
    if await _remote_has_branch(repo_dir, ssh):
        await _git(repo_dir, ssh, *_AUTHOR, "pull", "-q", "--rebase", "origin", BRANCH)
    rel = sth_path(th.tree_size)
    path = repo_dir / rel
    content = canonical_bytes(dataclasses.asdict(th))
    if path.exists():
        if path.read_bytes() != content:
            raise AnchorError("ANCHOR_CONFLICT", f"{rel} đã có với nội dung khác")
        await _git(repo_dir, ssh, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
        return (await _git(repo_dir, ssh, "log", "-1", "--format=%H", "--", rel))[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    await _git(repo_dir, ssh, "add", rel)
    await _git(repo_dir, ssh, *_AUTHOR, "commit", "-q", "-m", f"sth {th.tree_size}")
    await _git(repo_dir, ssh, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
    return (await _git(repo_dir, ssh, "rev-parse", "HEAD"))[1]
