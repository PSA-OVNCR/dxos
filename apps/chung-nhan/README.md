# App B: Chứng nhận số (Tầng 2, không gian [P] + [D])

Ứng dụng nhỏ, dùng để chứng minh Trust Core **tái sử dụng được mà không sửa lõi**.

**Tuyên bố phạm vi (bắt buộc, chép nguyên văn từ Design Spec mục 14):**

> Chứng nhận số là hệ thống **quản lý và xác minh giấy chứng nhận điện tử** (chứng nhận tham gia sự kiện). Đây **không phải** hệ thống cấp chứng thư số PKI, **không phải** chữ ký số hay dịch vụ chứng thực chữ ký số, và **không** cấp văn bằng, chứng chỉ thuộc hệ thống giáo dục quốc dân. "Niêm phong số" là chữ ký điện tử chuyên dùng của tổ chức vận hành, **chưa** được chứng nhận bảo đảm an toàn (mục 25.1); với người ngoài, đối soát là kiểm tra toàn vẹn về kỹ thuật.

## Nội dung

- `manifest.yaml`: bản 1.1.0 (nhãn trường, `revoke_roles` và `erase_roles` cho `truong_clb`).
- `bpmn/cap-chung-nhan.bpmn`: quy trình một bước `phe_duyet` (`truong_clb`), kết thúc `approved` (niêm phong) hoặc `rejected`.
  "Duyệt theo lô" là việc của SPA gọi `:complete` cho nhiều task; lõi không có API lô riêng.
- `web/`: giao diện (Plan 03).
