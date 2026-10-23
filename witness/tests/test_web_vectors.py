# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Vector dùng chung cho bộ kiểm gói bằng chứng trên trình duyệt (Plan 03 Task 4).

Mỗi vector ``sdk/js/test/vectors/<tên>.json`` = văn bản gói **đúng như sẽ đưa cho trình duyệt** + repo neo
(base64 từng tệp) + kết quả kỳ vọng của ``dxos_witness.bundle.verify_bundle`` ở chế độ ghim (``expected``) và
chưa ghim (``expected_unpinned``). ``sdk/js/test/proof.test.ts`` chạy cùng các vector đó và phải ra cùng mã.

- Khóa ký cố định (sinh từ hạt giống) và chữ ký ed25519 tất định, nên dựng lại luôn ra đúng từng byte: test so
  vector trong repo với bản vừa dựng, rồi kiểm lại vector trong repo bằng witness (phân tích JSON như CLI).
- Văn bản gói ghi bằng ``json.dumps`` của Python (số nguyên Python chính xác tuyệt đối, không qua số
  thực), giữ nguyên NFD/thứ tự khóa của gói để trình duyệt phải tự chuẩn hóa; vài vector dùng
  ``ensure_ascii=True`` để thử phần giải mã ``\\uXXXX`` (kể cả cặp surrogate).
