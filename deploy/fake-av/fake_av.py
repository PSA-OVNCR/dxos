# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""fake-av: stub nói giao thức clamd, CHỈ nhận diện tệp thử EICAR.

CHỈ DÙNG KHI PHÁT TRIỂN (hồ sơ dev-lite, R-4). Không phải trình diệt virus.
Lệnh hỗ trợ (tiền tố `z` kết thúc bằng NUL, hoặc `n` kết thúc bằng xuống dòng):
PING, VERSION, INSTREAM. Phản hồi giống clamd: `stream: OK` hoặc
`stream: Eicar-Test-Signature FOUND`.

Chuỗi EICAR được lưu ở dạng base64 để Windows Defender không cách ly mã nguồn.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import socket
import struct
import sys

EICAR = base64.b64decode(
    "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
)
SIGNATURE = "Eicar-Test-Signature"
VERSION = "ClamAV 0.0.0-dxos-fake-av/0/Thu Jan  1 00:00:00 1970"
MAX_STREAM = 50 * 1024 * 1024
MAX_COMMAND = 64


def scan(data: bytes) -> str:
    """Kết quả quét theo định dạng clamd cho một luồng dữ liệu."""
    return f"stream: {SIGNATURE} FOUND" if EICAR in data else "stream: OK"


async def _read_command(reader: asyncio.StreamReader) -> tuple[str, bytes] | None:
    prefix = await reader.read(1)
    if prefix == b"z":
        term = b"\0"
    elif prefix == b"n":
        term = b"\n"
    else:
        return None
    raw = await reader.readuntil(term)
    if len(raw) > MAX_COMMAND:
        return None
    return raw[:-1].decode("ascii", "replace"), term


async def _read_stream(reader: asyncio.StreamReader) -> bytes | None:
    """Đọc các khối `<uint32 big-endian độ dài><dữ liệu>` tới khối độ dài 0."""
    buf = bytearray()
    while True:
        (size,) = struct.unpack("!I", await reader.readexactly(4))
        if size == 0:
            return bytes(buf)
        if len(buf) + size > MAX_STREAM:
            return None
        buf += await reader.readexactly(size)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        parsed = await _read_command(reader)
        if parsed is None:
            writer.write(b"UNKNOWN COMMAND\n")
            return
        cmd, term = parsed
        if cmd == "PING":
            reply = "PONG"
        elif cmd == "VERSION":
            reply = VERSION
        elif cmd == "INSTREAM":
            data = await _read_stream(reader)
            reply = "INSTREAM size limit exceeded. ERROR" if data is None else scan(data)
        else:
            reply = "UNKNOWN COMMAND"
        writer.write(reply.encode() + term)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
        pass
    finally:
        try:
            await writer.drain()
        except ConnectionError:
            pass
        writer.close()


async def serve(host: str, port: int) -> asyncio.base_events.Server:
    return await asyncio.start_server(handle, host, port)


def ping(host: str = "127.0.0.1", port: int = 3310, timeout: float = 3.0) -> bool:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(b"zPING\0")
        return s.recv(16) == b"PONG\0"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0")  # noqa: S104 - chỉ nghe trong mạng nội bộ net-data
    ap.add_argument("--port", type=int, default=3310)
    ap.add_argument("--ping", action="store_true", help="kiểm tra sức khỏe rồi thoát")
    args = ap.parse_args(argv)
    if args.ping:
        return 0 if ping(port=args.port) else 1

    async def _run() -> None:
        server = await serve(args.host, args.port)
        print(f"fake-av (DEV-ONLY) nghe tại {args.host}:{args.port}", flush=True)
        async with server:
            await server.serve_forever()

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
