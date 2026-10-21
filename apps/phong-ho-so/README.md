# App A: Phòng hồ sơ số (Tầng 2, không gian [P] + [D])

Ứng dụng chính để trình diễn. Ban hành văn bản nội bộ có PII theo luồng: tải lên → kiểm dịch → duyệt 2 bước theo nguyên tắc bốn mắt → niêm phong → đối soát.

- `manifest.yaml`: bản 1.1.0: collection, vai trò, chính sách (thu hồi niêm phong: `giam_doc`; xóa PII: `van_thu`), workflow
- `bpmn/ban-hanh.bpmn`: quy trình ban hành `duyet_noi_dung` (trưởng phòng) → `ban_hanh` (giám đốc); `ban_hanh` có guard `not_same_actor:duyet_noi_dung` nên một người giữ cả hai vai trò không tự làm cả hai bước
- `web/`: SPA Vue 3 (Plan 03)

Ứng dụng **không có backend riêng**, mọi thao tác đi qua API của Trust Core. Dữ liệu demo dùng tổ chức hư cấu "Công ty TNHH Sao Mai".
