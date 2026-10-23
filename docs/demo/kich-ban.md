<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
# Kịch bản demo 15 phút (chung kết 10/12/2026)

Nguồn yêu cầu: Đề thi PMNM OLP 2026, mục 6 "Buổi thi chung kết" (trang 7): mỗi đội trình bày **15 phút** gồm giải pháp thiết kế
và lựa chọn công nghệ; tính năng của nền tảng và bài toán ứng dụng minh họa; kết quả sản phẩm và trình diễn demo; định hướng
tiếp theo. Đề khuyến khích chạy thử trên Internet để người dùng truy cập và phản hồi. Khung thời gian lấy từ spec mục 22
và `docs/superpowers/plans/2026-10-20-dxos-00-ke-hoach-tong-the.md` mục 10, **đã cập nhật** cho những gì có từ v0.9.0: S1 (dò dữ
liệu cá nhân, bản che), S2 (Viewer), S3 (trang quản trị), S4 (tag đã ký, sao lưu).

> Trạng thái: **chưa tập lần nào** (V48) và **chưa quay video** (V47). Mọi dòng "Dự phòng" bên dưới là kế hoạch, chưa phải
> thứ đã có. Dữ liệu trong demo là **hư cấu** ("Công ty TNHH Sao Mai", "Sự kiện CLB"); mọi CCCD, số điện thoại, số tài khoản trong
> PDF mẫu đều tự bịa (`demo/README.md`).

## Câu thống nhất về pháp lý (spec 25.1, dùng nguyên văn trên slide cuối và khi giám khảo hỏi)

> Niêm phong số là chữ ký điện tử chuyên dùng do tổ chức vận hành tạo lập (Điều 22 khoản 1 điểm a Luật Giao dịch điện tử 2023). Trong nội bộ tổ chức, niêm phong dùng để xác nhận văn bản đã được duyệt và chưa bị sửa. Niêm phong **chưa** được chứng nhận "bảo đảm an toàn", nên **không** tương đương chữ ký tay (Điều 23 khoản 2) và **không phải** chữ ký số. Muốn dùng niêm phong để giao dịch với tổ chức, cá nhân bên ngoài với giá trị pháp lý, tổ chức phải đăng ký chứng nhận (Điều 25 khoản 3). Với người ngoài, cổng đối soát là công cụ **kiểm tra toàn vẹn về kỹ thuật**.

Chỉ nói đúng câu này và những gì nó cho phép. Với watermark của Viewer, nói rõ nó **chỉ để răn đe**, không ngăn được chụp màn hình.
Ba điều không được nói về sản phẩm được liệt kê ở spec 25.1 mục "Không nói" và `docs/legal-mapping.md`; nếu giám khảo hỏi
thẳng thì trả lời bằng câu trên.

## Chuẩn bị

Hai việc cuối cùng làm **ngay trước** buổi trình bày; phần còn lại làm từ hôm trước.

1. **Máy**: laptop hồ sơ p8 (`docs/capacity.md`); dựng theo `BUILD.md`, mục "Máy Ubuntu 24.04 sạch, từng lệnh" nếu là máy mới.
   Chạy `ops/doctor.sh --profile p8` một lần để chắc điều kiện máy.
2. **OpenBao**: mở khóa sau mỗi lần khởi động lại (`docs/runbook-openbao.md`, mục 2). Khi khóa, niêm phong bị từ chối (fail-closed).
3. **Dữ liệu**: `make demo-seed ARGS="--only a"` (3 văn bản "Công ty TNHH Sao Mai" kèm PDF có CCCD hư cấu). **Chưa** nạp App B: đoạn
   cài App B trên sân khấu cần App B chưa có (`demo/README.md`, "Thứ tự khi diễn thật").
4. **Neo**: `dxos --server https://<DXOS_ADMIN_HOST> anchor run` ngay sau lần niêm phong đầu của buổi diễn (đoạn 4:30–6:00),
   vì cổng đối soát đã ghim repo neo chỉ báo "đã đối chiếu" khi STH phủ niêm phong đã lên repo neo **và** CDN của
   raw.githubusercontent.com đã cập nhật (trễ tới khoảng 5 phút, `docs/runbook-anchor.md` mục 3). Trước lúc đó cổng hiện
   **"Hợp lệ — chưa neo công khai"**: đó là trạng thái trung thực, không phải lỗi; nói rõ điều này khi nó xuất hiện.
