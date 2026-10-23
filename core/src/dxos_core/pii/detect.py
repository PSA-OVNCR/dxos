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
Cả dãy phải là một số hợp lệ; nếu không thì thử chia dãy ở các chỗ phân cách thành nhiều số hợp lệ
liên tiếp (ví dụ hai cột CCCD và điện thoại nằm hai dòng liền nhau). Chia không trọn vẹn thì bỏ cả
dãy, nên mã số thuế ``0312345678-001`` không bị nhận nhầm là điện thoại. Hệ quả: số nằm sát chữ
("CCCD079203012345") không được nhận.

Khi nhãn "stk" đứng trước, số được tính là ``BANK_ACCOUNT`` (nhãn tường minh thắng); nếu người gọi
không yêu cầu loại đó thì rơi về loại khác còn khớp (ví dụ 12 số hợp lệ mã tỉnh thành ``CCCD``).

Che chắn: hộp của một phát hiện phủ mọi ký tự từ ký tự đầu đến ký tự cuối của số (kể cả dấu phân
cách, trừ ký tự không có hộp), gộp theo dòng. Số nằm trên hai trang được **tách theo trang** (mỗi
trang một ``Finding``, mọi hộp của nó cùng trang) để dù bên vẽ dùng ``Finding.page`` hay
``Box.page`` thì mọi ký tự vẫn bị che; đổi lại một số như vậy được đếm hai lần. Chữ xoay dọc không
được gộp dòng đúng nghĩa (mỗi ký tự có thể ra một hộp), vẫn phủ đủ."""

import re
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

# Khác ``registry.model.PiiType`` (có thêm EMAIL, NAME): bộ dò chỉ hỗ trợ ba loại số này.
PiiType = Literal["CCCD", "PHONE", "BANK_ACCOUNT"]
_SUPPORTED: frozenset[str] = frozenset({"CCCD", "PHONE", "BANK_ACCOUNT"})

_KEYWORD_MAX_GAP = 30
_KEYWORD_LOOKBACK = _KEYWORD_MAX_GAP + 40
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


def _fold(ch: str) -> str:
    """NFKD bỏ dấu, chữ thường; chữ toàn chiều rộng thành ASCII. Chỉ dùng để so khớp."""
    if ch in "đĐ":
        return "d"
    out = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return out.casefold().translate(_DASHES)


def _is_alnum(ch: str) -> bool:
    return ch.isalnum()


def _has_keyword(folded: str, start: int) -> bool:
    window = folded[max(0, start - _KEYWORD_LOOKBACK):start]
    ends = [m.end() for m in _KEYWORD.finditer(window)]
    return bool(ends) and len(window) - max(ends) <= _KEYWORD_MAX_GAP


def _candidates(digits: str, *, intl: bool, keyword: bool) -> tuple[str, ...]:
    """Các loại mà dãy chữ số này có thể là, theo thứ tự ưu tiên (rỗng = không hợp lệ)."""
    n = len(digits)
    if intl:
        return ("PHONE",) if n == 9 and digits[0] in "35789" else ()
    out: list[str] = []
    if keyword and 8 <= n <= _MAX_DIGITS:
        out.append("BANK_ACCOUNT")
    if n == 12 and 1 <= int(digits[:3]) <= 96:
        out.append("CCCD")
    if n == 10 and digits[0] == "0" and digits[1] in "35789":
        out.append("PHONE")
    return tuple(out)


def _split_run(
    folded: str, groups: list[tuple[int, int]], intl: bool
) -> list[tuple[int, int, tuple[str, ...]]] | None:
    """Chia các nhóm chữ số thành các số hợp lệ liên tiếp (số dài trước); None nếu không chia trọn được.

    Trả về danh sách (nhóm đầu, nhóm cuối + 1, loại có thể).
    """
    n = len(groups)
    best: list[tuple[int, tuple[str, ...]] | None] = [None] * (n + 1)
    reachable = [False] * n + [True]
    for i in range(n - 1, -1, -1):
        total = 0
        digits = ""
        keyword = _has_keyword(folded, groups[i][0])
        for j in range(i + 1, n + 1):
            g = folded[groups[j - 1][0]:groups[j - 1][1]]
            total += len(g)
            if total > _MAX_DIGITS:
                break
            digits += g
            if not reachable[j]:
                continue
            cands = _candidates(digits, intl=intl and i == 0, keyword=keyword)
            if cands:
                reachable[i] = True
                best[i] = (j, cands)  # j tăng dần nên cuối cùng giữ số dài nhất
    if not reachable[0]:
        return None
    parts, i = [], 0
    while i < n:
        j, cands = best[i]  # type: ignore[misc]
        parts.append((i, j, cands))
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
        if (start > 0 and _is_alnum(folded[start - 1])) or (end < len(folded) and _is_alnum(folded[end])):
            continue
        run_start, run_end = m.span("run")
        groups = [(run_start + g.start(), run_start + g.end())
                  for g in _GROUP.finditer(folded[run_start:run_end])]
        parts = _split_run(folded, groups, intl=m.group("cc") is not None)
        if parts is None:
            continue
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
