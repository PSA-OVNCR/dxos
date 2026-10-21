# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Máy chủ ledger giả (chạy trong tiến trình test) và bộ dựng gói bằng chứng để kiểm dxos-witness độc lập với
trust-core. Không import ``dxos_core``: mọi thứ được dựng bằng code riêng của test + dxos-proof."""

import base64
import copy
import hashlib
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import consistency_proof, inclusion_proof, root


class FakeLedger:
    def __init__(self, anchor_dir: Path) -> None:
        self.anchor_dir = anchor_dir
        self.entries: list[bytes] = []
        self.key = Ed25519PrivateKey.generate()
        self.seal_key = Ed25519PrivateKey.generate()
        self.sths: list[dict] = []
        self.tamper = False
        self.throttle = 0
        self.extra_keys: dict = {}
        self.keys_override: dict | None = None      # đặt: /keys trả đúng object này
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

    def _served_keys(self) -> dict[str, bytes]:
        return {"sth-key": _raw(self.key), "seal-key": _raw(self.seal_key)}

    def publish_keys_to(self, anchor_dir: Path) -> None:
        """Ghi ``keys/<khóa>/v1.pub`` (base64 + ``\\n``) của khóa máy chủ đang phục vụ vào repo neo."""
        for name, raw in self._served_keys().items():
            f = Path(anchor_dir) / f"keys/{name}/v1.pub"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(base64.b64encode(raw) + b"\n")

    def rotate_key_same_version(self, key: str) -> None:
        """Máy chủ thay khóa ``key`` (``seal-key``/``sth-key``) bằng khóa mới nhưng vẫn gọi là v1."""
        if key == "sth-key":
            self.key = Ed25519PrivateKey.generate()
        else:
            self.seal_key = Ed25519PrivateKey.generate()

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
        if path == "/verify/v1/keys" and self.keys_override is not None:
            return 200, self.keys_override
        if path == "/verify/v1/keys":
            keys = {k: base64.b64encode(v).decode() for k, v in self._served_keys().items()}
            return 200, {"seal-key": {"1": keys["seal-key"]},
                         "sth-key": {"1": keys["sth-key"], **self.extra_keys}}
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


@pytest.fixture
def fake_ledger(server):
    """``FakeLedger`` đang phục vụ HTTP (như ``server``): cây 3 lá, STH cỡ 3 đã neo vào ``anchor_dir``."""
    return server


@pytest.fixture
def anchor_dir(fake_ledger):
    """Thư mục repo neo của ``fake_ledger`` (có ``sth/000000000003.json``)."""
    return fake_ledger.anchor_dir


@pytest.fixture
def state_dir(tmp_path):
    """Thư mục trạng thái riêng (rỗng) của witness."""
    return tmp_path / "state"


# ====================================================================== gói bằng chứng (Plan 02 Task 9)
def _raw(sk: Ed25519PrivateKey) -> bytes:
    return sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


SEAL_ID = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:26]
LEAF_INDEX = 5
ORIGINAL = "tệp gốc của bản ghi".encode()
# STH cần có của mỗi bố cục: (cỡ STH neo, cỡ STH trong gói). Lá niêm phong ở idx 5.
LAYOUTS = {
    "anchored_is_sth": (8, 8),        # như lõi sinh khi đã có neo phủ lá: anchored.sth == sth, proof rỗng
    "newer_sth": (7, 10),             # neo phủ lá, sth mới hơn: consistency 7 → 10
    "anchor_before_leaf": (5, 8),     # neo cỡ 5 = leaf_index: CHƯA phủ lá (C8)
}


def _sign_sth(sk: Ed25519PrivateKey, entries: list[bytes], size: int, ts: str, key_version: int = 1) -> dict:
    th = {"tree_size": size, "root_hash": root(entries[:size]).hex(), "ts": ts, "key_version": key_version}
    return {**th, "signature": _b64(sk.sign(canonical_bytes(th)))}


class BundleEnv:
    """Dựng gói ``dxos-seal-bundle/1`` hợp lệ + repo neo khớp, bằng thuật toán riêng của test (không lõi)."""

    seal_id = SEAL_ID
    original = ORIGINAL

    @staticmethod
    def pub_b64(sk: Ed25519PrivateKey) -> str:
        """Khóa công khai ed25519 thô của ``sk``, dạng base64."""
        return _b64(_raw(sk))

    def __init__(self, root_dir: Path) -> None:
        self.root = root_dir
        self.seal_sk = Ed25519PrivateKey.generate()
        self.sth_sk = Ed25519PrivateKey.generate()
        self._n = 0
        self.bundle, self.anchor_dir = self.build()

    # ---------------------------------------------------------------- dựng
    def statement(self, *, valid_from: str = "2026-10-21T08:00:00Z",
                  valid_until: str = "2036-10-19T08:00:00Z") -> dict:
        return {"format": "dxos-key-statement/1", "key": "seal-key", "version": 1, "serial": "seal-key/v1",
                "issuer": {"name": "Trường Đại học Thử", "id": "TDHT-01"}, "algorithm": "ed25519",
                "public_key": _b64(_raw(self.seal_sk)), "valid_from": valid_from, "valid_until": valid_until,
                "purpose": "Niêm phong hồ sơ số (thử)", "policy_url": None}

    def payload(self, issued_at: str, public_fields: dict | None = None) -> dict:
        pf = {"ref": "01/TF", "title": "Quyết định thử"} if public_fields is None else public_fields
        return {"seal_id": SEAL_ID, "app_id": "test-flow",
                "record_id": "0b9f6c1e-4c39-4f61-9b2a-3a1d7f6e0c55",
                "record_digest": _sha(b"digest"), "attachments": [_sha(ORIGINAL)], "issued_at": issued_at,
                "public_fields": pf, "key_version": 1}

    def build(self, *, layout: str = "anchored_is_sth", issued_at: str = "2026-10-21T09:00:00Z",
              statement: dict | None = None, public_fields: dict | None = None) -> tuple[dict, Path]:
        """``(gói, repo neo)`` hợp lệ theo ``layout`` (xem ``LAYOUTS``); mọi chữ ký/hash tính bằng
        ``canonical_bytes`` nên gói luôn tự nhất quán."""
        anchored_size, sth_size = LAYOUTS[layout]
        payload = self.payload(issued_at, public_fields)
        st = statement if statement is not None else self.statement()
        body = {"seal_id": SEAL_ID, "payload_sha256": _sha(canonical_bytes(payload))}
        entries_obj = []
        for i in range(12):
            e = {"idx": i, "ts": f"2026-10-21T09:00:{i:02d}Z", "type": "record.created",
                 "app_id": "test-flow", "subject": f"r{i}", "actor_ref": "a" * 16,
                 "body_sha256": _sha(f"b{i}".encode())}
            if i == LEAF_INDEX:
                e.update(type="record.sealed", subject=SEAL_ID, body_sha256=_sha(canonical_bytes(body)))
            entries_obj.append(e)
        entries = [canonical_bytes(e) for e in entries_obj]
        sth = _sign_sth(self.sth_sk, entries, sth_size, "2026-10-21T09:05:00Z")
        anchored_sth = (sth if anchored_size == sth_size
                        else _sign_sth(self.sth_sk, entries, anchored_size, "2026-10-21T09:04:00Z"))
        consistency = ([] if anchored_size == sth_size
                       else [p.hex() for p in consistency_proof(anchored_size, entries[:sth_size])])
        bundle = {
            "format": "dxos-seal-bundle/1", "status": "VALID", "payload": payload,
            "signature": _b64(self.seal_sk.sign(canonical_bytes(payload))),
            "seal_key": {"version": 1, "public_key": _b64(_raw(self.seal_sk)), "statement": st},
            "ledger": {"entry": entries_obj[LEAF_INDEX], "body": body},
            "inclusion": {"leaf_index": LEAF_INDEX, "tree_size": sth_size,
                          "proof": [p.hex() for p in inclusion_proof(LEAF_INDEX, entries[:sth_size])]},
            "sth": sth, "sth_keys": {"1": _b64(_raw(self.sth_sk))},
            "anchored": {"sth": copy.deepcopy(anchored_sth), "repo": "https://github.com/x/dxos-transparency-log",
                         "commit_sha": "c" * 40, "consistency": consistency},
            "generated_at": "2026-10-21T10:00:00Z",
        }
        self._n += 1
        anchor = self.root / f"anchor-{self._n}"
        files = {f"sth/{anchored_size:012d}.json": canonical_bytes(anchored_sth),
                 "sth/000000000003.json": canonical_bytes(_sign_sth(self.sth_sk, entries, 3,
                                                                    "2026-10-21T09:01:00Z")),
                 "keys/seal-key/v1.pub": base64.b64encode(_raw(self.seal_sk)) + b"\n",
                 "keys/sth-key/v1.pub": base64.b64encode(_raw(self.sth_sk)) + b"\n",
                 "keys/seal-key/v1.json": canonical_bytes(st) + b"\n"}
        for rel, content in files.items():
            (anchor / rel).parent.mkdir(parents=True, exist_ok=True)
            (anchor / rel).write_bytes(content)
        return bundle, anchor

    def copy(self, bundle: dict | None = None, anchor: Path | None = None) -> tuple[dict, Path]:
        """Bản sao sâu của gói và repo neo (mặc định: bản gốc) để sửa mà không ảnh hưởng bản khác."""
        self._n += 1
        dst = self.root / f"anchor-{self._n}"
        shutil.copytree(anchor or self.anchor_dir, dst)
        return copy.deepcopy(bundle or self.bundle), dst

    # ---------------------------------------------------------------- sửa
    def tampered(self, name: str) -> tuple[dict, Path]:
        """``(gói, repo neo)`` đã bị sửa theo kịch bản ``name`` (xem ``_TAMPERS``)."""
        if name == "consistency_node":
            b, a = self.copy(*self.build(layout="newer_sth"))
            b["anchored"]["consistency"][0] = _flip_hex(b["anchored"]["consistency"][0])
            return b, a
        if name == "leaf_after_last_anchor":
            return self.build(layout="anchor_before_leaf")
        b, a = self.copy()
        _TAMPERS[name](self, b, a)
        return b, a

    def with_issued_at_after_valid_until(self) -> tuple[dict, Path]:
        """Gói ký đúng nhưng ``payload.issued_at`` sau ``valid_until`` của tuyên bố (cả gói lẫn tệp neo)."""
        return self.build(issued_at="2026-10-21T09:00:00Z",
                          statement=self.statement(valid_until="2026-10-21T08:30:00Z"))


def _flip_hex(h: str) -> str:
    return ("0" if h[0] != "0" else "1") + h[1:]


def _flip_b64(s: str) -> str:
    raw = bytearray(base64.b64decode(s))
    raw[0] ^= 1
    return _b64(bytes(raw))


def _set_statement(a: Path, st: dict) -> None:
    (a / "keys/seal-key/v1.json").write_bytes(canonical_bytes(st) + b"\n")


def _swap_bundle_key(env: BundleEnv, b: dict, a: Path) -> None:
    """Kẻ tấn công ký lại payload bằng khóa của mình và đưa khóa đó vào gói (cả tuyên bố trong gói)."""
    sk = Ed25519PrivateKey.generate()
    b["signature"] = _b64(sk.sign(canonical_bytes(b["payload"])))
    b["seal_key"]["public_key"] = _b64(_raw(sk))
    b["seal_key"]["statement"]["public_key"] = _b64(_raw(sk))


def _statement_validity(env: BundleEnv, b: dict, a: Path) -> None:
    b["seal_key"]["statement"]["valid_until"] = "2026-10-21T08:59:59Z"
    _set_statement(a, b["seal_key"]["statement"])


def _statement_key(env: BundleEnv, b: dict, a: Path) -> None:
    b["seal_key"]["statement"]["public_key"] = _b64(_raw(Ed25519PrivateKey.generate()))
    _set_statement(a, b["seal_key"]["statement"])


_TAMPERS = {
    "payload_field": lambda e, b, a: b["payload"]["public_fields"].update(title="Quyết định đã sửa"),
    "signature": lambda e, b, a: b.update(signature=_flip_b64(b["signature"])),
    "entry_ts": lambda e, b, a: b["ledger"]["entry"].update(ts="2026-10-21T09:00:59Z"),
    "entry_idx": lambda e, b, a: b["ledger"]["entry"].update(idx=LEAF_INDEX + 1),
    "proof_node": lambda e, b, a: b["inclusion"]["proof"].__setitem__(
        0, _flip_hex(b["inclusion"]["proof"][0])),
    "sth_root": lambda e, b, a: b["sth"].update(root_hash=_flip_hex(b["sth"]["root_hash"])),
    "anchored_sth": lambda e, b, a: b["anchored"]["sth"].update(
        root_hash=_flip_hex(b["anchored"]["sth"]["root_hash"])),
    "swap_bundle_key": _swap_bundle_key,
    "key_version": lambda e, b, a: b["seal_key"].update(version=2),
    "anchored_null": lambda e, b, a: b.update(anchored=None),
    "anchor_file_missing": lambda e, b, a: (a / "sth/000000000008.json").unlink(),
    "statement_validity": _statement_validity,
    "statement_key": _statement_key,
    "statement_mismatch": lambda e, b, a: b["seal_key"]["statement"].update(purpose="Mục đích khác"),
    "statement_missing": lambda e, b, a: (a / "keys/seal-key/v1.json").unlink(),
}


@pytest.fixture
def bundle_env(tmp_path):
    """``BundleEnv``: ``.bundle``/``.anchor_dir`` hợp lệ (đã ghim được), ``tampered(name)``,
    ``build(layout=…)``, ``copy()``, ``with_issued_at_after_valid_until()``; khóa ``seal_sk``/``sth_sk``
    của test."""
    return BundleEnv(tmp_path / "bundle-env")
