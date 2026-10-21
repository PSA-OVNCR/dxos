# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bộ kiểm BPMN theo danh sách cho phép và bản dựng lại chuẩn (P2-D2, Plan 02 Task 3).

BPMN của ứng dụng là đầu vào không tin cậy: Flowable tính biểu thức JUEL (gọi được phương thức Java) ở rất
nhiều chỗ. Vì vậy lõi chỉ nhận một tập con rất hẹp của BPMN, rút ra ``ProcessModel``, rồi tự dựng lại XML từ
model đó (``render_bpmn``). Flowable chỉ bao giờ nhận bản do lõi dựng, không bao giờ nhận tệp tải lên.

Phần tử và thuộc tính được nhận diện theo (URI không gian tên, tên cục bộ), không theo tiền tố.
Mọi lỗi đều là ``ManifestError("BPMN_INVALID", "/workflow/bpmn", <thông điệp>)``.
"""

import io
import re
from collections import deque
from dataclasses import dataclass, replace
from xml.sax.saxutils import escape

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException

from dxos_core.registry.model import Manifest
from dxos_core.registry.validator import ManifestError

MAX_BPMN_BYTES = 256 * 1024

_PATH = "/workflow/bpmn"

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
FLOWABLE = "http://flowable.org/bpmn"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
_PREFIX = {BPMN: "", BPMNDI: "bpmndi:", DC: "dc:", DI: "di:", FLOWABLE: "flowable:", XSI: "xsi:"}


def _q(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


DEFINITIONS, PROCESS = _q(BPMN, "definitions"), _q(BPMN, "process")
START, END, TASK, GATEWAY = (_q(BPMN, n) for n in ("startEvent", "endEvent", "userTask", "exclusiveGateway"))
FLOW, COND = _q(BPMN, "sequenceFlow"), _q(BPMN, "conditionExpression")
CANDIDATE_GROUPS, XSI_TYPE = _q(FLOWABLE, "candidateGroups"), _q(XSI, "type")
_NODES = (START, END, TASK, GATEWAY)

# Phần tử con được phép theo phần tử cha (P2-D2). Phần tử không có trong bảng thì không được có con.
_CHILDREN: dict[str | None, frozenset[str]] = {
    None: frozenset({DEFINITIONS}),
    DEFINITIONS: frozenset({PROCESS, _q(BPMNDI, "BPMNDiagram")}),
    PROCESS: frozenset({*_NODES, FLOW}),
    FLOW: frozenset({COND}),
    _q(BPMNDI, "BPMNDiagram"): frozenset({_q(BPMNDI, "BPMNPlane")}),
    _q(BPMNDI, "BPMNPlane"): frozenset({_q(BPMNDI, "BPMNShape"), _q(BPMNDI, "BPMNEdge")}),
    _q(BPMNDI, "BPMNShape"): frozenset({_q(DC, "Bounds"), _q(BPMNDI, "BPMNLabel")}),
    _q(BPMNDI, "BPMNEdge"): frozenset({_q(DI, "waypoint"), _q(BPMNDI, "BPMNLabel")}),
    _q(BPMNDI, "BPMNLabel"): frozenset({_q(DC, "Bounds")}),
}

# Thuộc tính được phép theo từng phần tử. Cổng KHÔNG có ``default`` (C17): mọi flow ra khỏi cổng có điều kiện.
_ATTRS: dict[str, frozenset[str]] = {
    DEFINITIONS: frozenset({"id", "targetNamespace"}),
    PROCESS: frozenset({"id", "name", "isExecutable"}),
    START: frozenset({"id", "name"}),
    END: frozenset({"id", "name"}),
    GATEWAY: frozenset({"id", "name"}),
    TASK: frozenset({"id", "name", CANDIDATE_GROUPS}),
    FLOW: frozenset({"id", "sourceRef", "targetRef"}),
    COND: frozenset({XSI_TYPE}),
    # nhóm vẽ: chỉ thuộc tính hình học; lõi bỏ hết nhóm này khi dựng lại
    _q(BPMNDI, "BPMNDiagram"): frozenset({"id"}),
    _q(BPMNDI, "BPMNPlane"): frozenset({"id", "bpmnElement"}),
    _q(BPMNDI, "BPMNShape"): frozenset({"id", "bpmnElement", "isHorizontal", "isExpanded",
                                        "isMarkerVisible"}),
    _q(BPMNDI, "BPMNEdge"): frozenset({"id", "bpmnElement", "sourceElement", "targetElement"}),
    _q(BPMNDI, "BPMNLabel"): frozenset({"id"}),
    _q(DC, "Bounds"): frozenset({"x", "y", "width", "height"}),
    _q(DI, "waypoint"): frozenset({"x", "y"}),
}

# ``$`` của Python khớp cả trước ``\n`` cuối chuỗi, nên mọi mẫu dưới đây đều dùng ``fullmatch``.
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")              # như CHECK của records.wf_state (C11)
_CONDITION = re.compile(r"\$\{\s*decision\s*==\s*'([a-z][a-z0-9_]{0,31})'\s*\}", re.ASCII)
_ROLE = r"[a-z][a-z0-9_]{0,30}"
_EXPR = ("${", "#{")
_XML_WS = " \t\r\n"
# Trạng thái kết thúc do lõi tự đặt (Task 6); không nút nào của BPMN được dùng. ``creator`` (tham số của
# not_same_actor) bị cấm riêng cho userTask.
RESERVED_IDS = frozenset({"guard_failed", "cancelled"})
_TARGET_NAMESPACE = "urn:dxos:bpmn"


@dataclass(frozen=True)
class ProcessModel:
    """Model rút từ BPMN đã kiểm; ``render_bpmn`` dựng lại XML chỉ từ các trường này.

    - ``process_key``: ``"<app_id>.<tên>"``, ví dụ ``"test-flow.review"``.
    - ``user_tasks``: id userTask → role (lấy từ candidateGroups ``app:<id>:<role>``).
    - ``decisions_by_task``: các giá trị decision mà cổng ngay sau task chấp nhận; rỗng khi task đi thẳng
      tới end event (bridge chấp nhận mọi decision hợp lệ).
    - ``seal_tasks``: userTask tới được end event niêm phong mà không qua userTask khác.
    - ``flows``: ``(source, target, decision|None)``, sắp theo ``(source, target, decision or "")``.
    """

    process_key: str
    user_tasks: dict[str, str]
    end_events: frozenset[str]
    decisions_by_task: dict[str, frozenset[str]]
    seal_tasks: frozenset[str]
    flows: tuple[tuple[str, str, str | None], ...]


def _fail(message: str) -> ManifestError:
    return ManifestError("BPMN_INVALID", _PATH, message)


def _name(key: str, *, attr: bool = False) -> str:
    """``{uri}local`` → ``prefix:local`` quen thuộc, để thông điệp lỗi dễ đọc."""
    if not key.startswith("{"):
        return key
    ns, _, local = key[1:].partition("}")
    if attr and ns == BPMN:  # thuộc tính mang không gian tên BPMN, khác thuộc tính trơn cùng tên
        return f"bpmn:{local}"
    return f"{_PREFIX[ns]}{local}" if ns in _PREFIX else f"{{{ns}}}{local}"


# ---------- Đọc XML ----------

def _read_xml(xml: bytes):
    """Đọc bằng defusedxml (cấm DTD, entity, tham chiếu ngoài).

    Trả ``(gốc, {phần tử conditionExpression: xsi:type đã giải})``.

    Dùng ``iterparse`` thay cho ``fromstring`` (cùng bộ đọc, cùng cờ cấm) chỉ để theo dõi khai báo không gian
    tên, nhờ đó giải được tiền tố trong giá trị ``xsi:type`` (T3-a).
    """
    scope: list[tuple[str, str]] = []
    xsi_types: dict[object, tuple[str | None, str] | None] = {}
    try:
        it = DET.iterparse(io.BytesIO(xml), events=("start-ns", "end-ns", "start"),
                           forbid_dtd=True, forbid_entities=True, forbid_external=True)
        for event, item in it:
            if event == "start-ns":
                scope.append(item)
            elif event == "end-ns":
                scope.pop()
            elif item.tag == COND and XSI_TYPE in item.attrib:
                xsi_types[item] = _resolve_qname(item.attrib[XSI_TYPE], scope)
        return it.root, xsi_types
    except DefusedXmlException as exc:
        raise _fail(f"cấm DTD, entity và tham chiếu ngoài trong BPMN ({type(exc).__name__})") from None
    except (DET.ParseError, ValueError, LookupError) as exc:
        raise _fail(f"XML sai cú pháp: {exc}") from None


def _resolve_qname(value: str, scope: list[tuple[str, str]]) -> tuple[str | None, str] | None:
    """QName → (URI, tên cục bộ); không tiền tố → (None, tên); tiền tố chưa khai báo → None."""
    prefix, sep, local = value.partition(":")
    if not sep:
        return None, value
    for p, uri in reversed(scope):
        if p == prefix:
            return uri, local
    return None


# ---------- Bước 1: danh sách cho phép (phần tử, thuộc tính, văn bản) ----------

def _blank(text: str | None) -> bool:
    return text is None or not text.strip(_XML_WS)


def _check_tree(el, parent: str | None, xsi_types: dict) -> None:
    tag = el.tag if isinstance(el.tag, str) else repr(el.tag)
    if tag not in _CHILDREN.get(parent, frozenset()):
        if parent is None:
            raise _fail(f"phần tử gốc phải là definitions, không phải {_name(tag)}")
        raise _fail(f"phần tử {_name(tag)} không được phép trong {_name(parent)}")
    allowed = _ATTRS[tag]
    for key, value in el.attrib.items():
        if key not in allowed:
            raise _fail(f"thuộc tính {_name(key, attr=True)} không được phép trên {_name(tag)}")
        if any(e in value for e in _EXPR):
            raise _fail(f"thuộc tính {_name(key, attr=True)} của {_name(tag)} chứa biểu thức (${{ hoặc #{{)")
    if not _blank(el.tail):
        raise _fail(f"không được có văn bản sau {_name(tag)}")
    if tag == COND:
        _check_condition(el, xsi_types)
    elif not _blank(el.text):
        raise _fail(f"không được có văn bản trong {_name(tag)}")
    if tag == FLOW and len(el) > 1:
        raise _fail("sequenceFlow chỉ được có một conditionExpression")
    for child in el:
        _check_tree(child, tag, xsi_types)


def _check_condition(el, xsi_types: dict) -> None:
    resolved = xsi_types.get(el)
    if resolved is None or resolved[1] != "tFormalExpression" or resolved[0] not in (None, BPMN):
        raise _fail('conditionExpression phải có xsi:type="tFormalExpression"')
    if not _CONDITION.fullmatch(el.text or ""):
        raise _fail("conditionExpression chỉ được có dạng ${decision == '<giá trị>'}")


# ---------- Bước 2: process, id, candidateGroups ----------

def _check_process(root, app_id: str):
    processes = [el for el in root if el.tag == PROCESS]
    if len(processes) != 1:
        raise _fail(f"cần đúng một process, có {len(processes)}")
    proc = processes[0]
    if proc.get("isExecutable") != "true":
        raise _fail('process phải có isExecutable="true"')
    pid = proc.get("id") or ""
    if not re.fullmatch(re.escape(app_id) + r"\.[a-z][a-z0-9-]{0,62}", pid):
        raise _fail(f"process id {pid!r} phải có dạng '{app_id}.<tên>'")
    return proc, pid


def _check_ids(root, proc) -> None:
    seen: set[str] = set()
    for el in root.iter():
        i = el.get("id")
        if i is None:
            continue
        if i in seen:
            raise _fail(f"id trùng: {i!r}")
        seen.add(i)
    for el in proc:
        i = el.get("id")
        if i is None:
            raise _fail(f"{_name(el.tag)} thiếu id")
        if not _ID.fullmatch(i):
            raise _fail(f"id không hợp lệ: {i!r} (cần khớp {_ID.pattern})")
        if el.tag in _NODES and i in RESERVED_IDS:
            raise _fail(f"id {i!r} dành riêng cho lõi")
        if el.tag == TASK and i == "creator":
            raise _fail("userTask không được tên 'creator' (dành cho not_same_actor:creator)")


def _task_role(el, app_id: str) -> str:
    m = re.fullmatch(rf"app:{re.escape(app_id)}:({_ROLE})", el.get(CANDIDATE_GROUPS) or "")
    if not m:
        raise _fail(f"userTask {el.get('id')!r}: flowable:candidateGroups phải là đúng một nhóm "
                    f"app:{app_id}:<role>")
    return m.group(1)


# ---------- Bước 3: đồ thị (luật 7, T3-d) ----------

def _check_graph(kinds: dict[str, str], flows: list[tuple[str, str, str, str | None]]) -> None:
    """``kinds``: id nút → tag; ``flows``: (id flow, nguồn, đích, decision|None)."""
    starts = [n for n, k in kinds.items() if k == START]
    if len(starts) != 1:
        raise _fail(f"cần đúng một startEvent, có {len(starts)}")
    if END not in kinds.values():
        raise _fail("cần ít nhất một endEvent")
    out: dict[str, list[tuple[str, str, str | None]]] = {n: [] for n in kinds}
    inc: dict[str, list[str]] = {n: [] for n in kinds}
    for fid, src, dst, dec in flows:
        for ref in (src, dst):
            if ref not in kinds:
                raise _fail(f"sequenceFlow {fid!r} trỏ tới phần tử không tồn tại: {ref!r}")
        out[src].append((fid, dst, dec))
        inc[dst].append(src)
    start = starts[0]
    if inc[start]:
        raise _fail("startEvent không được có flow vào")
    if len(out[start]) != 1 or kinds[out[start][0][1]] != TASK:
        raise _fail("startEvent phải có đúng một flow ra, tới một userTask")
    for n, k in kinds.items():
        if k == END and out[n]:
            raise _fail(f"endEvent {n!r} không được có flow ra")
    for fid, src, _dst, dec in flows:
        if dec is not None and kinds[src] != GATEWAY:
            raise _fail(f"sequenceFlow {fid!r}: điều kiện chỉ được đặt trên flow ra khỏi cổng")
        if dec is None and kinds[src] == GATEWAY:
            raise _fail(f"sequenceFlow {fid!r} ra khỏi cổng phải có điều kiện decision")
    for n, k in kinds.items():
        if k != TASK:
            continue
        if len(out[n]) != 1:
            raise _fail(f"userTask {n!r} phải có đúng một flow ra")
        if kinds[out[n][0][1]] not in (END, GATEWAY):
            raise _fail(f"userTask {n!r} phải dẫn tới endEvent hoặc cổng")
    for n, k in kinds.items():
        if k != GATEWAY:
            continue
        if not inc[n] or not out[n]:
            raise _fail(f"cổng {n!r} phải có ít nhất một flow vào và một flow ra")
        decisions: set[str] = set()
        for _fid, dst, dec in out[n]:
            if dec in decisions:
                raise _fail(f"cổng {n!r}: giá trị decision trùng: {dec!r}")
            decisions.add(dec)
            if kinds[dst] not in (TASK, END):
                raise _fail(f"cổng {n!r} chỉ được dẫn tới userTask hoặc endEvent, không tới {dst!r}")
    succ = {n: [dst for _f, dst, _d in out[n]] for n in kinds}
    for n, k in kinds.items():
        if k == TASK and not any(kinds[x] == END for x in _reachable(n, succ)):
            raise _fail(f"từ userTask {n!r} không tới được endEvent nào")
    seen = _reachable(start, succ)
    for n in kinds:
        if n not in seen:
            raise _fail(f"{n!r} không tới được từ startEvent")


def _reachable(start: str, succ: dict[str, list[str]]) -> set[str]:
    seen, todo = {start}, deque([start])
    while todo:
        for nxt in succ[todo.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


# ---------- API ----------

def parse_bpmn(xml: bytes, *, app_id: str, seal_end: str | None) -> ProcessModel:
    """Kiểm BPMN theo danh sách cho phép, rút ra ``ProcessModel``; lỗi → ``ManifestError("BPMN_INVALID")``."""
    if not isinstance(xml, bytes | bytearray):
        raise _fail("BPMN phải là bytes")
    if len(xml) > MAX_BPMN_BYTES:
        raise _fail(f"BPMN vượt quá {MAX_BPMN_BYTES} byte")
    root, xsi_types = _read_xml(bytes(xml))
    _check_tree(root, None, xsi_types)
    proc, pid = _check_process(root, app_id)
    _check_ids(root, proc)

    kinds: dict[str, str] = {}
    roles: dict[str, str] = {}
    flows: list[tuple[str, str, str, str | None]] = []
    for el in proc:
        if el.tag == FLOW:
            src, dst = el.get("sourceRef"), el.get("targetRef")
            if not src or not dst:
                raise _fail(f"sequenceFlow {el.get('id')!r} thiếu sourceRef hoặc targetRef")
            cond = el.find(COND)
            dec = _CONDITION.fullmatch(cond.text).group(1) if cond is not None else None
            flows.append((el.get("id"), src, dst, dec))
        else:
            kinds[el.get("id")] = el.tag
            if el.tag == TASK:
                roles[el.get("id")] = _task_role(el, app_id)
    _check_graph(kinds, flows)

    ends = frozenset(n for n, k in kinds.items() if k == END)
    if seal_end is not None and seal_end not in ends:
        raise _fail(f"end event niêm phong {seal_end!r} không có trong BPMN")
    nxt = {src: dst for _f, src, dst, _d in flows if kinds[src] == TASK}
    gate_out: dict[str, list[tuple[str, str]]] = {}
    for _f, src, dst, dec in flows:
        if kinds[src] == GATEWAY:
            gate_out.setdefault(src, []).append((dst, dec))
    decisions: dict[str, frozenset[str]] = {}
    seal: set[str] = set()
    for t in roles:
        target = nxt[t]
        if kinds[target] == END:
            decisions[t] = frozenset()
            reach = {target}
        else:
            decisions[t] = frozenset(dec for _dst, dec in gate_out[target])
            reach = {dst for dst, _dec in gate_out[target]}
        if seal_end is not None and seal_end in reach:
            seal.add(t)
    return ProcessModel(
        process_key=pid,
        user_tasks=roles,
        end_events=ends,
        decisions_by_task=decisions,
        seal_tasks=frozenset(seal),
        flows=tuple(sorted(((s, d, dec) for _f, s, d, dec in flows), key=lambda f: (f[0], f[1], f[2] or ""))),
    )


def check_against_manifest(xml: bytes, m: Manifest) -> ProcessModel:
    """``parse_bpmn`` rồi đối chiếu: tập userTask = ``workflow.tasks``, role khớp, không task ``creator``."""
    if m.workflow is None:
        raise _fail("manifest không có workflow")
    tasks = m.workflow.tasks
    if "creator" in tasks:
        raise _fail("task không được tên 'creator' (dành cho not_same_actor:creator)")
    seal_end = m.policies.seal.on_event.removeprefix("process.completed:") if m.policies.seal else None
    pm = parse_bpmn(xml, app_id=m.app.id, seal_end=seal_end)
    if set(pm.user_tasks) != set(tasks):
        raise _fail(f"tập userTask của BPMN {sorted(pm.user_tasks)} khác workflow.tasks {sorted(tasks)}")
    for t, role in pm.user_tasks.items():
        if role != tasks[t].role:
            raise _fail(f"userTask {t!r}: role trong BPMN {role!r} khác manifest {tasks[t].role!r}")
    return pm


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def render_bpmn(model: ProcessModel) -> bytes:
    """Dựng BPMN chuẩn từ model: chỉ phần tử/thuộc tính ở luật 3–6, không ``name``, không ``bpmndi``.

    Ổn định: cùng model → cùng bytes (sha256 của bản này được ghi khi cài). Trước khi trả, bản dựng được
    kiểm lại bằng ``parse_bpmn`` và phải ra đúng model: XML chưa qua bộ kiểm không bao giờ tới Flowable.
    """
    app_id, sep, _ = model.process_key.rpartition(".")
    if not sep:
        raise _fail(f"process_key {model.process_key!r} phải có dạng '<app_id>.<tên>'")
    nodes = {n for s, d, _dec in model.flows for n in (s, d)} | set(model.user_tasks) | set(model.end_events)
    targets = {d for _s, d, _dec in model.flows}
    starts = sorted(n for n in nodes - set(model.user_tasks) - model.end_events if n not in targets)
    gateways = sorted(nodes - set(model.user_tasks) - model.end_events - set(starts))
    prefix = "f"
    while any(f"{prefix}{i}" in nodes for i in range(1, len(model.flows) + 1)):
        prefix += "_"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<definitions xmlns="{BPMN}" xmlns:flowable="{FLOWABLE}" xmlns:xsi="{XSI}" '
        f'targetNamespace="{_TARGET_NAMESPACE}">',
        f'  <process id="{_attr(model.process_key)}" isExecutable="true">',
    ]
    lines += [f'    <startEvent id="{_attr(n)}"/>' for n in starts]
    lines += [f'    <userTask id="{_attr(t)}" flowable:candidateGroups="{_attr(f"app:{app_id}:{role}")}"/>'
              for t, role in sorted(model.user_tasks.items())]
    lines += [f'    <exclusiveGateway id="{_attr(g)}"/>' for g in gateways]
    lines += [f'    <endEvent id="{_attr(e)}"/>' for e in sorted(model.end_events)]
    for i, (src, dst, dec) in enumerate(model.flows, start=1):
        head = f'    <sequenceFlow id="{prefix}{i}" sourceRef="{_attr(src)}" targetRef="{_attr(dst)}"'
        if dec is None:
            lines.append(head + "/>")
        else:
            cond = escape(f"${{decision == '{dec}'}}")
            lines.append(head + f'><conditionExpression xsi:type="tFormalExpression">{cond}'
                                "</conditionExpression></sequenceFlow>")
    lines += ["  </process>", "</definitions>", ""]
    out = "\n".join(lines).encode("utf-8")

    reparsed = parse_bpmn(out, app_id=app_id, seal_end=None)
    if replace(reparsed, seal_tasks=model.seal_tasks) != model:
        raise _fail("ProcessModel không nhất quán: bản dựng lại không cho ra đúng model")
    return out
