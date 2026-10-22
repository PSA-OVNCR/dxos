# Tệp CSV mẫu (Review Focus 1)

Tệp nhị phân, tạo một lần bằng script bên dưới (chạy trong thư mục này: `python3 -I - <<'PY' ... PY`) rồi commit.
Cả sáu tệp chứa CÙNG ba dòng dữ liệu (có ô chứa dấu phẩy, dấu nháy kép, và hai dòng trống ở cuối); chỉ khác bảng mã,
dấu phân cách và dạng Unicode.

| Tệp | Mô phỏng | Bảng mã | Phân cách |
| --- | --- | --- | --- |
| `utf8-bom.csv` | Excel "CSV UTF-8", locale vi-VN | UTF-8 có BOM | `;` |
| `cp1258.csv` | Excel tiếng Việt cũ, "CSV (Comma delimited)" | Windows-1258 (chữ cái gốc + dấu kết hợp) | `;` |
| `utf16le-bom.csv` | Excel "Unicode Text" | UTF-16LE có BOM | TAB |
| `utf16le-no-bom.csv` | công cụ ghi UTF-16 không BOM (phải bị từ chối, không được nhập: review cuối Plan 03, I3) | UTF-16LE không BOM | TAB |
| `utf8.csv` | công cụ khác | UTF-8 không BOM | `,` |
| `utf8-nfd.csv` | macOS | UTF-8, họ tên ở dạng NFD | `,` |

## Lệnh tạo

```sh
cd apps/chung-nhan/web/test/fixtures
python3 -I - <<'PY'
import codecs
import unicodedata

HEADER = ["Họ và tên", "Sự kiện", "Ngày cấp", "Email"]
ROWS = [
    ["Nguyễn Văn An", "Hội thảo Phần mềm nguồn mở", "10/11/2026", "an@example.vn"],
    ['Lê, Thị "Bình"', "Ngày hội Git, GitHub", "10/11/2026", ""],
    ["Phạm Đức Thịnh", "Tập huấn Ứng dụng Chứng nhận số", "12/11/2026", "thinh@example.vn"],
]


def cell(v, sep):
    return '"' + v.replace('"', '""') + '"' if any(c in v for c in (sep, '"', "\n", "\r")) else v


def text(sep, rows=ROWS, trailing="\r\n\r\n"):
    lines = [sep.join(cell(c, sep) for c in r) for r in [HEADER, *rows]]
    return "\r\n".join(lines) + trailing


def to_cp1258(s):
    """Windows-1258 chỉ có một số chữ ghép sẵn; phần còn lại là chữ cái gốc + dấu kết hợp (như Excel tiếng Việt cũ ghi)."""
    out = bytearray()
    for ch in unicodedata.normalize("NFC", s):
        try:
            out += codecs.encode(ch, "cp1258")
            continue
        except UnicodeEncodeError:
            pass
        d = unicodedata.normalize("NFD", ch)
        shape = "".join(m for m in d[1:] if m in "\u0302\u0306\u031b")  # â, ê, ô, ă, ơ, ư là chữ cái riêng của cp1258
        tone = [m for m in d[1:] if m not in shape]                       # dấu thanh: 0300, 0301, 0303, 0309, 0323
        out += codecs.encode(unicodedata.normalize("NFC", d[0] + shape), "cp1258")
        for mark in tone:
            out += codecs.encode(mark, "cp1258")
    return bytes(out)


def write(name, data):
    with open(name, "wb") as f:
        f.write(data)


write("utf8-bom.csv", b"\xef\xbb\xbf" + text(";").encode("utf-8"))          # Excel "CSV UTF-8", locale vi-VN
write("cp1258.csv", to_cp1258(text(";")))                                    # Excel tiếng Việt cũ ("CSV (Comma delimited)")
write("utf16le-bom.csv", b"\xff\xfe" + text("\t").encode("utf-16-le"))       # Excel "Unicode Text" (phân cách TAB)
write("utf16le-no-bom.csv", text("\t").encode("utf-16-le"))                 # UTF-16LE không BOM: phải bị từ chối
write("utf8.csv", text(",").encode("utf-8"))                                 # UTF-8 không BOM
write("utf8-nfd.csv", unicodedata.normalize("NFD", text(",")).encode("utf-8"))  # họ tên NFD như macOS
PY
```

`cp1258.csv` được mã hóa bằng `codecs.encode(..., 'cp1258')`. Windows-1258 chỉ có sẵn một số chữ ghép (â, ê, ô, ă, ơ, ư, à, á, ã...);
phần còn lại ("ễ", "ộ", "ị"...) là chữ cái gốc cộng dấu kết hợp (U+0300, U+0301, U+0303, U+0309, U+0323). Vì vậy "Nguyễn" được ghi là
`N g u y ê` (0xEA) + dấu ngã kết hợp (0xDE) + `n`, đúng như Excel trên Windows vẫn làm. Bộ giải mã phải chuẩn hóa NFC sau khi đọc.
