# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Biên nhận OpenTimestamps cho STH đã neo (Đ2; Plan 03 Task 14, P3-D10). **Mặc định tắt, cắt được.**

Lõi chỉ gửi digest STH tới các calendar và lưu biên nhận; nâng cấp lên Bitcoin và kiểm chứng do người kiểm
tự làm bằng công cụ chính thức ``ots`` (``ots upgrade``, ``ots verify``). Client calendar tự viết, tối thiểu:
không dùng gói ``opentimestamps`` (LGPL-3.0), không thêm phụ thuộc.

- Digest: ``SHA-256(canonical_bytes(sth))`` = SHA-256 của đúng tệp ``sth/<n>.json`` trong repo neo, nên
  ``ots verify -f sth/<n>.json ots/<n>.ots`` kiểm được trực tiếp. Không thêm nonce như ``ots stamp``: STH là
  dữ liệu công khai, không có gì để giấu.
- Tệp ``.ots`` (detached timestamp): ``MAGIC``, phiên bản ``0x01``, op ``0x08`` (sha256), 32 byte digest, rồi
  timestamp. Timestamp là một nút: mọi nhánh trừ nhánh cuối có tiền tố ``0xff``; nhánh là ``0x00`` + biên nhận
  (8 byte thẻ + varbytes) hoặc op + nút con. Phản hồi của calendar là timestamp bắt đầu từ chính digest.
- Phản hồi là dữ liệu từ mạng, sẽ nằm vĩnh viễn trong repo neo: phân tích chặt (thẻ biết trước, độ sâu, cỡ,
  không thừa byte) rồi **gộp** như ``Timestamp.merge`` của client chính thức. Một phản hồi đúng dạng chuẩn
  thì ra nguyên văn; hai phản hồi có op đầu khác nhau thì ra ``0xff`` + nhánh 1 + nhánh 2. Nối thẳng không đủ
  khi hai calendar trả cùng op đầu (cùng giây → cùng ``prepend``): trình đọc chính thức giữ op trong dict, sẽ
  mất một nhánh.
- Việc ``ots_stamp`` (xếp sau khi neo thành công, chỉ khi ``DXOS_OTS_CALENDARS`` có giá trị): calendar lỗi →
  ghi log, thử lại theo lịch của việc; không bao giờ chặn hay làm hỏng việc neo. Có ít nhất một biên nhận thì
  commit ``ots/<n 12 chữ số>.ots`` (dựng lại tất định từ bảng ``ots_receipts``) vào repo neo, cùng luật không
  ghi đè như STH.
