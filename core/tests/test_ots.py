# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client calendar OpenTimestamps tối thiểu và tệp ``.ots`` (Plan 03 Task 14, P3-D10; Đ2).

Tệp ``.ots`` (detached timestamp): magic, phiên bản ``0x01``, op ``0x08`` (sha256), 32 byte digest, rồi
timestamp. Timestamp là một nút: mọi nhánh trừ nhánh cuối có tiền tố ``0xff``; nhánh là ``0x00`` + biên nhận
(8 byte thẻ + varbytes) hoặc một op + nút con. Vector chuẩn với client chính thức chỉ chạy khi
``DXOS_OTS_CLIENT=ots`` (cần lệnh ``ots`` của opentimestamps-client trong PATH).
"""

import asyncio
import base64
import dataclasses
import hashlib
import http.server
import os
import shutil
import subprocess
import threading
import time

import httpx
import pytest
from dxos_core.ledger import ots
from dxos_core.ledger.sth import TreeHead
from dxos_proof.canonical import canonical_bytes

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
PENDING = bytes.fromhex("83dfe30d2ef90c8e")
DIGEST = hashlib.sha256(b"sth").digest()


def vb(b: bytes) -> bytes:
    assert len(b) < 128
    return bytes([len(b)]) + b


def pending(uri: str) -> bytes:
    return b"\x00" + PENDING + vb(vb(uri.encode()))


def reply(ts: bytes, mac: bytes, uri: str) -> bytes:
    """Như calendar thật: prepend(thời điểm 4 byte) → append(mac 8 byte) → sha256 → biên nhận pending."""
    return b"\xf1" + vb(ts) + b"\xf0" + vb(mac) + b"\x08" + pending(uri)


R_A = reply(b"\x65\x00\x00\x01", b"A" * 8, "https://a.example")
R_B = reply(b"\x65\x00\x00\x02", b"B" * 8, "https://b.example")
HEADER_LEN = len(MAGIC) + 2 + 32


# ---------- Step 1 của brief ----------

def test_request_digest_is_sha256_of_canonical_sth():
    th = TreeHead(5, "cd" * 32, "2026-10-20T00:00:00Z", 1, "c2ln")
    sth = dataclasses.asdict(th)
    assert ots.ots_request_digest(sth) == hashlib.sha256(canonical_bytes(sth)).digest()


def test_header_magic_version_and_digest_position():
    f = ots.detached_timestamp(DIGEST, [R_A])
    assert f.startswith(MAGIC)
    assert f[len(MAGIC)] == 0x01 and f[len(MAGIC) + 1] == 0x08
    assert f[len(MAGIC) + 2:HEADER_LEN] == DIGEST


def test_single_reply_is_appended_verbatim():
    assert ots.detached_timestamp(DIGEST, [R_A]) == MAGIC + b"\x01\x08" + DIGEST + R_A


def test_two_replies_have_exactly_one_fork_byte_between_branches():
    body = ots.detached_timestamp(DIGEST, [R_B, R_A])[HEADER_LEN:]
    assert body == b"\xff" + R_A + R_B                  # nhánh xếp theo op như client chính thức
    assert body.count(b"\xff") == 1
    assert ots.detached_timestamp(DIGEST, [R_A, R_B]) == ots.detached_timestamp(DIGEST, [R_B, R_A])


# ---------- bổ sung: biên nhận là dữ liệu từ mạng, kiểm trước khi ghi vĩnh viễn vào repo neo ----------

def test_replies_sharing_first_op_are_merged_not_duplicated():
    """Hai calendar nhận cùng giây → cùng op prepend đầu. Nối thẳng hai nhánh trùng op thì trình đọc chính
    thức (dict theo op) chỉ giữ một nhánh; phải gộp thành một op với nút con rẽ nhánh."""
    ts = b"\x65\x00\x00\x09"
    r1, r2 = reply(ts, b"A" * 8, "https://a.example"), reply(ts, b"B" * 8, "https://b.example")
    body = ots.detached_timestamp(DIGEST, [r1, r2])[HEADER_LEN:]
    tail1, tail2 = r1[len(b"\xf1" + vb(ts)):], r2[len(b"\xf1" + vb(ts)):]
    assert body == b"\xf1" + vb(ts) + b"\xff" + tail1 + tail2
    assert b"https://a.example" in body and b"https://b.example" in body


def test_identical_replies_collapse():
    assert ots.detached_timestamp(DIGEST, [R_A, R_A]) == ots.detached_timestamp(DIGEST, [R_A])


def test_forked_reply_is_merged_correctly():
    forked = b"\xff" + R_A + R_B                          # một calendar trả timestamp đã rẽ nhánh ở gốc
    r_c = reply(b"\x65\x00\x00\x03", b"C" * 8, "https://c.example")
    body = ots.detached_timestamp(DIGEST, [forked, r_c])[HEADER_LEN:]
    assert body == b"\xff" + R_A + b"\xff" + R_B + r_c


def test_attestation_branches_come_before_op_branches():
    direct = pending("https://d.example")                 # biên nhận ngay trên digest
    body = ots.detached_timestamp(DIGEST, [R_A, direct])[HEADER_LEN:]
    assert body == b"\xff" + direct + R_A


@pytest.mark.parametrize("bad", [
    b"",                                                   # rỗng
    R_A + b"\x00",                                         # thừa byte
    R_A[:-3],                                              # cụt
    b"\x42" + R_A,                                         # thẻ op lạ
    b"\xff\xff" + R_A,                                     # 0xff hai lần
    b"\xff" + R_A,                                         # 0xff mà không có nhánh sau
    b"\xf0\x00" + pending("https://x"),                    # append đối số rỗng
    b"\x08" * 300 + pending("https://x"),                  # quá sâu
    b"\x00" + PENDING + b"\x80",                           # varuint cụt
    b"<html>502 Bad Gateway</html>",
    # fix vòng 1: chặt như trình đọc chính thức (thông điệp qua op ≤ 4096, URI pending, payload đọc hết)
    b"\xf0" + bytes([0xa0, 0x1f]) + b"a" * 4000 + b"\xf0" + bytes([0xa0, 0x1f]) + b"b" * 4000
    + pending("https://x"),                                # 32 + 4000 + 4000 = 8032 > 4096
    b"\xf3" * 8 + pending("https://x"),                    # hexlify ×8: 32·2⁸ = 8192 > 4096
    pending("https://a b"),                                # khoảng trắng trong URI
    b"\x00" + PENDING + vb(vb(b"\xff\xfe")),               # URI không phải ASCII cho phép
    b"\x00" + PENDING + bytes([0xd2, 0x0f]) + bytes([0xd0, 0x0f]) + b"x" * 2000,   # URI 2000 > 1000
    b"\x00" + PENDING + vb(vb(b"https://x") + b"rac"),     # payload pending thừa byte
    b"\x00" + bytes.fromhex("0588960d73d71901") + vb(b"\x01\x02"),             # bitcoin: thừa byte
])
def test_malformed_reply_rejected(bad):
    with pytest.raises(ots.OtsFormatError):
        ots.parse_timestamp(bad)
    with pytest.raises(ots.OtsFormatError):
        ots.detached_timestamp(DIGEST, [bad])


def test_limits_of_official_reader_still_accepted():
    ots.parse_timestamp(b"\xf3" * 7 + pending("https://x"))                      # 32·2⁷ = 4096: vừa đủ
    ots.parse_timestamp(b"\xf0" + bytes([0xe0, 0x1f]) + b"a" * 4064 + pending("https://x"))   # 32 + 4064
    ots.parse_timestamp(b"\x08\x00" + PENDING + bytes([0xea, 0x07, 0xe8, 0x07]) + b"x" * 1000)   # URI 1000
    ots.parse_timestamp(b"\x00" + bytes.fromhex("0588960d73d71901") + vb(b"\x81\x01"))   # bitcoin, cao 129
    ots.parse_timestamp(b"\x00" + b"\x11" * 8 + vb("thẻ lạ".encode()))           # thẻ lạ: giữ nguyên
    with pytest.raises(ots.OtsFormatError):
        ots.parse_timestamp(b"\xf0" + bytes([0xe1, 0x1f]) + b"a" * 4065 + pending("https://x"))


def test_reply_size_limit():
    big = b"\xf0" + bytes([0x90, 0x4e]) + b"x" * 10000 + pending("https://x")   # varuint 10000
    with pytest.raises(ots.OtsFormatError):
        ots.parse_timestamp(big)


def test_needs_digest_and_reply():
    with pytest.raises(ValueError):
        ots.detached_timestamp(DIGEST, [])
    with pytest.raises(ValueError):
        ots.detached_timestamp(DIGEST[:31], [R_A])


def test_ots_path():
    assert ots.ots_path(42) == "ots/000000000042.ots"


# ---------- calendar ----------

async def test_submit_posts_raw_digest_like_official_client():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, content=R_A)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await ots.submit_digest(client, "https://a.example", DIGEST) == R_A
    (req,) = seen
    assert req.method == "POST" and str(req.url) == "https://a.example/digest"
    assert req.content == DIGEST
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert req.headers["accept"] == "application/vnd.opentimestamps.v1"
    assert req.extensions["timeout"] == {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}


@pytest.mark.parametrize("resp", [httpx.Response(500, content=R_A), httpx.Response(200, content=b"oops"),
                                  httpx.Response(200, content=R_A + b"x" * 10001)])
async def test_submit_rejects_bad_responses(resp):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: resp)) as client:
        with pytest.raises((httpx.HTTPError, ots.OtsFormatError)):
            await ots.submit_digest(client, "https://a.example", DIGEST)


async def test_submit_has_total_deadline_against_trickling_calendar(monkeypatch):
    """Timeout của httpx tính từng lần đọc: calendar nhỏ giọt từng byte phải bị cắt ở hạn tổng."""
    monkeypatch.setattr(ots, "CALENDAR_TIMEOUT_S", 0.5)

    async def trickle():
        for b in R_A:
            await asyncio.sleep(0.2)
            yield bytes([b])

    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=trickle()))
    t0 = time.monotonic()
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(TimeoutError):
            await ots.submit_digest(client, "https://a.example", DIGEST)
    assert time.monotonic() - t0 < 2.0


async def test_submit_stops_reading_oversized_stream():
    sent = []

    async def endless():
        while True:
            sent.append(1)
            yield b"\x08" * 1000

    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=endless()))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ots.OtsFormatError, match="10000"):
            await ots.submit_digest(client, "https://a.example", DIGEST)
    assert len(sent) <= 11                                 # dừng ngay khi quá 10000 byte, không đọc hết


def test_calendar_setting(make_settings):
    assert make_settings().ots_calendars == ""
    assert ots.calendar_urls(make_settings()) == []
    s = make_settings(ots_calendars=" https://a.pool.opentimestamps.org/,"
                                    " https://b.pool.opentimestamps.org ,")
    assert ots.calendar_urls(s) == ["https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org"]
    with pytest.raises(ValueError, match="https"):
        make_settings(ots_calendars="http://a.pool.opentimestamps.org")
    with pytest.raises(ValueError, match="trùng"):
        make_settings(ots_calendars="https://a.example,https://a.example/")
    assert ots.calendar_urls(make_settings(ots_calendars="https://a.example/cal/")) == ["https://a.example/cal"]
    for bad in ("https://", "https:///x", "https://a b.example", "https://u:p@a.example",
                "https://a.example?x=1", "https://a.example#f", "ftp://a.example", "a.example",
                "https://a.example\t/x"):
        with pytest.raises(ValueError, match="https"):
            make_settings(ots_calendars=bad)
    make_settings(ots_calendars=",".join(f"https://c{i}.example" for i in range(8)))
    with pytest.raises(ValueError, match="tối đa 8"):
        make_settings(ots_calendars=",".join(f"https://c{i}.example" for i in range(9)))


# ---------- vector chuẩn: client chính thức (chỉ khi DXOS_OTS_CLIENT=ots) ----------

class _FakeCalendar(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (tên do http.server quy định)
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(R_A)

    def log_message(self, *a):
        pass


@pytest.mark.skipif(os.environ.get("DXOS_OTS_CLIENT") != "ots" or shutil.which("ots") is None,
                    reason="cần DXOS_OTS_CLIENT=ots và lệnh `ots` (opentimestamps-client)")
def test_official_client_header_and_parses_our_file(tmp_path):
    th = TreeHead(5, "cd" * 32, "2026-10-20T00:00:00Z", 1, "c2ln")
    sth_file = tmp_path / "000000000005.json"
    sth_file.write_bytes(canonical_bytes(dataclasses.asdict(th)))      # đúng byte của sth/<n>.json
    digest = ots.ots_request_digest(dataclasses.asdict(th))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeCalendar)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cal = f"http://127.0.0.1:{srv.server_address[1]}"
        subprocess.run(["ots", "stamp", "-c", cal, "-m", "1", str(sth_file)], check=True, timeout=60)
    finally:
        srv.shutdown()
    official = (tmp_path / "000000000005.json.ots").read_bytes()
    ours = ots.detached_timestamp(digest, [R_A])
    assert official[:HEADER_LEN] == ours[:HEADER_LEN]
    ours_file = tmp_path / "ours.ots"
    ours_file.write_bytes(ours)
    info = subprocess.run(["ots", "info", str(ours_file)], check=True, capture_output=True, text=True,
                          timeout=60).stdout
    assert digest.hex() in info and "https://a.example" in info
    assert base64.b64encode(ours)                         # tệp đưa vào gói dạng base64
