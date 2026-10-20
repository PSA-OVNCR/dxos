# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Máy chủ ledger giả (chạy trong tiến trình test) để kiểm dxos-witness độc lập với trust-core."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import consistency_proof, root


class FakeLedger:
    def __init__(self, anchor_dir: Path) -> None:
        self.anchor_dir = anchor_dir
        self.entries: list[bytes] = []
        self.key = Ed25519PrivateKey.generate()
        self.sths: list[dict] = []
        self.tamper = False
        self.throttle = 0
        self.extra_keys: dict = {}
        self._n = 0

    # --- thao tác của "máy chủ"
    def add_entries(self, n: int, tag: str = "e") -> None:
        for _ in range(n):
            self.entries.append(canonical_bytes({"idx": len(self.entries), "tag": tag, "n": self._n}))
            self._n += 1

    def make_sth(self) -> dict:
        size = len(self.entries)
        th = {"tree_size": size, "root_hash": root(self.entries).hex(), "ts": "2026-10-20T00:00:00Z",
              "key_version": 1}
        th["signature"] = base64.b64encode(self.key.sign(canonical_bytes(th))).decode()
        self.sths.append(th)
        return th

    def anchor(self, th: dict) -> None:
        p = self.anchor_dir / f"sth/{th['tree_size']:012d}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(canonical_bytes(th))

    def make_and_anchor_sth(self) -> dict:
        th = self.make_sth()
        self.anchor(th)
        return th

    def make_sth_without_anchor(self) -> dict:
        return self.make_sth()

    def rebuild_log_with_different_entries(self, same_key: bool = True) -> None:
        """Kẻ có root VPS dựng lại toàn bộ log (khóa ký vẫn nằm trong tay hắn)."""
        n = len(self.entries) + 2
        self.entries = []
        self.add_entries(n, tag="forged")
        if not same_key:
            self.key = Ed25519PrivateKey.generate()

    def serve_tampered_signature(self) -> None:
        self.tamper = True

    # --- HTTP
    def handle(self, path: str, query: dict) -> tuple[int, dict]:
        if self.throttle > 0:
            self.throttle -= 1
            return 429, {"type": "rate-limited"}
        if path == "/verify/v1/sth/latest":
            if not self.sths:
                return 404, {"type": "not-found"}
            th = dict(self.sths[-1])
            if self.tamper:
                sig = bytearray(base64.b64decode(th["signature"]))
                sig[0] ^= 1
                th["signature"] = base64.b64encode(bytes(sig)).decode()
            return 200, th
        if path == "/verify/v1/keys":
            pk = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            return 200, {"seal-key": {}, "sth-key": {"1": base64.b64encode(pk).decode(), **self.extra_keys}}
        if path == "/verify/v1/sth/consistency":
            first, second = int(query["first"][0]), int(query["second"][0])
            if not 1 <= first <= second <= len(self.entries):
                return 400, {"type": "bad-request"}
            proof = consistency_proof(first, self.entries[:second])
            return 200, {"first": first, "second": second, "proof": [p.hex() for p in proof]}
        return 404, {"type": "not-found"}


@pytest.fixture
def server(tmp_path):
    anchor_dir = tmp_path / "anchor"
    anchor_dir.mkdir()
    ledger = FakeLedger(anchor_dir)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            u = urlsplit(self.path)
            status, body = ledger.handle(u.path, parse_qs(u.query))
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ledger.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    ledger.add_entries(3)
    ledger.make_and_anchor_sth()
    try:
        yield ledger
    finally:
        httpd.shutdown()
