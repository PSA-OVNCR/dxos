# Checklist AT-26 cho trưởng nhóm (V46, thay V31)

**AT-26** (Design Spec, bảng AT; hạng mục H13, R-5): *một người ngoài đội làm theo hướng dẫn H13, tạo được một app mới qua
manifest mà không sửa `core/`.* Hướng dẫn: [docs/tutorial-app-30-phut.md](tutorial-app-30-phut.md). Đây là kiểm thử **thủ
công**; kết quả ghi vào `docs/progress/` (mục 6) rồi cập nhật dòng AT-26 ở [docs/acceptance.md](acceptance.md).

Nhãn: **[BB]** bắt buộc theo Design Spec; **[ĐX]** đề xuất của đội, trưởng nhóm quyết định.

## 0. Làm mới ở M5 (Plan 04 Task 16): việc V46 thay V31

AT-26 giờ là việc **V46** (thay V31 của Plan 03), chạy ở **M5, trên bản nộp `v1.0.0`** chứ không trên commit tùy ý: người thử làm theo
hướng dẫn trên đúng thứ giám khảo sẽ thấy. Hai thay đổi so với bản đầu của checklist:

- **Máy thử là Ubuntu 24.04 sạch** khi có thể, cùng máy hay cùng loại máy của AT-23 (V45, `BUILD.md`, mục "Máy Ubuntu 24.04 sạch, từng lệnh").
  Cho người thử chạy `ops/doctor.sh` trước (chỉ đọc, liệt kê điều kiện thiếu); biên bản ghi đầu ra của nó. AT-23 và AT-26 có thể do **cùng một người** làm
  liền nhau trên cùng một máy, nhưng ghi hai biên bản riêng.
- **Bản thử**: `git checkout v1.0.0` (tag ký, V50). Chưa có tag thì thử trên `main` và ghi rõ commit, nhưng AT-26 chỉ được đóng sau khi chạy lại trên tag.

Trạng thái hiện tại: **chưa tổ chức** (V46). Mọi dòng "*chưa kiểm ở cloud — kiểm trong AT-26*" trong hướng dẫn còn nguyên.

## 1. Chọn người thử

- **[BB]** Người **ngoài đội** (không phải thành viên PSA_OVNCR, chưa tham gia viết `core/`, SDK hay hai app).
- **[ĐX]** Biết dùng terminal, Git và Docker ở mức cơ bản; chưa từng đọc mã lõi. Một người là đủ; hai người thì mỗi người
  một biên bản riêng.
- **[ĐX]** Chỉ ghi tên người thử khi họ đồng ý; nếu không, dùng mã ẩn danh (ví dụ `NT-01`). Không chép thông tin cá nhân khác.

## 2. Yêu cầu máy (máy của người thử, không phải máy đội)

| Mục | Yêu cầu | Nguồn |
|---|---|---|
| Hệ điều hành | Ubuntu 24.04 (ưu tiên, V45/V46); Linux khác, macOS hoặc Windows với WSL2 cũng được nhưng ghi lại | [BUILD.md](../BUILD.md) |
| Docker | Docker Engine hoặc Docker Desktop, Compose v2 ≥ 2.24, chạy được hồ sơ `dev-lite` | BUILD.md |
| Công cụ | Git, GNU Make, Python 3.12. **Không cần Node** (`make web-build` build trong container) | BUILD.md |
| Bộ nhớ | Hồ sơ `dev-lite` cho laptop; nếu máy chỉ có 8 GB thì dùng `PROFILE=p8` (máy 16 GB: `p16`). **Ghi lại RAM và CPU thực tế** vào biên bản | BUILD.md |
| Mạng | Tới Docker Hub, quay.io, ghcr.io, PyPI và npm registry (lần đầu kéo image và gói) | |
| Đồng hồ | Chính xác (lệch đồng hồ làm đăng nhập OIDC bị từ chối) | tutorial |
| Trình duyệt | Chromium, Firefox hoặc Safari bản mới; có điện thoại để quét QR (không bắt buộc) | |

