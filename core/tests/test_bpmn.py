# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test bộ kiểm BPMN danh sách cho phép và bản dựng lại chuẩn (Plan 02 Task 3, P2-D2)."""

import dataclasses
import re
from pathlib import Path

import pytest
from dxos_core.registry.bpmn import (
    MAX_BPMN_BYTES,
    ProcessModel,
    check_against_manifest,
    parse_bpmn,
    render_bpmn,
)
from dxos_core.registry.validator import ManifestError, validate_manifest
from helpers.manifests import load

FIX = Path(__file__).resolve().parent / "fixtures"
GOOD = (FIX / "bpmn/test-review.bpmn").read_bytes()
GOOD_TEXT = GOOD.decode("utf-8")
PATH = "/workflow/bpmn"


def variant(*pairs: tuple[str, str]) -> bytes:
    """GOOD với từng cặp (cũ, mới) được thay; mỗi chuỗi cũ phải có trong GOOD."""
    text = GOOD_TEXT
    for old, new in pairs:
        assert old in text, old
        text = text.replace(old, new)
    return text.encode("utf-8")


def rejects(xml: bytes, *, app_id: str = "test-flow", seal_end: str | None = "approved") -> ManifestError:
    with pytest.raises(ManifestError) as e:
        parse_bpmn(xml, app_id=app_id, seal_end=seal_end)
    assert e.value.code == "BPMN_INVALID"
    assert e.value.path == PATH
    return e.value


# ---------- Các test do Plan 02 Task 3 quy định ----------

def test_parses_good_model():
    pm = parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")
    assert pm.process_key == "test-flow.review"
    assert pm.user_tasks == {"review": "reviewer", "approve": "approver"}
    assert pm.end_events == {"approved", "rejected"}
    assert pm.decisions_by_task == {"review": {"approve", "reject"}, "approve": {"approve", "reject"}}
    assert pm.seal_tasks == {"approve"}


BAD = ["script-task", "service-task", "flowable-class", "flowable-expression", "delegate-expression",
       "execution-listener", "task-listener", "timer", "call-activity", "extension-elements", "documentation",
       "name-expression", "hash-expression", "condition-method-call", "condition-bean", "condition-language",
       "dtd-entity", "two-processes", "wrong-prefix", "other-app-group", "assignee-attr", "dangling-flow",
       "no-start", "unconditioned-gateway-flow", "task-named-creator", "reserved-end-name"]


@pytest.mark.parametrize("name", BAD)
def test_rejects_dangerous_bpmn(name):
    with pytest.raises(ManifestError) as e:
        parse_bpmn((FIX / f"bpmn/bad/{name}.bpmn").read_bytes(), app_id="test-flow", seal_end="approved")
    assert e.value.code == "BPMN_INVALID"


def test_bad_fixtures_all_listed():
    assert {p.stem for p in (FIX / "bpmn/bad").glob("*.bpmn")} == set(BAD)


def test_billion_laughs_never_expands():
    xml = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">]><definitions>&a;</definitions>'
    with pytest.raises(ManifestError):
        parse_bpmn(xml, app_id="test-flow", seal_end=None)


def test_render_is_stable_and_reparses_to_same_model():
    pm = parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")
    out = render_bpmn(pm)
    assert out == render_bpmn(pm) and b"bpmndi" not in out
    assert parse_bpmn(out, app_id="test-flow", seal_end="approved") == pm


def test_manifest_and_bpmn_must_agree():
    check_against_manifest(GOOD, validate_manifest(load("test-flow")))
    doc = load("test-flow"); doc["workflow"]["tasks"]["extra"] = {"role": "reviewer"}  # noqa: E702 (như plan)
    with pytest.raises(ManifestError):
        check_against_manifest(GOOD, validate_manifest(doc))


# ---------- Mỗi tệp bad/ = GOOD cộng đúng một lỗi, và bị từ chối vì đúng lỗi đó ----------

