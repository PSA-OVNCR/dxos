# Đóng góp cho DX-OS Trust Core

Cảm ơn bạn quan tâm. Quy trình:

1. Mở **Issue** mô tả lỗi hoặc đề xuất trước khi làm thay đổi lớn.
2. Tạo nhánh từ `main`: `feat/<mô-tả>`, `fix/<mô-tả>` hoặc `docs/<mô-tả>`.
3. **Viết test trước (TDD).** Mọi thay đổi hành vi đều phải có test.
4. Mọi tệp mã mới phải có header:
   ```
   # SPDX-FileCopyrightText: 2026 DX-OS Trust Core contributors
   # SPDX-License-Identifier: Apache-2.0
   ```
5. Chạy `make check` trước khi mở Pull Request.
6. Thêm thư viện mới thì cập nhật `LICENSES-THIRD-PARTY.md` **trong cùng commit**. Chỉ dùng thư viện giấy phép MIT, BSD, Apache-2.0, ISC hoặc PSF.
7. Không chép (vendor) mã của dự án khác vào kho; không sửa mã thư viện bên thứ ba.
8. Ghi thay đổi vào mục `[Unreleased]` của `CHANGELOG.md`.

Pull Request cần CI xanh và ít nhất 1 người duyệt.
