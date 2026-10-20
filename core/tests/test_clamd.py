# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test client clamd INSTREAM (Plan 01 Task 14) với fake clamd chạy trong tiến trình."""

import asyncio

import pytest
from dxos_core.objects.clamd import ScannerUnavailable, ScanResult, clamd_version, instream_scan
from helpers.files import eicar, fixture


async def test_instream_found(fake_clamd):   # fake_clamd: server tạm, trả FOUND khi gặp EICAR
    assert await instream_scan(*fake_clamd, eicar()) == ScanResult(False, "Eicar-Test-Signature")


async def test_instream_unavailable():
    with pytest.raises(ScannerUnavailable):
        await instream_scan("127.0.0.1", 1, b"x", timeout_s=1)


async def test_instream_clean_and_chunked(fake_clamd):
    data = fixture("clean-text.pdf") * 50
    assert await instream_scan(*fake_clamd, data, chunk=100) == ScanResult(True, None)


async def test_eicar_split_across_chunks_still_found(fake_clamd):
    data = b"A" * 30 + eicar() + b"B" * 30
    assert (await instream_scan(*fake_clamd, data, chunk=7)).clean is False


async def test_empty_data(fake_clamd):
    assert (await instream_scan(*fake_clamd, b"")).clean is True


async def _serve_reply(reply: bytes):
    async def handle(reader, writer):
        await reader.read(65536)
        writer.write(reply)
        await writer.drain()
        writer.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.parametrize("reply", [b"INSTREAM size limit exceeded. ERROR\0", b"gibberish\0", b""])
async def test_error_or_garbage_reply_is_unavailable(reply):     # F8: fail-closed
    server, port = await _serve_reply(reply)
    try:
        with pytest.raises(ScannerUnavailable):
            await instream_scan("127.0.0.1", port, b"data", timeout_s=2)
    finally:
        server.close()


async def test_silent_server_times_out():
    async def handle(reader, writer):
        await asyncio.sleep(5)
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    try:
        with pytest.raises(ScannerUnavailable):
            await instream_scan("127.0.0.1", server.sockets[0].getsockname()[1], b"x", timeout_s=0.5)
    finally:
        server.close()


async def test_version(fake_clamd):
    assert (await clamd_version(*fake_clamd)).startswith("ClamAV")
