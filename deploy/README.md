# deploy/: hạ tầng Docker Compose

Các tệp sẽ có (Plan 01 Task 4):
- `compose.yaml`: dịch vụ và **9 mạng** theo ma trận ở spec 6.2
- `compose.p16.yaml`, `compose.p8.yaml`: hồ sơ tài nguyên
- `compose.dev-lite.yaml`: dùng khi phát triển (có `fake-av`, nhãn `DEV-ONLY`)
- `compose.test.yaml`: dịch vụ cho integration test
- `network-matrix.yaml`: **nguồn sự thật** cho phân vùng mạng và AT-01
- `caddy/`, `apisix/`, `keycloak/`, `openbao/`: cấu hình từng thành phần

Mọi image ghim bằng `@sha256:` và được ghi vào `LICENSES-THIRD-PARTY.md`.
