<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Task 3 — controller rulings and context (binding; they refine the brief)

P2-D2 (plan decision the brief refers to): allowed elements are `definitions`, `process`, `startEvent`, `endEvent`, `userTask`, `exclusiveGateway`, `sequenceFlow`, `conditionExpression`, plus the `bpmndi`/`dc`/`di` drawing group (geometry only). Every `${` / `#{` in text or attributes is banned except the one conditionExpression pattern. The core deploys the XML it re-renders, never the uploaded file.

Earlier rulings:
- C1: tests import `load` from `core/tests/helpers/manifests.py` (Task 1 added "test-flow" there).
- C2: `parse_bpmn` itself rejects a userTask with id `creator` (BPMN_INVALID); `check_against_manifest` keeps its own check too.
- C11: every endEvent id must match `^[A-Za-z_][A-Za-z0-9_-]{0,63}$` (same as records.wf_state CHECK).
- C17: gateways do NOT get the `default` attribute — remove it from the allow-list (rule 7 requires every gateway flow to carry a decision condition). The brief's "Riêng cổng có thêm `default`" is overridden.
- `seal_end` for `check_against_manifest` = the part after `process.completed:` in `m.policies.seal.on_event` (already validated by Task 1's validator); `None` when the manifest has no seal policy.

New rulings for this task:
- T3-a Namespaces: identify elements and attributes by (namespace URI, local name), never by prefix. BPMN model `http://www.omg.org/spec/BPMN/20100524/MODEL`; DI `http://www.omg.org/spec/BPMN/20100524/DI`, `http://www.omg.org/spec/DD/20100524/DC`, `http://www.omg.org/spec/DD/20100524/DI`; flowable `http://flowable.org/bpmn`; xsi `http://www.w3.org/2001/XMLSchema-instance`. Element in any other namespace → BPMN_INVALID. Namespace declarations (xmlns) are not attributes in ElementTree; `definitions` may declare any prefixes but only allow-listed namespaces may be USED. `conditionExpression` `xsi:type` value must be a QName whose local part is `tFormalExpression` and whose prefix (if any) resolves to the BPMN model namespace — if resolving prefixes is impractical with defusedxml ET, accept exactly `tFormalExpression` or `bpmn:tFormalExpression`/`bpmn2:tFormalExpression` and say so in the report.
- T3-b Text: non-whitespace text (or tail) anywhere except inside `conditionExpression` → BPMN_INVALID (stricter than rule 5; there is no legitimate text in the allowed elements). The `${`/`#{` ban still applies to every attribute value, including bpmndi ones and `targetNamespace`.
- T3-c Ids: every id of a flow node / flow / process must match `^[A-Za-z_][A-Za-z0-9_-]{0,63}$` (process id additionally follows rule 2); duplicate ids → BPMN_INVALID.
- T3-d Graph shape (so render can rebuild node kinds from ProcessModel alone): startEvent has no incoming flow and exactly one outgoing; endEvent has no outgoing; each gateway has ≥1 incoming and ≥1 outgoing; on any gateway the decision values of its outgoing flows are pairwise distinct; conditions only on flows leaving a gateway (a condition elsewhere → BPMN_INVALID); a gateway's outgoing flows must target userTasks or endEvents (no gateway→gateway chains). Loops back to an earlier userTask are allowed.
- T3-e Canonical model: `flows` is a sorted tuple (sort by (source, target, decision or "")), so render→reparse equals the original model regardless of document order. Node kinds in render: id in user_tasks → userTask; in end_events → endEvent; the unique node with no incoming flow → startEvent; anything else → exclusiveGateway. Render emits generated flow ids (deterministic, e.g. `f1..fn` in the sorted order), the process `id` = process_key, `isExecutable="true"`, `flowable:candidateGroups="app:<app_id>:<role>"`; no `name` attributes, no bpmndi. Encoding UTF-8 with an XML declaration; same model → same bytes.
- T3-f Errors: every failure, including size limit, DTD/entity rejection from defusedxml and XML syntax errors, raises `ManifestError("BPMN_INVALID", <path>, <message>)`; path is "/workflow/bpmn" (use the same path everywhere). Never let defusedxml/ParseError exceptions escape.
- T3-g defusedxml: brief says `defusedxml.ElementTree.fromstring(..., forbid_dtd=True, forbid_entities=True, forbid_external=True)`. Add `defusedxml>=0.7,<1` to core/pyproject.toml and install it in the venv (`pip install` into .venv). License row in LICENSES-THIRD-PARTY.md: read the actual license from the installed wheel metadata (it is PSF-2.0 per the plan — verify, write what the metadata says).
