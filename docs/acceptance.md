<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Ma trận nghiệm thu AT-01..AT-28

Nguồn: spec mục 19 (`docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`, "Tiêu chí nghiệm thu"). Bảng này nói
**mỗi AT được tự động kiểm bằng test nào, test chạy ở đâu, và bằng chứng gần nhất nằm ở đâu**. Tệp
`tests/repo/test_at_matrix.py` bắt buộc: đủ 28 dòng; mọi `đường_dẫn::tên_test` phải tồn tại (có `def <tên>` hoặc
`test('<tên>'`/`it('<tên>'` trong tệp); chỉ AT-18, AT-21, AT-22, AT-23, AT-26 được ghi `Thủ công`, mỗi dòng như vậy
phải dẫn một tài liệu bằng chứng có thật hoặc ghi "chưa có — V<số>" (việc của trưởng nhóm, xem
`docs/progress/`); tài liệu bằng chứng nào được dẫn trong cột cuối cũng phải tồn tại.

Cột "Chạy ở đâu":
- **CI unit**: job `unit` của `.github/workflows/ci.yml` (`make test`, không cần Docker).
- **CI integration**: job `integration` (PostgreSQL, OpenBao, SeaweedFS, Flowable từ `deploy/compose.test.yaml`).
- **CI web**: job `web` (`npm run check`, Playwright của cổng đối soát).
- **Stack dev**: cần stack dev-lite đang chạy; `pytest -m infra` hoặc `ops/e2e/run_e2e.sh` (marker `e2e`).
- **VPS / máy trưởng nhóm**: cần máy thật hoặc hành động bên ngoài, không chạy được ở cloud.

Cột "Bằng chứng gần nhất" chỉ ghi điều đã có trong repo. Test chạy ở CI thì log nằm trên GitHub Actions, không chép vào
repo. "Chưa có" nghĩa là chưa ai chạy hoặc chưa lưu kết quả.