5. **Hai quản trị viên** (`admin1`, `admin2`) đăng nhập sẵn ở hai cửa sổ, vì cài app cần bốn mắt (người duyệt khác người nộp).
6. **60 phút trước giờ diễn**: `ops/demo_preflight.sh` (OpenBao đã mở khóa, health xanh, STH mới nhất đã neo, mạng, dữ liệu demo).
   Mã thoát 1 thì **không diễn** cho tới khi sửa xong; OpenBao khóa thì làm theo lệnh nó in ra. `--strict` trong lần tập cuối.
7. Video dự phòng (bảng cuối) copy sẵn vào laptop **và** USB; tắt thông báo; sạc pin; ảnh chụp trang repo neo mở sẵn.

## Khung 15 phút

| Thời gian | Màn hình | Nội dung nói và làm | Bằng chứng | Dự phòng |
|---|---|---|---|---|
| 0:00–2:00 | Slide | Luận điểm "tự kiểm chứng": nền tảng tự chứng minh dữ liệu chưa bị sửa, không cần tin người vận hành. Ba tầng (lõi headless, hai app, người dùng); mạng phân vùng (AT-01, `make netcheck`) | Ảnh `make netcheck` toàn PASS | Slide ảnh tĩnh |
| 2:00–3:00 | Trình duyệt | Đăng nhập **một lần** (Keycloak SSO), vào được cả App A và App B; mở console Keycloak (giao diện quản trị của dịch vụ nguồn mở) | — | V1 |
| 3:00–4:30 | App A, rồi trang quản trị | Tải tệp **EICAR** vào văn bản: ClamAV chặn, hiện **"Nhiễm mã độc — đã cách ly"**. Mở `https://<DXOS_ADMIN_HOST>/ui/` (S3), màn hình Cách ly cho thấy tệp ở phía quản trị | Lá `object.infected` | V2 |
| 4:30–6:00 | App A | Văn bản `[DEMO] Hợp đồng cung cấp dịch vụ kế toán thuế năm 2027 (hư cấu)`, đã có PDF sạch. **S1**: hệ thống báo "Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)"; người đọc thường chỉ tải được **bản che** (CCCD, số điện thoại, số tài khoản đã bị che ngay trong PDF, dạng ảnh), bản gốc chỉ cho vai trò `reveal_pii` (giám đốc, văn thư). Trưởng phòng duyệt, văn thư xác nhận đã rà, giám đốc ban hành: **niêm phong + mã QR**. Ngay sau đó chạy `dxos anchor run` ở cửa sổ khác | `pii.detected`, `pii.reviewed`, `field.revealed`, `record.sealed` | V3 |
| 6:00–8:00 | Terminal | **Bảng thử vượt rào** (`make vuot-rao`): tự duyệt văn bản của mình, gọi thẳng S3/core-db, IDOR, manifest nới chính sách. Tất cả bị chặn; cuối bảng là danh sách lá `policy.denied` | `policy.denied` | V4 |
| 8:00–10:00 | CLI, trang quản trị, App B | Cài **App B** ngay trên sân khấu: `dxos --server https://<DXOS_ADMIN_HOST> app install apps/chung-nhan` (admin1, in diff quyền), rồi **admin2 duyệt** (`dxos ... app approve chung-nhan 1.1.0` hoặc nút "Duyệt phiên bản này" ở `/ui/`; người nộp tự duyệt bị từ chối). Không sửa dòng nào của `core/` (AT-13). Sau khi App B chạy: `make demo-seed ARGS="--only b"`, trưởng CLB phê duyệt một chứng nhận; **khán giả quét QR** | AT-13: diff `core/` rỗng; `app.installed` | V5 |
| 10:00–12:00 | Terminal | Sửa **một dòng** của sổ cái trong DB: `verify` báo lệch. Dựng lại toàn bộ log: witness báo **REWRITE_DETECTED** (so với STH đã neo) | AT-15, AT-16 | V6 |
| 12:00–14:00 | GitHub | Repo công khai, CI xanh, Release (không zip/rar), SBOM, `LICENSES-THIRD-PARTY.md`, witness độc lập, issue từ người dùng thử. Nhắc S4: triển khai chỉ nhận **tag đã ký** và tự quay lui khi health hỏng; sao lưu mã hóa (`ops/backup.sh`) và diễn tập khôi phục (`ops/at21_drill.sh`) | — | Ảnh chụp |
| 14:00–15:00 | Slide | Giới hạn: watermark **chỉ để răn đe**; niêm phong là chữ ký điện tử chuyên dùng, không phải chữ ký số (đọc câu thống nhất ở trên); X3 và X4 (root VPS, admin repo neo); dò dữ liệu cá nhân là heuristic, không OCR. Định hướng: App của cộng đồng qua manifest, 3-of-5 cho OpenBao, witness độc lập thêm | — | Slide |

