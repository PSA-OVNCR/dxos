<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Dữ liệu demo (toàn bộ hư cấu)

Mọi thứ trong thư mục này là **hư cấu**: "Công ty TNHH Sao Mai" và "Sự kiện CLB" không có thật, họ tên, số CCCD, số điện
thoại, số tài khoản đều tự bịa, không thuộc ai; email dùng tên miền `example.invalid` (không gửi được tới đâu). Mỗi bản
ghi do seed tạo có tên bắt đầu bằng `[DEMO] ` và ghi "(hư cấu)", nên trên màn hình, trong bản ghi niêm phong hay trên
trang đối soát đều nhìn ra ngay đây là dữ liệu mẫu. Công ty Sao Mai là công ty tư nhân hư cấu nên Nghị định 30/2020/NĐ-CP
không áp dụng với nó; App A chỉ vận dụng cách làm, không tuyên bố tuân thủ (`docs/legal-mapping.md`).

| Tệp | Nội dung |
|---|---|
| `sao-mai/quy-che-chi-tieu.pdf` | PDF 1 trang: CCCD và số điện thoại hư cấu |
| `sao-mai/hop-dong-ke-toan.pdf` | PDF 1 trang: CCCD, số điện thoại và số tài khoản hư cấu |
| `sao-mai/thong-bao-tuyen-dung.pdf` | PDF 1 trang: CCCD và số điện thoại hư cấu |
| `su-kien-clb.csv` | 12 chứng nhận của "Sự kiện CLB"; UTF-8 có BOM, cột `Họ và tên`, `Sự kiện`, `Ngày cấp` (DD/MM/YYYY), `Email` |
| `make_demo_pdfs.py` | Dựng lại 3 PDF (tất định; dùng `core/tests/helpers/make_pii_pdf.py`): `python demo/make_demo_pdfs.py` |

PDF chỉ có chữ ASCII (phông Helvetica chuẩn), nên tiếng Việt trong PDF không có dấu. Mỗi số hư cấu đi kèm chú thích
"(hu cau)". Các số này để bước dò dữ liệu cá nhân (S1) có việc thật phải làm: sau khi tệp được kiểm dịch, màn hình văn bản
hiện số phát hiện theo loại và cho tải bản che.

## Nạp dữ liệu

Cần stack dev đang chạy (có realm dev; app nào được nạp thì phải đã cài, xem `BUILD.md`, mục "E2E"):

```bash
make demo-seed ARGS="--only a"                   # chỉ App A (mặc định https://localhost)
make demo-seed ARGS="--only b"                   # chỉ App B
make demo-seed                                   # cả hai (diễn tập); App B chưa cài thì bỏ qua, mã thoát 0
make demo-seed ARGS="--only a --ca-file <caddy-root.crt>"  # nếu Python chưa tin CA nội bộ của Caddy
```

### Thứ tự khi diễn thật

Kịch bản demo có đoạn **cài App B ngay trên sân khấu** (`dxos app install apps/chung-nhan`, quản trị viên thứ hai duyệt,
khán giả quét mã QR của một chứng nhận vừa niêm phong). Nếu App B đã được nạp trước, bước cài sẽ không làm gì (bản đang
hoạt động thì được bỏ qua) và đoạn diễn thành giả. Vì vậy:

1. Trước buổi demo: `make demo-seed ARGS="--only a"` (App B chưa cài, chưa có dữ liệu).
2. Trên sân khấu: cài và duyệt App B bằng CLI như kịch bản.
3. Sau khi App B hoạt động: `make demo-seed ARGS="--only b"`, rồi trưởng CLB phê duyệt một chứng nhận để có mã QR mới niêm phong.
4. Diễn tập thì chạy `make demo-seed` không cờ (nạp cả hai nếu cả hai đã cài).

Seed gọi API thật bằng người dùng dev (`chuyen_vien1` cho App A, `can_bo_clb1` cho App B). Mật khẩu dev chỉ đọc từ biến
môi trường `DXOS_E2E_PASSWORD` (mặc định `dev-only-password`), không có tham số dòng lệnh cho mật khẩu và seed không bao
giờ in nó ra. Chạy trên máy khác `localhost` phải thêm `--allow-remote` (chỉ khi stack đó có realm dev).

Chạy lại bao nhiêu lần cũng không tạo trùng: seed đọc danh sách bản ghi hiện có và bỏ qua mục có tên `[DEMO] ...` đã có;
mục làm dở (chưa có tệp, chưa bắt đầu quy trình) được làm nốt. Bản ghi demo nằm lại trên stack và sổ cái chỉ-thêm nên
không xóa được dấu vết; muốn bắt đầu lại từ đầu thì dựng lại stack dev.

## Trạng thái sau khi nạp (seed không duyệt, không niêm phong)

Duyệt và ban hành là phần diễn ở buổi demo, nên seed dừng trước các bước đó.

| App | Mục | Trạng thái | Dùng để demo |
|---|---|---|---|
| A | `[DEMO] Về việc ban hành Quy chế chi tiêu nội bộ năm 2027 (hư cấu)` | Nháp: đã có PDF, tệp đã CLEAN, **chưa** bắt đầu quy trình | Chuyên viên bấm "Bắt đầu quy trình" |
| A | `[DEMO] Hợp đồng cung cấp dịch vụ kế toán thuế năm 2027 (hư cấu)` | Đã bắt đầu quy trình, chờ `truong_phong1` duyệt nội dung | Trưởng phòng duyệt, văn thư rà PII, giám đốc ban hành, đối soát |
| A | `[DEMO] Thông báo tuyển dụng nhân viên hành chính quý I/2027 (hư cấu)` | Như trên | Bản dự phòng cho lần diễn thứ hai |
| B | 8 chứng nhận đầu của CSV (Nguyễn Văn An đến Hoàng Gia Minh) | Đã bắt đầu quy trình, chờ `truong_clb1` phê duyệt | Trưởng CLB phê duyệt, niêm phong, đối soát không cần tệp |
| B | 4 chứng nhận cuối (Ngô Thùy Nhung đến Lý Thế Sơn) | Nháp, chưa bắt đầu quy trình | Cán bộ CLB gửi duyệt trực tiếp trên màn hình |

Seed nhập CSV bằng `records:bulk`, nên với App B đã nạp, chứng nhận nằm sẵn trên stack. Màn hình "Nhập CSV" của App B chỉ
diễn lại được trên stack chưa nạp App B (chưa chạy `--only b`): chọn tệp `su-kien-clb.csv` ở đó. Trên stack đã nạp, chọn
lại tệp này sẽ tạo trùng (hệ thống không chặn trùng) nên đừng làm.
Chạy thật trên laptop là việc V44 (`docs/progress/2026-10-21-tong-ket-tien-do.md`, mục 14).
