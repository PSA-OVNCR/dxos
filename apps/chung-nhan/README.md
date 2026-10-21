# App B: Chứng nhận số (Tầng 2, không gian [P] + [D])

Ứng dụng nhỏ, dùng để chứng minh Trust Core **tái sử dụng được mà không sửa lõi**.

**Tuyên bố phạm vi (bắt buộc, chép nguyên văn từ Design Spec mục 14):**

> Chứng nhận số là hệ thống **quản lý và xác minh giấy chứng nhận điện tử** (chứng nhận tham gia sự kiện). Đây **không phải** hệ thống cấp chứng thư số PKI, **không phải** chữ ký số hay dịch vụ chứng thực chữ ký số, và **không** cấp văn bằng, chứng chỉ thuộc hệ thống giáo dục quốc dân. "Niêm phong số" là chữ ký điện tử chuyên dùng của tổ chức vận hành, **chưa** được chứng nhận bảo đảm an toàn (mục 25.1); với người ngoài, đối soát là kiểm tra toàn vẹn về kỹ thuật.

## Nội dung

- `manifest.yaml`: bản 1.1.0 (nhãn trường, `revoke_roles` và `erase_roles` cho `truong_clb`).
- `bpmn/cap-chung-nhan.bpmn`: quy trình một bước `phe_duyet` (`truong_clb`), kết thúc `approved` (niêm phong) hoặc `rejected`.
  "Duyệt theo lô" là việc của SPA gọi `:complete` cho nhiều task; lõi không có API lô riêng.
- `web/`: giao diện SPA (Vue 3, gói npm `dxos-app-chung-nhan`, phục vụ ở `/apps/chung-nhan/`), chỉ gọi API Tầng 2 của lõi:
  danh sách và chi tiết chứng nhận, **nhập từ CSV** (bên dưới), **duyệt theo lô**, niêm phong (mã QR, đối soát, thu hồi), xóa email
  của người nhận và **trang in** A4 ngang (chỉ trường công khai và tuyên bố phạm vi ở trên, không bao giờ có email).
  Kiểm thử: `npm run test -w dxos-app-chung-nhan`; tệp CSV mẫu và lệnh tạo ở `web/test/fixtures/README.md`.

## Nhập từ CSV

Dòng đầu là tiêu đề, dùng đúng nhãn của manifest (`Họ và tên`, `Sự kiện`, `Ngày cấp`, `Email`; tên trường như `ho_ten` cũng được,
không phân biệt hoa thường). Ngày viết `DD/MM/YYYY`. Số chứng nhận do lõi tự cấp nên không có cột. Giao diện đọc được tệp Excel lưu
dạng UTF-8 (có hoặc không BOM), Windows-1258 (Excel tiếng Việt cũ) và UTF-16 ("Unicode Text"), phân cách `,` `;` hoặc TAB, họ tên ở
dạng NFC hay NFD. Nếu có dòng lỗi (thiếu trường bắt buộc, ngày sai, ký tự không đọc được do sai bảng mã), danh sách lỗi theo số dòng
trong tệp hiện ra và chưa có gì được gửi lên máy chủ. Khi tạo, mỗi lần gửi tối đa 500 dòng; lõi vẫn kiểm tra lại từng dòng.
