# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đồng bộ một lần với máy chủ DX-OS (spec 11.4; Plan 01 Task 16).

1. Lấy STH mới nhất và khóa công khai; kiểm chữ ký → sai: ``BAD_SIGNATURE``.
   Khóa của một phiên bản đã ghim mà đổi (key pinning) cũng là ``BAD_SIGNATURE``.
2. Đọc **mọi** STH trong repo neo; tệp sai chữ ký/sai tên, hoặc cùng ``tree_size`` mà khác STH máy chủ
   → ``ANCHOR_MISMATCH``; có STH neo lớn hơn STH máy chủ (máy chủ quay lui) → ``REWRITE_DETECTED``.
3. **Chuỗi neo**: từng cặp STH neo liên tiếp (từ mốc đã kiểm lần trước) và STH neo mới nhất → STH hiện tại
   phải có consistency proof hợp lệ → sai: ``INCONSISTENT``. Nhờ vậy lịch sử **đã neo** không viết lại được,
   kể cả khi witness mất trạng thái hay chạy lần đầu (spec 11.3, mô hình X3).
4. So với STH witness đã kiểm lần trước: cây nhỏ đi hoặc cùng cỡ khác root → ``REWRITE_DETECTED``;
   consistency sai → ``INCONSISTENT``.
5. Đạt hết: lưu trạng thái, trả ``FIRST_RUN`` (lần đầu) hoặc ``OK``.