R = '<userTask id="review" name="Xem xét" flowable:candidateGroups="app:test-flow:reviewer"/>'
A = '<userTask id="approve" name="Phê duyệt" flowable:candidateGroups="app:test-flow:approver"/>'
S = '<startEvent id="start" name="Bắt đầu"/>'
COND_OK = ('<sequenceFlow id="f_review_ok" sourceRef="gw_review" targetRef="approve">\n'
           '      <conditionExpression xsi:type="tFormalExpression">')
REVIEW_OK = COND_OK + "${decision == 'approve'}"
REVIEW_NO = ('<sequenceFlow id="f_review_no" sourceRef="gw_review" targetRef="rejected">\n'
             '      <conditionExpression xsi:type="tFormalExpression">${decision == \'reject\'}')
GA_REJ = 'sourceRef="gw_approve" targetRef="rejected"'
START_FLOW = '<sequenceFlow id="f_start" sourceRef="start" targetRef="review"/>'
END_P = "  </process>"
MODEL = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def with_attr(tag: str, attr: str) -> str:
    return tag[:-2] + " " + attr + "/>"


def with_child(tag: str, child: str, name: str) -> str:
    return tag[:-2] + ">" + child + f"</{name}>"


# tên -> (các cặp thay thế áp lên GOOD, các mảnh phải có trong thông điệp lỗi)
DEFECTS: dict[str, tuple[list[tuple[str, str]], tuple[str, ...]]] = {
    "script-task": ([(R, '<scriptTask id="review" name="Xem xét" scriptFormat="groovy">'
                         '<script>java.lang.Runtime.getRuntime().exec("id")</script></scriptTask>')],
                    ("scriptTask",)),
    "service-task": ([(R, '<serviceTask id="review" name="Xem xét" flowable:class="org.example.Evil"/>')],
                     ("serviceTask",)),
    "flowable-class": ([(R, with_attr(R, 'flowable:class="org.example.Evil"'))], ("flowable:class",)),
    "flowable-expression": ([(R, with_attr(R, "flowable:expression=\"${runtime.exec('id')}\""))],
                            ("flowable:expression",)),
    "delegate-expression": ([(R, with_attr(R, 'flowable:delegateExpression="${evilDelegate}"'))],
                            ("flowable:delegateExpression",)),
    "execution-listener": ([(R, with_child(R, '<flowable:executionListener event="start" '
                                              'class="org.example.Evil"/>', "userTask"))],
                           ("flowable:executionListener",)),
    "task-listener": ([(A, with_child(A, '<flowable:taskListener event="create" '
                                         'expression="${evil.run(task)}"/>', "userTask"))],
                      ("flowable:taskListener",)),
    "timer": ([(S, with_child(S, "<timerEventDefinition><timeCycle>R/PT1M</timeCycle></timerEventDefinition>",
                              "startEvent"))], ("timerEventDefinition",)),
    "call-activity": ([(A, '<callActivity id="approve" name="Phê duyệt" calledElement="other.process"/>')],
                      ("callActivity",)),
    "extension-elements": ([('isExecutable="true">',
                             'isExecutable="true">\n    <extensionElements><flowable:executionListener '
                             'event="start" class="org.example.Evil"/></extensionElements>')],
                           ("extensionElements",)),
    "documentation": ([(R, with_child(R, "<documentation>${evil.describe(task)}</documentation>",
                                      "userTask"))],
                      ("documentation",)),
    "name-expression": ([('name="Xem xét"', 'name="${evil.name()}"')], ("name", "biểu thức")),
    "hash-expression": ([('name="Đã duyệt"', 'name="#{evil.name()}"')], ("name", "biểu thức")),
    "condition-method-call": ([(REVIEW_OK, COND_OK + "${decision == 'approve' and "
                                                     "''.getClass().forName('java.lang.Runtime') != null}")],
                              ("conditionExpression chỉ được",)),
    "condition-bean": ([(REVIEW_OK, COND_OK + "${reviewService.isApproved(execution)}")],
                       ("conditionExpression chỉ được",)),
    "condition-language": ([(COND_OK, COND_OK.replace('"tFormalExpression">',
                                                      '"tFormalExpression" language="groovy">'))],
                           ("language",)),
    "dtd-entity": ([('<?xml version="1.0" encoding="UTF-8"?>\n',
                     '<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<!DOCTYPE definitions [<!ENTITY who "Xem xét">]>\n'),
                    ('name="Xem xét"', 'name="&who;"')], ("DTD",)),
    "two-processes": ([(END_P + "\n", END_P + '\n  <process id="test-flow.other" isExecutable="true"/>\n')],
                      ("đúng một process",)),
    "wrong-prefix": ([('id="test-flow.review"', 'id="other-app.review"')], ("process id",)),
    "other-app-group": ([("app:test-flow:reviewer", "app:other-app:reviewer")], ("candidateGroups",)),
    "assignee-attr": ([(R, with_attr(R, 'flowable:assignee="admin"'))], ("flowable:assignee",)),
    "dangling-flow": ([(GA_REJ, GA_REJ.replace('"rejected"', '"archived"'))],
                      ("không tồn tại",)),
    "no-start": ([(S + "\n    ", ""), (START_FLOW + "\n    ", "")],
                 ("đúng một startEvent",)),
    "unconditioned-gateway-flow": ([(REVIEW_NO + "</conditionExpression>\n    </sequenceFlow>",
                                     '<sequenceFlow id="f_review_no" sourceRef="gw_review" '
                                     'targetRef="rejected"/>')],
                                   ("phải có điều kiện",)),
    "task-named-creator": ([('"review"', '"creator"')], ("creator",)),
    "reserved-end-name": ([('"rejected"', '"cancelled"')], ("dành riêng",)),
}


