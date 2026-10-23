<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Nộp bài dự thi (hồ sơ gửi BTC, checklist cuối, thủ tục 1.0.0)

Trang này dành cho trưởng nhóm. Thứ tự các mốc: gắn tag ký `v1.0.0` **trước 04/12** (M5), tập demo, **gửi email sáng 06/12**, hạn nộp
**17:00 Chủ Nhật 06/12/2026**. Nhãn: **[BB]** bắt buộc theo Đề hay Thể lệ; **[TK]** tham khảo; **[ĐX]** đề xuất của đội.

> **Trạng thái**: soạn ở cloud, **chưa gửi gì và chưa gắn tag nào**. Phiên bản trong mã vẫn là `0.9.0`: việc nâng lên `1.0.0` và đóng
> băng mã là việc của M5, sau khi các việc chạy thật V37 đến V46 xong và lỗi tìm ra đã được sửa (ruling R30,
> `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 14.6). Thủ tục chính xác nằm ở mục 5 ("Thủ tục đóng băng 1.0.0") bên dưới và ở hàng V50.

## 1. Hạn và địa chỉ nhận bài [BB]

Nguồn: Đề thi PMNM OLP 2026, mục 5 "Gửi bài thi" (trang 6).

| Mục | Nội dung |
|---|---|
| Hình thức | Thư điện tử, đúng quy cách ở mục 2 |
| Địa chỉ nhận bài | olpvietnam@vaip.vn, thuky@vfossa.vn |
| Hạn gửi | **17:00 Chủ Nhật ngày 06/12/2026** |
| Lưu ý về năm | Đề in "17:00 Chủ Nhật ngày 06/12/2025": đó là lỗi đánh máy (06/12/2025 là Thứ Bảy, và cuộc thi diễn ra năm 2026). Đội làm theo giải đáp **G12** của BTC: hạn là 17:00 06/12/2026. Trưởng nhóm nên xác nhận lại với BTC nếu còn nghi ngờ (ruling R31) |
| Gửi lúc nào | **Sáng 06/12**, không chờ sát giờ; giữ bản đã gửi và ảnh chụp thời điểm gửi [ĐX] |
| Sau đó | 07 đến 09/12 BTC chấm kho mã; **10/12** chung kết (trình bày 15 phút, Đề mục 6, trang 7); 11/12 trao giải (Thể lệ) |

## 2. Mẫu email

### 2.1. Mẫu nguyên văn của Đề (mục 5, trang 6)

```text
Tiêu đề thư: BÀI THI PMNM 2026 - [Tên Đội] - [Tên Trường]

Nội dung thư:
Kính gửi BTC cuộc thi PMNM 2026,
Đội thi [Tên Đội] - [Tên Trường] đã hoàn thành bài thi và xin gửi BTC kết quả như sau
Thành viên đội
1. Tên thành viên 1, năm sinh, ngành đào tạo
2. Tên thành viên 2, năm sinh, ngành đào tạo
3. Tên thành viên 3, năm sinh, ngành đào tạo
Người hướng dẫn: Tên Thầy/Cô - Khoa/Viện/Trường
Kho mã nguồn dự thi: [đường dẫn truy cập kho mã nguồn chứa đầy đủ nội dung kết quả dự thi]
Đội thi đã hoàn thành việc đăng kí dự thi theo đúng quy định của BTC thông qua [Tên Trường]. Chúng tôi cam kết toàn bộ bản quyền sử dụng đối với sản phẩm dự thi tuân thủ theo đúng các quy tắc của phần mềm tự do nguồn mở.

Địa chỉ nhận bài: olpvietnam@vaip.vn, thuky@vfossa.vn
```

### 2.2. Bản điền sẵn phần đội biết (các ô còn lại do đội điền)

Tên đội là **PSA_OVNCR**. Tên trường, họ tên, năm sinh, ngành đào tạo của từng thành viên và thông tin người hướng dẫn là dữ liệu
cá nhân do chính các thành viên cung cấp: **tài liệu này không điền và không được bịa**; thay mọi chỗ trong `[...]` trước khi gửi.

```text
Tiêu đề thư: BÀI THI PMNM 2026 - PSA_OVNCR - [Tên Trường]

Kính gửi BTC cuộc thi PMNM 2026,
Đội thi PSA_OVNCR - [Tên Trường] đã hoàn thành bài thi và xin gửi BTC kết quả như sau
Thành viên đội
1. [Họ tên thành viên 1], [năm sinh], [ngành đào tạo]
2. [Họ tên thành viên 2], [năm sinh], [ngành đào tạo]
3. [Họ tên thành viên 3], [năm sinh], [ngành đào tạo]
Người hướng dẫn: [Tên Thầy/Cô - Khoa/Viện/Trường]
Kho mã nguồn dự thi: https://github.com/PSA-OVNCR/dxos (bản nộp: tag v1.0.0, https://github.com/PSA-OVNCR/dxos/releases/tag/v1.0.0)
Đội thi đã hoàn thành việc đăng kí dự thi theo đúng quy định của BTC thông qua [Tên Trường]. Chúng tôi cam kết toàn bộ bản quyền sử dụng đối với sản phẩm dự thi tuân thủ theo đúng các quy tắc của phần mềm tự do nguồn mở.

Địa chỉ nhận bài: olpvietnam@vaip.vn, thuky@vfossa.vn
```

Ghi chú khi gửi [ĐX]: gửi từ một địa chỉ mà cả đội truy cập được, cho cả ba thành viên và người hướng dẫn vào Cc; không đính kèm tệp
(Đề yêu cầu đường dẫn tới kho mã). Kho mã phải mở được khi **chưa đăng nhập GitHub** (kiểm bằng cửa sổ riêng tư). Lời cam kết bản quyền
ở trên là của đội: chỉ gửi khi đã chạy `reuse lint` và `make licenses` đạt trên đúng commit của tag (mục 3).

## 3. Checklist PoF cuối (Thể lệ trang 1 đến 3) [BB]

Thể lệ tr.1: bắt buộc giấy phép nguồn mở được OSI công nhận và mã nguồn truy cập tự do trên Internet. Sáu tiêu chí PoF ở tr.2–3, mỗi
tiêu chí kèm cách tự kiểm trong kho. Tích từng ô trên đúng bản sẽ nộp (checkout tag `v1.0.0`); ô nào chưa kiểm được thì để trống và ghi lý do.

- [ ] **(1) Kho mã trên Internet, truy cập mở, có web viewer**: repo `PSA-OVNCR/dxos` ở chế độ public; mở trong cửa sổ riêng tư thấy cây thư mục, `README.md`, `LICENSE`.
- [ ] **(2) Giấy phép OSI**: `LICENSE` có toàn văn Apache-2.0; `NOTICE` nêu mục đích; **mỗi tệp mã có SPDX** (`reuse lint` mã thoát 0, `LICENSES/`); không xung đột giấy phép (`make licenses` mã thoát 0, ngoại lệ đã duyệt ở `LICENSES-THIRD-PARTY.md`).
- [ ] **(3) Có ít nhất một Release trước thời điểm nộp, theo phiên bản, định dạng mở**: trang Releases có `v1.0.0` (và `v0.x`) với `dxos-1.0.0.tar.gz`, wheel, `sbom-1.0.0.cdx.json`, `trust-core-image-1.0.0.txt`, `viewer-image-1.0.0.txt`; **không zip, không rar**.
- [ ] **(4) Build từ mã nguồn**: `BUILD.md` có hướng dẫn, gồm mục "Máy Ubuntu 24.04 sạch, từng lệnh" **đã được người ngoài đội làm theo trên máy sạch (AT-23, V45)**; cấu hình qua `.env` và biến môi trường trước khi dựng (không sửa tay tệp header hay mã); không công cụ đóng; chạy được ngoài thư mục nguồn (wheel và image theo digest ở Release).
- [ ] **(5) Thư viện**: `LICENSES-THIRD-PARTY.md` nêu rõ từng thư viện, giấy phép và cách dùng; `constraints.txt` và `package-lock.json` ghim phiên bản; dùng thư viện hệ thống/image chính thức; không phát hành kèm gói phụ thuộc (không vendor); không sửa mã gói đính kèm; SBOM (`sbom-1.0.0.cdx.json`) khớp bản phát hành.
- [ ] **(6) Tài liệu**: bug tracker (GitHub Issues bật, có nhãn và ít nhất một issue của người dùng thử, V38); `CHANGELOG.md` có `## [1.0.0]` đã ghi ngày; `README.md` và `README_EN.md`; hướng dẫn `BUILD.md`, `docs/tutorial-app-30-phut.md`, các runbook trong `docs/`.
- [ ] **Đã đẩy tag v1.0.0 trước khi gửi email** (tag ký, `verify-tag` đạt) và Release của tag đã dựng xong; email chỉ trỏ tới bản này.
- [ ] CI xanh ở đúng commit của tag (`gh run list -R PSA-OVNCR/dxos --limit 5`: mọi job của run `ci` là `success`).
- [ ] `make release-check VERSION=1.0.0` mã thoát 0 trước khi tag (5 gói Python, CHANGELOG có ngày, cây sạch, `HEAD` = `origin/main`).
- [ ] Gate trên đúng commit tag, kiểm bằng mã thoát: `make check PYTHON=python`, `npm run check`, `reuse lint` (mục 5, bước 6).
- [ ] Không có bí mật trong kho và lịch sử: job `gitleaks` của CI xanh; `.env`, `.secrets/`, `deploy/release.env` không được commit.
- [ ] Trạng thái "đã kiểm / chưa kiểm" trong README và `docs/progress/` khớp thực tế (không câu nào nói đã chạy khi chưa chạy; các việc V chưa xong vẫn được ghi là chưa xong).
- [ ] Câu chữ pháp lý đúng spec 25.1 (niêm phong là chữ ký điện tử chuyên dùng, chưa được chứng nhận; watermark chỉ để răn đe): `tests/repo/test_docs_m4.py` và `tests/repo/test_docs_m5.py` xanh.
- [ ] Người hướng dẫn và trường đã xác nhận đội **đăng kí dự thi thông qua trường** (câu cam kết trong email nói điều này) [BB].
- [ ] Email đã điền hết `[...]`, tiêu đề đúng `BÀI THI PMNM 2026 - [Tên Đội] - [Tên Trường]` với tên thật, địa chỉ nhận đủ hai người, đã gửi **trước 17:00 06/12/2026**.
- [ ] Sau khi gửi: giữ bản thư đã gửi; **không** force-push, xóa hay dời tag trong lúc BTC chấm kho mã (07 đến 09/12) [ĐX]; chỉ sửa lỗi thật sự và báo BTC nếu cần.

## 4. Lịch các ngày cuối [ĐX]

| Ngày | Việc |
|---|---|
| Trước 04/12 | V37 đến V46 xong, lỗi đã sửa; đóng băng 1.0.0 theo mục 5; tag ký `v1.0.0` (V50); AT-23 và AT-26 trên bản này |
| 05/12 | Tập demo lần 1; chạy lại checklist mục 3 trên tag |
| Sáng 06/12 | Điền email, kiểm lần cuối, **gửi**; hạn cứng 17:00 |
| 07 đến 09/12 | BTC chấm kho mã; tập demo (07/12, 08/12 hai lần, 09/12) |
| 10/12 | Chung kết, 15 phút (`docs/demo/kich-ban.md`) |

## 5. Thủ tục đóng băng 1.0.0

Đây là thủ tục **chính xác** của M5 (04/12), chưa chạy. Ở Task 16 cố ý không làm (ruling R30): `v0.9.0` chưa gắn tag, và các việc chạy
thật V37 đến V44 có thể còn sửa mã; sửa xong rồi mới đóng băng. **Điều kiện trước**: `v0.9.0` đã gắn tag ký (`docs/progress/2026-10-21-tong-ket-tien-do.md`,
mục 14.4); có khóa ký trong `deploy/allowed_signers` (V42); mọi lỗi tìm ra từ V37 đến V46 đã sửa và nằm trên `main`.

1. `git pull`; `git status` sạch. Từ commit bước 7 trở đi mã **đóng băng**: chỉ sửa lỗi.
2. Đổi phiên bản `1.0.0` (theo `BUILD.md`, mục "Phát hành"):
   - `version` trong `libs/dxos-proof/pyproject.toml`, `core/pyproject.toml`, `witness/pyproject.toml`, `cli/pyproject.toml`, `viewer/pyproject.toml`;
   - `__version__` trong `core/src/dxos_core/__init__.py`, `witness/src/dxos_witness/__init__.py`, `cli/src/dxos_cli/__init__.py`, `viewer/src/dxos_viewer/__init__.py`;
   - `version` của `package.json` gốc, `sdk/js/package.json`, `verify-portal/app/package.json`, `admin-ui/package.json`, `apps/phong-ho-so/web/package.json`,
     `apps/chung-nhan/web/package.json`, `examples/so-muon-sach/web/package.json`, và các mục tương ứng trong `package-lock.json`
     (`npm version 1.0.0 --workspaces --include-workspace-root --no-git-tag-version`, hoặc sửa tay rồi chạy `npm install --package-lock-only`; chưa thử ở cloud vì lệnh cần registry: kiểm bằng `tests/repo/test_docs_m4.py::test_package_lock_matches`);
   - tìm các chỗ còn ghi cứng bản cũ: `grep -rn '0\.9\.0' --include='*.py' --include='*.md' --include='*.json' --include='*.yaml' . | grep -v node_modules`.
     Đã biết: `viewer/src/dxos_viewer/app.py` (tham số `version` của FastAPI), `viewer/tests/test_package.py`, `viewer/README.md`, tiêu đề
     "Trạng thái v0.9.0" của `README.md` và `README_EN.md`, và các hằng `VERSION = "0.9.0"` cùng kiểm CHANGELOG `[0.9.0]` trong
     `tests/repo/test_docs_m4.py` (đổi sang `1.0.0`, vẫn giữ kiểm riêng mục `[0.9.0]` cũ) và hai khẳng định "chưa đóng băng" trong
     `tests/repo/test_docs_m5.py` (xóa).
3. `make openapi` (sinh lại `docs/api/openapi.json`; `tests/ops/test_openapi.py` đỏ nếu bỏ qua bước này).
4. `CHANGELOG.md`: thêm `## [1.0.0] - YYYY-MM-DD` ngay dưới `## [Unreleased]`, mô tả "đóng băng mã, chỉ sửa lỗi sau commit này". Gom vào đó:
   `ops/doctor.sh`, `ops/demo_preflight.sh`, `docs/demo/kich-ban.md`, `docs/nop-bai.md`, mục "Máy Ubuntu 24.04 sạch" của `BUILD.md`,
   `docs/at26-checklist.md` làm mới (Task 16) và mọi sửa lỗi sau V37 đến V46; ghi kết quả V45, V46 (đạt hay không) vào "Known limitations" nếu còn dở.
   Dùng `python ops/changelog_section.py 1.0.0` để kiểm mục đọc được.
5. Cập nhật bảng V và mục 14 của `docs/progress/2026-10-21-tong-ket-tien-do.md` cho đúng thực tế (V nào đã chạy, kết quả, commit).
6. Gate, **kiểm bằng mã thoát** (không qua `| tail`): `. .venv/bin/activate && make check PYTHON=python && npm run check && reuse lint`; thêm integration của phần đã đụng.
7. Commit `chore(release): 1.0.0`, `git push origin main`. **Chờ CI xanh** ở đúng commit này: `gh run list -R PSA-OVNCR/dxos --limit 5` mọi job của run `ci` là `success`.
8. `git pull`, rồi `make release-check VERSION=1.0.0` phải thoát 0 (5 gói Python kể cả `viewer`, CHANGELOG có ngày, cây sạch, `HEAD` = `origin/main`).
9. Tag ký (việc của trưởng nhóm, một hành động công khai):
   ```bash
   git tag -s v1.0.0 <sha của commit chore(release): 1.0.0> -m "v1.0.0: đóng băng mã, M5"
   git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=deploy/allowed_signers verify-tag refs/tags/v1.0.0   # phải in "for <principal>"
   git push origin v1.0.0
   ```
10. Workflow `release` chạy (job `check`, `image`, `image-viewer`, `release`): xem Release có đủ tệp ở mục 3 (3); package GHCR `trust-core` và `viewer` công khai (V19).
11. Trên VPS: `ops/deploy.sh v1.0.0` (V29, V42), rồi `ops/demo_preflight.sh` (V48). Sau tag, lỗi quan trọng được sửa bằng `1.0.1`; **không** xóa hay dời tag đã đẩy.
12. Tích hết checklist mục 3, rồi mới gửi email (mục 2).
