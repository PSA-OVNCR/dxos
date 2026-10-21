# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""E2E mốc M2, App A "Phòng hồ sơ số" (Plan 02 Task 15): tải tệp → quy trình hai bước → niêm phong → đối
soát → gói bằng chứng ngoại tuyến → xóa PII → thu hồi.

Cần: App A 1.1.0 đã cài bằng CLI (``ops/e2e/install_apps.sh``), ``DXOS_ORG_NAME`` đặt (không phải giá trị mẫu)
trong ``.env`` của stack và trong môi trường chạy test, CLI ``dxos-witness`` và ``git``.

Thứ tự: bước 11 (xóa PII, AT-27) chạy **trước** bước 10 (thu hồi), vì sau khi thu hồi trạng thái là
``REVOKED`` nên không còn kiểm được "vẫn ``VALID``".
"""

import json

import httpx
import pytest

pytestmark = [pytest.mark.infra, pytest.mark.e2e]

CCCD = "079203001234"


def test_m2_app_a_end_to_end(stack, tmp_path):
    a, col = stack.APP_A, stack.COL_A
    creator = "chuyen_vien_tp1"        # chuyên viên kiêm trưởng phòng: người tạo không được tự duyệt (AT-07)

    # 1. Tạo văn bản; EICAR → INFECTED, PDF sạch → CLEAN (AT-03).
    rec = stack.create(a, col, {"trich_yeu": "E2E M2 ban hành", "loai_van_ban": "Quyết định",
                                "chuc_vu_nguoi_ky": "Giám đốc", "nguoi_lien_he_cccd": CCCD}, creator)
    rid = rec["id"]
    bad = stack.upload(a, col, rid, stack.eicar(), creator)
    pdf = stack.clean_pdf()
    good = stack.upload(a, col, rid, pdf, creator)
    assert stack.wait_upload(bad, creator) == "INFECTED"
    assert stack.wait_upload(good, creator) == "CLEAN"

    # 2. Bắt đầu quy trình.
    r = stack.start(a, col, rid, creator)
    assert r.status_code == 200, r.text

    # 3. Người tạo tự duyệt → 403 not_same_actor (AT-07).
    r = stack.complete_task(a, col, rid, "duyet_noi_dung", "approve", creator)
    assert r.status_code == 403, r.text
    assert r.json().get("reason") == "same_actor", r.text

    # 4. Trưởng phòng khác duyệt nội dung.
    r = stack.complete_task(a, col, rid, "duyet_noi_dung", "approve", "truong_phong1")
    assert r.status_code == 200, r.text

    # 5. Giám đốc ban hành khi chưa xác nhận rà PII → 409 pii_reviewed.
    r = stack.complete_task(a, col, rid, "ban_hanh", "approve", "giam_doc1")
    assert r.status_code == 409, r.text
    assert r.json().get("guard") == "pii_reviewed", r.text

    # 6. Văn thư xác nhận rà PII; giám đốc ban hành → SEALED.
    r = stack.pii_review(a, col, rid, "van_thu1")
    assert r.status_code == 200, r.text
    r = stack.complete_task(a, col, rid, "ban_hanh", "approve", "giam_doc1")
    assert r.status_code == 200, r.text
    stack.wait_sealed(a, col, rid, "giam_doc1")
    seal_id = stack.seal_id(a, col, rid, "giam_doc1")

    # 7. Trang công khai: hợp lệ, chỉ trường public; issuer là tên tổ chức của stack (AT-28).
    view = stack.wait_anchored(seal_id)
    assert view["status"] == "VALID" and view["signature_valid"] is True
    assert view["inclusion"]["verified"] is True
    assert set(view["public_fields"]) <= {"so_hieu", "loai_van_ban", "trich_yeu", "chuc_vu_nguoi_ky"}
    text = json.dumps(view, ensure_ascii=False)
    assert "record_id" not in view and rid not in text and CCCD not in text and stack.sha256(pdf) not in text
    assert stack.ORG_NAME, "đặt DXOS_ORG_NAME (giống .env của stack) để kiểm issuer.name (AT-28)"
    assert view["issuer"]["name"] == stack.ORG_NAME

    # 8. :check đúng tệp → khớp; sửa 1 byte → không khớp (AT-05).
    check = f"{stack.base}/verify/v1/seals/{seal_id}:check"
    assert httpx.post(check, json={"sha256": stack.sha256(pdf)}, timeout=30).json()["match"] is True
    tampered = pdf[:-1] + bytes([pdf[-1] ^ 0x01])
    assert httpx.post(check, json={"sha256": stack.sha256(tampered)}, timeout=30).json()["match"] is False

    # 9. Gói bằng chứng → dxos-witness verify-bundle --anchor-dir trả 0 (AT-17);
    #    repo neo có tuyên bố khóa (AT-28).
    bundle_url = f"{stack.base}/verify/v1/seals/{seal_id}:bundle"
    pdf_path = tmp_path / "van-ban.pdf"
    pdf_path.write_bytes(pdf)
    bundle = tmp_path / f"dxos-seal-{seal_id}.json"
    r = httpx.post(bundle_url, json={"sha256": stack.sha256(pdf)}, timeout=30)
    assert r.status_code == 200, r.text
    bundle.write_bytes(r.content)
    anchor = stack.clone_anchor(tmp_path / "anchor")
    assert (anchor / f"keys/seal-key/v{view['key_version']}.json").is_file()
    assert stack.verify_bundle(bundle, anchor, pdf_path).returncode == 0

    # 11. Văn thư xóa CCCD (AT-27): trường biến mất; niêm phong vẫn VALID; gói vẫn kiểm được.
    v = stack.version(a, col, rid, "van_thu1")
    r = httpx.post(f"{stack.base}{stack.records(a, col)}/{rid}:erase-pii",
                   json={"fields": ["nguoi_lien_he_cccd"], "reason_code": "data_subject_request"},
                   headers=stack.h("van_thu1", **{"If-Match": f'"{v}"'}), timeout=30)
    assert r.status_code == 200, r.text
    assert "nguoi_lien_he_cccd" not in stack.get(a, col, rid, "van_thu1")["data"]
    assert stack.public(seal_id).json()["status"] == "VALID"
    r = httpx.post(bundle_url, json={"sha256": stack.sha256(pdf)}, timeout=30)
    assert r.status_code == 200, r.text
    after = tmp_path / f"dxos-seal-{seal_id}-sau-xoa.json"
    after.write_bytes(r.content)
    assert stack.verify_bundle(after, stack.clone_anchor(anchor), pdf_path).returncode == 0

    # 10. Giám đốc thu hồi → REVOKED.
    v = stack.version(a, col, rid, "giam_doc1")
    r = httpx.post(f"{stack.base}{stack.records(a, col)}/{rid}:revoke", json={"reason_code": "superseded"},
                   headers=stack.h("giam_doc1", **{"If-Match": f'"{v}"'}), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["seal_state"] == "REVOKED"
    assert stack.public(seal_id).json()["status"] == "REVOKED"