def test_defect_table_covers_bad_list():
    assert set(DEFECTS) == set(BAD)


@pytest.mark.parametrize("name", BAD)
def test_bad_fixture_is_good_plus_one_defect(name):
    pairs, _ = DEFECTS[name]
    assert (FIX / f"bpmn/bad/{name}.bpmn").read_bytes() == variant(*pairs)


@pytest.mark.parametrize("name", BAD)
def test_bad_fixture_fails_for_its_own_reason(name):
    err = rejects((FIX / f"bpmn/bad/{name}.bpmn").read_bytes())
    for fragment in DEFECTS[name][1]:
        assert fragment in err.message, (name, err.message)


# ---------- Các luật bổ sung (phán quyết C2, C11, C17, T3-a..f) ----------

def edge(src: str, dst: str) -> str:
    return f'sourceRef="{src}" targetRef="{dst}"'


def retarget(src: str, old: str, new: str) -> tuple[str, str]:
    return edge(src, old), edge(src, new)


def add(xml: str) -> tuple[str, str]:
    """Thêm một phần tử vào cuối process."""
    return END_P, f"  {xml}\n{END_P}"


# khai báo tiền tố m ngay trên conditionExpression đầu tiên; phạm vi của nó dừng ở phần tử đó
LOCAL_M = f'xmlns:m="{MODEL}" xsi:type="m:tFormalExpression"'

