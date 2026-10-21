# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Hàm thuần của niêm phong và tuyên bố khóa (Plan 02 Task 7; P2-D7, P2-D22, spec 11.5, 25.3)."""

import base64
import re
from datetime import UTC, datetime, timedelta

import pytest
from dxos_core import worker
from dxos_core.records.digest import data_digest
from dxos_core.seal.job import process_seal_job
from dxos_core.seal.keys import ORG_NAME_DEFAULT, STATEMENT_FORMAT, build_statement, within_validity
from dxos_core.seal.service import (
    SEAL_JOB,
    new_seal_id,
    record_digest,
    seal_payload,
    seal_signing_bytes,
    sealed_leaf_body,
)
from dxos_proof.canonical import canonical_bytes, sha256_hex
from pydantic import ValidationError

RID = "00000000-0000-4000-8000-000000000001"


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


# ---------- Các test do Plan 02 Task 7 quy định ----------

def test_payload_is_canonical_and_attachments_sorted():
    p = seal_payload(seal_id="A" * 26, app_id="test-flow", record_id=RID, record_digest="d" * 64,
                     attachments=["b" * 64, "a" * 64], public_fields={"title": "Nguyễn"},
                     issued_at="2026-11-05T00:00:00Z", key_version=1)
    assert p["attachments"] == ["a" * 64, "b" * 64]
    assert seal_signing_bytes(p) == canonical_bytes(p)
    assert sealed_leaf_body(p)["payload_sha256"] == sha256_hex(canonical_bytes(p))


def test_record_digest_is_salted():                                              # P2-D7
    data = {"email": "a@example.org", "ho_ten": "Nguyễn Văn A"}
    d1, d2 = record_digest(data, b64(b"\x00" * 16)), record_digest(data, b64(b"\x01" * 16))
    assert d1 != d2 and d1 != sha256_hex(canonical_bytes(data))


def test_seal_id_shape():
    assert re.fullmatch(r"[A-Z2-7]{26}", new_seal_id()) and new_seal_id() != new_seal_id()


def test_validity_capped_at_ten_years(make_settings):
    assert make_settings(seal_key_validity_days=3650).seal_key_validity_days == 3650
    with pytest.raises(ValidationError):
        make_settings(seal_key_validity_days=3651)


# ---------- Bổ sung ----------

def test_record_digest_is_the_data_digest_of_task_2():                          # một công thức duy nhất
    data, salt = {"title": "x"}, b64(b"\x07" * 16)
    assert record_digest(data, salt) == data_digest(data, salt)


def test_payload_has_exactly_the_spec_keys_and_leaf_body_has_two():           # spec 11.5, P2-D7
    p = seal_payload(seal_id="B" * 26, app_id="test-flow", record_id=RID, record_digest="d" * 64,
                     attachments=(), public_fields={}, issued_at="2026-11-05T00:00:00Z", key_version=2)
    assert set(p) == {"seal_id", "app_id", "record_id", "record_digest", "attachments", "issued_at",
                      "public_fields", "key_version"}
    assert p["attachments"] == [] and p["key_version"] == 2
    assert sealed_leaf_body(p) == {"seal_id": "B" * 26, "payload_sha256": sha256_hex(canonical_bytes(p))}


def test_build_statement_matches_spec_25_3(make_settings):
    s = make_settings(org_name="Công ty TNHH Sao Mai", org_id="0101234567", seal_key_validity_days=10,
                      key_policy_url="https://example.org/key-policy")
    st = build_statement(s, version=3, public_key=b"\x05" * 32, valid_from="2026-11-05T07:08:09Z")
    assert st == {
        "format": STATEMENT_FORMAT, "key": "seal-key", "version": 3, "serial": "seal-key/v3",
        "issuer": {"name": "Công ty TNHH Sao Mai", "id": "0101234567"}, "algorithm": "ed25519",
        "public_key": b64(b"\x05" * 32), "valid_from": "2026-11-05T07:08:09Z",
        "valid_until": "2026-11-15T07:08:09Z", "purpose": s.seal_purpose,
        "policy_url": "https://example.org/key-policy"}
    assert within_validity(st, "2026-11-15T07:08:09Z") and not within_validity(st, "2026-11-15T07:08:10Z")


def test_build_statement_defaults_to_null_id_and_policy(make_settings):
    st = build_statement(make_settings(), version=1, public_key=b"\x01" * 32,
                         valid_from="2026-11-05T00:00:00Z")
    assert st["issuer"] == {"name": "Tổ chức thử nghiệm", "id": None} and st["policy_url"] is None
    until = datetime(2026, 11, 5, tzinfo=UTC) + timedelta(days=make_settings().seal_key_validity_days)
    assert st["valid_until"] == until.strftime("%Y-%m-%dT%H:%M:%SZ") == "2036-11-02T00:00:00Z"


def test_blank_org_settings_fall_back_to_not_configured(make_settings):
    """Compose truyền ``${DXOS_ORG_NAME:-}``: chuỗi rỗng phải là "chưa cấu hình", không phải tên rỗng."""
    s = make_settings(org_name="  ", org_id="", key_policy_url="", seal_purpose="")
    assert s.org_name == ORG_NAME_DEFAULT and s.org_id is None and s.key_policy_url is None
    assert s.seal_purpose == make_settings().seal_purpose


def test_seal_settings_defaults(make_settings):
    s = make_settings()
    assert s.public_base_url == "https://localhost" and s.sth_after_seal is True


def test_worker_runs_seal_jobs():
    assert worker.HANDLERS[SEAL_JOB] is process_seal_job and SEAL_JOB == "seal"