| AT | Nội dung | Tự động bằng | Chạy ở đâu | Bằng chứng gần nhất |
|---|---|---|---|---|
| AT-01 | Ma trận kết nối mạng thực tế khớp ma trận mong đợi (Internet chỉ vào 443; Viewer, net-app, Flowable và caddy không tới được dịch vụ cấm) | `tests/infra/test_network_live.py::test_probes_match_matrix`<br>`tests/infra/test_compose_static.py::test_membership_matches_matrix`<br>`tests/ops/test_netcheck.py::test_mismatch_is_reported_and_exit_code_nonzero` | Stack dev (probe thật); CI unit (tĩnh và runner giả) | `docs/progress/2026-10-20-task4-kiem-tra-song.md`: 30/30 probe đạt trên dev-lite 20/10 (bằng script PowerShell tương đương, chưa chạy lại bằng pytest) |
| AT-02 | Gọi không JWT, hoặc JWT sai `aud`/chữ ký, đều 401 | `core/tests/test_identity.py::test_rejected_tokens`<br>`core/tests/test_identity.py::test_bad_token_401_problem_with_www_authenticate`<br>`tests/e2e/test_m1_flow.py::test_gateway_rejects_missing_token_and_verify_is_public`<br>`tests/infra/test_network_live.py::test_api_requires_token` | CI unit (lõi); Stack dev (gateway) | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: 4 test `test_m1_flow` PASSED |
| AT-03 | Tải EICAR thì `INFECTED`; mọi API đọc trả 404/409 | `core/tests/integration/test_ingest.py::test_eicar_quarantined`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI integration; Stack dev; bảng thử V8 | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED; `ops/vuot_rao.py` V8 chưa chạy (V28) |
| AT-04 | Tệp đang `STAGING` không đọc được, kể cả với `dxos-admin` | `core/tests/integration/test_ingest.py::test_staging_not_readable_even_by_admin` | CI integration | CI job `integration` |
| AT-05 | Sửa 1 byte thì sha256 mới; niêm phong cũ vẫn hợp lệ với tệp cũ; tệp đã sửa thì "Không khớp" | `core/tests/integration/test_ingest.py::test_cas_dedup_and_byte_change`<br>`core/tests/integration/test_verify_api.py::test_check_matches_original_not_modified_file`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI integration; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED |
| AT-06 | Người dùng X đọc bản ghi của Y thì 404, ledger ghi `policy.denied` | `core/tests/integration/test_records_api.py::test_idor_returns_404_and_logs`<br>`tests/e2e/test_m1_flow.py::test_idor_and_admin_least_privilege` | CI integration; Stack dev; bảng thử V2 | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m1_flow` PASSED; V2 chưa chạy (V28) |
| AT-07 | Người tạo tự duyệt văn bản của mình thì 403 (`not_same_actor`) | `core/tests/test_guards.py::test_creator_cannot_approve_own_record`<br>`core/tests/integration/test_workflow_api.py::test_creator_self_approval_denied_and_logged`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI unit; CI integration; Stack dev; bảng thử V1 | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED; V1 chưa chạy (V28) |
| AT-08 | Duyệt khi tệp đính kèm chưa CLEAN thì 409 | `core/tests/test_guards.py::test_pending_upload_blocks_with_409`<br>`core/tests/integration/test_workflow_api.py::test_start_needs_clean_attachments` | CI unit; CI integration | CI job `unit`, `integration` |
| AT-09 | PATCH bản ghi đã niêm phong thì 409; trigger chặn UPDATE trực tiếp | `core/tests/integration/test_records_api.py::test_sealed_record_patch_409`<br>`core/tests/integration/test_migrations.py::test_sealed_record_data_immutable` | CI integration; bảng thử V5 | CI job `integration`; V5 chưa chạy (V28) |
| AT-10 | PII bị che với `nhan_vien`, hiện rõ với `giam_doc`; mỗi lần hiện rõ có `field.revealed` | `core/tests/integration/test_records_api.py::test_pii_masked_and_reveal_logged`<br>`tests/e2e/test_m1_flow.py::test_pii_masked_for_creator_revealed_for_director` | CI integration; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m1_flow` PASSED |
| AT-11 | Manifest khai `quarantine: optional` hoặc guard ngoài danh mục thì bị từ chối | `core/tests/test_manifest_validator.py::test_floor_weakened`<br>`core/tests/test_manifest_validator.py::test_unknown_guard`<br>`core/tests/integration/test_installer.py::test_submit_bad_manifest_422_with_code`<br>`tests/e2e/test_m2_attacks.py::test_manifest_weakening_quarantine_is_rejected_by_cli` | CI unit; CI integration; Stack dev; bảng thử V9 | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_attacks` (CLI từ chối 3 manifest) PASSED; V9 chưa chạy (V28) |
| AT-12 | Manifest đòi vai trò hoặc collection ngoài namespace thì bị từ chối | `core/tests/test_manifest_validator.py::test_namespace_violation`<br>`tests/e2e/test_m2_attacks.py::test_manifest_claiming_foreign_role_is_rejected_by_cli` | CI unit; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_attacks` PASSED |
| AT-13 | Cài App B trên image lõi đã phát hành (cùng digest); diff `core/` và gateway rỗng; e2e App B đạt | `tests/ops/test_at13_reuse.py::test_unchanged_stack_passes_and_writes_comparison_table`<br>`tests/e2e/test_m2_app_b.py::test_m2_app_b_batch_certificates` | CI unit (logic script, docker giả); VPS (`ops/at13_reuse.sh` với image GHCR); Stack dev (e2e App B) | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_b_batch_certificates` PASSED. Phần "image đã phát hành, cùng digest": chưa có — V20 (tệp docs/evidence/at13-reuse.txt do `ops/at13_reuse.sh` ghi) |
| AT-14 | CI quét `core/` không chứa định danh của app | `tests/apps/test_app_manifests.py::test_core_never_names_any_app_identifier`<br>`core/tests/test_manifest_validator.py::test_core_never_names_tier2_apps` | CI unit | CI job `unit` |
| AT-15 | Superuser tắt trigger, sửa một lá thì `verify` báo lệch tại idx n | `core/tests/integration/test_ledger_log.py::test_verify_detects_tamper` | CI integration | CI job `integration` |
| AT-16 | Dựng lại toàn bộ log và ký STH mới thì witness phát hiện consistency proof thất bại so với STH đã neo | `witness/tests/test_sync.py::test_witness_detects_full_rewrite`<br>`witness/tests/test_sync.py::test_rewrite_of_anchored_history_after_last_witness_run` | CI unit | CI job `unit` |
| AT-17 | Gói bằng chứng kiểm chứng ngoại tuyến chỉ với khóa công khai và STH đã neo | `witness/tests/test_bundle.py::test_valid_bundle_offline_with_pinned_keys`<br>`core/tests/integration/test_verify_api.py::test_core_bundle_passes_witness_verify_bundle`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI unit; CI integration; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED (repo neo cục bộ, không phải GitHub) |
| AT-18 | Force-push vào nhánh neo bằng deploy key thì GitHub từ chối (kiểm thủ công, có ảnh) | Thủ công | VPS / máy trưởng nhóm (repo neo thật trên GitHub) | chưa có — V13 (ảnh `at18-force-push-rejected.png`, xem `docs/evidence/README.md`). Phần mã neo có test: `core/tests/integration/test_anchor.py` |
| AT-19 | Vượt rate-limit `/verify` thì 429; phản hồi chỉ chứa trường `public` | `tests/e2e/test_m2_attacks.py::test_public_verify_is_rate_limited_even_with_forged_forwarded_for`<br>`core/tests/integration/test_verify_api.py::test_public_view_has_only_allowed_keys` | Stack dev; CI integration | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_attacks` (có rate-limit) PASSED; cùng tài liệu lại ghi AT-19 ở mục "Chưa làm", cần trưởng nhóm xác nhận |
| AT-20 | OpenBao khóa trước task cuối thì 503, Flowable không bị tác động; hỏng sau Flowable thì `SEAL_PENDING` rồi tự hoàn tất; ClamAV ngừng thì tệp ở `STAGING` | `tests/e2e/test_m2_attacks.py::test_openbao_sealed_before_last_task_is_503_and_flowable_untouched`<br>`core/tests/integration/test_workflow_api.py::test_kms_down_before_last_task_is_503_and_flowable_untouched`<br>`core/tests/integration/test_seal.py::test_kms_fails_after_flowable_then_recovers`<br>`core/tests/integration/test_ingest.py::test_clamd_down_stays_staging_and_retries` | CI integration; VPS / máy chủ stack (E2E cần `docker` và unseal key) | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: test E2E của AT-20 SKIPPED (thiếu `DXOS_E2E_BAO_TOKEN`); phần integration chạy ở CI job `integration` |
| AT-21 | (SHOULD) Diễn tập khôi phục: dữ liệu và niêm phong vẫn đối soát được | Thủ công | Máy chủ thật (diễn tập sao lưu/khôi phục) | chưa có — S4 (Plan 04) |
| AT-22 | Đỉnh RAM dưới 80% trên hồ sơ p8 | Thủ công | VPS hồ sơ p8 (`ops/measure.sh`, `ops/capacity_report.py`) | chưa có — V13 (đo RAM Plan 01 Task 7). Công cụ có test: `tests/ops/test_capacity_report.py` |
| AT-23 | `reuse lint` đạt; SBOM sinh ra; người ngoài đội build từ nguồn trên máy sạch theo README | Thủ công | CI (`reuse lint`, SBOM ở trang Release); máy sạch của người ngoài đội | chưa có — V33 (Release `v0.3.0` có SBOM; việc build bởi người ngoài đội làm cùng đợt AT-26/V31). `reuse lint` đã chạy ở CI job `reuse` |
| AT-24 | Compose production không chứa `fake-av` hay dịch vụ gắn nhãn `DEV-ONLY` | `tests/infra/test_compose_static.py::test_no_dev_only_service_in_production` | CI unit | CI job `unit` |
| AT-25 | `:check` kèm tệp bị từ chối (415); trang đối soát tính hash bằng WebCrypto, không request nào chứa nội dung tệp | `core/tests/integration/test_verify_api.py::test_check_refuses_files_and_large_bodies`<br>`verify-portal/app/e2e/at25.spec.ts::AT-25: file never leaves the browser, only {"sha256"} is sent` | CI integration (API); CI web (Playwright); bảng thử V7 trên stack | CI job `integration`, `web`; V7 chưa chạy (V28) |
| AT-26 | Một người ngoài đội làm theo hướng dẫn H13, tạo được app mới qua manifest mà không sửa `core/` | Thủ công | Người ngoài đội, máy của họ | chưa có — V31 (checklist `docs/at26-checklist.md`, hướng dẫn `docs/tutorial-app-30-phut.md` và ví dụ `examples/so-muon-sach` đã có từ Plan 03 Task 13; ví dụ có test tĩnh ở `tests/apps/test_app_manifests.py`, chưa ai ngoài đội thử) |
| AT-27 | `:erase-pii` trên bản ghi đã niêm phong: trường biến mất, salt bị xóa; niêm phong vẫn `VALID`, `verify-bundle` đạt; không còn giá trị đã xóa trong dump | `core/tests/integration/test_seal.py::test_erase_pii_keeps_seal_valid_and_leaves_no_trace`<br>`core/tests/integration/test_seal.py::test_no_unsalted_commitment_anywhere`<br>`core/tests/integration/test_verify_api.py::test_bundle_after_erase_pii_passes_witness_verify_bundle`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI integration; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED |
| AT-28 | Mỗi phiên bản `seal-key` có tuyên bố khóa đã neo; niêm phong ngoài thời hạn bị từ chối; tên tổ chức chưa cấu hình thì 503; `verify-bundle` báo `INVALID` khi tuyên bố bị sửa | `core/tests/integration/test_seal.py::test_key_statement_created_once_and_enforced`<br>`witness/tests/test_bundle.py::test_key_statement_tamper_is_invalid`<br>`witness/tests/test_bundle.py::test_seal_issued_outside_key_validity_is_invalid`<br>`tests/e2e/test_m2_app_a.py::test_m2_app_a_end_to_end` | CI integration; CI unit; Stack dev | `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`: `test_m2_app_a_end_to_end` PASSED |

