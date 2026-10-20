# witness/: công cụ `dxos-witness`

CLI dành cho **bên thứ ba** kiểm chứng nhật ký minh bạch của DX-OS mà không cần tin bên vận hành:
lấy STH mới nhất → kiểm chữ ký → kiểm consistency proof → lưu lịch sử.

- `src/dxos_witness/`: mã CLI (Plan 01 Task 16)
- `template/`: mẫu repo để witness độc lập tự chạy bằng GitHub Actions (spec 11.7)
