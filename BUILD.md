# Hướng dẫn build từ mã nguồn

> Tài liệu này được cập nhật theo từng mốc. Phần đánh dấu *(sắp có)* sẽ được bổ sung ở các task sau của Plan 01.

## Yêu cầu
| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | ≥ 3.12 | CI chạy 3.12 |
| GNU Make | bất kỳ | |
| Git | bất kỳ | |
| Docker + Docker Compose v2 | *(sắp có)* | Cần cho `make up` |
| Node.js | *(sắp có)* | Cần cho SDK và ứng dụng Tầng 2 |

Toàn bộ công cụ build đều là phần mềm nguồn mở.

## Build và kiểm thử phần đã có
```bash
git clone <địa-chỉ-repo> dxos && cd dxos
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
make dev-install
make check
```
Kết quả mong đợi: `ruff` không báo lỗi; `reuse lint` in dòng `Congratulations!`; toàn bộ test đơn vị đạt.

## Cấu hình
Mọi cấu hình đặt qua biến môi trường (xem `.env.example`). Không cần sửa mã nguồn để cấu hình.

## Chạy toàn bộ hệ thống *(sắp có, Plan 01 Task 4)*
```bash
cp .env.example .env   # rồi điền giá trị
make up
```
