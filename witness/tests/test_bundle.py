# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test ``dxos-witness verify-bundle`` (Plan 02 Task 9; spec 11.5, 25.3; AT-17, AT-28).

Gói và repo neo do ``bundle_env`` (conftest) dựng bằng thuật toán riêng của test, không import ``dxos_core``.
Mỗi kịch bản sửa phải hỏng đúng ở bước dự định: test so mã ``detail``, không chỉ ``INVALID``.
"""

import base64
import copy
import hashlib
import json
import unicodedata

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dxos_proof.canonical import canonical_bytes
from dxos_witness.bundle import BundleResult, verify_bundle
from dxos_witness.cli import main

SEAL_ID = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"                      # = BundleEnv.seal_id
ORIGINAL = "tệp gốc của bản ghi".encode()                    # = BundleEnv.original
REVOCATION_NOTE = f"trạng thái thu hồi cần tra trực tuyến: GET /verify/v1/seals/{SEAL_ID}"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _code(r: BundleResult) -> str:
    return r.detail.split(":", 1)[0]


# ---------- Các test do Plan 02 Task 9 quy định ----------

def test_valid_bundle_offline_with_pinned_keys(bundle_env):                               # AT-17
    assert (bundle_env.seal_id, bundle_env.original) == (SEAL_ID, ORIGINAL)
    r = verify_bundle(bundle_env.bundle, anchor_dir=bundle_env.anchor_dir)
    assert r.ok and r.status == "VALID" and r.pinned and r.revocation == "unknown_offline"
    assert REVOCATION_NOTE in r.detail
    assert r.issuer == "Trường Đại học Thử (TDHT-01)"


EXPECTED = {
    "payload_field": "SIGNATURE",
    "signature": "SIGNATURE",
    "entry_ts": "INCLUSION",
    "entry_idx": "LEAF_LINK",
    "proof_node": "INCLUSION",
    "sth_root": "INCLUSION",
    "anchored_sth": "NOT_ANCHORED",
    "consistency_node": "CONSISTENCY",
    "swap_bundle_key": "KEY_MISMATCH",
    "key_version": "KEY_VERSION",
    "anchored_null": "NOT_ANCHORED",
    "anchor_file_missing": "NOT_ANCHORED",
    "leaf_after_last_anchor": "NOT_ANCHORED",                      # ruling C8
}


@pytest.mark.parametrize("tamper", ["payload_field", "signature", "entry_ts", "entry_idx", "proof_node",
                                    "sth_root", "anchored_sth", "consistency_node", "swap_bundle_key",
                                    "key_version", "anchored_null", "anchor_file_missing",
                                    "leaf_after_last_anchor"])
def test_any_tamper_is_invalid(bundle_env, tamper):
    b, anchor = bundle_env.tampered(tamper)
    r = verify_bundle(b, anchor_dir=anchor)
    assert r.status == "INVALID" and not r.ok
    assert _code(r) == EXPECTED[tamper], r.detail
    assert r.issuer is None and r.revocation == "unknown_offline"


def test_status_field_is_ignored(bundle_env):
    b = dict(bundle_env.bundle, status="REVOKED")
    assert verify_bundle(b, anchor_dir=bundle_env.anchor_dir).status == "VALID"


def test_file_hash_must_be_in_attachments(bundle_env):
    r = verify_bundle(bundle_env.bundle, anchor_dir=bundle_env.anchor_dir, file_sha256="0" * 64)
    assert r.status == "INVALID" and _code(r) == "FILE_NOT_IN_SEAL"
    ok = verify_bundle(bundle_env.bundle, anchor_dir=bundle_env.anchor_dir,
                       file_sha256=hashlib.sha256(ORIGINAL).hexdigest())
    assert ok.status == "VALID"


def test_cli_exit_codes(bundle_env, tmp_path, capsys):
    f = tmp_path / "b.json"
    f.write_text(json.dumps(bundle_env.bundle))
    assert main(["verify-bundle", str(f), "--anchor-dir", str(bundle_env.anchor_dir)]) == 0
    assert main(["verify-bundle", str(f)]) == 3


# ---------- Bổ sung 21/10 (P2-D25, spec 25.3) do plan quy định ----------

STATEMENT_EXPECTED = {"statement_validity": "KEY_NOT_VALID_AT_ISSUE", "statement_key": "KEY_STATEMENT",
                      "statement_mismatch": "KEY_STATEMENT",
                      "statement_missing": "KEY_STATEMENT_NOT_ANCHORED"}


@pytest.mark.parametrize("tamper", ["statement_validity", "statement_key", "statement_mismatch",
                                    "statement_missing"])
def test_key_statement_tamper_is_invalid(bundle_env, tamper):                              # AT-28
    b, anchor = bundle_env.tampered(tamper)
    r = verify_bundle(b, anchor_dir=anchor)
    assert r.status == "INVALID" and _code(r) == STATEMENT_EXPECTED[tamper], r.detail


def test_seal_issued_outside_key_validity_is_invalid(bundle_env):
    b, anchor = bundle_env.with_issued_at_after_valid_until()
    assert verify_bundle(b, anchor_dir=anchor).detail.startswith("KEY_NOT_VALID_AT_ISSUE")


def test_unknown_top_level_keys_are_ignored(bundle_env):
    b = dict(bundle_env.bundle, timestamps=[{"type": "opentimestamps", "ots": "AAAA"}])
    assert verify_bundle(b, anchor_dir=bundle_env.anchor_dir).status == "VALID"


# ---------- Bổ sung của Task 9: khóa trong gói chỉ là gợi ý (ruling) ----------

def test_without_anchor_dir_is_valid_but_unpinned(bundle_env):
    r = verify_bundle(bundle_env.bundle, anchor_dir=None)
    assert r.status == "VALID" and r.ok and not r.pinned and "chưa ghim" in r.detail
    assert REVOCATION_NOTE in r.detail and r.issuer == "Trường Đại học Thử (TDHT-01)"


def test_tamper_cases_also_fail_without_anchor_dir(bundle_env):
    """Các bước không phụ thuộc repo neo vẫn bắt được khi kiểm chỉ bằng khóa trong gói."""
    for name, code in [("payload_field", "SIGNATURE"), ("entry_idx", "LEAF_LINK"),
                       ("proof_node", "INCLUSION"),
                       ("consistency_node", "CONSISTENCY"), ("key_version", "KEY_VERSION"),
                       ("statement_validity", "KEY_NOT_VALID_AT_ISSUE"), ("statement_key", "KEY_STATEMENT")]:
        b, _ = bundle_env.tampered(name)
        r = verify_bundle(b, anchor_dir=None)
        assert (r.status, _code(r)) == ("INVALID", code), (name, r.detail)


def test_anchored_sth_tamper_without_anchor_dir_fails_on_signature(bundle_env):
    b, _ = bundle_env.tampered("anchored_sth")
    assert _code(verify_bundle(b, anchor_dir=None)) == "ANCHORED_SIGNATURE"


def test_newer_sth_than_anchor_is_valid(bundle_env):
    b, anchor = bundle_env.build(layout="newer_sth")
    assert b["anchored"]["consistency"] and b["anchored"]["sth"] != b["sth"]
    assert verify_bundle(b, anchor_dir=anchor).status == "VALID"


def test_leaf_after_last_anchor_without_anchor_dir_is_unpinned_not_anchored(bundle_env, tmp_path):  # C8
    b, _ = bundle_env.tampered("leaf_after_last_anchor")
    r = verify_bundle(b, anchor_dir=None)
    assert r.status == "VALID" and not r.pinned and "chưa neo" in r.detail
    b2 = dict(bundle_env.bundle, anchored=None)
    r2 = verify_bundle(b2, anchor_dir=None)
    assert r2.status == "VALID" and not r2.pinned and "chưa neo" in r2.detail
    f = tmp_path / "b.json"
    f.write_text(json.dumps(b))
    assert main(["verify-bundle", str(f)]) == 3                                      # không bao giờ là 0


def test_anchored_keys_win_over_bundle_keys(bundle_env):
    """Có repo neo: khóa chỉ lấy từ repo neo; khóa trong gói khác → KEY_MISMATCH; bỏ khóa mà ký lại → sai
    chữ ký."""
    attacker = Ed25519PrivateKey.generate()
    # 1. STH ký lại bằng khóa của kẻ tấn công, khóa đó đưa vào sth_keys
    b, a = bundle_env.copy()
    forged = {k: b["sth"][k] for k in ("tree_size", "root_hash", "ts", "key_version")}
    forged["signature"] = _b64(attacker.sign(canonical_bytes(forged)))
    b["sth"] = forged
    b["anchored"]["sth"] = copy.deepcopy(forged)
    b["sth_keys"] = {"1": bundle_env.pub_b64(attacker)}
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_MISMATCH"
    # 2. như trên nhưng bỏ gợi ý khóa: khóa neo không kiểm được chữ ký giả
    b["sth_keys"] = {}
    assert _code(verify_bundle(b, anchor_dir=a)) == "STH_SIGNATURE"
    # 3. payload ký lại bằng khóa khác, gói không kèm khóa
    b, a = bundle_env.copy()
    b["signature"] = _b64(attacker.sign(canonical_bytes(b["payload"])))
    b["seal_key"]["public_key"] = None
    assert _code(verify_bundle(b, anchor_dir=a)) == "SIGNATURE"
    # 4. không có repo neo: gói khóa giả tự nhất quán vẫn chỉ là "chưa ghim", không bao giờ ghim
    b, _ = bundle_env.tampered("swap_bundle_key")
    r = verify_bundle(b, anchor_dir=None)
    assert r.status == "VALID" and not r.pinned


@pytest.mark.parametrize("rel", ["keys/seal-key/v1.pub", "keys/sth-key/v1.pub"])
def test_missing_anchored_public_key(bundle_env, rel):
    b, a = bundle_env.copy()
    (a / rel).unlink()
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_NOT_ANCHORED"


def test_anchored_public_key_file_is_compared_exactly(bundle_env):
    b, a = bundle_env.copy()
    f = a / "keys/seal-key/v1.pub"
    f.write_bytes(f.read_bytes().rstrip(b"\n"))                      # thiếu "\n": không đúng định dạng neo
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_NOT_ANCHORED"


def test_anchored_sth_file_compared_byte_for_byte(bundle_env):
    b, a = bundle_env.copy()
    f = a / "sth/000000000008.json"
    f.write_bytes(json.dumps(json.loads(f.read_bytes()), indent=1).encode())     # cùng nội dung, khác byte
    assert _code(verify_bundle(b, anchor_dir=a)) == "NOT_ANCHORED"


def test_statement_absent_from_bundle(bundle_env):
    """Lõi bỏ ``seal_key.statement`` khi không có tuyên bố đã kiểm (Task 8 fix vòng 1)."""
    b, a = bundle_env.copy()
    del b["seal_key"]["statement"]
    r = verify_bundle(b, anchor_dir=a)                                 # dùng tuyên bố đã neo
    assert r.status == "VALID" and r.issuer == "Trường Đại học Thử (TDHT-01)"
    (a / "keys/seal-key/v1.json").unlink()
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_STATEMENT_NOT_ANCHORED"
    assert _code(verify_bundle(b, anchor_dir=None)) == "KEY_STATEMENT_MISSING"


def test_anchored_statement_must_be_canonical(bundle_env):
    b, a = bundle_env.copy()
    del b["seal_key"]["statement"]
    f = a / "keys/seal-key/v1.json"
    f.write_bytes(json.dumps(json.loads(f.read_bytes()), indent=1).encode() + b"\n")
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_STATEMENT"


def test_issuer_without_id(bundle_env):
    st = bundle_env.statement()
    st["issuer"] = {"name": "Trường Đại học Thử", "id": None}
    b, a = bundle_env.build(statement=st)
    assert verify_bundle(b, anchor_dir=a).issuer == "Trường Đại học Thử"


def test_bundle_without_keys_and_without_anchor_dir(bundle_env):
    b, _ = bundle_env.copy()
    b["seal_key"]["public_key"] = None
    assert _code(verify_bundle(b, anchor_dir=None)) == "KEY_MISSING"
    b, _ = bundle_env.copy()
    b["sth_keys"] = {}
    assert _code(verify_bundle(b, anchor_dir=None)) == "KEY_MISSING"


def test_validity_compared_as_datetimes_not_strings(bundle_env):
    # 10:00+07:00 = 03:00Z: so chuỗi sẽ cho "09:00Z ≤ 10:00+07:00" là đúng
    st = bundle_env.statement(valid_until="2026-10-21T10:00:00+07:00")
    b, a = bundle_env.build(statement=st)
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_NOT_VALID_AT_ISSUE"
    st = bundle_env.statement(valid_from="2026-10-21T16:00:00+07:00")          # = 09:00Z: biên, hợp lệ
    b, a = bundle_env.build(statement=st)
    assert verify_bundle(b, anchor_dir=a).status == "VALID"
    for bad in ("2026-10-21T08:00:00", "2026-10-21", "không phải thời gian"):    # thiếu múi giờ / sai dạng
        b, a = bundle_env.build(statement=bundle_env.statement(valid_from=bad))
        assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_NOT_VALID_AT_ISSUE", bad


def test_wrong_format(bundle_env):
    b = dict(bundle_env.bundle, format="dxos-seal-bundle/2")
    assert _code(verify_bundle(b, anchor_dir=bundle_env.anchor_dir)) == "FORMAT"


def test_anchored_newer_than_sth_is_invalid(bundle_env):
    """STH đã neo lớn hơn STH dùng để chứng minh: không có consistency proof hợp lệ theo chiều ngược."""
    b, a = bundle_env.build(layout="newer_sth")
    b["sth"], b["anchored"]["sth"] = b["anchored"]["sth"], b["sth"]
    assert verify_bundle(b, anchor_dir=None).status == "INVALID"


# ---------- Fail-closed: không ngoại lệ nào lọt ra ngoài ----------

def _paths(obj, prefix=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield prefix + (k,)
            yield from _paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield prefix + (i,)
            yield from _paths(v, prefix + (i,))


_DELETED = object()
# Đường dẫn mà sửa/xóa vẫn có thể VALID: không được dùng, hoặc chỉ là gợi ý khóa.
_UNUSED = {("status",), ("generated_at",), ("anchored", "repo"), ("anchored", "commit_sha")}
_OPTIONAL = {("seal_key", "public_key"), ("seal_key", "statement"), ("sth_keys",), ("sth_keys", "1")}


def test_malformed_bundles_never_raise(bundle_env):
    base = bundle_env.bundle
    for path in list(_paths(base)):
        for value in (_DELETED, None, "x", 0, -1, True, [], {}, 1.5):
            b = copy.deepcopy(base)
            parent = b
            for k in path[:-1]:
                parent = parent[k]
            if value is _DELETED:
                if isinstance(parent, list):
                    parent.pop(path[-1])
                else:
                    del parent[path[-1]]
            else:
                parent[path[-1]] = value
            if json.dumps(b, sort_keys=True) == json.dumps(base, sort_keys=True):
                continue                                               # không đổi gì (vd. [] thay [])
            r = verify_bundle(b, anchor_dir=bundle_env.anchor_dir)
            assert isinstance(r, BundleResult) and r.status in ("VALID", "INVALID")
            assert r.ok == (r.status == "VALID")
            hint_absent = path in _OPTIONAL and (value in (_DELETED, None)
                                                 or (path == ("sth_keys",) and value == {}))
            if path[:2] in _UNUSED or hint_absent:
                continue                                               # gợi ý khóa vắng mặt: dùng repo neo
            assert r.status == "INVALID", (path, value)


@pytest.mark.parametrize("bundle", [None, [], "x", 1, {"format": "dxos-seal-bundle/1"}])
def test_non_bundle_input(bundle, bundle_env):
    r = verify_bundle(bundle, anchor_dir=bundle_env.anchor_dir)
    assert r.status == "INVALID" and not r.ok and r.detail


def test_anchor_dir_without_files(bundle_env, tmp_path):
    empty = tmp_path / "trong"
    empty.mkdir()
    assert _code(verify_bundle(bundle_env.bundle, anchor_dir=empty)) == "KEY_NOT_ANCHORED"


# ---------- CLI ----------

def test_cli_prints_result_issuer_and_hashes_file_locally(bundle_env, tmp_path, capsys):
    f = tmp_path / "b.json"
    f.write_text(json.dumps(bundle_env.bundle), encoding="utf-8")
    doc = tmp_path / "goc.bin"
    doc.write_bytes(ORIGINAL)
    args = ["verify-bundle", str(f), "--anchor-dir", str(bundle_env.anchor_dir)]
    assert main([*args, "--file", str(doc)]) == 0
    out = capsys.readouterr().out
    assert "VALID" in out and "Niêm phong bởi: Trường Đại học Thử (TDHT-01)" in out
    assert REVOCATION_NOTE in out
    other = tmp_path / "khac.bin"
    other.write_bytes(b"tep khac")
    assert main([*args, "--file", str(other)]) == 2
    out = capsys.readouterr().out
    assert "INVALID" in out and "FILE_NOT_IN_SEAL" in out and "Niêm phong bởi" not in out


def test_cli_invalid_inputs_exit_2(bundle_env, tmp_path, capsys):
    b, a = bundle_env.tampered("signature")
    f = tmp_path / "b.json"
    f.write_text(json.dumps(b), encoding="utf-8")
    assert main(["verify-bundle", str(f), "--anchor-dir", str(a)]) == 2
    assert main(["verify-bundle", str(f)]) == 2
    assert main(["verify-bundle", str(tmp_path / "khong-co.json")]) == 2
    (tmp_path / "hong.json").write_text("{not json", encoding="utf-8")
    assert main(["verify-bundle", str(tmp_path / "hong.json")]) == 2
    good = tmp_path / "g.json"
    good.write_text(json.dumps(bundle_env.bundle), encoding="utf-8")
    assert main(["verify-bundle", str(good), "--file", str(tmp_path / "khong-co.bin")]) == 2
    dup = json.dumps(bundle_env.bundle)[:-1] + ', "format": "dxos-seal-bundle/1"}'       # khóa trùng
    (tmp_path / "dup.json").write_text(dup, encoding="utf-8")
    assert main(["verify-bundle", str(tmp_path / "dup.json"), "--anchor-dir",
                 str(bundle_env.anchor_dir)]) == 2
    capsys.readouterr()


def test_sign_sth_helper_matches_spec_signing_bytes(bundle_env):
    """Tự kiểm của bộ dựng test: chữ ký STH phủ đúng 4 trường (spec 11.3)."""
    th = bundle_env.bundle["sth"]
    sig = base64.b64decode(th["signature"])
    bundle_env.sth_sk.public_key().verify(
        sig, canonical_bytes({k: th[k] for k in ("tree_size", "root_hash", "ts", "key_version")}))


# ---------- Fix vòng 1 ----------

def test_cli_deeply_nested_json_is_exit_2(tmp_path, capsys):                                        # m1
    f = tmp_path / "sau.json"
    f.write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    assert main(["verify-bundle", str(f)]) == 2
    assert capsys.readouterr().out.startswith("INVALID MALFORMED")


def test_issuer_comes_from_anchored_statement(bundle_env, tmp_path, capsys):                        # m2
    b, a = bundle_env.copy()
    nfc = b["seal_key"]["statement"]["issuer"]["name"]
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    b["seal_key"]["statement"]["issuer"]["name"] = nfd          # chuẩn hóa ra cùng byte với tệp neo
    r = verify_bundle(b, anchor_dir=a)
    assert r.status == "VALID" and r.issuer == "Trường Đại học Thử (TDHT-01)" and r.issuer.startswith(nfc)
    f = tmp_path / "b.json"
    f.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert main(["verify-bundle", str(f), "--anchor-dir", str(a)]) == 0
    assert f"Niêm phong bởi: {nfc} (TDHT-01)\n" in capsys.readouterr().out


def test_keys_colliding_after_nfc_are_rejected(bundle_env):                                         # m3
    key = "tiêu đề"
    pf = {"ref": "01/TF", key: "Bản A", unicodedata.normalize("NFD", key): "Bản B"}
    assert len(set(pf)) == 3
    # canonical_bytes nay từ chối khóa trùng sau NFC (rà soát cuối, m1): dựng gói như một bên dùng bộ chuẩn
    # hóa cũ (gộp, giá trị sau thắng): chữ ký/hash trên bản đã gộp, gói mang bản có hai khóa.
    b, a = bundle_env.build(public_fields={"ref": "01/TF", key: "Bản B"})
    b["payload"]["public_fields"] = pf                          # gói tự nhất quán theo cách gộp cũ
    r = verify_bundle(b, anchor_dir=a)
    assert r.status == "INVALID" and _code(r) == "MALFORMED", r.detail
    assert "payload.public_fields" in r.detail and "NFC" in r.detail
    assert _code(verify_bundle(b, anchor_dir=None)) == "MALFORMED"


@pytest.mark.parametrize("where", ["statement", "entry", "body", "sth", "anchored_sth"])
def test_nfc_colliding_keys_rejected_everywhere(bundle_env, where):                                # m3
    b, a = bundle_env.copy()
    obj = {"statement": b["seal_key"]["statement"], "entry": b["ledger"]["entry"],
           "body": b["ledger"]["body"],
           "sth": b["sth"], "anchored_sth": b["anchored"]["sth"]}[where]
    obj["ghi chú"] = "1"
    obj[unicodedata.normalize("NFD", "ghi chú")] = "2"
    r = verify_bundle(b, anchor_dir=a)
    assert _code(r) == "MALFORMED" and "NFC" in r.detail, r.detail


def test_consistency_tamper_exact_code_with_and_without_anchor_dir(bundle_env):                     # m6
    b, a = bundle_env.tampered("consistency_node")              # neo phủ lá → bước neo qua, consistency hỏng
    assert b["anchored"]["sth"]["tree_size"] > b["inclusion"]["leaf_index"]
    assert _code(verify_bundle(b, anchor_dir=a)) == "CONSISTENCY"
    assert _code(verify_bundle(b, anchor_dir=None)) == "CONSISTENCY"


def test_valid_until_boundary(bundle_env):                                                          # m6
    b, a = bundle_env.build(issued_at="2026-10-21T09:00:00Z",
                            statement=bundle_env.statement(valid_until="2026-10-21T09:00:00Z"))
    assert verify_bundle(b, anchor_dir=a).status == "VALID"                      # issued_at == valid_until
    b, a = bundle_env.build(issued_at="2026-10-21T09:00:01Z",
                            statement=bundle_env.statement(valid_until="2026-10-21T09:00:00Z"))
    assert _code(verify_bundle(b, anchor_dir=a)) == "KEY_NOT_VALID_AT_ISSUE"     # +1 s


# ---------- Plan 03 Task 14: "timestamps" (OpenTimestamps) chỉ được ghi chú, không đổi kết quả ----------
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OTS_PENDING = b"\x00" + bytes.fromhex("83dfe30d2ef90c8e") + b"\x12\x11https://a.example"


def _ots_for(th: dict) -> str:
    return _b64(OTS_MAGIC + b"\x01\x08" + hashlib.sha256(canonical_bytes(th)).digest() + OTS_PENDING)


def _with_ots(bundle_env, **entry):
    b = copy.deepcopy(bundle_env.bundle)
    th = b["anchored"]["sth"]
    b["timestamps"] = [{"type": "opentimestamps", "tree_size": th["tree_size"], "ots": _ots_for(th), **entry}]
    return b


def test_ots_receipt_is_only_noted(bundle_env, tmp_path):
    base = verify_bundle(bundle_env.bundle, anchor_dir=bundle_env.anchor_dir)
    b = _with_ots(bundle_env)
    size = b["anchored"]["sth"]["tree_size"]
    for anchor_dir in (bundle_env.anchor_dir, None):
        r = verify_bundle(b, anchor_dir=anchor_dir)
        assert r.ok and r.pinned == (anchor_dir is not None), r.detail
        assert (f"OTS: biên nhận OpenTimestamps cho sth/{size:012d}.json đang chờ xác nhận trên Bitcoin"
                f" — kiểm bằng `ots upgrade` rồi `ots verify`") in r.detail
    r = verify_bundle(b, anchor_dir=bundle_env.anchor_dir)
    assert (r.status, r.issuer) == (base.status, base.issuer)
    assert r.detail.startswith(base.detail.split(";")[0])
    f = tmp_path / "goi.json"
    f.write_text(json.dumps(b), encoding="utf-8")
    assert main(["verify-bundle", str(f), "--anchor-dir", str(bundle_env.anchor_dir)]) == 0
    assert main(["verify-bundle", str(f)]) == 3


@pytest.mark.parametrize("entry", [
    {"ots": _b64(OTS_MAGIC + b"\x01\x08" + b"\x00" * 32 + OTS_PENDING)},        # cam kết digest khác
    {"tree_size": 999},                                                           # không phải STH đã neo
    {"ots": "!!khong-phai-base64"},
    {"ots": _b64(b"rac")},
    {"ots": None},
])
def test_ots_receipt_mismatch_is_a_note_not_invalid(bundle_env, entry):
    r = verify_bundle(_with_ots(bundle_env, **entry), anchor_dir=bundle_env.anchor_dir)
    assert r.ok and "OTS: biên nhận không cam kết anchored.sth" in r.detail, r.detail
    assert "đang chờ xác nhận" not in r.detail


@pytest.mark.parametrize("timestamps", ["x", [1], [{"type": "khac", "ots": "AA=="}], [], None, {"a": 1}])
def test_odd_timestamps_never_change_verdict(bundle_env, timestamps):
    b = copy.deepcopy(bundle_env.bundle)
    b["timestamps"] = timestamps
    r = verify_bundle(b, anchor_dir=bundle_env.anchor_dir)
    assert r.ok and "OTS: biên nhận OpenTimestamps" not in r.detail


def test_ots_does_not_rescue_or_alter_invalid(bundle_env):
    b, a = bundle_env.tampered("signature")
    b = copy.deepcopy(b)
    b["timestamps"] = [{"type": "opentimestamps", "tree_size": b["anchored"]["sth"]["tree_size"],
                        "ots": _ots_for(b["anchored"]["sth"])}]
    r = verify_bundle(b, anchor_dir=a)
    assert _code(r) == "SIGNATURE" and "OTS" not in r.detail
