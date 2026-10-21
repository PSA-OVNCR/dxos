<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 14 — controller rulings and context (binding; refine the brief)

- C1: Task 1 already added "test-flow" to `PATHS` / `load` (core/tests/helpers/manifests.py, test_manifest_validator.py). Skip the brief's "Thêm test-flow vào PATHS" line; only migrate the core tests that still use App A/B manifests to `test-app`/`test-flow`.
- BPMN must be hand-written to pass the strict allow-list validator from Task 3 (core/src/dxos_core/registry/bpmn.py): elements definitions/process/startEvent/endEvent/userTask/exclusiveGateway/sequenceFlow/conditionExpression (+ bpmndi geometry only); no `incoming`/`outgoing` child elements, no exporter attributes, no `name`-less issues — check `parse_bpmn` rules; start → userTask; every gateway flow has `${decision == '<v>'}` exactly; candidateGroups exactly one `app:<app_id>:<role>`; end ids match `^[A-Za-z_][A-Za-z0-9_-]{0,63}$`; no `guard_failed`/`cancelled`/`creator` ids. Use core/tests/fixtures/bpmn/test-review.bpmn as the model. Including bpmndi shapes is optional (nice for the modeler view); if you include them, only geometry attributes.
- Upgrade rules (Task 12 `check_upgrade`, stricter than P2-D14's literal list): an existing field cannot become required, its `pii` cannot be removed or changed, tasks/workflow cannot be dropped, new fields must not be required. Compare against `tests/apps/fixtures/<app>-1.0.0.yaml` (copy of the CURRENT manifests before you change them, take them from git HEAD). If the brief's App A field list conflicts with these rules (e.g. `trich_yeu` required but new), keep the brief's intent but make the upgrade pass: report the exact field and the choice in the report.
- AT-14 test scans shipped core code for every identifier from every apps/*/manifest.yaml (app id in both forms, collection names, role names). If it finds hits in core/src (docstrings/comments count), remove them (rephrase generically) — never weaken the test. List every removed hit in the report.
- Spec §14 scope statement: copy the line starting with "> Chứng nhận số là hệ thống" VERBATIM into apps/chung-nhan/README.md (keep markdown as in the spec, since the test compares the raw line), plus the brief's `không phải** hệ thống cấp chứng thư số PKI` check (both tests must pass with the same text).
- `tests/apps/test_app_manifests.py`: make sure pytest collects it (pytest.ini testpaths) and that `make check` runs it.
- Labels must be Vietnamese exactly as the brief; App B fields: map the five labels onto the existing App B fields in order of meaning (number, full name, event, issue date, email) — read the manifest to match.
