# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đồng bộ một lần với máy chủ DX-OS (spec 11.4; Plan 01 Task 16).

1. Lấy STH mới nhất và khóa công khai; kiểm chữ ký → sai: ``BAD_SIGNATURE``.
   Khóa của cùng một phiên bản mà đổi so với lần trước (key pinning) cũng là ``BAD_SIGNATURE``.
2. Có tệp neo cùng ``tree_size`` mà khác nội dung → ``ANCHOR_MISMATCH``.
3. Chưa có STH đã lưu → lưu, ``FIRST_RUN``.
4. Cùng ``tree_size`` khác root, hoặc cây nhỏ đi → ``REWRITE_DETECTED``.
5. Cây lớn hơn → kiểm consistency proof; sai → ``INCONSISTENT``; đúng → lưu, ``OK``.

Chỉ lưu trạng thái mới khi kết quả là ``OK``/``FIRST_RUN``: bằng chứng cũ không bao giờ bị ghi đè
bởi STH đáng ngờ.
Witness không import dxos-core; chỉ dùng thư viện chung dxos-proof.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import verify_consistency

Status = Literal["OK", "FIRST_RUN", "REWRITE_DETECTED", "INCONSISTENT", "BAD_SIGNATURE", "ANCHOR_MISMATCH"]
STATE_FILE = "latest-sth.json"
KEYS_FILE = "known-keys.json"
_STH_FIELDS = ("tree_size", "root_hash", "ts", "key_version", "signature")


@dataclass
class SyncResult:
    status: Status
    tree_size: int
    detail: str


class WitnessError(Exception):
    """Không làm được phép kiểm (mạng, phản hồi sai dạng). Không kết luận được log đúng hay sai."""


def sth_path(tree_size: int) -> str:
    return f"sth/{tree_size:012d}.json"


def signing_bytes(th: dict) -> bytes:
    return canonical_bytes({k: th[k] for k in ("tree_size", "root_hash", "ts", "key_version")})


def signature_ok(th: dict, pubkey: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(base64.b64decode(th["signature"], validate=True),
                                                          signing_bytes(th))
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False


def _get(client: httpx.Client, path: str, **params) -> dict:
    try:
        r = client.get(path, params=params or None)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WitnessError(f"GET {path}: {type(exc).__name__}: {exc}") from exc


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_sth(obj: dict) -> dict:
    try:
        th = {k: obj[k] for k in _STH_FIELDS}
        if not (isinstance(th["tree_size"], int) and isinstance(th["key_version"], int)):
            raise TypeError("tree_size/key_version phải là số nguyên")
        bytes.fromhex(th["root_hash"])
        return th
    except (KeyError, TypeError, ValueError) as exc:
        raise WitnessError(f"STH sai dạng: {exc}") from exc


def sync(server_url: str, anchor_dir: Path, state_dir: Path, *, timeout_s: float = 15.0) -> SyncResult:
    anchor_dir, state_dir = Path(anchor_dir), Path(state_dir)
    with httpx.Client(base_url=server_url.rstrip("/"), timeout=timeout_s) as client:
        th = _parse_sth(_get(client, "/verify/v1/sth/latest"))
        keys = _get(client, "/verify/v1/keys").get("sth-key", {})
        size = th["tree_size"]

        # 1. chữ ký + key pinning
        try:
            pubkey = base64.b64decode(keys[str(th["key_version"])], validate=True)
        except (KeyError, ValueError, binascii.Error):
            return SyncResult("BAD_SIGNATURE", size, f"không có khóa sth-key phiên bản {th['key_version']}")
        known = _load(state_dir / KEYS_FILE) or {}
        pinned = known.get(str(th["key_version"]))
        if pinned is not None and pinned != keys[str(th["key_version"])]:
            return SyncResult("BAD_SIGNATURE", size,
                              f"khóa sth-key v{th['key_version']} bị thay so với lần trước")
        if not signature_ok(th, pubkey):
            return SyncResult("BAD_SIGNATURE", size, "chữ ký STH không hợp lệ")

        # 2. đối chiếu repo neo
        anchored = anchor_dir / sth_path(size)
        if anchored.exists():
            try:
                anchored_th = json.loads(anchored.read_text(encoding="utf-8"))
            except ValueError:
                return SyncResult("ANCHOR_MISMATCH", size, f"{sth_path(size)} không phải JSON")
            if {k: anchored_th.get(k) for k in _STH_FIELDS} != th:
                return SyncResult("ANCHOR_MISMATCH", size,
                                  f"STH máy chủ khác {sth_path(size)} trong repo neo")

        # 3. lần đầu
        prev = _load(state_dir / STATE_FILE)
        if prev is None:
            _save(state_dir / STATE_FILE, th)
            _save(state_dir / KEYS_FILE, {**known, **keys})
            return SyncResult("FIRST_RUN", size, "đã lưu STH đầu tiên")

        # 4. viết lại
        if size < prev["tree_size"]:
            return SyncResult("REWRITE_DETECTED", size, f"cây nhỏ đi: {prev['tree_size']} → {size}")
        if size == prev["tree_size"]:
            if th["root_hash"] != prev["root_hash"]:
                return SyncResult("REWRITE_DETECTED", size, "cùng kích thước nhưng root khác")
            return SyncResult("OK", size, "không đổi")

        # 5. consistency
        resp = _get(client, "/verify/v1/sth/consistency", first=prev["tree_size"], second=size)
        proof = resp.get("proof", [])
        try:
            ok = verify_consistency(prev["tree_size"], size, bytes.fromhex(prev["root_hash"]),
                                    bytes.fromhex(th["root_hash"]), [bytes.fromhex(p) for p in proof])
        except ValueError:
            ok = False
        if not ok:
            return SyncResult("INCONSISTENT", size,
                              f"consistency proof {prev['tree_size']} → {size} không hợp lệ")
        _save(state_dir / STATE_FILE, th)
        _save(state_dir / KEYS_FILE, {**known, **keys})
        return SyncResult("OK", size, f"{prev['tree_size']} → {size} nhất quán")