- Sinh lại: ``DXOS_WRITE_VECTORS=1 python -m pytest witness/tests/test_web_vectors.py``.
"""

import base64
import copy
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dxos_proof.canonical import canonical_bytes
from dxos_proof.merkle import (
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    root,
    verify_consistency,
    verify_inclusion,
)
from dxos_witness.bundle import verify_bundle
from dxos_witness.cli import _no_duplicate_keys

VEC_DIR = Path(__file__).resolve().parents[2] / "sdk" / "js" / "test" / "vectors"
MERKLE_VEC = VEC_DIR / "merkle" / "rfc9162.json"
ORIGINAL = "tệp gốc của bản ghi".encode()


def _key(tag: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f"dxos-web-vectors/{tag}".encode()).digest())


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _flip_hex(h: str) -> str:
    return ("0" if h[0] != "0" else "1") + h[1:]


def _flip_b64(s: str) -> str:
    raw = bytearray(base64.b64decode(s))
    raw[0] ^= 1
    return _b64(bytes(raw))


def _raw_pub(sk: Ed25519PrivateKey) -> bytes:
    return sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


# ---------------------------------------------------------------- biến đổi
# Biến đổi ``str`` = (tham số cho builder trước khi ký, hàm sửa sau khi ký
# ``(env, gói, tệp neo) -> tùy chọn``).
# Tùy chọn: ``file_sha256`` (như ``--file``), ``ascii`` (ghi văn bản gói bằng ``ensure_ascii=True``).
def _swap_bundle_key(env, b, files):
    sk = _key("attacker")
    b["signature"] = _b64(sk.sign(canonical_bytes(b["payload"])))
    b["seal_key"]["public_key"] = _b64(_raw_pub(sk))
    b["seal_key"]["statement"]["public_key"] = _b64(_raw_pub(sk))


def _lenient_b64_hint(env, b, files):
    # 32 byte = 43 ký tự + "=", 2 bit thừa cuối: Python (validate=True) vẫn nhận khi 2 bit đó khác 0.
    s = b["seal_key"]["public_key"]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    b["seal_key"]["public_key"] = s[:42] + alphabet[alphabet.index(s[42]) | 1] + "="


def _three_pad_b64_hint(env, b, files):
    # 44 ký tự dữ liệu (nhóm đủ, 33 byte) + "===": Python (validate=True) nhận thừa dấu "=" sau nhóm đủ,
    # giải ra 33 byte nên khóa bị bỏ vì sai độ dài; JS phải ra cùng kết quả (KEY_MISMATCH/KEY_MISSING).
    s = b["seal_key"]["public_key"]
    b["seal_key"]["public_key"] = s[:43] + "A" + "==="


INT_4301 = "@@INT-4301-DIGITS@@"


def _int_4301_digits(env, b, files):
    # Python: json.loads từ chối số nguyên dài hơn 4300 chữ số (giới hạn đổi sang chuỗi), CLI báo MALFORMED,
    # kể cả ở trường không được ký. json.dumps chịu cùng giới hạn nên ghi chỗ giữ chỗ rồi thay vào văn bản.
    b["ghi_chu"] = INT_4301
    return {"text_replace": {json.dumps(INT_4301): "1" * 4301}}


def _re_anchor(b, files, size):
    files[f"sth/{size:012d}.json"] = canonical_bytes(b["anchored"]["sth"])


def _anchored_signature(env, b, files):
    b["anchored"]["sth"]["signature"] = _flip_b64(b["anchored"]["sth"]["signature"])
    _re_anchor(b, files, b["anchored"]["sth"]["tree_size"])


def _ots_receipt(env, b, files):
    # Plan 03 Task 14: biên nhận OpenTimestamps (pending) cho anchored.sth; hai bên chỉ ghi chú, không đổi mã.
    th = b["anchored"]["sth"]
    magic = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
    pending = b"\x00" + bytes.fromhex("83dfe30d2ef90c8e") + b"\x12\x11https://a.example"
    digest = hashlib.sha256(canonical_bytes(th)).digest()
    ots = magic + b"\x01\x08" + digest + b"\xf1\x04\x65\x00\x00\x01" + pending
    b["timestamps"] = [{"type": "opentimestamps", "tree_size": th["tree_size"], "ots": _b64(ots)}]


def _validity_us(env):
    # 16:00:00.0002+07:00 = 09:00:00.000200Z > 09:00:00.000100Z: chỉ thấy khi so tới micro giây.
    return {"issued_at": "2026-10-21T16:00:00.0002+07:00",
            "statement": env.statement(valid_until="2026-10-21T09:00:00.0001Z")}


def _nothing(env):
    return {}


NFD_ASTRAL = {"ho_ten": unicodedata.normalize("NFD", "Nguyễn 𝔸")}
MUTATIONS = {
    "flip_public_field": (_nothing, lambda e, b, f: b["payload"]["public_fields"].update(
        title="Quyết định đã sửa")),
    "flip_signature": (_nothing, lambda e, b, f: b.update(signature=_flip_b64(b["signature"]))),
    "flip_proof": (_nothing, lambda e, b, f: b["inclusion"]["proof"].__setitem__(
        0, _flip_hex(b["inclusion"]["proof"][0]))),
    "flip_root": (_nothing, lambda e, b, f: b["sth"].update(root_hash=_flip_hex(b["sth"]["root_hash"]))),
    "status_valid_but_bad_sig": (_nothing, lambda e, b, f: b.update(
        status="VALID", signature=_flip_b64(b["signature"]))),
    "issued_after_valid_until": (
        lambda e: {"issued_at": "2026-10-21T09:00:00Z",
                   "statement": e.statement(valid_until="2026-10-21T08:30:00Z")},
        None),
    "anchor_dir_other_sth": (_nothing, lambda e, b, f: f.update(
        {"sth/000000000008.json": f["sth/000000000003.json"]})),
    # ---- bổ sung (Review Focus 2 và đủ các mã của witness)
    "ascii_text": (lambda e: {"public_fields": NFD_ASTRAL}, lambda e, b, f: {"ascii": True}),
    "lone_surrogate": (_nothing, lambda e, b, f: (b["payload"]["public_fields"].update(title="x\ud800y"),
                                                   {"ascii": True})[1]),
    "nfc_key_collision": (_nothing, lambda e, b, f: b["payload"]["public_fields"].update(
        {"é": 1, "é": 2})),
    "float_in_payload": (_nothing, lambda e, b, f: b["payload"]["public_fields"].update(diem=1.5)),
    "float_integral_key_version": (_nothing, lambda e, b, f: b["payload"].update(key_version=1.0)),
    "float_in_unsigned": (_nothing, lambda e, b, f: b.update(
        generated_at=1.5, ghi_chu=[float("inf"), float("-inf"), float("nan"), -0.0, 1e300, 2.5e-3])),
    "status_revoked": (_nothing, lambda e, b, f: b.update(status="REVOKED")),
    "format_wrong": (_nothing, lambda e, b, f: b.update(format="dxos-seal-bundle/2")),
    "key_version": (_nothing, lambda e, b, f: b["seal_key"].update(version=2)),
    "swap_bundle_key": (_nothing, _swap_bundle_key),
    "lenient_b64_hint": (_nothing, _lenient_b64_hint),
    "three_pad_b64_hint": (_nothing, _three_pad_b64_hint),
    "int_4301_digits": (_nothing, _int_4301_digits),
    "bad_b64_hint": (_nothing, lambda e, b, f: b["seal_key"].update(public_key="!!not-base64!!")),
    "bundle_keys_absent": (_nothing, lambda e, b, f: (b["seal_key"].update(public_key=None),
                                                       b.pop("sth_keys"))),
    "seal_key_not_anchored": (_nothing, lambda e, b, f: f.pop("keys/seal-key/v1.pub")),
    "sth_key_not_anchored": (_nothing, lambda e, b, f: f.pop("keys/sth-key/v1.pub")),
    "anchored_key_no_newline": (_nothing, lambda e, b, f: f.update(
        {"keys/seal-key/v1.pub": f["keys/seal-key/v1.pub"][:-1]})),
    "statement_not_anchored": (_nothing, lambda e, b, f: f.pop("keys/seal-key/v1.json")),
    "statement_differs": (_nothing, lambda e, b, f: b["seal_key"]["statement"].update(
        purpose="Mục đích khác")),
    "statement_only_anchored": (_nothing, lambda e, b, f: b["seal_key"].pop("statement")),
    "validity_microseconds": (_validity_us, None),
    "issued_at_bad_format": (lambda e: {"issued_at": "2026-10-21 09:00:00Z"}, None),
    "validity_overflow": (lambda e: {"statement": e.statement(valid_from="0001-01-01T00:00:00+01:00")}, None),
    "entry_idx": (_nothing, lambda e, b, f: b["ledger"]["entry"].update(idx=6)),
    "no_sth": (_nothing, lambda e, b, f: b.update(sth=None)),
    "sth_extra_field": (_nothing, lambda e, b, f: b["sth"].update(extra=1)),
    "flip_sth_signature": (_nothing, lambda e, b, f: b["sth"].update(
        signature=_flip_b64(b["sth"]["signature"]))),
    "anchored_signature": (_nothing, _anchored_signature),
    "flip_consistency": (_nothing, lambda e, b, f: b["anchored"]["consistency"].__setitem__(
        0, _flip_hex(b["anchored"]["consistency"][0]))),
    "file_in_seal": (_nothing, lambda e, b, f: {"file_sha256": hashlib.sha256(ORIGINAL).hexdigest().upper()}),
    "file_not_in_seal": (_nothing, lambda e, b, f: {"file_sha256": hashlib.sha256(b"khac").hexdigest()}),
    "ots_receipt": (_nothing, _ots_receipt),
}

CASES = [  # (tên, layout, biến đổi, kỳ vọng mã)
    ("ok-anchored", "anchored_is_sth", None, None),
    ("ok-newer-sth", "newer_sth", None, None),
    ("bigint-public-field", "anchored_is_sth", {"public_fields": {"diem": 2**60}}, None),
    ("nfd-and-astral", "anchored_is_sth", {"public_fields": NFD_ASTRAL}, None),
    ("tampered-payload", "anchored_is_sth", "flip_public_field", "SIGNATURE"),
    ("tampered-signature", "anchored_is_sth", "flip_signature", "SIGNATURE"),
    ("tampered-proof", "newer_sth", "flip_proof", "INCLUSION"),
    ("tampered-sth-root", "anchored_is_sth", "flip_root", "INCLUSION"),
    ("status-lies", "anchored_is_sth", "status_valid_but_bad_sig", "SIGNATURE"),
    ("issued-outside-validity", "anchored_is_sth", "issued_after_valid_until", "KEY_NOT_VALID_AT_ISSUE"),
    ("anchor-sth-mismatch", "anchored_is_sth", "anchor_dir_other_sth", "NOT_ANCHORED"),
]
EXTRA_CASES = [
    ("control-chars-nfd-key-bigint-edges", "anchored_is_sth", {"public_fields": {
        unicodedata.normalize("NFD", "Họ và tên"): "a\x00\x01\x1f\x7f  \"\\/\b\f\n\r\t﻿",
        "am_lon": -(2**63), "bien_tren": 2**53, "an_toan": -(2**53 - 1), "lon": 2**64 + 1,
        "long": [9007199254740993, {"z": 1, "\U0001d538": 2, "￿": 3, "": 4, "": 0}]}}, None),
    ("ascii-escaped-astral", "anchored_is_sth", "ascii_text", None),
    ("lone-surrogate-escape", "anchored_is_sth", "lone_surrogate", "MALFORMED"),
    ("nfc-key-collision", "anchored_is_sth", "nfc_key_collision", "MALFORMED"),
    ("float-in-payload", "anchored_is_sth", "float_in_payload", "MALFORMED"),
    ("float-integral-key-version", "anchored_is_sth", "float_integral_key_version", "MALFORMED"),
    ("float-in-unsigned-field", "anchored_is_sth", "float_in_unsigned", None),
    ("status-revoked-ignored", "anchored_is_sth", "status_revoked", None),
    ("format-wrong", "anchored_is_sth", "format_wrong", "FORMAT"),
    ("key-version", "anchored_is_sth", "key_version", "KEY_VERSION"),
    ("key-mismatch", "anchored_is_sth", "swap_bundle_key", "KEY_MISMATCH"),
    ("lenient-b64-key-hint", "anchored_is_sth", "lenient_b64_hint", None),
    ("bad-b64-key-hint", "anchored_is_sth", "bad_b64_hint", "KEY_MISMATCH"),
    ("b64-three-pad", "anchored_is_sth", "three_pad_b64_hint", "KEY_MISMATCH"),
    ("int-4301-digits", "anchored_is_sth", "int_4301_digits", "MALFORMED"),
    ("bundle-keys-absent", "newer_sth", "bundle_keys_absent", None),
    ("seal-key-not-anchored", "anchored_is_sth", "seal_key_not_anchored", "KEY_NOT_ANCHORED"),
    ("sth-key-not-anchored", "anchored_is_sth", "sth_key_not_anchored", "KEY_NOT_ANCHORED"),
    ("anchored-key-no-newline", "anchored_is_sth", "anchored_key_no_newline", "KEY_NOT_ANCHORED"),
    ("statement-not-anchored", "anchored_is_sth", "statement_not_anchored", "KEY_STATEMENT_NOT_ANCHORED"),
    ("statement-differs", "anchored_is_sth", "statement_differs", "KEY_STATEMENT"),
    ("statement-only-anchored", "anchored_is_sth", "statement_only_anchored", None),
    ("validity-microseconds", "anchored_is_sth", "validity_microseconds", "KEY_NOT_VALID_AT_ISSUE"),
    ("issued-at-bad-format", "anchored_is_sth", "issued_at_bad_format", "KEY_NOT_VALID_AT_ISSUE"),
    ("validity-overflow", "anchored_is_sth", "validity_overflow", "MALFORMED"),
    ("leaf-link", "anchored_is_sth", "entry_idx", "LEAF_LINK"),
    ("no-sth", "anchored_is_sth", "no_sth", "NO_STH"),
    ("sth-extra-field", "anchored_is_sth", "sth_extra_field", "MALFORMED"),
    ("sth-signature", "newer_sth", "flip_sth_signature", "STH_SIGNATURE"),
    ("anchored-signature", "newer_sth", "anchored_signature", "ANCHORED_SIGNATURE"),
    ("consistency", "newer_sth", "flip_consistency", "CONSISTENCY"),
    ("leaf-after-last-anchor", "anchor_before_leaf", None, "NOT_ANCHORED"),
    ("file-in-seal", "anchored_is_sth", "file_in_seal", None),
    ("file-not-in-seal", "anchored_is_sth", "file_not_in_seal", "FILE_NOT_IN_SEAL"),
    ("ots-timestamps", "newer_sth", "ots_receipt", None),
]
# Kỳ vọng khi KHÔNG có repo neo (khóa lấy từ gói); vắng mặt = như ``expected``.
UNPINNED = {
    "anchor-sth-mismatch": None, "key-mismatch": None, "seal-key-not-anchored": None,
    "sth-key-not-anchored": None, "anchored-key-no-newline": None, "statement-not-anchored": None,
    "statement-differs": None, "leaf-after-last-anchor": None,
    "bad-b64-key-hint": "KEY_MISSING", "b64-three-pad": "KEY_MISSING", "bundle-keys-absent": "KEY_MISSING",
    "statement-only-anchored": "KEY_STATEMENT_MISSING",
}


def make_vector(env, layout: str, mutation) -> dict:
    """``{"bundle_text", "anchor_files": {đường dẫn: base64}, "file_sha256"?}`` (khóa cố định → tất định)."""
    env.seal_sk, env.sth_sk = _key("seal-key"), _key("sth-key")
    pre, post = (None, None) if mutation is None else (
        (lambda e: mutation, None) if isinstance(mutation, dict) else MUTATIONS[mutation])
    bundle, anchor = env.build(layout=layout, **(pre(env) if pre else {}))
    bundle = copy.deepcopy(bundle)
    files = {p.relative_to(anchor).as_posix(): p.read_bytes() for p in anchor.rglob("*") if p.is_file()}
    opts = post(env, bundle, files) if post else None
    opts = opts if isinstance(opts, dict) else {}
    text = json.dumps(bundle, ensure_ascii=bool(opts.get("ascii")), separators=(",", ":"))
    for old, new in opts.get("text_replace", {}).items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    vec = {"bundle_text": text,
           "anchor_files": {k: _b64(files[k]) for k in sorted(files)}}
    if "file_sha256" in opts:
        vec["file_sha256"] = opts["file_sha256"]
    return vec


def write_anchor(vec: dict, root: Path) -> Path:
    for rel, data in vec["anchor_files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(base64.b64decode(data))
    return root


def python_verdicts(vec: dict, root: Path) -> tuple[str | None, str | None]:
    """(mã khi ghim, mã khi chưa ghim) của witness; gói phân tích JSON đúng như CLI ``verify-bundle``."""
    out = []
    for anchor_dir in (write_anchor(vec, root), None):
        try:
            bundle = json.loads(vec["bundle_text"], object_pairs_hook=_no_duplicate_keys)
        except Exception:  # noqa: BLE001 — như CLI ``verify-bundle``: gói không đọc được → INVALID MALFORMED
            out.append("MALFORMED")
            continue
        res = verify_bundle(bundle, anchor_dir=anchor_dir, file_sha256=vec.get("file_sha256"))
        assert res.pinned == (anchor_dir is not None)
        out.append(None if res.ok else res.detail.split(":")[0])
    return out[0], out[1]


@pytest.mark.parametrize("name,layout,mutation,expected", CASES + EXTRA_CASES)
def test_vector_matches_python_verifier(name, layout, mutation, expected, bundle_env, tmp_path):
    expected_unpinned = UNPINNED.get(name, expected)
    vec = make_vector(bundle_env, layout, mutation)
    assert python_verdicts(vec, tmp_path / "fresh") == (expected, expected_unpinned)
    full = {**vec, "expected": expected, "expected_unpinned": expected_unpinned}
    out = VEC_DIR / f"{name}.json"
    if os.environ.get("DXOS_WRITE_VECTORS") == "1":
        VEC_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(full, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert out.is_file(), f"thiếu {out}; sinh bằng DXOS_WRITE_VECTORS=1"
    committed = json.loads(out.read_text(encoding="utf-8"))
    assert committed == full, f"{out.name} cũ so với builder; sinh lại bằng DXOS_WRITE_VECTORS=1"
    # Vector trong repo (đúng tệp trình duyệt đọc) tự kiểm lại bằng witness.
    assert python_verdicts(committed, tmp_path / "committed") == (expected, expected_unpinned)


def test_big_integers_are_written_exactly():
    text = (VEC_DIR / "bigint-public-field.json").read_text(encoding="utf-8")
    assert json.loads(json.loads(text)["bundle_text"])["payload"]["public_fields"]["diem"] == 2**60
    assert str(2**60) in json.loads(text)["bundle_text"]


def test_no_stray_vectors():
    names = {c[0] for c in CASES + EXTRA_CASES}
    assert {p.stem for p in VEC_DIR.glob("*.json")} == names


# -------------------------------------------- base64 (``b64decode(validate=True)``) và giới hạn số nguyên
B64_VEC = VEC_DIR / "b64" / "validate.json"
B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _b64_vectors() -> list[dict]:
    """Chuỗi → byte (hex) mà ``b64decode(s, validate=True)`` của Python 3.12 trả, hoặc ``None`` nếu từ chối.

    Gồm mọi (số ký tự dữ liệu 0…9) × (số dấu ``=`` 0…7), nhất là nhóm đủ kèm 3 dấu ``=`` trở lên: Python vẫn
    nhận (``b64-three-pad``), cùng các chuỗi lạ (khoảng trắng, ``=`` giữa chuỗi, URL-safe, chữ số Unicode)."""
    inputs = []
    for d in range(10):
        data = "".join(B64_ALPHABET[(7 * i + 3 * d + 1) % 64] for i in range(d))   # bit thừa cuối khác 0
        inputs += [data + "=" * p for p in range(8)]
    inputs += [f"AAAA{'=' * p}" for p in range(8)] + ["AAA===", "AA====", "A==="]
    inputs += ["", "=", "====", "AAAA\n", " AAAA", "AA AA", "AAAA ==", "AAAA==\n", "AA-_", "AA==AA==",
               "AAAA=AAA", "AAAA===\n", "AAA=\u0663", "é", "AAAA\u00a0", "QUJD", "QUJD===", "QUI=", "QUI====",
               "QQ==", "QQ=====", "AAAA" * 11 + "=" * 3, "A" * 43 + "=", "A" * 43 + "===", "A" * 44 + "==="]
    out = []
    for s in dict.fromkeys(inputs):
        try:
            out.append({"input": s, "hex": base64.b64decode(s, validate=True).hex()})
        except (ValueError, TypeError):   # binascii.Error là ValueError; chuỗi non-ASCII → ValueError
            out.append({"input": s, "hex": None})
    return out


def test_b64_vectors():
    vec = _b64_vectors()
    by = {c["input"]: c["hex"] for c in vec}
    assert by["AAAA==="] == "000000" and by["AAAA======="] == "000000"       # thừa "=" sau nhóm đủ: nhận
    assert by["AAA==="] is None and by["AA===="] is None and by["A==="] is None
    assert sum(c["hex"] is not None for c in vec) > 20 and sum(c["hex"] is None for c in vec) > 20
    if os.environ.get("DXOS_WRITE_VECTORS") == "1":
        B64_VEC.parent.mkdir(parents=True, exist_ok=True)
        B64_VEC.write_text(json.dumps(vec, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    assert json.loads(B64_VEC.read_text(encoding="utf-8")) == vec, "sinh lại bằng DXOS_WRITE_VECTORS=1"


def test_python_integer_limit_is_4300_digits_without_the_sign():
    """JS (parseJson) phải khớp: 4300 chữ số nhận (kể cả dấu trừ), 4301 từ chối (mặc định Python 3.11+)."""
    assert sys.get_int_max_str_digits() == 4300, "đặt lại PYTHONINTMAXSTRDIGITS về mặc định để chạy vector"
    for ok in ("1" * 4300, "-" + "1" * 4300):
        assert len(json.loads(ok).__str__().lstrip("-")) == 4300
    for bad in ("1" * 4301, "-" + "1" * 4301):
        with pytest.raises(ValueError, match="4300 digits"):
            json.loads(bad)
    # Số thực không chịu giới hạn này (float() không đổi qua int).
    assert json.loads("1" * 4301 + ".5") == float("inf") or json.loads("1" * 4301 + ".5") > 1e300


# ---------------------------------------------------------------- Merkle (RFC 9162) cho cây 1…9 lá
def _merkle_vectors() -> dict:
    """Mọi inclusion/consistency của cây 1…9 lá, kèm biến thể hỏng; ``ok`` là kết quả của dxos-proof."""
    inc, con = [], []
    for n in range(1, 10):
        entries = [canonical_bytes({"i": i}) for i in range(n)]
        r = root(entries)
        for i in range(n):
            leaf, proof = leaf_hash(entries[i]), inclusion_proof(i, entries)
            variants = [(i, n, proof), (i + 1, n, proof), (i, n + 1, proof), (i, n, proof[:-1])]
            if proof:
                variants.append((i, n, [bytes([proof[0][0] ^ 1]) + proof[0][1:], *proof[1:]]))
            for idx, size, pr in variants:
                inc.append({"leaf": leaf.hex(), "index": idx, "size": size, "proof": [p.hex() for p in pr],
                            "root": r.hex(), "ok": verify_inclusion(leaf, idx, size, pr, r)})
        for m in range(1, n + 1):
            rm, proof = root(entries[:m]), consistency_proof(m, entries)
            variants = [(m, n, rm, proof), (m, n, r, proof), (m, n, rm, proof[:-1]), (m + 1, n, rm, proof)]
            if proof:
                variants.append((m, n, rm, [bytes([proof[0][0] ^ 1]) + proof[0][1:], *proof[1:]]))
            for mm, nn, root_m, pr in variants:
                con.append({"m": mm, "n": nn, "root_m": root_m.hex(), "root_n": r.hex(),
                            "proof": [p.hex() for p in pr], "ok": verify_consistency(mm, nn, root_m, r, pr)})
    return {"inclusion": inc, "consistency": con}


def test_merkle_vectors():
    vec = _merkle_vectors()
    for kind, base in (("inclusion", 45), ("consistency", 45)):     # 45 bằng chứng gốc đúng + biến thể hỏng
        assert sum(c["ok"] for c in vec[kind]) >= base and not all(c["ok"] for c in vec[kind])
    if os.environ.get("DXOS_WRITE_VECTORS") == "1":
        MERKLE_VEC.parent.mkdir(parents=True, exist_ok=True)
        MERKLE_VEC.write_text(json.dumps(vec, indent=None, separators=(",", ":")) + "\n", encoding="utf-8")
    assert json.loads(MERKLE_VEC.read_text(encoding="utf-8")) == vec, "sinh lại bằng DXOS_WRITE_VECTORS=1"