Chỉ lưu trạng thái mới khi kết quả là ``OK``/``FIRST_RUN``: bằng chứng cũ không bao giờ bị ghi đè
bởi STH đáng ngờ. Witness không import dxos-core; chỉ dùng thư viện chung dxos-proof.
"""

import base64
import binascii
import json
import re
import time
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
    """GET JSON object; 429 (API công khai có rate-limit) thì chờ rồi thử lại tối đa 5 lần."""
    for attempt in range(1, 6):
        try:
            r = client.get(path, params=params or None)
            if r.status_code == 429 and attempt < 5:
                retry_after = r.headers.get("retry-after", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else 1.5 * attempt)
                continue
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WitnessError(f"GET {path}: {type(exc).__name__}: {exc}") from exc
        if not isinstance(body, dict):
            raise WitnessError(f"GET {path}: phản hồi không phải JSON object")
        return body
    raise WitnessError(f"GET {path}: vẫn bị giới hạn tốc độ sau 5 lần")


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


_ANCHOR_NAME = re.compile(r"^(\d{12})\.json$")


def _consistent(client: httpx.Client, a: dict, b: dict) -> bool:
    """STH ``a`` (cỡ nhỏ hơn hoặc bằng) có phải tiền tố của STH ``b`` không."""
    if a["tree_size"] == b["tree_size"]:
        return a["root_hash"] == b["root_hash"]
    resp = _get(client, "/verify/v1/sth/consistency", first=a["tree_size"], second=b["tree_size"])
    proof = resp.get("proof")
    if not isinstance(proof, list) or not all(isinstance(x, str) for x in proof):
        return False
    try:
        return verify_consistency(a["tree_size"], b["tree_size"], bytes.fromhex(a["root_hash"]),
                                  bytes.fromhex(b["root_hash"]), [bytes.fromhex(x) for x in proof])
    except ValueError:
        return False


def _pubkey(keys: dict, version: int) -> bytes | None:
    try:
        return base64.b64decode(keys[str(version)], validate=True)
    except (KeyError, ValueError, binascii.Error, TypeError):
        return None


def _read_anchors(anchor_dir: Path, keys: dict) -> tuple[list[dict], str | None]:
    """Mọi STH trong repo neo, sắp theo tree_size; lỗi thì trả (…, mô tả lỗi)."""
    out = []
    for f in sorted((anchor_dir / "sth").glob("*.json")) if (anchor_dir / "sth").is_dir() else []:
        m = _ANCHOR_NAME.match(f.name)
        try:
            th = _parse_sth(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, WitnessError) as exc:
            return out, f"{f.name}: không đọc được ({exc})"
        if not m or int(m.group(1)) != th["tree_size"]:
            return out, f"{f.name}: tên tệp không khớp tree_size {th['tree_size']}"
        pk = _pubkey(keys, th["key_version"])
        if pk is None or not signature_ok(th, pk):
            return out, f"{f.name}: chữ ký STH neo không hợp lệ"
        out.append(th)
    return sorted(out, key=lambda x: x["tree_size"]), None


def sync(server_url: str, anchor_dir: Path, state_dir: Path, *, timeout_s: float = 15.0) -> SyncResult:
    anchor_dir, state_dir = Path(anchor_dir), Path(state_dir)
    with httpx.Client(base_url=server_url.rstrip("/"), timeout=timeout_s) as client:
        th = _parse_sth(_get(client, "/verify/v1/sth/latest"))
        served = _get(client, "/verify/v1/keys").get("sth-key", {})
        if not isinstance(served, dict):
            raise WitnessError("keys: sth-key không phải object")
        size = th["tree_size"]

        # 1. chữ ký + key pinning: khóa đã ghim luôn thắng khóa máy chủ đưa
        known = _load(state_dir / KEYS_FILE) or {}
        for v, k in served.items():
            if v in known and known[v] != k:
                return SyncResult("BAD_SIGNATURE", size, f"khóa sth-key v{v} bị thay so với lần trước")
        keys = {**served, **known}
        pk = _pubkey(keys, th["key_version"])
        if pk is None:
            return SyncResult("BAD_SIGNATURE", size, f"không có khóa sth-key phiên bản {th['key_version']}")
        if not signature_ok(th, pk):
            return SyncResult("BAD_SIGNATURE", size, "chữ ký STH không hợp lệ")

        # 2. repo neo
        anchors, err = _read_anchors(anchor_dir, keys)
        if err:
            return SyncResult("ANCHOR_MISMATCH", size, err)
        for a in anchors:
            if a["tree_size"] > size:
                return SyncResult("REWRITE_DETECTED", size,
                                  f"máy chủ trả cây {size} nhỏ hơn STH đã neo {a['tree_size']}")
            if a["tree_size"] == size and a != th:
                return SyncResult("ANCHOR_MISMATCH", size,
                                  f"STH máy chủ khác {sth_path(size)} trong repo neo")

        # 3. chuỗi neo: từ mốc đã kiểm lần trước tới STH hiện tại
        state = _load(state_dir / STATE_FILE)
        verified = int((state or {}).get("anchor_verified_size", 0))
        chain = [a for a in anchors if a["tree_size"] >= verified] + [th]
        for a, b in zip(chain, chain[1:], strict=False):
            if not _consistent(client, a, b):
                return SyncResult("INCONSISTENT", size,
                                  f"chuỗi neo: {a['tree_size']} → {b['tree_size']} không nhất quán")

        # 4. so với lần kiểm trước của chính witness
        prev = None if state is None else {k: state[k] for k in _STH_FIELDS}
        if prev is not None:
            if size < prev["tree_size"]:
                return SyncResult("REWRITE_DETECTED", size, f"cây nhỏ đi: {prev['tree_size']} → {size}")
            if size == prev["tree_size"] and th["root_hash"] != prev["root_hash"]:
                return SyncResult("REWRITE_DETECTED", size, "cùng kích thước nhưng root khác")
            if not _consistent(client, prev, th):
                return SyncResult("INCONSISTENT", size,
                                  f"consistency proof {prev['tree_size']} → {size} không hợp lệ")

        # 5. lưu
        new_verified = max([a["tree_size"] for a in anchors] + [verified])
        _save(state_dir / STATE_FILE, {**th, "anchor_verified_size": new_verified})
        _save(state_dir / KEYS_FILE, keys)
        detail = f"{len(anchors)} STH neo nhất quán"
        if prev is None:
            return SyncResult("FIRST_RUN", size, f"đã lưu STH đầu tiên; {detail}")
        return SyncResult("OK", size, f"{prev['tree_size']} → {size}; {detail}")
