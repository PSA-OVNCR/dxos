# App A: Phòng hồ sơ số (Tầng 2, không gian [P] + [D])

Ứng dụng chính để trình diễn. Ban hành văn bản nội bộ có PII theo luồng: tải lên → kiểm dịch → duyệt 2 bước theo nguyên tắc bốn mắt → niêm phong → đối soát.

- `manifest.yaml`: bản 1.1.0: collection, vai trò, chính sách (thu hồi niêm phong: `giam_doc`; xóa PII: `van_thu`), workflow
- `bpmn/ban-hanh.bpmn`: quy trình ban hành `duyet_noi_dung` (trưởng phòng) → `ban_hanh` (giám đốc); `ban_hanh` có guard `not_same_actor:duyet_noi_dung` nên một người giữ cả hai vai trò không tự làm cả hai bước
- `web/`: SPA Vue 3 (gói `dxos-app-phong-ho-so`, phục vụ ở `/apps/phong-ho-so/`, router băm). Plan 03 Task 7: danh sách văn bản, tạo văn bản, sửa, tải tệp PDF kèm trạng thái kiểm dịch, gửi duyệt; Task 8 thêm hộp việc và sổ đăng ký. SPA không có quy tắc quyết định: ẩn/hiện nút theo vai trò chỉ để tiện, mọi lỗi của lõi hiện nguyên văn qua `ProblemMessage`. Chạy kiểm tra: `npm run test -w dxos-app-phong-ho-so` và `npm run typecheck -w dxos-app-phong-ho-so`.
  - Chốt chặn vòng lặp đăng nhập (`src/session.ts`): 401 lần đầu chuyển sang Keycloak và đặt dấu trong sessionStorage; nếu sau khi quay về máy chủ vẫn trả 401 (lệch đồng hồ, lõi từ chối token) thì hiện màn hình "Phiên đăng nhập không được máy chủ chấp nhận" với nút "Đăng nhập lại". Dấu bị xóa khi có lời gọi API thành công đầu tiên.
  - Router chỉ được tạo sau `await auth.init()` (`src/boot.ts`) vì init đổi URL bằng `history.replaceState`, không bắn `hashchange`.

Ứng dụng **không có backend riêng**, mọi thao tác đi qua API của Trust Core. Dữ liệu demo dùng tổ chức hư cấu "Công ty TNHH Sao Mai".
