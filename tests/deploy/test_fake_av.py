# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""fake-av nói đúng giao thức clamd và chỉ nhận diện EICAR (hồ sơ dev-lite, R-4)."""

import asyncio
import base64
import importlib.util
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("fake_av", ROOT / "deploy/fake-av/fake_av.py")
fake_av = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_av)

# Tệp thử EICAR lưu dạng base64 (không commit nguyên văn, Plan 01 Global Constraints).
EICAR = base64.b64decode(
    "WDVPIVAlQEFQWzRcUFpYNTQoUF4pN0NDKTd9JEVJQ0FSLVNUQU5EQVJELUFOVElWSVJVUy1URVNULUZJTEUhJEgrSCo="
)


def _chunks(data: bytes, size: int) -> bytes:
    out = b"".join(
        struct.pack("!I", len(data[i : i + size])) + data[i : i + size]
        for i in range(0, len(data), size)
    )
    return out + struct.pack("!I", 0)


async def _talk(payload: bytes) -> bytes:
    server = await fake_av.serve("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(payload)
        await writer.drain()
        reply = await asyncio.wait_for(reader.read(), timeout=5)
        writer.close()
        return reply
    finally:
        server.close()
        await server.wait_closed()


def talk(payload: bytes) -> bytes:
    return asyncio.run(_talk(payload))


def test_eicar_fixture_is_the_standard_68_byte_file():
    assert len(EICAR) == 68 and EICAR.startswith(b"X5O!") and fake_av.EICAR == EICAR


def test_ping_pong_null_and_newline_terminated():
    assert talk(b"zPING\0") == b"PONG\0"
    assert talk(b"nPING\n") == b"PONG\n"


def test_version():
    assert talk(b"zVERSION\0").startswith(b"ClamAV ")


def test_clean_stream_is_ok():
    assert talk(b"zINSTREAM\0" + _chunks(b"%PDF-1.7 hello", 4)) == b"stream: OK\0"


@pytest.mark.parametrize("chunk", [5, 68, 4096])
def test_eicar_found_even_when_split_across_chunks(chunk):
    data = b"prefix " + EICAR + b" suffix"
    assert talk(b"zINSTREAM\0" + _chunks(data, chunk)) == b"stream: Eicar-Test-Signature FOUND\0"


def test_stream_size_limit(monkeypatch):
    monkeypatch.setattr(fake_av, "MAX_STREAM", 10)
    assert talk(b"zINSTREAM\0" + _chunks(b"x" * 11, 11)) == b"INSTREAM size limit exceeded. ERROR\0"


def test_unknown_command():
    assert talk(b"zSCAN /etc/passwd\0") == b"UNKNOWN COMMAND\0"
    assert talk(b"garbage") == b"UNKNOWN COMMAND\n"
