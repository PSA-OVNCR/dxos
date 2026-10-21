# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test tĩnh của hai ứng dụng Tầng 2 (Plan 02 Task 14): manifest 1.1.0 khớp BPMN, nâng cấp từ 1.0.0, AT-14."""

import json
from pathlib import Path

import pytest
import yaml
from dxos_core.registry.bpmn import check_against_manifest, parse_bpmn
from dxos_core.registry.client_view import client_view
from dxos_core.registry.upgrade import check_upgrade
from dxos_core.registry.validator import ManifestError, validate_manifest
from helpers import at14

ROOT = Path(__file__).resolve().parents[2]
APPS = ["phong-ho-so", "chung-nhan"]
SEAL_TASKS = {"phong-ho-so": {"ban_hanh"}, "chung-nhan": {"phe_duyet"}}


def _manifest(app: str):
    return validate_manifest(yaml.safe_load((ROOT / f"apps/{app}/manifest.yaml").read_text(encoding="utf-8")))


@pytest.mark.parametrize("app", APPS)
def test_app_manifest_and_bpmn_agree(app):
    m = _manifest(app)
    xml = (ROOT / f"apps/{app}" / m.workflow.bpmn).read_bytes()
    seal_end = m.policies.seal.on_event.split(":", 1)[1]
    pm = check_against_manifest(xml, m)
    assert pm == parse_bpmn(xml, app_id=app, seal_end=seal_end)
    assert pm.seal_tasks == SEAL_TASKS[app]


def test_core_never_names_any_app_identifier():                                       # AT-14
    assert at14.scan(ROOT) == []                  # bộ quét duy nhất, dùng chung với core/tests


def test_app_b_readme_has_scope_statement():
    readme = (ROOT / "apps/chung-nhan/README.md").read_text(encoding="utf-8")
    assert "không phải** hệ thống cấp chứng thư số PKI" in readme


