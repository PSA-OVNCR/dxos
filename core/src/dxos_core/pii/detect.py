# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dò PII trên văn bản kèm toạ độ từng ký tự (S1 "PII trong tài liệu").

Hàm thuần: không I/O, không ghi log. Kết quả ``Finding`` chỉ có loại, trang và các hộp; giá trị số
(và băm của nó) không bao giờ nằm trong kết quả, trong thông báo lỗi hay trong ``repr`` (I5, P4-D2).

Quy ước toạ độ: ``Box`` tính bằng PDF point, gốc ở góc dưới-trái của trang. ``Box.page`` và
``Finding.page`` là số trang **bắt đầu từ 1** ("trang 1"); bộ dò chỉ chép số trang từ các hộp được
đưa vào, không tự đánh số.

Loại và quy tắc (đều là heuristic để gợi ý che, không phải kiểm tra pháp lý):

* ``CCCD``: đúng 12 chữ số, 3 số đầu (mã tỉnh) trong ``001``-``096``. Phạm vi này lấy theo yêu cầu
  của Plan 04 Task 3, tham chiếu Thông tư 07/2016/TT-BCA (quy định về số định danh cá nhân 12 số, 3
  số đầu là mã tỉnh/thành hoặc nơi đăng ký khai sinh). Danh sách mã thật là một tập con không liên
  tục của ``001``-``096``; ở đây dùng cả khoảng nên có thể nhận thừa (an toàn hơn cho việc che),
  không bỏ sót mã hợp lệ. [ĐX] Chưa đối chiếu từng mã với văn bản gốc trong phiên này.
* ``PHONE``: di động Việt Nam, 10 số dạng ``0`` + ``3|5|7|8|9`` + 8 số, hoặc ``+84``/``(+84)`` + 9
  số bắt đầu ``3|5|7|8|9``. **Giới hạn đã biết**: đầu số ``02x`` (điện thoại bàn) và ``84`` không có
  dấu ``+`` nằm ngoài phạm vi.
* ``BANK_ACCOUNT``: 8-19 chữ số và phải có từ khoá ``stk``, ``so tai khoan`` hoặc ``tai khoan`` (bỏ
  dấu, không phân biệt hoa thường) đứng trước, cách đầu số không quá 30 ký tự (tính từ cuối từ
  khoá).

