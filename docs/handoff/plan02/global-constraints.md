<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

## Global Constraints

Toàn bộ "Global Constraints" của Plan 00 và Plan 01 áp dụng nguyên văn. Plan này thêm các ràng buộc sau.

**Gọi Flowable**
- **Chỉ `trust-core-api` được gọi Flowable.** API là container duy nhất nằm trong `net-wf`; worker không ở đó (`deploy/network-matrix.yaml`).
- Worker không bao giờ cần Flowable: kết quả quy trình được đọc **đồng bộ** ngay sau khi hoàn thành task.

**BPMN**
- BPMN là đầu vào không tin cậy, vì Flowable thực thi script và biểu thức trong BPMN.
- Lõi chỉ nhận BPMN qua bộ kiểm **danh sách cho phép** (Task 3). Đọc XML bằng `defusedxml`, cấm DTD và entity.
- Không bao giờ chuyển cho Flowable một BPMN chưa qua bộ kiểm.

**Ký**
- Mọi chữ ký niêm phong dùng `seal-key`; mọi chữ ký STH dùng `sth-key`.
- Không bao giờ ghi vào bảng `seals` một hàng thiếu chữ ký.

**Thông tin công khai**
- Endpoint công khai (`/verify/v1/*`) **không** trả `record_id`, không trả hash của tệp đính kèm, không trả trường thiếu cờ `public` (F5, T7).
- Ngoại lệ duy nhất là gói bằng chứng (Task 8), vì gói cần payload đầy đủ để kiểm chữ ký.

**Secret**
- Secret mới (`flowable-rest-password`, `installer-client-secret`) chỉ cấp cho `trust-core-api`, **không** cấp cho worker (quyền tối thiểu).

**Dependency**
- Dependency Python mới: chỉ **defusedxml** (PSF-2.0).
- Ghi vào `LICENSES-THIRD-PARTY.md` trong cùng commit.
- Giấy phép khác MIT/BSD/Apache-2.0/PSF/ISC thì **dừng lại hỏi trưởng nhóm**.

**Test**
- Test **mới** của lõi chỉ dùng manifest tổng hợp (D6 của Plan 01): `test-app` và manifest mới `test-flow` (Task 1).
- Lưu ý: vài test lõi của Plan 01 vẫn nạp manifest A/B qua `core/tests/helpers/manifests.py` và `helpers/api.py`, ví dụ `test_pdp`, `test_records_api`, `test_ingest`, `test_anchor`, `test_seed`.
  - Task 14 chuyển các test đó sang `test-app`/`test-flow` khi nâng manifest A/B lên 1.1.0.
  - Sau Task 14, manifest A/B chỉ còn xuất hiện trong test tĩnh của `apps/` và trong e2e.


## Spec-level constraints (spec 1.0.3)
- Spec section 25 wins over plan text when they conflict.
- Every new code/config file carries SPDX headers `SPDX-FileCopyrightText: 2026 PSA_OVNCR`, `SPDX-License-Identifier: Apache-2.0`; `reuse lint` must pass.
- Lõi mù nghiệp vụ (I3): core/src, core/migrations, core/docker, core/Dockerfile, core/pyproject.toml contain no app id, collection or role name of any apps/*/manifest.yaml.
- I5: values of `pii` fields, free text outside `data`, and record salts never go into the ledger, STH or append-only tables.
- Ledger stores no bodies, only body_sha256; only INSERT on ledger_entries/tree_heads/anchors.
