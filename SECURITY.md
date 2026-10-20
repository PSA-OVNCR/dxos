# Chính sách bảo mật

## Báo lỗ hổng
**Không** báo lỗ hổng bảo mật qua Issue công khai. Hãy dùng chức năng *Private vulnerability reporting* (Security → Report a vulnerability) của kho mã. Nhóm sẽ phản hồi trong vòng 72 giờ.

## Phạm vi
Mọi mã trong kho này, đặc biệt các bất biến an ninh mô tả trong thiết kế:
- I1: mọi truy cập dữ liệu đều đi qua lõi
- I2: tệp phải được kiểm dịch trước khi dùng
- I3: lõi không chứa logic nghiệp vụ
- I4: bằng chứng kiểm chứng được độc lập

## Giới hạn đã công bố
Xem mục 15 của tài liệu thiết kế: watermark chỉ để răn đe; niêm phong nội bộ không phải chữ ký số có giá trị pháp lý; neo công khai chỉ mạnh ngang số witness độc lập.
