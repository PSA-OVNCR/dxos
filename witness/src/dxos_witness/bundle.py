# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm **ngoại tuyến** gói bằng chứng niêm phong ``dxos-seal-bundle/1`` (spec 11.5, 25.3; Plan 02 Task 9;
AT-17, AT-28).

Các bước, theo thứ tự; bước đầu tiên sai → ``INVALID`` kèm ``detail`` bắt đầu bằng mã lỗi:

1. ``format == "dxos-seal-bundle/1"`` → ``FORMAT``.
2. Khóa và tuyên bố khóa:
   - ``seal_key.version == payload.key_version`` → ``KEY_VERSION``.
   - Có repo neo: khóa **chỉ** lấy từ ``keys/seal-key/v<n>.pub`` và ``keys/sth-key/v<n>.pub`` (thiếu →
     ``KEY_NOT_ANCHORED``). Khóa trong gói chỉ là gợi ý không tin cậy: có mà khác khóa neo → ``KEY_MISMATCH``.
     Tuyên bố: ``keys/seal-key/v<n>.json`` (thiếu → ``KEY_STATEMENT_NOT_ANCHORED``) phải trùng byte với
     ``canonical_bytes(seal_key.statement) + "\\n"``; gói không kèm tuyên bố thì dùng tệp đã neo.
   - Không có repo neo: dùng khóa trong gói (thiếu → ``KEY_MISSING``), tuyên bố trong gói (thiếu →
     ``KEY_STATEMENT_MISSING``); kết quả tốt nhất là VALID **chưa ghim**.
   - Tuyên bố sai dạng, hoặc ``statement.public_key`` khác khóa đang dùng → ``KEY_STATEMENT``.
   - ``valid_from ≤ payload.issued_at ≤ valid_until`` (so sau khi parse RFC 3339 thành UTC) →
     ``KEY_NOT_VALID_AT_ISSUE``. Tuyên bố không có chữ ký nên không kiểm chữ ký nào trên nó.
3. Chữ ký payload bằng ``seal-key`` → ``SIGNATURE``.
4. Liên kết payload ↔ lá ``record.sealed`` → ``LEAF_LINK``.
5. Inclusion của ``leaf_hash(canonical(entry))`` trong ``sth`` → ``NO_STH`` / ``INCLUSION``.
6. Chữ ký STH bằng ``sth-key`` → ``STH_SIGNATURE``.
7. Neo:
   - Có repo neo: bắt buộc ``anchored``, STH đã neo phải **phủ lá** (``tree_size > leaf_index``, ruling C8) và
     ``sth/<tree_size 12 chữ số>.json`` phải trùng byte với ``canonical(anchored.sth)`` → ``NOT_ANCHORED``.
   - Chữ ký ``anchored.sth`` → ``ANCHORED_SIGNATURE``; consistency ``anchored.sth`` → ``sth`` →
     ``CONSISTENCY``.
   - Không có repo neo: ``anchored`` vắng hoặc chưa phủ lá vẫn có thể VALID chưa ghim, ``detail`` ghi
     "chưa neo".
8. ``file_sha256`` (nếu có) ∈ ``payload.attachments`` → ``FILE_NOT_IN_SEAL``.

Trường ``status`` của gói **không** được ký nên **không** được dùng: trạng thái thu hồi luôn cần tra trực
tuyến (``revocation="unknown_offline"``). Khóa lạ ở mức gốc của gói bị bỏ qua. Riêng ``timestamps``
(biên nhận OpenTimestamps của STH đã neo, Plan 03 Task 14) chỉ được ghi chú ở kết quả VALID: không đổi
``ok``/mã thoát; người kiểm dùng ``ots upgrade`` + ``ots verify``. Mọi trường thiếu hoặc sai
kiểu → ``INVALID`` (``MALFORMED`` nếu không thuộc bước nào ở trên); không ngoại lệ nào lọt ra ngoài.

