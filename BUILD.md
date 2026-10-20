# Hướng dẫn build từ mã nguồn

> Tài liệu này được cập nhật theo từng mốc. Phần đánh dấu *(sắp có)* sẽ được bổ sung ở các task sau của Plan 01.

## Yêu cầu
| Công cụ | Phiên bản | Ghi chú |
|---|---|---|
| Python | ≥ 3.12 | CI chạy 3.12 |
| GNU Make | bất kỳ | |
| Git | bất kỳ | |
| Docker + Docker Compose v2 (≥ 2.24) | Docker Desktop hoặc Docker Engine | Cần cho `make up`; Windows nên chạy lệnh trong WSL2 |
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

## Chạy toàn bộ hệ thống
```bash
cp .env.example .env          # giá trị mẫu chạy được trên localhost; đổi mật khẩu khi lên VPS
make pin-images               # lần đầu: ghim digest image (cần mạng tới Docker Hub, quay.io)
make up PROFILE=dev-lite      # laptop; máy 8 GB dùng PROFILE=p8; máy chủ dùng p16 (mặc định)
make ps                       # chờ các container "healthy"
make netcheck                 # kiểm ma trận mạng (AT-01): mọi dòng phải PASS
make test-infra               # test sống: AT-01, AT-02 phía gateway
```

Không có `make` (Windows thuần): thay `make up PROFILE=dev-lite` bằng
`docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.dev-lite.yaml up -d --build`
và `make netcheck` bằng `python ops/netcheck.py`.

| Hồ sơ | Dùng khi | Khác biệt |
|---|---|---|
| `p16` | máy chủ 16 GB | heap JVM 1 GB, ClamAV mặc định |
| `p8` | máy 8 GB, laptop demo dự phòng | heap 512 MB, ClamAV 1 luồng, không nạp chữ ký song song |
| `dev-lite` | phát triển trên laptop | **ClamAV thay bằng `fake-av` (chỉ nhận EICAR)**; không dùng để nghiệm thu |

Người dùng dev (chỉ hồ sơ dev-lite, mật khẩu `dev-only-password`): `chuyen_vien1`, `truong_phong1`, `giam_doc1`, `van_thu1`, `nhan_vien1`, `can_bo_clb1`, `truong_clb1`, `owner_a1`, `owner_b1`, `admin1`.
Realm chỉ được nạp lần đầu; muốn nạp lại thì xóa volume `dxos_kc-db-data`.

Truy cập: `https://localhost/auth/` (Keycloak), `https://localhost/api/v1/...` (qua APISIX).
Trình duyệt sẽ cảnh báo chứng chỉ vì Caddy dùng CA nội bộ cho `localhost`.