### Ghi chú theo hồ sơ máy

- **S2 (Viewer) chỉ có ở p16**: laptop p8 **không có Viewer** (spec 16.1; `COMPOSE_PROFILES=viewer` bị p8 bỏ qua). Trên p8 chỉ diễn bản che tải
  về ở đoạn 4:30–6:00; muốn cho xem trang PDF có watermark thì dùng VPS p16 (V40) hoặc ảnh chụp, và nói rõ đó là ảnh.
- **Thiếu giờ thì cắt theo thứ tự** (spec 18.3): cảnh Viewer, rồi màn hình Cách ly ở `/ui/`, rồi bước văn thư rà PII. Không cắt: EICAR,
  niêm phong, bảng vượt rào, cài App B, phát hiện sửa log.
- **QR của App B** vừa niêm phong có thể còn hiện "Hợp lệ — chưa neo công khai" vì STH chưa phủ nó: đó là câu trả lời đúng. QR của
  văn bản App A (đã `anchor run` từ 6:00) là cái nên đã "đã đối chiếu repo neo" nếu CDN kịp; quét cả hai và giải thích sự khác nhau.
- Mã QR trỏ tới `https://<DXOS_DOMAIN>/apps/verify/#<mã niêm phong>`. Nếu mạng hội trường chặn, trang đối soát vẫn chạy trên máy demo (chọn tệp PDF để
  băm tại trình duyệt).

## Video dự phòng

Quay ở M5 (việc V47), mỗi video bấm giờ theo đoạn tương ứng, có phụ đề tiếng Việt, **không thu bí mật** (mật khẩu, token, unseal key,
`.env`). Lưu trên laptop và USB; không commit vào repo (nặng); ghi tên tệp, độ dài và băm sha256 vào `docs/progress/` khi quay xong.
Tên "V1 đến V6" ở đây là video, **khác** với 10 kịch bản của bảng vượt rào (cũng đánh số V1 đến V10 trong `make vuot-rao`) và khác bảng
việc V37 trở đi ở `docs/progress/2026-10-21-tong-ket-tien-do.md`.

| # | Đoạn | Quay cái gì | Độ dài |
|---|---|---|---|
| V1 | 2:00–3:00 | Đăng nhập một lần vào App A và App B; mở console Keycloak | ≤ 60 giây |
| V2 | 3:00–4:30 | Tải EICAR, "Nhiễm mã độc — đã cách ly", màn hình Cách ly ở `/ui/` | ≤ 90 giây |
| V3 | 4:30–6:00 | Bản che có CCCD bị che, duyệt hai cấp, văn thư rà, ban hành, niêm phong, quét QR | ≤ 90 giây |
| V4 | 6:00–8:00 | Bảng thử vượt rào chạy đủ 10 kịch bản và danh sách `policy.denied` | ≤ 120 giây |
| V5 | 8:00–10:00 | Cài App B bằng CLI, admin thứ hai duyệt, quét QR chứng nhận | ≤ 120 giây |
| V6 | 10:00–12:00 | Sửa một dòng sổ cái, `verify` báo lệch; dựng lại log, witness báo REWRITE_DETECTED | ≤ 120 giây |

## Lịch tập

Tập tối thiểu **5 lần** (V48): 05/12, 07/12, 08/12 (2 lần), 09/12. Mỗi lần bấm giờ từng đoạn, ghi đoạn nào trễ, chạy `ops/demo_preflight.sh`
trước lần tập và `--strict` ở lần cuối, và thử đúng một sự cố (OpenBao khóa, mất mạng) để tập chuyển sang video. Ghi kết quả vào
`docs/progress/`. Sau mỗi lần tập, dựng lại stack hoặc dùng bản ghi `[DEMO]` còn lại để lần sau không diễn lại trên dữ liệu đã niêm phong.