Module chỉ dùng dxos-proof và cryptography, không import dxos-core, không gọi mạng.
"""

import base64
import binascii
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dxos_proof.canonical import canonical_bytes, sha256_hex
from dxos_proof.merkle import leaf_hash, verify_consistency, verify_inclusion

BUNDLE_FORMAT = "dxos-seal-bundle/1"
STATEMENT_FORMAT = "dxos-key-statement/1"
_STH_FIELDS = ("tree_size", "root_hash", "ts", "key_version", "signature")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})")


@dataclass(frozen=True)
class BundleResult:
    ok: bool
    status: Literal["VALID", "INVALID"]
    revocation: Literal["unknown_offline"]   # gói không ký trạng thái thu hồi
    detail: str
    pinned: bool                              # True khi khóa lấy từ repo neo
    issuer: str | None = None                 # "<tên> (<mã>)" hoặc "<tên>"; chỉ có khi VALID


class AnchorFileError(ValueError):
    """Tệp trong repo neo có nhưng sai định dạng."""


class _Fail(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> NoReturn:
    raise _Fail(code, message)


# ---------------------------------------------------------------- đọc trường (sai kiểu → MALFORMED)
def _obj(v: Any, name: str) -> dict:
    if not isinstance(v, dict):
        _fail("MALFORMED", f"{name} phải là object")
    return v


def _int(v: Any, name: str) -> int:
    if type(v) is not int:            # bool là int trong Python: loại ra
        _fail("MALFORMED", f"{name} phải là số nguyên")
    return v


def _str(v: Any, name: str) -> str:
    if not isinstance(v, str):
        _fail("MALFORMED", f"{name} phải là chuỗi")
    return v


def _hex32(v: Any, name: str) -> bytes:
    if not isinstance(v, str) or not _HEX64.fullmatch(v):
        _fail("MALFORMED", f"{name} phải là 64 ký tự hex thường")
    return bytes.fromhex(v)


def _hex_list(v: Any, name: str) -> list[bytes]:
    if not isinstance(v, list):
        _fail("MALFORMED", f"{name} phải là mảng")
    return [_hex32(x, f"{name}[{i}]") for i, x in enumerate(v)]


def _sth(v: Any, name: str) -> dict:
    th = _obj(v, name)
    if set(th) != set(_STH_FIELDS):
        _fail("MALFORMED", f"{name} phải có đúng các trường {', '.join(_STH_FIELDS)}")
    _int(th["tree_size"], f"{name}.tree_size")
    _int(th["key_version"], f"{name}.key_version")
    _hex32(th["root_hash"], f"{name}.root_hash")
    _str(th["ts"], f"{name}.ts")
    _str(th["signature"], f"{name}.signature")
    if th["tree_size"] < 1:
        _fail("MALFORMED", f"{name}.tree_size phải ≥ 1")
    return th


def _no_nfc_collisions(v: Any, name: str) -> None:
    """Mọi object lồng trong ``v`` không được có hai khóa trùng nhau sau chuẩn hóa NFC: ``canonical_bytes``
    gộp chúng làm một, nên chữ ký/hash đúng mà người đọc gói có thể thấy giá trị khác → ``MALFORMED``."""
    if isinstance(v, dict):
        seen: set[str] = set()
        for k, item in v.items():
            if not isinstance(k, str):
                _fail("MALFORMED", f"{name}: khóa phải là chuỗi")
            n = unicodedata.normalize("NFC", k)
            if n in seen:
                _fail("MALFORMED", f"{name}: hai khóa trùng nhau sau chuẩn hóa NFC: {n!r}")
            seen.add(n)
            _no_nfc_collisions(item, f"{name}.{n}")
    elif isinstance(v, list):
        for i, item in enumerate(v):
            _no_nfc_collisions(item, f"{name}[{i}]")


def _b64_key(v: Any) -> bytes | None:
    """Khóa ed25519 thô từ base64 chặt; sai dạng → None."""
    if not isinstance(v, str):
        return None
    try:
        raw = base64.b64decode(v, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) == 32 else None


def _ed25519_ok(pub: bytes, signature: Any, message: bytes) -> bool:
    if not isinstance(signature, str):
        return False
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(base64.b64decode(signature, validate=True), message)
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False


def sth_signature_ok(th: dict, pub: bytes) -> bool:
    """Chữ ký STH phủ đúng 4 trường ``tree_size, root_hash, ts, key_version`` (spec 11.3)."""
    return _ed25519_ok(pub, th["signature"], canonical_bytes({k: th[k] for k in _STH_FIELDS[:4]}))


def parse_rfc3339(v: Any) -> datetime:
    """RFC 3339 có múi giờ (chấp nhận ``Z``) → datetime UTC; sai dạng hoặc thiếu múi giờ → ValueError."""
    if not isinstance(v, str) or not _RFC3339.fullmatch(v):
        raise ValueError(f"không phải thời điểm RFC 3339 có múi giờ: {v!r}")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"thiếu múi giờ: {v!r}")
    return dt.astimezone(UTC)


# ---------------------------------------------------------------- repo neo
def anchored_public_key(anchor_dir: Path, name: str, version: int) -> bytes | None:
    """Khóa đã neo ``keys/<name>/v<version>.pub`` (base64 khóa thô + ``\\n``, đúng từng byte).

    Chưa có tệp → None; có mà sai dạng → ``AnchorFileError``."""
    f = Path(anchor_dir) / "keys" / name / f"v{int(version)}.pub"
    if not f.is_file():
        return None
    data = f.read_bytes()
    raw = _b64_key(data[:-1].decode("ascii", "replace")) if data.endswith(b"\n") else None
    if raw is None or base64.b64encode(raw) + b"\n" != data:
        raise AnchorFileError(f"keys/{name}/v{int(version)}.pub sai định dạng (base64 khóa ed25519 + \\n)")
    return raw


def _pinned_key(anchor_dir: Path, name: str, version: int, hint: Any) -> bytes:
    try:
        pub = anchored_public_key(anchor_dir, name, version)
    except AnchorFileError as exc:
        _fail("KEY_NOT_ANCHORED", str(exc))
    if pub is None:
        _fail("KEY_NOT_ANCHORED", f"repo neo không có keys/{name}/v{version}.pub")
    if hint is not None and _b64_key(hint) != pub:
        _fail("KEY_MISMATCH", f"khóa {name} v{version} trong gói khác khóa đã neo")
    return pub


def _anchored_statement(anchor_dir: Path, version: int, statement: Any) -> dict:
    f = anchor_dir / "keys" / "seal-key" / f"v{version}.json"
    if not f.is_file():
        _fail("KEY_STATEMENT_NOT_ANCHORED", f"repo neo không có keys/seal-key/v{version}.json")
    data = f.read_bytes()
    if statement is not None and (not isinstance(statement, dict)
                                  or canonical_bytes(statement) + b"\n" != data):
        _fail("KEY_STATEMENT", f"tuyên bố khóa trong gói khác keys/seal-key/v{version}.json đã neo")
    # Luôn dùng bản ĐÃ NEO (không dùng bản trong gói, kể cả khi trùng byte sau chuẩn hóa): issuer hiển thị
    # đúng chuỗi trong repo neo.
    try:
        st = json.loads(data)
    except ValueError:
        _fail("KEY_STATEMENT", f"keys/seal-key/v{version}.json không phải JSON")
    if not isinstance(st, dict) or canonical_bytes(st) + b"\n" != data:
        _fail("KEY_STATEMENT", f"keys/seal-key/v{version}.json không ở dạng chuẩn hóa")
    return st


def _check_statement(st: dict, version: int, seal_pub: bytes, issued_at: Any) -> str:
    """Kiểm nội dung tuyên bố (không có chữ ký) và thời hạn; trả chuỗi ``issuer`` để hiển thị."""
    if (st.get("format") != STATEMENT_FORMAT or st.get("key") != "seal-key"
            or type(st.get("version")) is not int or st.get("version") != version
            or st.get("algorithm") != "ed25519"):
        _fail("KEY_STATEMENT", f"tuyên bố không phải {STATEMENT_FORMAT} của seal-key v{version} (ed25519)")
    if _b64_key(st.get("public_key")) != seal_pub:
        _fail("KEY_STATEMENT", "public_key của tuyên bố khác khóa seal-key đang dùng")
    issuer = st.get("issuer")
    if (not isinstance(issuer, dict) or not isinstance(issuer.get("name"), str) or not issuer["name"]
            or not (issuer.get("id") is None or isinstance(issuer.get("id"), str))):
        _fail("KEY_STATEMENT", "issuer của tuyên bố sai dạng")
    try:
        start, end = parse_rfc3339(st.get("valid_from")), parse_rfc3339(st.get("valid_until"))
        at = parse_rfc3339(issued_at)
    except ValueError as exc:
        _fail("KEY_NOT_VALID_AT_ISSUE", str(exc))
    if not start <= at <= end:
        _fail("KEY_NOT_VALID_AT_ISSUE",
              f"issued_at {issued_at} nằm ngoài {st['valid_from']} … {st['valid_until']}"
              f" của seal-key v{version}")
    return issuer["name"] if issuer.get("id") is None else f"{issuer['name']} ({issuer['id']})"


# ---------------------------------------------------------------- kiểm
def verify_bundle(bundle: dict, *, anchor_dir: Path | None, file_sha256: str | None = None) -> BundleResult:
    pinned = anchor_dir is not None
    try:
        return _verify(bundle, None if anchor_dir is None else Path(anchor_dir), file_sha256)
    except _Fail as f:
        return BundleResult(False, "INVALID", "unknown_offline", str(f), pinned)
    except Exception as exc:  # noqa: BLE001 — fail-closed: mọi lỗi bất ngờ là INVALID, không bao giờ lọt ra
        return BundleResult(False, "INVALID", "unknown_offline", f"MALFORMED: {type(exc).__name__}: {exc}",
                            pinned)


def _verify(b: Any, anchor_dir: Path | None, file_sha256: str | None) -> BundleResult:
    # 1. định dạng
    b = _obj(b, "gói")
    if b.get("format") != BUNDLE_FORMAT:
        _fail("FORMAT", f"format phải là {BUNDLE_FORMAT}")
    payload = _obj(b.get("payload"), "payload")
    sk_raw, ledger_raw, anchored_raw = (b.get(k) if isinstance(b.get(k), dict) else {}
                                        for k in ("seal_key", "ledger", "anchored"))
    for obj, name in ((payload, "payload"), (sk_raw.get("statement"), "seal_key.statement"),
                      (ledger_raw.get("entry"), "ledger.entry"), (ledger_raw.get("body"), "ledger.body"),
                      (b.get("sth"), "sth"), (anchored_raw.get("sth"), "anchored.sth")):
        _no_nfc_collisions(obj, name)
    kv = _int(payload.get("key_version"), "payload.key_version")
    seal_id = _str(payload.get("seal_id"), "payload.seal_id")

    # 2. khóa
    sk = _obj(b.get("seal_key"), "seal_key")
    if type(sk.get("version")) is not int or sk["version"] != kv:
        _fail("KEY_VERSION", f"seal_key.version {sk.get('version')!r} khác payload.key_version {kv}")
    sth = None if b.get("sth") is None else _sth(b["sth"], "sth")
    anchored = None if b.get("anchored") is None else _obj(b["anchored"], "anchored")
    anchored_sth = None if anchored is None else _sth(anchored.get("sth"), "anchored.sth")
    hints = b.get("sth_keys")
    hints = {} if hints is None else _obj(hints, "sth_keys")
    versions = sorted({th["key_version"] for th in (sth, anchored_sth) if th is not None})
    statement = sk.get("statement")
    if anchor_dir is not None:
        seal_pub = _pinned_key(anchor_dir, "seal-key", kv, sk.get("public_key"))
        sth_pubs = {v: _pinned_key(anchor_dir, "sth-key", v, hints.get(str(v))) for v in versions}
        st = _anchored_statement(anchor_dir, kv, statement)
    else:
        seal_pub = _b64_key(sk.get("public_key"))
        if seal_pub is None:
            _fail("KEY_MISSING", "gói không kèm khóa seal-key và không có --anchor-dir")
        sth_pubs = {}
        for v in versions:
            if (pk := _b64_key(hints.get(str(v)))) is None:
                _fail("KEY_MISSING", f"gói không kèm khóa sth-key v{v} và không có --anchor-dir")
            sth_pubs[v] = pk
        if statement is None:
            _fail("KEY_STATEMENT_MISSING", "gói không kèm tuyên bố khóa và không có --anchor-dir")
        if not isinstance(statement, dict):
            _fail("KEY_STATEMENT", "seal_key.statement phải là object")
        st = statement
    issuer = _check_statement(st, kv, seal_pub, payload.get("issued_at"))

    # 3. chữ ký niêm phong
    if not _ed25519_ok(seal_pub, b.get("signature"), canonical_bytes(payload)):
        _fail("SIGNATURE", "chữ ký niêm phong không hợp lệ với khóa seal-key")

    # 4. payload ↔ lá ledger
    ledger = _obj(b.get("ledger"), "ledger")
    body = _obj(ledger.get("body"), "ledger.body")
    entry = _obj(ledger.get("entry"), "ledger.entry")
    inclusion = _obj(b.get("inclusion"), "inclusion")
    leaf_index = _int(inclusion.get("leaf_index"), "inclusion.leaf_index")
    links = [
        (body.get("payload_sha256") == sha256_hex(canonical_bytes(payload)), "body.payload_sha256"),
        (body.get("seal_id") == seal_id, "body.seal_id"),
        (entry.get("body_sha256") == sha256_hex(canonical_bytes(body)), "entry.body_sha256"),
        (entry.get("type") == "record.sealed", "entry.type"),
        (entry.get("subject") == seal_id, "entry.subject"),
        (type(entry.get("idx")) is int and entry["idx"] == leaf_index, "entry.idx"),
    ]
    for ok, what in links:
        if not ok:
            _fail("LEAF_LINK", f"{what} không khớp niêm phong")

    # 5. inclusion
    if sth is None:
        _fail("NO_STH", "chưa có STH nào phủ lá của niêm phong; tải lại gói sau")
    proof = _hex_list(inclusion.get("proof"), "inclusion.proof")
    size = sth["tree_size"]
    if (type(inclusion.get("tree_size")) is not int or inclusion["tree_size"] != size
            or not verify_inclusion(leaf_hash(canonical_bytes(entry)), leaf_index, size, proof,
                                    bytes.fromhex(sth["root_hash"]))):
        _fail("INCLUSION", f"inclusion proof của lá {leaf_index} trong cây {size} không hợp lệ")

    # 6. chữ ký STH
    if not sth_signature_ok(sth, sth_pubs[sth["key_version"]]):
        _fail("STH_SIGNATURE", f"chữ ký STH cỡ {size} không hợp lệ với khóa sth-key v{sth['key_version']}")

    # 7. neo
    covered = anchored_sth is not None and anchored_sth["tree_size"] > leaf_index
    if anchor_dir is not None:
        if anchored_sth is None:
            _fail("NOT_ANCHORED", "gói không có STH đã neo")
        a_size = anchored_sth["tree_size"]
        if not covered:
            _fail("NOT_ANCHORED", f"STH đã neo (cỡ {a_size}) chưa phủ lá {leaf_index}")
        f = anchor_dir / "sth" / f"{a_size:012d}.json"
        if not f.is_file() or f.read_bytes() != canonical_bytes(anchored_sth):
            _fail("NOT_ANCHORED", f"sth/{a_size:012d}.json trong repo neo thiếu hoặc khác anchored.sth")
    if anchored_sth is not None:
        a_size = anchored_sth["tree_size"]
        if not sth_signature_ok(anchored_sth, sth_pubs[anchored_sth["key_version"]]):
            _fail("ANCHORED_SIGNATURE", f"chữ ký STH đã neo cỡ {a_size} không hợp lệ")
        consistency = _hex_list(anchored.get("consistency"), "anchored.consistency")
        if a_size == size:
            consistent = not consistency and anchored_sth["root_hash"] == sth["root_hash"]
        else:
            consistent = a_size < size and verify_consistency(
                a_size, size, bytes.fromhex(anchored_sth["root_hash"]), bytes.fromhex(sth["root_hash"]),
                consistency)
        if not consistent:
            _fail("CONSISTENCY", f"consistency proof {a_size} → {size} không hợp lệ")

    # 8. tệp
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        _fail("MALFORMED", "payload.attachments phải là mảng")
    if file_sha256 is not None and file_sha256.lower() not in attachments:
        _fail("FILE_NOT_IN_SEAL", "SHA-256 của tệp không thuộc niêm phong này")

    # 9. kết quả; status của gói không được dùng
    notes = ["OK"]
    if anchor_dir is not None:
        notes.append(f"khóa đã ghim từ repo neo; đã neo: sth/{anchored_sth['tree_size']:012d}.json")
    else:
        notes.append("chưa ghim khóa: khóa lấy từ chính gói (không có --anchor-dir)")
        notes.append("STH đã neo theo gói, chưa đối chiếu repo neo" if covered
                     else "chưa neo: chưa có STH đã neo phủ lá")
    ots_note = _ots_note(b.get("timestamps"), anchored_sth)
    if ots_note:
        notes.append(ots_note)
    notes.append(f"trạng thái thu hồi cần tra trực tuyến: GET /verify/v1/seals/{seal_id}")
    return BundleResult(True, "VALID", "unknown_offline", "; ".join(notes), anchor_dir is not None, issuer)


# ---------------------------------------------------------------- OpenTimestamps: chỉ ghi chú (P3 Task 14)
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"


def _ots_note(timestamps: Any, anchored_sth: dict | None) -> str | None:
    """Ghi chú cho các mục ``{"type": "opentimestamps"}`` của ``timestamps``; không bao giờ đổi kết quả.

    Chỉ kiểm phần đầu tệp ``.ots`` (magic, phiên bản 1, op sha256, digest = SHA-256(canonical(anchored.sth))),
    tức tệp có đúng là biên nhận cho STH đã neo hay không. Biên nhận đã vào khối Bitcoin hay chưa thì ngoại
    tuyến không kiểm được: việc đó của ``ots upgrade`` + ``ots verify`` (P3-D10)."""
    if not isinstance(timestamps, list):
        return None
    entries = [t for t in timestamps if isinstance(t, dict) and t.get("type") == "opentimestamps"]
    if not entries:
        return None
    try:
        size = anchored_sth["tree_size"]
        header = OTS_MAGIC + b"\x01\x08" + hashlib.sha256(canonical_bytes(anchored_sth)).digest()
        good = any(type(t.get("tree_size")) is int and t["tree_size"] == size
                   and len(raw := base64.b64decode(t.get("ots"), validate=True)) > len(header)
                   and raw.startswith(header) for t in entries)
    except Exception:  # noqa: BLE001 — mục OTS sai dạng chỉ được ghi chú, không bao giờ làm hỏng kết quả
        good = False
    if not good:
        return "OTS: biên nhận không cam kết anchored.sth — bỏ qua"
    return (f"OTS: biên nhận OpenTimestamps cho sth/{size:012d}.json đang chờ xác nhận trên Bitcoin"
            " — kiểm bằng `ots upgrade` rồi `ots verify`")
