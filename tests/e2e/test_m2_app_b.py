# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""E2E mốc M2, App B "Chứng nhận số" (Plan 02 Task 15): nhập lô → duyệt từng chứng nhận → niêm phong → đối
soát không cần tệp.

Đây cũng là bước "e2e của App B đạt" trong AT-13 (``ops/at13_reuse.sh`` chạy riêng tệp này sau khi cài App B
bằng CLI trên image lõi đã phát hành).
"""

import json

import httpx
import pytest

pytestmark = [pytest.mark.infra, pytest.mark.e2e]


def test_m2_app_b_batch_certificates(stack):
    b, col = stack.APP_B, stack.COL_B
    rows = [{"ho_ten": f"Nguyễn Văn E2E {i}", "su_kien": "Hội thảo nguồn mở E2E", "ngay_cap": "2026-11-10",
             "email": f"e2e-{i}@example.invalid"} for i in range(3)]

    # 1. Cán bộ CLB tạo 3 chứng nhận bằng records:bulk rồi bắt đầu quy trình từng cái.
    ids = stack.bulk(b, col, rows, "can_bo_clb1")
    assert len(ids) == 3
    for rid in ids:
        r = stack.start(b, col, rid, "can_bo_clb1")
        assert r.status_code == 200, r.text

    # 2. Trưởng CLB hoàn thành 3 task phê duyệt.
    for rid in ids:
        r = stack.complete_task(b, col, rid, "phe_duyet", "approve", "truong_clb1")
        assert r.status_code == 200, r.text

    # 3. Cả 3 đều SEALED.
    seal_ids = []
    for rid in ids:
        stack.wait_sealed(b, col, rid, "truong_clb1")
        seal_ids.append(stack.seal_id(b, col, rid, "truong_clb1"))
    assert len(set(seal_ids)) == 3

    # 4. Đối soát không cần tệp; email không xuất hiện trong response công khai (F5, AT-19 phần nội dung).
    for sid, row in zip(seal_ids, rows, strict=True):
        r = stack.public(sid)
        assert r.status_code == 200, r.text
        view = r.json()
        assert view["status"] == "VALID" and view["signature_valid"] is True
        assert view["require_file"] is False and view["attachments_count"] == 0
        assert view["public_fields"]["ho_ten"] == row["ho_ten"]
        assert "email" not in view["public_fields"]
        assert row["email"] not in json.dumps(view, ensure_ascii=False)
        if stack.ORG_NAME:
            assert view["issuer"]["name"] == stack.ORG_NAME                                     # AT-28
        bundle = httpx.get(f"{stack.base}/verify/v1/seals/{sid}/bundle", timeout=30)
        assert bundle.status_code == 200, bundle.text
        assert bundle.json()["format"] == "dxos-seal-bundle/1"
        assert row["email"] not in bundle.text