VARIANTS = {
    # C17: cổng không có thuộc tính default
    "gateway-default": ([('<exclusiveGateway id="gw_review" name="Kết quả xem xét"/>',
                          '<exclusiveGateway id="gw_review" name="Kết quả xem xét" default="f_review_no"/>')],
                        ("default",)),
    # C11 / T3-c: id
    "end-id-digit": ([('"approved"', '"1approved"')], ("id không hợp lệ",)),
    "end-id-too-long": ([('"approved"', '"' + "a" * 65 + '"')], ("id không hợp lệ",)),
    "task-id-dot": ([('"review"', '"re.view"')], ("id không hợp lệ",)),
    "duplicate-node-id": ([('id="s_start"', 'id="start"')], ("id trùng",)),
    "duplicate-flow-id": ([('id="f_review_no"', 'id="f_review_ok"')], ("id trùng",)),
    "reserved-guard-failed": ([('"approved"', '"guard_failed"')], ("dành riêng",)),
    # T3-b: văn bản
    "text-in-task": ([(R, with_child(R, "hello", "userTask"))], ("văn bản",)),
    "tail-text": ([(S, S + "abc")], ("văn bản",)),
    "text-in-root": ([('targetNamespace="urn:dxos:test">', 'targetNamespace="urn:dxos:test">hello')],
                     ("văn bản",)),
    "text-in-bpmndi": ([('<dc:Bounds x="20" y="102" width="36" height="36"/>',
                         '<dc:Bounds x="20" y="102" width="36" height="36">1</dc:Bounds>')], ("văn bản",)),
    "expr-in-bpmndi": ([('bpmnElement="start"', 'bpmnElement="${evil}"')], ("biểu thức",)),
    "expr-in-target-namespace": ([('targetNamespace="urn:dxos:test"', 'targetNamespace="#{evil}"')],
                                 ("biểu thức",)),
    "expr-in-process-name": ([('name="Xem xét và phê duyệt"', 'name="a ${x} b"')], ("biểu thức",)),
    # T3-a: không gian tên
    "unknown-namespace-element": ([(S, '<x:startEvent xmlns:x="urn:evil" id="start" name="Bắt đầu"/>')],
                                  ("urn:evil",)),
    "qualified-id-attr": ([('<endEvent id="approved"',
                            f'<endEvent xmlns:m="{MODEL}" m:id="x" id="approved"')],
                          ("bpmn:id", "không được phép")),
    "xsi-type-other-ns": ([(COND_OK, COND_OK.replace('xsi:type="tFormalExpression"',
                                                     'xmlns:e="urn:evil" xsi:type="e:tFormalExpression"'))],
                          ("xsi:type",)),
    "xsi-type-undeclared-prefix": ([(COND_OK, COND_OK.replace('"tFormalExpression"',
                                                              '"zz:tFormalExpression"'))],
                                   ("xsi:type",)),
    "xsi-type-prefix-out-of-scope": ([(COND_OK, COND_OK.replace('xsi:type="tFormalExpression"', LOCAL_M)),
                                      (REVIEW_NO, REVIEW_NO.replace('"tFormalExpression"',
                                                                    '"m:tFormalExpression"'))],
                                     ("xsi:type",)),
    "xsi-type-wrong-local": ([(COND_OK, COND_OK.replace('"tFormalExpression"', '"tExpression"'))],
                             ("xsi:type",)),
    "xsi-type-missing": ([(COND_OK, COND_OK.replace(' xsi:type="tFormalExpression"', ""))], ("xsi:type",)),
    "xsi-type-on-task": ([(R, with_attr(R, 'xsi:type="tUserTask"'))], ("xsi:type",)),
    "condition-whitespace-outside": ([(REVIEW_OK, COND_OK + " ${decision == 'approve'}")],
                                     ("conditionExpression chỉ được",)),
    "condition-upper-value": ([(REVIEW_OK, COND_OK + "${decision == 'Approve'}")],
                              ("conditionExpression chỉ được",)),
    "two-conditions": ([(REVIEW_OK + "</conditionExpression>",
                         REVIEW_OK + "</conditionExpression>"
                                     "<conditionExpression xsi:type=\"tFormalExpression\">"
                                     "${decision == 'other'}</conditionExpression>")],
                       ("một conditionExpression",)),
    "incoming-element": ([(R, with_child(R, "<incoming>f_start</incoming>", "userTask"))], ("incoming",)),
    # luật 2, 6
    "not-executable": ([('isExecutable="true"', 'isExecutable="false"')], ("isExecutable",)),
    "process-id-upper": ([('id="test-flow.review"', 'id="test-flow.Review"')], ("process id",)),
    "two-groups": ([('app:test-flow:reviewer"', 'app:test-flow:reviewer,app:test-flow:approver"')],
                   ("candidateGroups",)),
    "no-group": ([(R, '<userTask id="review" name="Xem xét"/>')], ("candidateGroups",)),
    # luật 7 và T3-d: hình dạng đồ thị
    "start-incoming": ([retarget("gw_approve", "rejected", "start")], ("flow vào",)),
    "start-two-out": ([add('<sequenceFlow id="f_start2" sourceRef="start" targetRef="approve"/>')],
                      ("startEvent phải có đúng một flow ra",)),
    "start-to-gateway": ([retarget("start", "review", "gw_review")],
                         ("startEvent phải có đúng một flow ra",)),
    "end-outgoing": ([add('<sequenceFlow id="f_back" sourceRef="approved" targetRef="review"/>')],
                     ("endEvent",)),
    "gateway-isolated": ([add('<exclusiveGateway id="gw_x"/>')], ("ít nhất một flow vào và một flow ra",)),
    "gateway-dup-decision": ([(REVIEW_NO, REVIEW_NO.replace("'reject'", "'approve'"))], ("trùng",)),
    "condition-off-gateway": ([('<sequenceFlow id="f_review" sourceRef="review" targetRef="gw_review"/>',
                                '<sequenceFlow id="f_review" sourceRef="review" targetRef="gw_review">'
                                '<conditionExpression xsi:type="tFormalExpression">${decision == \'approve\'}'
                                "</conditionExpression></sequenceFlow>")], ("điều kiện chỉ",)),
    "gateway-to-gateway": ([retarget("gw_review", "approve", "gw_approve")], ("chỉ được dẫn tới",)),
    "task-two-out": ([add('<sequenceFlow id="f_review2" sourceRef="review" targetRef="rejected"/>')],
                     ("đúng một flow ra",)),
    "task-to-task": ([retarget("review", "gw_review", "approve")], ("endEvent hoặc cổng",)),
    "no-exit-loop": ([retarget("gw_review", "rejected", "approve"),
                      retarget("gw_approve", "approved", "review"),
                      retarget("gw_approve", "rejected", "review")], ("không tới được endEvent",)),
    "unreachable-task": ([add('<userTask id="orphan" flowable:candidateGroups="app:test-flow:reviewer"/>'),
                          add('<sequenceFlow id="f_orphan" sourceRef="orphan" targetRef="approved"/>')],
                         ("không tới được từ startEvent",)),
    "no-end": ([('<endEvent id="approved" name="Đã duyệt"/>',
                 '<userTask id="approved" flowable:candidateGroups="app:test-flow:approver"/>'),
                ('<endEvent id="rejected" name="Từ chối"/>',
                 '<userTask id="rejected" flowable:candidateGroups="app:test-flow:approver"/>')],
               ("ít nhất một endEvent",)),
}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_rejects_variant_for_its_reason(name):
    pairs, fragments = VARIANTS[name]
    err = rejects(variant(*pairs))
    for fragment in fragments:
        assert fragment in err.message, (name, err.message)


