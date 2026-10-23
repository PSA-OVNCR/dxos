# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test bộ dò PII trên văn bản có toạ độ (Plan 04 Task 3, S1).

Mọi số CCCD, số điện thoại, số tài khoản trong file này đều là HƯ CẤU (không thuộc ai).
"""

import dataclasses
import unicodedata

import pytest
from dxos_core.pii import Box, Finding, detect_text

ALL = {"CCCD", "PHONE", "BANK_ACCOUNT"}
W, H = 6.0, 12.0  # bề rộng ký tự, chiều cao dòng (PDF point)


def layout(text: str, page: int = 1, page_of=None) -> list[Box | None]:
    """Xếp chữ lên trang: mỗi ký tự một hộp; ký tự xuống dòng là ký tự PDFium sinh thêm (None)."""
    boxes: list[Box | None] = []
    x, line = 0, 0
    for i, ch in enumerate(text):
        if ch in "\r\n":
            boxes.append(None)
            if ch == "\n":
                x, line = 0, line + 1
            continue
        top = 800.0 - line * (H + 3)
        pg = page_of(i) if page_of else page
        boxes.append(Box(pg, 50.0 + x * W, top - H, 50.0 + (x + 1) * W, top))
        x += 1
    return boxes


def run(text: str, types=ALL, **kw) -> list[Finding]:
    return detect_text(text, layout(text, **kw), types)


def covered(f: Finding, box: Box) -> bool:
    return any(
        b.page == box.page and b.left <= box.left and b.bottom <= box.bottom
        and b.right >= box.right and b.top >= box.top for b in f.boxes)


@pytest.mark.parametrize("text", [
    "CCCD: 079203012345",
    "079 203 012 345",
    "079.203.012.345",
    "０７９２０３０１２３４５",  # toàn chiều rộng: NFKC chỉ để so khớp
    "079-203-012-345",
    "079203 012345",
])
def test_cccd_forms(text):
    found = run(text)
    assert [f.type for f in found] == ["CCCD"]
    assert found[0].page == 1


def test_cccd_boxes_cover_every_digit_and_stay_on_one_line():
    text = "CCCD: 079 203 012 345."
    (f,) = run(text)
    assert len(f.boxes) == 1
    first = text.index("0")
    last = text.rindex("5")
    boxes = layout(text)
    for i in range(first, last + 1):
        assert covered(f, boxes[i])
    assert not covered(f, boxes[0])  # chữ "CCCD" không bị che
    assert not covered(f, boxes[-1])  # dấu chấm cuối câu không bị che


@pytest.mark.parametrize("text", [
    "099203012345",  # mã tỉnh 099 >= 097 không hợp lệ
    "79203012345",  # 11 số
    "0792030123456",  # 13 số
    "0312345678-001",  # mã số thuế
    "A079203012345",  # chữ cái liền trước
    "079203012345B",  # chữ cái liền sau
    "000203012345",  # mã tỉnh 000
])
def test_cccd_rejects_bad_province_and_length(text):
    assert run(text) == []


@pytest.mark.parametrize("text", [
    "0912345678", "0912-345-678", "+84 912 345 678", "(+84) 912.345.678", "SĐT: 0987 654 321",
    "0356789012", "0501234567", "0701234567", "0812345678",
])
def test_phone_forms(text):
    found = run(text)
    assert [f.type for f in found] == ["PHONE"]


@pytest.mark.parametrize("text", [
    "0212345678",  # 02x là điện thoại bàn cố định: ngoài phạm vi (giới hạn đã biết)
    "0112345678", "0412345678", "0612345678",
    "091234567",  # 9 số
    "09123456789",  # 11 số
    "+84 212 345 678",
    "0312345678-001",  # mã số thuế không bị nhận là điện thoại
])
def test_phone_rejects(text):
    assert run(text) == []


def test_phone_country_code_box_includes_prefix():
    text = "ĐT (+84) 912.345.678 nhé"
    (f,) = run(text)
    boxes = layout(text)
    for i in range(text.index("("), text.index("8", text.index(")") + 1) + 12):
        if text[i] in "(+)84 912.345.678"[:0] or i > text.index("8", 12):
            break
    assert covered(f, boxes[text.index("(")])
    assert covered(f, boxes[text.index("+")])
    assert covered(f, boxes[text.rindex("8")])
    assert not covered(f, boxes[-1])


@pytest.mark.parametrize("text", [
    "STK: 1234 5678 9012",
    "Số tài khoản 0123456789012",
    "SỐ TÀI KHOẢN: 12345678",  # 8 số, hoa thường không phân biệt
    "Tài khoản ngân hàng: 1234567890123456789",  # 19 số
    "stk 1234.5678.9012",
    unicodedata.normalize("NFD", "Số tài khoản 0123456789012"),  # dấu rời
    "So tai khoan\n0123456789",
])
def test_bank_account_with_keyword(text):
    found = run(text)
    assert [f.type for f in found] == ["BANK_ACCOUNT"]


@pytest.mark.parametrize("text", [
    "Mã hợp đồng 1234567890",
    "1234 5678 9012",
    "STK: 1234567",  # 7 số
    "STK: 12345678901234567890",  # 20 số
    "STK" + " " * 31 + "1234567890123",  # từ khóa cách số quá 30 ký tự
    "STK: abc1234567890",  # chữ liền trước
])
def test_bank_account_needs_keyword(text):
    assert run(text) == []


def test_bank_account_keyword_distance_boundary():
    # khoảng cách tính từ cuối từ khóa đến đầu số: đúng 30 thì còn nhận, 31 thì không
    assert [f.type for f in run("STK" + " " * 30 + "1234567890123")] == ["BANK_ACCOUNT"]
    assert run("STK" + " " * 31 + "1234567890123") == []


def test_keyword_makes_it_bank_account_but_cccd_still_found_when_only_cccd_requested():
    assert [f.type for f in run("STK: 079203012345")] == ["BANK_ACCOUNT"]
    assert [f.type for f in run("STK: 079203012345", types={"CCCD"})] == ["CCCD"]


def test_number_split_across_lines_is_found_once():
    for text in ("079 203\n012 345", "079 203\r\n012 345"):
        found = run(text)
        assert len(found) == 1 and found[0].type == "CCCD"
        assert len(found[0].boxes) == 2
        top_box, bottom_box = found[0].boxes
        assert top_box.bottom > bottom_box.bottom
        boxes = layout(text)
        for i in range(len(text)):
            if boxes[i] is not None:
                assert covered(found[0], boxes[i])


def test_adjacent_numbers_in_a_table_are_both_found():
    text = "079203012345\n0912345678\nSTK: 12345678901"
    assert [f.type for f in run(text)] == ["CCCD", "PHONE", "BANK_ACCOUNT"]
    assert [f.type for f in run("079203012345\n0912345678", types={"PHONE"})] == ["PHONE"]
    assert run("079203012345\n0912345678\n5") == []  # còn dư số lạ thì không đoán


def test_separator_is_one_character_at_most():
    assert run("079  203 012 345") == []
    assert run("079 . 203 012 345") == []


def test_only_requested_types():
    text = "CCCD 079203012345, ĐT 0912345678, STK 1234567890"
    assert [f.type for f in run(text)] == ["CCCD", "PHONE", "BANK_ACCOUNT"]
    assert [f.type for f in run(text, types={"PHONE"})] == ["PHONE"]
    assert run(text, types=set()) == []


def test_unknown_type_rejected():
    with pytest.raises(ValueError, match="EMAIL"):
        run("x", types={"EMAIL"})


def test_finding_has_no_value():
    text = "CCCD: 079203012345 ĐT 0912345678"
    for f in run(text):
        d = dataclasses.asdict(f)
        assert set(d) == {"type", "page", "boxes"}
        blob = repr(d) + repr(f) + str(f)
        for digits in ("079203012345", "0912345678", "079", "0912"):
            assert digits not in blob


def test_length_mismatch_error_has_no_digits():
    with pytest.raises(ValueError) as e:
        detect_text("079203012345", [None] * 3, ALL)
    assert "079203012345" not in str(e.value)
    assert str(e.value) == "text has 12 characters but char_boxes has 3 entries"


def test_page_is_copied_from_boxes_one_based():
    (f,) = run("079203012345", page=3)
    assert f.page == 3 and all(b.page == 3 for b in f.boxes)


def test_number_across_two_pages_is_split_per_page_and_fully_covered():
    text = "079 203\n012 345"
    boxes = layout(text, page_of=lambda i: 1 if i < 8 else 2)
    found = detect_text(text, boxes, ALL)
    assert [(f.type, f.page) for f in found] == [("CCCD", 1), ("CCCD", 2)]
    for f in found:
        assert all(b.page == f.page for b in f.boxes)
    for box in boxes:
        if box is not None:
            assert any(covered(f, box) for f in found if f.page == box.page)


def test_generated_characters_without_box_are_skipped_but_may_separate():
    text = "079 203\n012 345"
    boxes = layout(text)
    assert boxes[7] is None
    (f,) = detect_text(text, boxes, ALL)
    assert all(b is not None for b in f.boxes)


def test_digits_without_any_box_are_not_reported():
    assert detect_text("079203012345", [None] * 12, ALL) == []


def test_empty_and_noise():
    assert detect_text("", [], ALL) == []
    assert run("Biên bản họp ngày 12.03.2026, số 45/QĐ-UBND, giá 1.000.000.000 đồng") == []


def test_results_follow_text_order():
    text = "ĐT 0912345678 và CCCD 079203012345"
    assert [f.type for f in run(text)] == ["PHONE", "CCCD"]


def test_long_digit_run_does_not_blow_up():
    text = "\n".join(["079203012345"] * 300)
    assert len(run(text)) == 300
    assert run("1" * 5000) == []
