# Kiểm giấy phép pypdfium2 (để trưởng nhóm duyệt)

*Kiểm ngày 21/10/2026 trên wheel `pypdfium2-5.14.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`,
sha256 `11f281613fa22313d9c7ab89947665e84eccf8ebe40e1198a84a88352305648d` (tải từ PyPI). Nguồn: thư mục
`pypdfium2-5.14.0.dist-info/licenses/` bên trong wheel và trường `License` trong `METADATA`.*

## Cách dùng trong dự án
- `dxos-core` gọi pypdfium2 để kiểm PDF (có lớp chữ, không mã hóa) ở worker (Plan 01 Task 14).
- Wheel được **pip cài lúc build image**, không có tệp nào của pypdfium2 hay PDFium trong kho mã. Theo G4, thứ nằm ngoài kho
  và nạp khi chạy không làm thay đổi giấy phép của dự án; dù vậy mọi thành phần dưới đây đều là giấy phép dễ dãi (permissive).

## Thành phần trong wheel
| Thành phần | Tệp giấy phép trong wheel | Giấy phép | Loại (ScanCode LicenseDB) | Nghĩa vụ chính |
|---|---|---|---|---|
| pypdfium2 (mã Python) | `LICENSES/Apache-2.0.txt`, `LICENSES/BSD-3-Clause.txt` | Apache-2.0 **hoặc** BSD-3-Clause | Permissive, OSI | Giữ thông báo bản quyền |
| pypdfium2 (tài liệu, dữ liệu) | `LICENSES/CC-BY-4.0.txt` | CC-BY-4.0 | Permissive (giấy phép nội dung, không phải mã) | Ghi nguồn nếu chép tài liệu |
| PDFium | `pdfium.txt` | BSD-3-Clause | Permissive, OSI | Giữ thông báo |
| pdfium-binaries (bản build) | `pdfium-binaries.txt` | MIT | Permissive, OSI | Giữ thông báo |
| FreeType | `freetype.txt` | **FTL** (FreeType License; FreeType cho chọn FTL hoặc GPL-2.0, wheel kèm văn bản FTL nên đội dùng theo FTL) | Permissive | Ghi công FreeType trong tài liệu |
| ICU | `icu.txt` | Unicode-3.0 | Permissive | Giữ thông báo |
| libjpeg-turbo | `libjpeg_turbo.md`, `libjpeg_turbo.ijg` | IJG + BSD-3-Clause + Zlib | Permissive | Ghi công IJG trong tài liệu |
| libpng | `libpng.txt` | libpng-2.0 | Permissive | Giữ thông báo |
| zlib | `zlib.txt` | Zlib | Permissive, OSI | Giữ thông báo |
| OpenJPEG | `libopenjpeg.txt` | BSD-2-Clause | Permissive, OSI | Giữ thông báo |
| Little-CMS | `lcms.txt` | MIT | Permissive, OSI | Giữ thông báo |
| abseil | `abseil.txt` | Apache-2.0 | Permissive, OSI | Giữ thông báo |
| llvm-libc | `llvm-libc.txt` | Apache-2.0 WITH LLVM-exception | Permissive, OSI | Giữ thông báo |
| Anti-Grain Geometry 2.3 | `agg23.txt` | Giấy phép riêng kiểu "permission to copy, use, modify…" (tương đương BSD) | Dễ dãi (đọc văn bản; chưa tra trong LicenseDB) | Giữ thông báo |
| fast_float | `fast_float.txt` | MIT | Permissive, OSI | Giữ thông báo |
| simdutf | `simdutf.txt` | MIT | Permissive, OSI | Giữ thông báo |

*"OSI" chỉ ghi cho giấy phép chắc chắn thuộc danh sách OSI. Các giấy phép còn lại được ScanCode LicenseDB xếp loại Permissive; vì wheel không nằm trong kho mã (G4), chúng không ảnh hưởng tới điều kiện "mã nguồn trong kho có giấy phép OSI" (TL tr.1).*

**Không có** thành phần GPL, AGPL, LGPL hay giấy phép "nguồn mở có điều kiện" (G3) trong wheel.

## Quyết định
**Trưởng nhóm duyệt giữ pypdfium2 ngày 21/10/2026.** Ba việc dưới đây đã làm.

## Kết luận đề xuất [ĐX]
Dùng được. Đội chỉ cần: (1) giữ dòng pypdfium2 trong `LICENSES-THIRD-PARTY.md`; (2) ghi công FreeType và IJG trong mục giấy
phép của README khi phân phối image; (3) ghim phiên bản `pypdfium2>=5.14,<6` để bản build lại dùng đúng bộ thành phần đã kiểm
(G17). Phương án dự phòng nếu không duyệt: pypdf (BSD-3-Clause, thuần Python).

## Cách tự kiểm lại
```bash
pip download --no-deps "pypdfium2==5.14.0" -d /tmp/w
python -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('/tmp/w/*.whl')[0]); print('\n'.join(n for n in z.namelist() if 'licenses/' in n))"
```
