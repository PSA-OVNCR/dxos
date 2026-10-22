# tests/attack/: "bảng thử vượt rào"

Các kịch bản tấn công dùng khi demo và kiểm thử: tự duyệt văn bản của mình, đọc chéo người dùng, gọi bằng token sai app,
admin đọc dữ liệu app, sửa văn bản đã niêm phong, ban hành khi chưa rà PII, gửi tệp tới cổng đối soát, tải EICAR,
manifest nới chính sách, duyệt bằng task của app khác. Plan 03 (S9.1, H11).

Kịch bản nằm trong **`ops/vuot_rao.py`** (chạy bằng `make vuot-rao` hoặc `python ops/vuot_rao.py`), không phải trong
thư mục này. Test của chính script nằm ở `tests/ops/test_vuot_rao.py` (stack giả, không cần Docker). Ma trận kỳ vọng
V1..V10 và AT tương ứng ở cuối `docs/acceptance.md`. Kết quả chạy trên stack dev 22/10/2026 (10/10, V28): `docs/progress/2026-10-22-web-live.md`.
