# App A: Phòng hồ sơ số (Tầng 2, không gian [P] + [D])

Ứng dụng chính để trình diễn. Ban hành văn bản nội bộ có PII theo luồng: tải lên → kiểm dịch → duyệt 2 bước theo nguyên tắc bốn mắt → niêm phong → đối soát.

- `manifest.yaml`: khai báo collection, vai trò, chính sách, workflow (Plan 01 Task 11)
- `bpmn/ban-hanh.bpmn`: quy trình ban hành (Plan 02)
- `web/`: SPA Vue 3 (Plan 03)

Ứng dụng **không có backend riêng**, mọi thao tác đi qua API của Trust Core. Dữ liệu demo dùng tổ chức hư cấu "Công ty TNHH Sao Mai".