Hồ sơ `dev-lite` dùng `fake-av` thay ClamAV: **được phép** cho AT-26 (không kiểm tệp đính kèm) nhưng ghi rõ trong biên bản.

## 3. Trưởng nhóm chuẩn bị (trước ngày thử)

1. Chọn bản thử và ghi lại: `git rev-parse HEAD` (đã `git checkout v1.0.0`, mục 0). Commit phải chứa `docs/tutorial-app-30-phut.md`, `examples/so-muon-sach/`
   và `make web-build` đã gồm `so-muon-sach` (kiểm: `grep so-muon-sach ops/build_web.sh`).
2. Trên máy của bạn, chạy qua **một lần** toàn bộ hướng dẫn (bạn là người thử "không tính điểm") để mọi dòng
   "*chưa kiểm ở cloud — kiểm trong AT-26*" thành đã kiểm, hoặc ghi lại chỗ sai. Sửa hướng dẫn trước khi mời người ngoài.
3. Quyết định hai giá trị người thử sẽ cần mà hướng dẫn không tự sinh: tên tổ chức `DXOS_ORG_NAME` cho `.env`, và cách mở khóa
   OpenBao (hướng dẫn trỏ tới BUILD.md và [docs/runbook-openbao.md](runbook-openbao.md)). Ghi chúng vào biên bản.
4. Chuẩn bị chỗ ngồi/hình thức quan sát: bạn **chỉ quan sát và bấm giờ**, không chỉ đường. Cho phép quay màn hình nếu người thử đồng ý.

## 4. Trong buổi thử

1. **Chỉ đưa cho họ hai thứ**: địa chỉ repo `https://github.com/PSA-OVNCR/dxos` và đường dẫn tài liệu
   `docs/tutorial-app-30-phut.md`. Không giải thích thêm, không gửi BUILD.md hay mã nguồn khác.
2. Bấm giờ từ lúc họ mở tài liệu. Ghi **giờ bắt đầu và kết thúc từng mục** của bảng ở mục 6. Chờ máy (kéo image, `make web-build`)
   thì ghi **riêng** cột "chờ máy" để thấy được thời gian thao tác thật.
3. Ghi **từng chỗ vướng** (mục 5). Họ tự gỡ được thì ghi cách gỡ; phải nhờ bạn thì ghi đó là "cần trợ giúp" và bạn đã nói gì.
4. Nếu họ bỏ cuộc, ghi lý do và bước đang làm; **không** tính là đạt.

### Phần B: tự tạo app của riêng họ (khoảng 10 phút, sau khi xong năm bước)

