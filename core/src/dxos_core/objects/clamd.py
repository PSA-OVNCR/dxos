# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client clamd tối giản (giao thức INSTREAM). Mọi bất thường đều là ``ScannerUnavailable`` (fail-closed, F8).

ClamAV chạy như dịch vụ độc lập; lõi chỉ nói chuyện qua socket (G2), không nhúng mã GPL.
"""

import asyncio
import re
import struct
from dataclasses import dataclass

_FOUND = re.compile(r"^stream: (.+) FOUND$")


@dataclass
class ScanResult:
    clean: bool
    signature: str | None


class ScannerUnavailable(Exception):
    """clamd không trả lời, trả lỗi hoặc trả nội dung không hiểu được."""


async def _talk(host: str, port: int, payload: list[bytes], timeout_s: float) -> str:
    async def run() -> bytes:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            for part in payload:
                writer.write(part)
                await writer.drain()
            return await reader.readuntil(b"\0")
        finally:
            writer.close()
    try:
        raw = await asyncio.wait_for(run(), timeout_s)
    except (OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise ScannerUnavailable(f"clamd {host}:{port}: {type(exc).__name__}") from exc
    return raw[:-1].decode("utf-8", "replace").strip()


async def instream_scan(host: str, port: int, data: bytes, chunk: int = 65536,
                        timeout_s: float = 30) -> ScanResult:
    parts = [b"zINSTREAM\0"]
    for i in range(0, len(data), chunk):
        block = data[i:i + chunk]
        parts.append(struct.pack("!I", len(block)) + block)
    parts.append(b"\0\0\0\0")
    reply = await _talk(host, port, parts, timeout_s)
    if reply == "stream: OK":
        return ScanResult(True, None)
    m = _FOUND.match(reply)
    if m:
        return ScanResult(False, m.group(1))
    raise ScannerUnavailable(f"clamd trả lời không hợp lệ: {reply[:80]!r}")


async def clamd_version(host: str, port: int, timeout_s: float = 5) -> str:
    return await _talk(host, port, [b"zVERSION\0"], timeout_s)