Cách ghép số: các nhóm chữ số nối nhau bằng đúng 1 dấu phân cách (cách, ``.``, ``-``, xuống dòng;
``\\r\\n`` tính một) tạo thành một "dãy". Dãy không được có chữ số hay chữ cái liền trước/liền sau.
Nhóm nối bằng ``.`` hoặc ``-`` là một khối không tách; nhóm cách nhau bởi khoảng trắng hoặc xuống dòng
thì tách được. Trong dãy, quét từ trái sang phải, tại mỗi khối lấy dãy khối liên tiếp hợp lệ dài nhất
(một số CCCD, điện thoại hay tài khoản); khối không thuộc số hợp lệ nào (số thứ tự, ngày, mục "2.") bị
bỏ qua mà không làm mất số hợp lệ bên cạnh. Vì vậy mã số thuế ``0312345678-001`` (một khối 13 số) không
cho phát hiện nào. Hệ quả: số nằm sát chữ ("CCCD079203012345") không được nhận, trừ ``(``/``+`` mở đầu
số điện thoại quốc tế ("ĐT(+84)912345678").

Mã số thuế: nếu trong 30 ký tự ngay trước số có "mst" hoặc "mã số thuế" (bỏ dấu, không phân biệt hoa
thường) và giữa từ khoá với số không có chữ số khác, số đó không được coi là CCCD hay điện thoại (mã số thuế
10 số dễ giống đầu số di động). Số nằm sau nhãn "stk" vẫn có thể là tài khoản.

Giới hạn đã biết khác: ``+84 0912...`` (có số 0 thừa) và ``0084 ...`` không được nhận. Ký tự như ² hay ①
không phải chữ số dù NFKD đổi chúng thành số.

Khi nhãn "stk" đứng trước, số được tính là ``BANK_ACCOUNT`` (nhãn tường minh thắng); nếu người gọi
không yêu cầu loại đó thì rơi về loại khác còn khớp (ví dụ 12 số hợp lệ mã tỉnh thành ``CCCD``).

Che chắn: hộp của một phát hiện phủ mọi ký tự từ ký tự đầu đến ký tự cuối của số (kể cả dấu phân
cách, trừ ký tự không có hộp), gộp theo dòng. Số nằm trên hai trang được **tách theo trang** (mỗi
trang một ``Finding``, mọi hộp của nó cùng trang) để dù bên vẽ dùng ``Finding.page`` hay
``Box.page`` thì mọi ký tự vẫn bị che; đổi lại một số như vậy được đếm hai lần. Chữ xoay dọc không
được gộp dòng đúng nghĩa (mỗi ký tự có thể ra một hộp), vẫn phủ đủ."""

import functools
import re
import unicodedata
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Literal

# Khác ``registry.model.PiiType`` (có thêm EMAIL, NAME): bộ dò chỉ hỗ trợ ba loại số này.
PiiType = Literal["CCCD", "PHONE", "BANK_ACCOUNT"]
DETECTABLE: tuple[PiiType, ...] = ("CCCD", "PHONE", "BANK_ACCOUNT")
_SUPPORTED: frozenset[str] = frozenset(DETECTABLE)

_KEYWORD_MAX_GAP = 30
_KEYWORD_LOOKBACK = _KEYWORD_MAX_GAP + 40
_MIN_DIGITS = 8  # số ngắn nhất cần dò (tài khoản)
_MAX_DIGITS = 19  # số dài nhất cần dò (tài khoản); dãy dài hơn chỉ chia được thành nhiều số
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")


@dataclass(frozen=True)
class Box:
    """Hộp bao một ký tự hoặc một đoạn chữ; PDF point, gốc dưới-trái; ``page`` bắt đầu từ 1."""

    page: int
    left: float
    bottom: float
    right: float
    top: float


@dataclass(frozen=True)
class Finding:
    """Một chỗ có PII: loại, trang (từ 1) và các hộp cần che. Không chứa giá trị."""

    type: PiiType
    page: int
    boxes: tuple[Box, ...]


# Dãy chữ số nối bằng tối đa 1 dấu phân cách, có thể mở đầu bằng +84 / (+84).
_RUN = re.compile(r"(?P<cc>(?:\(\+84\)|\+84)[ .\-]?)?(?P<run>[0-9](?:(?:\r\n|[ .\-\r\n])?[0-9])*)")
_GROUP = re.compile(r"[0-9]+")
_KEYWORD = re.compile(r"(?<![a-z0-9])(?:stk|so\s+tai\s+khoan|tai\s+khoan)(?![a-z0-9])")
_TAX_KEYWORD = re.compile(r"(?<![a-z0-9])(?:mst|ma\s+so\s+thue)(?![a-z0-9])")


def _fold(ch: str) -> str:
    """NFKD bỏ dấu, chữ thường; chữ số toàn chiều rộng (Nd) thành ASCII. Chỉ dùng để so khớp.

    Ký tự không thuộc Nd mà NFKD đổi ra chữ số (số mũ ², vòng tròn ①...) bị thay bằng U+FFFD.
    """
    if ch in "đĐ":
        return "d"
    if unicodedata.category(ch) != "Nd" and any("0" <= c <= "9" for c in unicodedata.normalize("NFKD", ch)):
        return "\ufffd" * len(unicodedata.normalize("NFKD", ch))  # ², ①, ... không phải chữ số
    out = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return out.casefold().translate(_DASHES)


def _is_alnum(ch: str) -> bool:
    return ch.isalnum()


def _has_keyword(folded: str, start: int) -> bool:
    window = folded[max(0, start - _KEYWORD_LOOKBACK):start]
    ends = [m.end() for m in _KEYWORD.finditer(window)]
    return bool(ends) and len(window) - max(ends) <= _KEYWORD_MAX_GAP


def _has_tax_keyword(folded: str, start: int) -> bool:
    """Có "MST"/"mã số thuế" trong 30 ký tự trước số, và giữa nó với số không có chữ số nào khác."""
    window = folded[max(0, start - _KEYWORD_LOOKBACK):start]
    ends = [m.end() for m in _TAX_KEYWORD.finditer(window)]
    if not ends or len(window) - max(ends) > _KEYWORD_MAX_GAP:
        return False
    return not any("0" <= c <= "9" for c in window[max(ends):])


def _candidates(
    digits: str, *, intl: bool, keyword: Callable[[], bool], tax: Callable[[], bool]
) -> tuple[str, ...]:
    """Các loại mà dãy chữ số này có thể là, theo thứ tự ưu tiên (rỗng = không hợp lệ)."""
    n = len(digits)
    if intl:
        return ("PHONE",) if n == 9 and digits[0] in "35789" else ()
    out: list[str] = []
    if 8 <= n <= _MAX_DIGITS and keyword():
        out.append("BANK_ACCOUNT")
    is_cccd = n == 12 and 1 <= int(digits[:3]) <= 96
    is_phone = n == 10 and digits[0] == "0" and digits[1] in "35789"
    if (is_cccd or is_phone) and not tax():  # mã số thuế: không phải CCCD hay điện thoại
        out.append("CCCD" if is_cccd else "PHONE")
    return tuple(out)


def _split_run(
    folded: str, groups: list[tuple[int, int]], intl: bool
) -> list[tuple[int, int, tuple[str, ...]]]:
    """Lấy các số hợp lệ trong một dãy, bỏ các nhóm lẻ (số thứ tự, ngày, mục...) đứng cạnh.

    Nhóm nối nhau bằng ``.`` hoặc ``-`` là một khối không tách; nhóm cách nhau bởi khoảng trắng hoặc
    xuống dòng thì tách được. Quét từ trái sang phải: tại mỗi khối, lấy dãy khối liên tiếp hợp lệ dài
    nhất bắt đầu từ đó; không có thì bỏ khối ấy. Trả về danh sách (nhóm đầu, nhóm cuối + 1, loại có thể).
    """
    # khối = các nhóm nối bằng . hoặc -
    blocks: list[tuple[int, int]] = []  # (chỉ số nhóm đầu, nhóm cuối + 1)
    for k, (g0, _g1) in enumerate(groups):
        if k and folded[groups[k - 1][1]:g0] and not folded[groups[k - 1][1]:g0].isspace():
            blocks[-1] = (blocks[-1][0], k + 1)
        else:
            blocks.append((k, k + 1))
    digits_of = [sum(groups[k][1] - groups[k][0] for k in range(f, e)) for f, e in blocks]
    parts: list[tuple[int, int, tuple[str, ...]]] = []
    i, n = 0, len(blocks)
    while i < n:
        start = groups[blocks[i][0]][0]
        keyword = functools.cache(lambda start=start: _has_keyword(folded, start))
        tax = functools.cache(lambda start=start: _has_tax_keyword(folded, start))
        total, best, text = 0, None, ""
        for j in range(i + 1, n + 1):
            total += digits_of[j - 1]
            if total > _MAX_DIGITS:
                break
            text += "".join(folded[g0:g1] for g0, g1 in groups[blocks[j - 1][0]:blocks[j - 1][1]])
            if total < _MIN_DIGITS:
                continue
            cands = _candidates(text, intl=intl and i == 0, keyword=keyword, tax=tax)
            if cands:
                best = (j, cands)  # j tăng dần nên cuối cùng giữ dãy dài nhất
        if best is None:
            i += 1
            continue
        j, cands = best
        parts.append((blocks[i][0], blocks[j - 1][1], cands))
        i = j
    return parts


def _same_line(a: Box, b: Box) -> bool:
    if a.page != b.page:
        return False
    overlap = min(a.top, b.top) - max(a.bottom, b.bottom)
    smaller = min(a.top - a.bottom, b.top - b.bottom)
    if smaller <= 0:
        return overlap >= 0 and abs(a.bottom - b.bottom) < 1e-6
    return overlap > 0.5 * smaller


def _merge_lines(boxes: list[Box]) -> list[Box]:
    merged: list[Box] = []
    for b in boxes:
        if merged and _same_line(merged[-1], b):
            m = merged[-1]
            merged[-1] = Box(m.page, min(m.left, b.left), min(m.bottom, b.bottom),
                             max(m.right, b.right), max(m.top, b.top))
        else:
            merged.append(b)
    return merged


def detect_text(text: str, char_boxes: Sequence[Box | None], types: Collection[PiiType]) -> list[Finding]:
    """Dò PII trong ``text``; ``char_boxes[i]`` là hộp của ``text[i]`` hoặc None (ký tự do PDFium sinh thêm).

    Trả về các ``Finding`` theo thứ tự xuất hiện. Phát hiện mà không ký tự chữ số nào có hộp thì bị bỏ
    (không có gì để che). Raises ``ValueError`` nếu ``types`` có loại lạ hoặc độ dài hai dãy khác nhau; thông
    báo lỗi không chứa nội dung văn bản.
    """
    wanted = set(types)
    unknown = wanted - _SUPPORTED
    if unknown:
        raise ValueError(f"unsupported PII type(s): {sorted(unknown)}")
    if len(text) != len(char_boxes):
        raise ValueError(f"text has {len(text)} characters but char_boxes has {len(char_boxes)} entries")
    if not wanted or not text:
        return []

    folded_parts: list[str] = []
    origin: list[int] = []  # chỉ số trong chuỗi đã chuẩn hóa -> chỉ số trong text gốc
    for i, ch in enumerate(text):
        f = _fold(ch)
        folded_parts.append(f)
        origin.extend([i] * len(f))
    folded = "".join(folded_parts)

    findings: list[Finding] = []
    for m in _RUN.finditer(folded):
        start, end = m.start(), m.end()
        # "ĐT(+84)912345678": dấu ( hoặc + sau chữ cái vẫn mở đầu một số điện thoại
        glued_ok = m.group("cc") is not None and start > 0 and folded[start - 1].isalpha()
        if (start > 0 and _is_alnum(folded[start - 1]) and not glued_ok) or (
                end < len(folded) and _is_alnum(folded[end])):
            continue
        run_start, run_end = m.span("run")
        groups = [(run_start + g.start(), run_start + g.end())
                  for g in _GROUP.finditer(folded[run_start:run_end])]
        parts = _split_run(folded, groups, intl=m.group("cc") is not None)
        for first, last, cands in parts:
            kind = next((c for c in cands if c in wanted), None)
            if kind is None:
                continue
            a = start if first == 0 else groups[first][0]  # +84 thuộc số đầu tiên của dãy
            b = groups[last - 1][1]
            findings.extend(_findings_for(kind, char_boxes, origin[a], origin[b - 1]))
    return findings


def _findings_for(kind: str, char_boxes: Sequence[Box | None], lo: int, hi: int) -> list[Finding]:
    by_page: dict[int, list[Box]] = {}
    for box in char_boxes[lo:hi + 1]:
        if box is not None:
            by_page.setdefault(box.page, []).append(box)
    return [Finding(kind, page, tuple(_merge_lines(boxes))) for page, boxes in by_page.items()]  # type: ignore[arg-type]