def test_app_b_readme_copies_spec_scope_statement():
    spec = (ROOT / "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md").read_text(encoding="utf-8")
    quote = next(line for line in spec.splitlines() if line.startswith("> Chứng nhận số là hệ thống"))
    assert quote in (ROOT / "apps/chung-nhan/README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("app", APPS)
def test_v110_upgrades_v100_only_before_any_seal(app):                     # P2-D14 ngoại lệ
    old = validate_manifest(yaml.safe_load(
        (ROOT / f"tests/apps/fixtures/{app}-1.0.0.yaml").read_text(encoding="utf-8")))
    new = _manifest(app)
    assert (old.app.version, new.app.version) == ("1.0.0", "1.1.0")
    check_upgrade(old, new, sealed_before=False)
    with pytest.raises(ManifestError):
        check_upgrade(old, new, sealed_before=True)


def test_app_a_public_fields_have_labels_and_no_pii():
    m = _manifest("phong-ho-so")
    fields = m.collections["van_ban"].fields
    assert m.policies.seal.public_fields
    assert all(fields[f].label and not fields[f].pii for f in m.policies.seal.public_fields)


# ---------- Bổ sung: nội dung 1.1.0 theo brief ----------

def test_app_a_v110_content():
    m = _manifest("phong-ho-so")
    f = m.collections["van_ban"].fields
    assert m.app.version == "1.1.0"
    assert f["so_hieu"].format == "{n:02}/QĐ-SM" and f["so_hieu"].reset == "yearly" and f["so_hieu"].public
    assert f["loai_van_ban"].public and not f["loai_van_ban"].required
    assert f["chuc_vu_nguoi_ky"].public and f["noi_nhan"].label == "Nơi nhận" and not f["noi_nhan"].public
    assert f["nguoi_lien_he_cccd"].pii == "CCCD" and not f["nguoi_lien_he_cccd"].public
    assert f["trich_yeu"].required and f["trich_yeu"].label == "Trích yếu nội dung"
    assert m.policies.seal.public_fields == ["so_hieu", "loai_van_ban", "trich_yeu", "chuc_vu_nguoi_ky"]
    assert m.policies.seal.revoke_roles == ["giam_doc"] and m.policies.pii.erase_roles == ["van_thu"]
    guards = m.workflow.tasks["ban_hanh"].guards
    assert "not_same_actor:duyet_noi_dung" in guards and "not_same_actor:creator" in guards  # tách nhiệm vụ
    every_guard = guards + m.workflow.tasks["duyet_noi_dung"].guards
    assert "field_required:loai_van_ban" not in every_guard   # guard chạy lúc :complete, bản ghi đã khóa sửa


def test_app_b_v110_content():
    m = _manifest("chung-nhan")
    f = m.collections["chung_nhan"].fields
    assert m.app.version == "1.1.0"
    assert [f[k].label for k in ("so_chung_nhan", "ho_ten", "su_kien", "ngay_cap", "email")] == \
        ["Số chứng nhận", "Họ và tên", "Sự kiện", "Ngày cấp", "Email"]
    assert m.policies.seal.revoke_roles == ["truong_clb"] and m.policies.pii.erase_roles == ["truong_clb"]
    assert all(not f[k].pii for k in m.policies.seal.public_fields)


@pytest.mark.parametrize("app", APPS)
def test_bpmn_process_id_and_ends(app):
    m = _manifest(app)
    pm = check_against_manifest((ROOT / f"apps/{app}" / m.workflow.bpmn).read_bytes(), m)
    keys = {"phong-ho-so": "phong-ho-so.ban-hanh", "chung-nhan": "chung-nhan.cap-chung-nhan"}
    assert pm.process_key == keys[app]
    assert pm.end_events == {"approved", "rejected"}


# Nhánh của cổng quyết định: đổi chỗ approve/reject phải làm test đỏ (brief Task 14).
EXPECTED_FLOWS = {
    "phong-ho-so": {
        "user_tasks": {"duyet_noi_dung": "truong_phong", "ban_hanh": "giam_doc"},
        "flows": {("start", "duyet_noi_dung", None), ("duyet_noi_dung", "gw_duyet", None),
                  ("gw_duyet", "ban_hanh", "approve"), ("gw_duyet", "rejected", "reject"),
                  ("ban_hanh", "gw_ban_hanh", None),
                  ("gw_ban_hanh", "approved", "approve"), ("gw_ban_hanh", "rejected", "reject")},
    },
    "chung-nhan": {
        "user_tasks": {"phe_duyet": "truong_clb"},
        "flows": {("start", "phe_duyet", None), ("phe_duyet", "gw_phe_duyet", None),
                  ("gw_phe_duyet", "approved", "approve"), ("gw_phe_duyet", "rejected", "reject")},
    },
}


@pytest.mark.parametrize("app", APPS)
def test_bpmn_gateway_branches(app):
    m = _manifest(app)
    pm = check_against_manifest((ROOT / f"apps/{app}" / m.workflow.bpmn).read_bytes(), m)
    want = EXPECTED_FLOWS[app]
    assert pm.user_tasks == want["user_tasks"]
    assert set(pm.flows) == want["flows"] and len(pm.flows) == len(want["flows"])
    assert pm.decisions_by_task == {t: frozenset({"approve", "reject"}) for t in want["user_tasks"]}


# ---------- Ví dụ của hướng dẫn "app trong 30 phút" (Plan 03 Task 13, P2-D2, AT-14, AT-26) ----------

EXAMPLES = ["so-muon-sach"]
EXAMPLE = ROOT / "examples/so-muon-sach"


def _example_doc(name: str) -> dict:
    return yaml.safe_load((ROOT / f"examples/{name}/manifest.yaml").read_text(encoding="utf-8"))


def _example(name: str):
    return validate_manifest(_example_doc(name))


def _example_pm(name: str):
    m = _example(name)
    return m, check_against_manifest((ROOT / f"examples/{name}" / m.workflow.bpmn).read_bytes(), m)


@pytest.mark.parametrize("name", EXAMPLES)
def test_example_manifest_and_bpmn_pass_the_same_allow_list_checker(name):
    m, pm = _example_pm(name)
    xml = (ROOT / f"examples/{name}" / m.workflow.bpmn).read_bytes()
    seal_end = m.policies.seal.on_event.split(":", 1)[1]
    assert pm == parse_bpmn(xml, app_id=m.app.id, seal_end=seal_end)
    assert pm.end_events == {"approved", "rejected"}


def test_so_muon_sach_manifest_content():
    m = _example("so-muon-sach")
    f = m.collections["phieu_muon"].fields
    assert (m.app.id, m.app.version, m.roles) == ("so-muon-sach", "1.0.0", ["ban_doc", "thu_thu"])
    assert list(f) == ["so_phieu", "ten_sach", "nguoi_muon", "ngay_muon", "email"]
    assert f["so_phieu"].type == "sequence" and f["so_phieu"].format == "{n}/PM" and f["so_phieu"].public
    assert f["ten_sach"].required and f["ten_sach"].public
    assert f["nguoi_muon"].required and f["nguoi_muon"].pii == "NAME" and not f["nguoi_muon"].public
    assert f["ngay_muon"].type == "date" and f["ngay_muon"].required
    assert f["email"].pii == "EMAIL" and not f["email"].required and not f["email"].public
    assert all(x.label for x in f.values())
    assert m.policies.seal.on_event == "process.completed:approved"
    assert m.policies.verify.public is True and m.policies.verify.require_file is False
    assert set(m.policies.seal.public_fields) <= {k for k, x in f.items() if x.public and not x.pii}
    task = m.workflow.tasks["duyet_muon"]
    assert (task.role, task.guards) == ("thu_thu", ["not_same_actor:creator"])
    assert list(m.workflow.tasks) == ["duyet_muon"]


def test_so_muon_sach_bpmn_is_one_step_with_approve_and_reject_branches():
    _, pm = _example_pm("so-muon-sach")
    assert pm.process_key == "so-muon-sach.duyet-muon"
    assert pm.user_tasks == {"duyet_muon": "thu_thu"} and pm.seal_tasks == {"duyet_muon"}
    assert set(pm.flows) == {
        ("start", "duyet_muon", None), ("duyet_muon", "gw_duyet_muon", None),
        ("gw_duyet_muon", "approved", "approve"), ("gw_duyet_muon", "rejected", "reject")}
    assert pm.decisions_by_task == {"duyet_muon": frozenset({"approve", "reject"})}


def test_so_muon_sach_is_in_the_at14_scan_list_and_absent_from_core():
    assert {"so-muon-sach", "so_muon_sach", "phieu_muon", "ban_doc", "thu_thu"} <= at14.identifiers(ROOT)
    assert at14.scan(ROOT) == []
    core_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "core/src").rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".sql", ".md"})
    assert all(x not in core_text for x in ("so-muon-sach", "so_muon_sach", "phieu_muon"))


def test_example_floor_cannot_be_weakened():                          # ví dụ FLOOR_WEAKENED trong hướng dẫn
    doc = _example_doc("so-muon-sach")
    doc["collections"]["phieu_muon"]["attachments"] = {
        "kinds": ["pdf"], "max_mb": 5, "min": 0, "quarantine": "optional"}
    with pytest.raises(ManifestError) as e:
        validate_manifest(doc)
    assert e.value.code == "FLOOR_WEAKENED"
    assert e.value.path == "/collections/phieu_muon/attachments/quarantine"


def test_example_web_fixture_is_exactly_what_the_core_would_serve():
    """Fixture của test web = đúng thân `GET /api/v1/apps/so-muon-sach/manifest` (không chép tay schema)."""
    m, pm = _example_pm("so-muon-sach")
    want = client_view(m, {t: sorted(v) for t, v in pm.decisions_by_task.items()})
    got = json.loads((EXAMPLE / "web/test/fixtures/manifest-view.json").read_text(encoding="utf-8"))
    assert got == want, "fixture lệch manifest: sinh lại theo lệnh ở examples/so-muon-sach/README.md"