def test_seal_end_must_exist():
    assert "niêm phong" in rejects(GOOD, seal_end="archived").message


def test_without_seal_end_no_seal_tasks():
    assert parse_bpmn(GOOD, app_id="test-flow", seal_end=None).seal_tasks == frozenset()


def test_other_app_id_rejects_good():
    assert "process id" in rejects(GOOD, app_id="other-app").message


def test_loop_back_to_earlier_task_is_allowed():
    xml = variant(retarget("gw_approve", "rejected", "review"))
    pm = parse_bpmn(xml, app_id="test-flow", seal_end="approved")
    assert ("gw_approve", "review", "reject") in pm.flows
    assert pm.seal_tasks == {"approve"}


def test_task_straight_to_end_accepts_any_decision():
    xml = variant(('sourceRef="approve" targetRef="gw_approve"', 'sourceRef="approve" targetRef="approved"'),
                  ('<exclusiveGateway id="gw_approve" name="Kết quả phê duyệt"/>', ""),
                  ('<sequenceFlow id="f_approve_ok" sourceRef="gw_approve" targetRef="approved">\n'
                   "      <conditionExpression xsi:type=\"tFormalExpression\">${decision == 'approve'}"
                   "</conditionExpression>\n    </sequenceFlow>", ""),
                  ('<sequenceFlow id="f_approve_no" sourceRef="gw_approve" targetRef="rejected">\n'
                   "      <conditionExpression xsi:type=\"tFormalExpression\">${decision == 'reject'}"
                   "</conditionExpression>\n    </sequenceFlow>", ""))
    pm = parse_bpmn(xml, app_id="test-flow", seal_end="approved")
    assert pm.decisions_by_task["approve"] == frozenset()
    assert pm.seal_tasks == {"approve"}