## Bảng thử vượt rào (`ops/vuot_rao.py`)

Mỗi kịch bản đòi cả mã lẫn `type` problem+json của lõi: 404 của gateway hay `app-not-active` không tính là bị chặn.
Chạy trên stack dev (`make vuot-rao`, hoặc `python ops/vuot_rao.py`), in bảng `| # | Hành vi tấn công | Kỳ vọng | Thực tế |
Kết quả |` rồi 20 lá `policy.denied` gần nhất. Dùng khi demo (H11) và đối chiếu AT. Kết quả thật trên stack dev 22/10/2026 (10/10, V28): `docs/progress/2026-10-22-web-live.md`.

| # | Hành vi tấn công | Kỳ vọng | AT |
|---|---|---|---|
| V1 | Người tạo tự duyệt văn bản của mình | 403 `guard-failed` (`same_actor`) | AT-07 |
| V2 | `chuyen_vien1` đọc văn bản của `chuyen_vien_tp1` | 404 `not-found` | AT-06 |
| V3 | Token chỉ có vai trò App B gọi danh sách App A | 403 `forbidden` | Review Focus 3 (Plan 00) |
| V4 | `admin1` đọc dữ liệu App A | 403 `forbidden` | spec 9.2 |
| V5 | Sửa văn bản đã niêm phong | 409 `record-sealed` | AT-09 |
| V6 | Giám đốc ban hành khi chưa rà PII | 409 `guard-failed` (`pii_reviewed`) | spec 9.3 |
| V7 | Gửi nguyên tệp PDF tới `:check` | 415 `unsupported-media-type` | AT-25 |
| V8 | Tải EICAR rồi đọc tệp | `INFECTED`; đọc tệp 404 `not-found` | AT-03 |
| V9 | Nộp thẳng lên API quản trị manifest nới `quarantine` | 422 `manifest-invalid` | AT-11 |
| V10 | Duyệt bằng task của app khác | 404 `not-found` | Plan 02 |