AT-26 đòi "một app **mới**". Sau bước (25–30') yêu cầu người thử:

1. Sao chép `examples/so-muon-sach` sang thư mục mới (ví dụ `examples/<tên-họ-chọn>`), **đổi** `app.id`, tên collection, tên
   role và ít nhất một trường theo ý họ (ví dụ sổ mượn thiết bị), tăng `version` nếu cần.
2. Kiểm cục bộ bằng đoạn Python trong hướng dẫn (mục 5–15'), rồi
   `dxos --ca-file caddy-root.crt app install <thư mục>` và `dxos --ca-file caddy-root.crt app approve <id> <version>`
   (admin thứ hai, đã `dxos --ca-file caddy-root.crt login`), rồi `dxos --ca-file caddy-root.crt app list` phải thấy app mới ở
   trạng thái `ACTIVE`. `--ca-file` không được CLI lưu nên phải có ở **mọi** lệnh khi dùng `https://admin.localhost`.
3. Giao diện của Phần B là tùy chọn (SPA ví dụ gắn với `so-muon-sach`). Nếu làm, xem danh sách đổi tên dưới đây.

**Danh sách đổi tên khi sao chép ví dụ** (sót một chỗ là lỗi `422 manifest-invalid` hoặc app không hoạt động):

- `app.id` trong `manifest.yaml` (khớp `^[a-z][a-z0-9-]{1,30}$`) và tên thư mục.
- `id` của `<process>` trong BPMN phải là `<app.id mới>.<tên>`; `targetNamespace` nên đổi theo.
- Tên role: `roles`, `access`, `policies.*`, `workflow.tasks.<t>.role` **và** `flowable:candidateGroups="app:<app.id mới>:<role>"`
  trong BPMN phải cùng một bộ tên.
- `id` của `userTask` trong BPMN phải trùng khóa trong `workflow.tasks` (và `gateway`, `sequenceFlow` đổi theo nếu bạn đổi tên task).
- Tên collection và trường: `policies.seal.public_fields` chỉ được liệt kê trường có `public: true`.
- Đường dẫn trong lệnh và đoạn Python của hướng dẫn đang cứng `examples/so-muon-sach` (và `so-muon-sach 1.0.0` ở `diff`/`approve`):
  thay bằng thư mục và `<id> <version>` của bạn.
- Nếu làm giao diện: sao chép `examples/so-muon-sach/web`, đổi tên gói npm, `APP`, `COL`, `BASE` ở `src/session.ts`, `base` ở
  `vite.config.ts`; thêm thư mục vào `workspaces` của `package.json` và một mục `<tên>:examples/<tên>/web/dist` vào `DIST_MAP`
  của `ops/build_web.sh` (ngoài `core/`, không vi phạm P1).
- Sau khi đổi, chạy lại: kiểm cục bộ, rồi `git diff --stat <commit> -- core/ deploy/apisix/` phải rỗng.

## 5. Ghi chỗ vướng

**[BB] Không bao giờ ghi bí mật vào biên bản, ảnh hay bản quay mà bạn sẽ commit vào `docs/progress/` hay `docs/evidence/`:** khóa
unseal và token của OpenBao, giá trị bí mật trong `.env` (mật khẩu, secret client, `OPENBAO_CORE_TOKEN`), mật khẩu quản trị
Keycloak (`KEYCLOAK_ADMIN_PASSWORD`), mã thiết bị và liên kết của lệnh đăng nhập CLI (device flow), token `DXOS_TOKEN`. Cắt hoặc làm mờ
ảnh chụp console Keycloak và terminal trước khi lưu; chép lỗi bằng văn bản đã bỏ các giá trị đó. Nghi ngờ lộ thì xoay bí mật
đó, không chỉ xóa tệp.

Ghi mỗi chỗ vướng một dòng trong bảng "Vướng" của biên bản: bước, điều bạn thấy (chép nguyên văn thông báo lỗi, đính ảnh nếu
có), nguyên nhân (tài liệu thiếu/sai, môi trường, hiểu nhầm), cách gỡ, mức độ: **chặn** (không đi tiếp được), **chậm** (mất
thêm thời gian), **khó hiểu** (làm được nhưng phải đoán). Mọi dòng "chặn" và "chậm" phải thành một sửa tài liệu hoặc một
issue trước khi đóng AT-26.

## 6. Xác nhận `core/` không đổi và ghi biên bản

Sau buổi thử, trên máy người thử, ở thư mục gốc repo:

```bash
git diff --stat <commit trước khi bắt đầu> -- core/ deploy/apisix/
git status --short -- core/ deploy/apisix/
```

**Cả hai phải in rỗng** **[BB]**. Chụp màn hình hoặc chép nguyên đầu ra vào biên bản. Nếu khác rỗng: AT-26 không đạt; xem người thử
đã sửa gì và vì sao (thường là hướng dẫn thiếu một bước).

**Nơi lưu.** Biên bản: `docs/progress/<yyyy-mm-dd>-at26.md` (cùng thư mục với các báo cáo tiến độ khác, theo
[docs/progress/README.md](progress/README.md)). Ảnh và log: `docs/evidence/at26-<mô-tả>.png` hoặc `.txt`; thêm một dòng vào bảng
của [docs/evidence/README.md](evidence/README.md). Sau đó sửa dòng AT-26 trong [docs/acceptance.md](acceptance.md) (cột "Trạng thái":
ghi ngày, tên biên bản). Cuối cùng cập nhật các dấu "*chưa kiểm ở cloud — kiểm trong AT-26*" trong hướng dẫn thành "đã kiểm" cho
những lệnh người thử chạy thật thành công, kèm ngày.

### Mẫu biên bản

Chép khối dưới đây vào `docs/progress/<yyyy-mm-dd>-at26.md` và điền.

```markdown
# AT-26: người ngoài đội làm theo hướng dẫn "app trong 30 phút" — <yyyy-mm-dd>

| Mục | Giá trị |
|---|---|
| Người thử | <tên (đã đồng ý) hoặc mã ẩn danh>; quan hệ với đội: ngoài đội |
| Người quan sát | <tên trưởng nhóm> |
| Commit thử | <40 ký tự hex> (`git rev-parse HEAD`) |
| Máy | <hệ điều hành, CPU, RAM, ổ đĩa>; Docker <phiên bản>; hồ sơ compose: <dev-lite/p8/p16> |
| `DXOS_ORG_NAME`, mở khóa OpenBao | <giá trị đã dùng; ai mở khóa> |
| Tài liệu đưa cho người thử | docs/tutorial-app-30-phut.md (chỉ tài liệu này) |

## Thời gian

| Mục | Mốc hướng dẫn | Bắt đầu | Kết thúc | Thao tác (phút) | Chờ máy (phút) | Xong? |
|---|---|---|---|---|---|---|
| 1. Dựng stack dev-lite | 0–5' | | | | | |
| 2. Viết manifest và BPMN | 5–15' | | | | | |
| 3. Nộp, diff, duyệt bốn mắt | 15–20' | | | | | |
| 4. Gán vai trò trong Keycloak | 20–25' | | | | | |
| 5. Giao diện, tạo phiếu, duyệt, QR | 25–30' | | | | | |
| Phần B: app riêng của người thử | ~10' | | | | | |
| **Tổng** | 30' | | | | | |

## Vướng

| # | Bước | Điều đã thấy (nguyên văn lỗi, ảnh) | Nguyên nhân | Cách gỡ / ai giúp | Mức độ (chặn/chậm/khó hiểu) | Sửa tài liệu hay issue |
|---|---|---|---|---|---|---|
| 1 | | | | | | |

## Kết quả kiểm

| Kiểm | Kết quả | Minh chứng |
|---|---|---|
| App mới `ACTIVE` (`dxos --ca-file caddy-root.crt app list`) qua manifest, người duyệt khác người nộp | | |
| Tạo phiếu, duyệt bởi người khác, niêm phong, đối soát QR (bước 5) | | |
| `git diff --stat <commit> -- core/ deploy/apisix/` rỗng | | |
| `git status --short -- core/ deploy/apisix/` rỗng | | |
| Người thử cần trợ giúp ngoài tài liệu? (số lần, nội dung) | | |

## Kết luận

- AT-26: **đạt / không đạt** — <lý do>.
- Thời gian thao tác tổng: <phút> (mục tiêu của tên tài liệu: 30 phút). [ĐX] Vượt mục tiêu thì ghi để sửa tài liệu; đạt AT-26
  về chức năng không phụ thuộc thời gian, trừ khi trưởng nhóm quyết định khác.
- Việc phải làm sau buổi thử: <danh sách sửa tài liệu/issue, người phụ trách, hạn>.
```

## 7. Tiêu chí kết luận

- **Đạt [BB]:** người ngoài đội, làm theo tài liệu, có một app mới `ACTIVE` bằng manifest do họ viết/sửa, và hai lệnh kiểm `core/`
  ở mục 6 rỗng.
- **[ĐX]** Ghi "đạt, có điều kiện" nếu phải nhờ bạn quá một lần cho cùng một bước (tài liệu thiếu): sửa tài liệu rồi thử lại
  bước đó với một người khác nếu còn thời gian.
- **Không đạt:** người thử bỏ cuộc, hoặc `core/` hay `deploy/apisix/` bị đổi.

## 8. Dọn dẹp sau buổi thử

`make down` (xóa volume nếu muốn dựng lại từ đầu); gỡ vai trò `app:so-muon-sach:*` khỏi người dùng dev trong console Keycloak nếu
dùng chung realm. Nếu thử trên VPS, người dùng dev tạm phải gỡ theo [docs/evidence/README.md](evidence/README.md), mục "Người dùng
dev tạm trên VPS".