def test_xsi_type_prefix_declared_on_the_element_itself():
    xml = variant((COND_OK, COND_OK.replace('xsi:type="tFormalExpression"', LOCAL_M)))
    assert parse_bpmn(xml, app_id="test-flow", seal_end="approved") == parse_bpmn(
        GOOD, app_id="test-flow", seal_end="approved")


def test_prefixes_do_not_matter_only_namespaces():
    names = ("definitions|process|startEvent|endEvent|userTask|exclusiveGateway"
             "|sequenceFlow|conditionExpression")
    text = re.sub(rf"<(/?)({names})\b", r"<\1m:\2", GOOD_TEXT)
    text = text.replace(f'xmlns="{MODEL}"', f'xmlns:m="{MODEL}"')
    text = text.replace('xsi:type="tFormalExpression"', 'xsi:type="m:tFormalExpression"')
    text = text.replace("xmlns:flowable=", "xmlns:fl=")
    text = text.replace("flowable:candidateGroups", "fl:candidateGroups")
    assert "<m:userTask" in text and "fl:candidateGroups" in text
    pm = parse_bpmn(text.encode(), app_id="test-flow", seal_end="approved")
    assert pm == parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")


# ---------- T3-f: lỗi XML, kích thước ----------

def test_size_limit_exact_ok_and_one_byte_over_rejected():
    padded = GOOD + b" " * (MAX_BPMN_BYTES - len(GOOD))
    assert len(padded) == MAX_BPMN_BYTES
    parse_bpmn(padded, app_id="test-flow", seal_end="approved")
    assert "vượt quá" in rejects(padded + b" ").message


@pytest.mark.parametrize("xml", [
    b"", b"<definitions", b"not xml", b"\xff\xfe\x00<",
    b'<?xml version="1.0" encoding="no-such-codec"?><definitions/>',
    b'<?xml version="1.0"?><!DOCTYPE d SYSTEM "http://127.0.0.1:1/x.dtd"><definitions/>',
    b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "x"><!ENTITY b "&a;&a;">]><definitions>&b;</definitions>',
])
def test_xml_errors_are_bpmn_invalid(xml):
    rejects(xml, seal_end=None)


def test_root_must_be_definitions():
    xml = f'<process xmlns="{MODEL}" id="test-flow.review" isExecutable="true"/>'.encode()
    assert "definitions" in rejects(xml, seal_end=None).message


def test_input_must_be_bytes():
    rejects(GOOD_TEXT)  # type: ignore[arg-type]


# ---------- render_bpmn ----------

def test_render_shape():
    out = render_bpmn(parse_bpmn(GOOD, app_id="test-flow", seal_end="approved"))
    assert out.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n')
    assert b' name="' not in out and b"bpmndi" not in out
    assert b'<process id="test-flow.review" isExecutable="true">' in out
    assert b'flowable:candidateGroups="app:test-flow:reviewer"' in out
    assert (b"<conditionExpression xsi:type=\"tFormalExpression\">${decision == 'approve'}"
            b"</conditionExpression>") in out
    assert out.count(b"<sequenceFlow ") == 7
    assert b'<sequenceFlow id="f1" ' in out and b'<sequenceFlow id="f7" ' in out


def test_render_ignores_document_order_and_original_flow_ids():
    shuffled = variant(('id="f_review_ok"', 'id="zz1"'), ('id="f_start"', 'id="aa9"'),
                       ('    <endEvent id="approved" name="Đã duyệt"/>\n', ""),
                       ('    <endEvent id="rejected" name="Từ chối"/>\n', ""),
                       (S, '<endEvent id="rejected"/><endEvent id="approved"/>' + S))
    pm = parse_bpmn(shuffled, app_id="test-flow", seal_end="approved")
    assert pm == parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")
    assert render_bpmn(pm) == render_bpmn(parse_bpmn(GOOD, app_id="test-flow", seal_end="approved"))