"""

import dataclasses
import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
import httpx
from dxos_proof.canonical import canonical_bytes

from dxos_core.jobs.context import WorkerContext
from dxos_core.jobs.queue import Job, complete, fail, retry_later
from dxos_core.ledger.anchor import AnchorError, ensure_clone, publish_files
from dxos_core.ledger.sth import get_sth

log = logging.getLogger("dxos_core.ledger.ots")

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
VERSION = 0x01
OP_SHA256 = 0x08
CALENDAR_TIMEOUT_S = 10.0
MAX_REPLY_BYTES = 10_000          # như client chính thức
OTS_JOB = "ots_stamp"
OTS_ATTEMPTS = 6                  # số lượt hỏi calendar còn thiếu, trước khi commit với biên nhận đã có
OTS_RETRY_S = 600
PUSH_RETRY_S = 60

_UNARY = {0x02, 0x03, 0x08, 0x67, 0xf2, 0xf3}     # sha1, ripemd160, sha256, keccak256, reverse, hexlify
_BINARY = {0xf0, 0xf1}                            # append, prepend
_MAX_ARG = 4096
_MAX_PAYLOAD = 8192
_MAX_DEPTH = 256


class OtsFormatError(ValueError):
    """Phản hồi calendar không phải timestamp OpenTimestamps hợp lệ."""


# ---------------------------------------------------------------- định dạng
@dataclass
class _Node:
    attestations: set[bytes] = field(default_factory=set)      # 8 byte thẻ + varbytes(payload)
    ops: dict[bytes, "_Node"] = field(default_factory=dict)    # thẻ op (+ varbytes đối số) → nút con

    def merge(self, other: "_Node") -> None:
        self.attestations |= other.attestations
        for op, child in other.ops.items():
            if op in self.ops:
                self.ops[op].merge(child)
            else:
                self.ops[op] = child

    def serialize(self) -> bytes:
        branches = [b"\x00" + a for a in sorted(self.attestations)]
        branches += [op + child.serialize() for op, child in sorted(self.ops.items(), key=_op_order)]
        return b"".join(b"\xff" + br for br in branches[:-1]) + branches[-1]


def _op_order(item: tuple[bytes, _Node]) -> tuple[int, bytes]:
    op = item[0]
    return op[0], _read_varbytes(op, 1, _MAX_ARG)[0] if op[0] in _BINARY else b""


def _read_varuint(buf: bytes, pos: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        if pos >= len(buf):
            raise OtsFormatError("varuint bị cụt")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise OtsFormatError("varuint quá dài")


def _read_varbytes(buf: bytes, pos: int, max_len: int, min_len: int = 0) -> tuple[bytes, int]:
    n, pos = _read_varuint(buf, pos)
    if not min_len <= n <= max_len or pos + n > len(buf):
        raise OtsFormatError(f"varbytes dài {n} không hợp lệ")
    return buf[pos:pos + n], pos + n


def _parse_branch(buf: bytes, pos: int, tag: int, node: _Node, depth: int) -> int:
    if tag == 0x00:
        start = pos
        if pos + 8 > len(buf):
            raise OtsFormatError("thẻ biên nhận bị cụt")
        _, pos = _read_varbytes(buf, pos + 8, _MAX_PAYLOAD)
        node.attestations.add(buf[start:pos])
        return pos
    start = pos - 1
    if tag in _BINARY:
        _, pos = _read_varbytes(buf, pos, _MAX_ARG, min_len=1)
    elif tag not in _UNARY:
        raise OtsFormatError(f"thẻ op lạ 0x{tag:02x}")
    op = buf[start:pos]
    child, pos = _parse_node(buf, pos, depth + 1)
    if op in node.ops:
        node.ops[op].merge(child)
    else:
        node.ops[op] = child
    return pos


def _parse_node(buf: bytes, pos: int, depth: int) -> tuple[_Node, int]:
    if depth > _MAX_DEPTH:
        raise OtsFormatError("timestamp lồng quá sâu")
    node = _Node()
    while True:
        if pos >= len(buf):
            raise OtsFormatError("timestamp bị cụt")
        tag = buf[pos]
        pos += 1
        if tag != 0xFF:
            return node, _parse_branch(buf, pos, tag, node, depth)
        if pos >= len(buf) or buf[pos] == 0xFF:
            raise OtsFormatError("sau 0xff phải là một nhánh")
        pos = _parse_branch(buf, pos + 1, buf[pos], node, depth)


def parse_timestamp(reply: bytes) -> _Node:
    """Phân tích chặt timestamp (phản hồi calendar). Sai dạng, thừa byte hoặc quá cỡ → ``OtsFormatError``."""
    if len(reply) > MAX_REPLY_BYTES:
        raise OtsFormatError(f"phản hồi quá {MAX_REPLY_BYTES} byte")
    node, pos = _parse_node(bytes(reply), 0, 0)
    if pos != len(reply):
        raise OtsFormatError(f"thừa {len(reply) - pos} byte sau timestamp")
    return node


def ots_request_digest(sth: Mapping) -> bytes:
    return hashlib.sha256(canonical_bytes(dict(sth))).digest()


def ots_header(digest: bytes) -> bytes:
    if len(digest) != 32:
        raise ValueError("digest phải dài 32 byte (SHA-256)")
    return MAGIC + bytes([VERSION, OP_SHA256]) + digest


def detached_timestamp(digest: bytes, calendar_replies: list[bytes]) -> bytes:
    """Tệp ``.ots`` cho ``digest`` từ các phản hồi calendar (gộp như client chính thức, thứ tự tất định)."""
    header = ots_header(digest)
    if not calendar_replies:
        raise ValueError("cần ít nhất một phản hồi calendar")
    root = _Node()
    for r in calendar_replies:
        root.merge(parse_timestamp(r))
    return header + root.serialize()


def ots_path(tree_size: int) -> str:
    return f"ots/{tree_size:012d}.ots"


# ---------------------------------------------------------------- calendar
def calendar_urls(settings) -> list[str]:
    """``DXOS_OTS_CALENDARS`` (phân tách bằng dấu phẩy) → danh sách URL, bỏ ``/`` cuối. Rỗng = tắt."""
    return [u.strip().rstrip("/") for u in (settings.ots_calendars or "").split(",") if u.strip()]


async def submit_digest(client: httpx.AsyncClient, calendar: str, digest: bytes) -> bytes:
    """``POST <calendar>/digest`` với thân là 32 byte digest (như client chính thức); trả phản hồi đã kiểm."""
    r = await client.post(f"{calendar}/digest", content=digest, timeout=CALENDAR_TIMEOUT_S, headers={
        "content-type": "application/x-www-form-urlencoded", "accept": "application/vnd.opentimestamps.v1",
        "user-agent": "dxos-trust-core"})
    r.raise_for_status()
    parse_timestamp(r.content)
    return r.content


# ---------------------------------------------------------------- việc nền ots_stamp
async def _receipts(conn: asyncpg.Connection, tree_size: int) -> list[bytes]:
    rows = await conn.fetch("SELECT reply FROM ots_receipts WHERE tree_size=$1 ORDER BY calendar", tree_size)
    return [bytes(r["reply"]) for r in rows]


async def receipts_ots(conn: asyncpg.Connection, tree_size: int, sth: Mapping) -> bytes | None:
    """Tệp ``.ots`` của STH ``tree_size`` dựng từ ``ots_receipts``; chưa có biên nhận → None."""
    replies = await _receipts(conn, tree_size)
    return detached_timestamp(ots_request_digest(sth), replies) if replies else None


async def process_ots_job(ctx: WorkerContext, job: Job) -> None:
    s = ctx.settings
    size = int(job.payload["tree_size"])
    cals = calendar_urls(s)
    async with ctx.pool.acquire() as conn:
        th = await get_sth(conn, size)
        if th is None:
            raise ValueError(f"không có STH cỡ {size}")
        if not cals or not s.anchor_remote:
            log.info("OpenTimestamps đã tắt: bỏ việc %s cho STH %s", OTS_JOB, size)
            await complete(conn, job.id)
            return
        digest = ots_request_digest(dataclasses.asdict(th))
        have = {r["calendar"] for r in await conn.fetch(
            "SELECT calendar FROM ots_receipts WHERE tree_size=$1", size)}
        errors: list[str] = []
        missing = [c for c in cals if c not in have]
        if missing and job.attempts <= OTS_ATTEMPTS:
            async with httpx.AsyncClient(transport=ctx.http_transport) as client:
                for cal in missing:
                    try:
                        reply = await submit_digest(client, cal, digest)
                    except (httpx.HTTPError, OtsFormatError) as exc:
                        log.warning("calendar %s không cấp biên nhận cho STH %s: %s", cal, size, exc)
                        errors.append(f"{cal}: {type(exc).__name__}: {exc}")
                        continue
                    await conn.execute(
                        "INSERT INTO ots_receipts(tree_size, calendar, reply) VALUES ($1, $2, $3)"
                        " ON CONFLICT DO NOTHING", size, cal, reply)
        replies = await _receipts(conn, size)
        if errors and job.attempts < OTS_ATTEMPTS:
            await retry_later(conn, job.id, OTS_RETRY_S, "; ".join(errors)[:500])
            return
        if not replies:
            log.error("không calendar nào cấp biên nhận cho STH %s sau %s lượt", size, job.attempts)
            await fail(conn, job.id, ("; ".join(errors) or "không có biên nhận")[:500])
            return
        content = detached_timestamp(digest, replies)
        repo = Path(s.anchor_repo_dir)
        try:
            await ensure_clone(s.anchor_remote, repo, s.anchor_git_ssh_command)
            await publish_files([(ots_path(size), content)], repo, s.anchor_git_ssh_command,
                                message=f"ots {size}")
        except AnchorError as exc:
            if exc.code == "ANCHOR_CONFLICT":
                log.error("repo neo đã có %s khác: %s", ots_path(size), exc)
                await fail(conn, job.id, str(exc))
            else:
                log.warning("đẩy %s lỗi, thử lại sau %ss: %s", ots_path(size), PUSH_RETRY_S, exc)
                await retry_later(conn, job.id, PUSH_RETRY_S, str(exc)[:500])
            return
        await complete(conn, job.id)
