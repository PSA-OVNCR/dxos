# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""E2E mốc M1 (Plan 01 Task 17): tạo hồ sơ → tải tệp → kiểm dịch → STH → neo → witness."""

import base64
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.infra, pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "core/tests/fixtures/files"
ANCHOR_REMOTE = os.environ.get("DXOS_E2E_ANCHOR_REMOTE", "file:///var/lib/dxos/anchor-remote.git")
URL_A = "/api/v1/apps/phong-ho-so/collections/van_ban/records"


def eicar() -> bytes:
    return base64.b64decode((FILES / "eicar.b64").read_text(encoding="ascii").strip())


def fixture(name: str) -> bytes:
    return (FILES / name).read_bytes()


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def post(base: str, path: str, body, tok: str) -> dict:
    r = httpx.post(base + path, json=body, headers=_h(tok), timeout=30)
    assert r.status_code in (200, 201, 202), (path, r.status_code, r.text)
    return r.json()


def upload(base: str, rid: str, data: bytes, tok: str, name: str = "tep.pdf") -> str:
    r = httpx.post(f"{base}{URL_A}/{rid}/attachments", files={"file": (name, data, "application/pdf")},
                   headers=_h(tok), timeout=60)
    assert r.status_code == 202, r.text
    return r.json()["upload_id"]


def wait_status(base: str, upload_id: str, tok: str, timeout_s: float = 120) -> str:
    deadline = time.monotonic() + timeout_s
    while True:
        st = httpx.get(f"{base}/api/v1/uploads/{upload_id}", headers=_h(tok), timeout=30).json()["status"]
        if st != "STAGING" or time.monotonic() > deadline:
            return st
        time.sleep(2)


def test_m1_end_to_end(kc_token, base, admin_base, tmp_path):
    cv = kc_token("chuyen_vien1")
    adm = kc_token("admin1")
    rid = post(base, URL_A, {"trich_yeu": "E2E"}, cv)["id"]
    bad = upload(base, rid, eicar(), cv)
    good = upload(base, rid, fixture("clean-text.pdf"), cv)
    assert wait_status(base, bad, cv) == "INFECTED" and wait_status(base, good, cv) == "CLEAN"   # AT-03

    th = post(admin_base, "/admin/v1/anchor:run", {}, adm)
    assert th["tree_size"] > 0

    deadline = time.monotonic() + 120
    while True:                                     # worker đẩy STH lên repo neo
        status = httpx.get(f"{admin_base}/admin/v1/ledger/status", headers=_h(adm), timeout=30).json()
        anchored = (status["last_anchor"] or {}).get("tree_size", 0)
        if anchored >= th["tree_size"] or time.monotonic() > deadline:
            break
        time.sleep(3)
    assert status["last_anchor"]["tree_size"] >= th["tree_size"]
    assert status["verify"] == {"ok": True, "first_bad_idx": None}

    clone = tmp_path / "anchor"
    subprocess.run(["git", "clone", "-q", ANCHOR_REMOTE, str(clone)], check=True)
    cmd = ["dxos-witness", "sync", "--server", base, "--anchor-dir", str(clone),
           "--state-dir", str(tmp_path / "state")]
    witness = subprocess.run(cmd, check=False, capture_output=True, text=True)
    print(witness.stdout, witness.stderr)
    assert witness.returncode == 0


def test_idor_and_admin_least_privilege(kc_token, base):                                     # AT-06, D4
    cv = kc_token("chuyen_vien1")
    rid = post(base, URL_A, {"trich_yeu": "IDOR"}, cv)["id"]
    other = kc_token("owner_b1")
    assert httpx.get(f"{base}{URL_A}/{rid}", headers=_h(other), timeout=30).status_code == 404
    adm = kc_token("admin1")
    assert httpx.get(f"{base}{URL_A}/{rid}", headers=_h(adm), timeout=30).status_code == 404


def test_pii_masked_for_creator_revealed_for_director(kc_token, base):                      # AT-10
    cv = kc_token("chuyen_vien1")
    rid = post(base, URL_A, {"trich_yeu": "PII", "nguoi_lien_he_cccd": "079203001234"}, cv)["id"]
    gd = kc_token("giam_doc1")
    seen_cv, seen_gd = (httpx.get(f"{base}{URL_A}/{rid}", headers=_h(t), timeout=30).json()["data"]
                        ["nguoi_lien_he_cccd"] for t in (cv, gd))
    assert (seen_cv, seen_gd) == ("07********34", "079203001234")


def test_gateway_rejects_missing_token_and_verify_is_public(base):                         # AT-02
    assert httpx.get(f"{base}{URL_A}", timeout=30).status_code == 401
    assert httpx.get(f"{base}/verify/v1/keys", timeout=30).status_code == 200


def test_admin_api_not_on_public_host(kc_token, base):
    adm = kc_token("admin1")
    assert httpx.post(f"{base}/admin/v1/anchor:run", headers=_h(adm), timeout=30).status_code == 404