def test_render_flow_ids_never_collide_with_node_ids():
    xml = variant(('"review"', '"f1"'), ('"approve"', '"f2"'))
    pm = parse_bpmn(xml, app_id="test-flow", seal_end="approved")
    out = render_bpmn(pm)
    assert parse_bpmn(out, app_id="test-flow", seal_end="approved") == pm


def test_flows_are_sorted():
    pm = parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")
    assert list(pm.flows) == sorted(pm.flows, key=lambda f: (f[0], f[1], f[2] or ""))


@pytest.mark.parametrize("change", [
    {"user_tasks": {"review": "Bad Role", "approve": "approver"}},
    {"process_key": "test-flow.review\"><scriptTask id=\"x"},
    {"decisions_by_task": {"review": frozenset({"approve"}), "approve": frozenset({"approve", "reject"})}},
    {"end_events": frozenset({"approved", "rejected", "extra"})},
    {"flows": (("start", "review", "${x}"),)},
])
def test_render_refuses_inconsistent_model(change):
    pm = dataclasses.replace(parse_bpmn(GOOD, app_id="test-flow", seal_end="approved"), **change)
    with pytest.raises(ManifestError) as e:
        render_bpmn(pm)
    assert e.value.code == "BPMN_INVALID"


def test_process_model_is_frozen():
    pm = parse_bpmn(GOOD, app_id="test-flow", seal_end="approved")
    assert isinstance(pm, ProcessModel)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pm.process_key = "x"  # type: ignore[misc]


# ---------- check_against_manifest ----------

def test_check_against_manifest_returns_model_with_seal_from_policy():
    pm = check_against_manifest(GOOD, validate_manifest(load("test-flow")))
    assert pm.seal_tasks == {"approve"} and pm.process_key == "test-flow.review"


def test_check_against_manifest_role_mismatch():
    doc = load("test-flow"); doc["workflow"]["tasks"]["review"]["role"] = "approver"  # noqa: E702
    with pytest.raises(ManifestError) as e:
        check_against_manifest(GOOD, validate_manifest(doc))
    assert e.value.code == "BPMN_INVALID" and e.value.path == PATH and "role" in e.value.message


def test_check_against_manifest_missing_task():
    doc = load("test-flow")
    del doc["workflow"]["tasks"]["approve"]
    with pytest.raises(ManifestError) as e:
        check_against_manifest(GOOD, validate_manifest(doc))
    assert e.value.code == "BPMN_INVALID" and "workflow.tasks" in e.value.message


def test_check_against_manifest_seal_end_from_on_event():
    doc = load("test-flow"); doc["policies"]["seal"]["on_event"] = "process.completed:archived"  # noqa: E702
    with pytest.raises(ManifestError) as e:
        check_against_manifest(GOOD, validate_manifest(doc))
    assert "niêm phong" in e.value.message


def test_check_against_manifest_without_seal_policy():
    doc = load("test-flow"); del doc["policies"]["seal"]  # noqa: E702
    assert check_against_manifest(GOOD, validate_manifest(doc)).seal_tasks == frozenset()


def test_check_against_manifest_needs_workflow():
    m = validate_manifest(load("test-flow"))
    m = m.model_copy(update={"workflow": None})
    with pytest.raises(ManifestError) as e:
        check_against_manifest(GOOD, m)
    assert e.value.code == "BPMN_INVALID"


def test_check_against_manifest_refuses_creator_task_itself():
    m = validate_manifest(load("test-flow"))
    tasks = dict(m.workflow.tasks)
    tasks["creator"] = tasks.pop("review")
    m = m.model_copy(update={"workflow": m.workflow.model_copy(update={"tasks": tasks})})
    with pytest.raises(ManifestError) as e:
        check_against_manifest(variant(('"review"', '"creator"')), m)
    assert e.value.code == "BPMN_INVALID" and "creator" in e.value.message
