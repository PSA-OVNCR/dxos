**Diễn giải kỹ thuật của đội, không phải tư vấn pháp lý.**

# Bản chất pháp lý của niêm phong số: ánh xạ cơ chế ↔ điều khoản

Tài liệu này giải thích niêm phong số của DX-OS Trust Core **là gì và không là gì** theo các văn bản pháp luật được
dẫn. Nội dung lấy từ spec mục 25.1, 25.2 và 25.5 (bản 1.0.3,
[`docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`](superpowers/specs/2026-10-20-dxos-trust-core-design.md));
khi lệch nhau, spec mục 25 thắng.

Ngày đối chiếu ghi trong các bảng là ngày agent đọc các điều được dẫn (21/10/2026, spec 25 và 25.6). Thành viên đội đọc
lại toàn văn từng điều trước khi đưa câu chữ vào README và slide, rồi ghi tên và ngày đọc ở
[mục cuối](#thành-viên-đã-đọc-toàn-văn).

## Câu thống nhất

Dùng nguyên văn cho spec, README, slide và trang đối soát (spec 25.1):

> Niêm phong số là chữ ký điện tử chuyên dùng do tổ chức vận hành tạo lập (Điều 22 khoản 1 điểm a Luật Giao dịch điện tử 2023). Trong nội bộ tổ chức, niêm phong dùng để xác nhận văn bản đã được duyệt và chưa bị sửa. Niêm phong **chưa** được chứng nhận "bảo đảm an toàn", nên **không** tương đương chữ ký tay (Điều 23 khoản 2) và **không phải** chữ ký số. Muốn dùng niêm phong để giao dịch với tổ chức, cá nhân bên ngoài với giá trị pháp lý, tổ chức phải đăng ký chứng nhận (Điều 25 khoản 3). Với người ngoài, cổng đối soát là công cụ **kiểm tra toàn vẹn về kỹ thuật**.

## Căn cứ đã đối chiếu

Ba cột đầu chép từ bảng "Căn cứ đã đối chiếu" của spec 25.1; link văn bản gốc lấy từ spec 25.6.

| Văn bản | Điều | Nội dung dùng trong thiết kế | Văn bản gốc | Ngày đối chiếu |
|---|---|---|---|---|
| Luật Giao dịch điện tử 2023 (20/2023/QH15) | Đ22 k1 điểm a | Chữ ký điện tử chuyên dùng do cơ quan, tổ chức tạo lập cho hoạt động của mình | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |
| Luật Giao dịch điện tử 2023 (20/2023/QH15) | Đ22 k2 | 4 yêu cầu: (a) xác nhận chủ thể ký và sự chấp thuận; (b) chỉ gắn với nội dung được chấp thuận; (c) chỉ thuộc kiểm soát của chủ thể ký lúc ký; (d) kiểm tra được theo điều kiện các bên thỏa thuận | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |
| Luật Giao dịch điện tử 2023 (20/2023/QH15) | Đ23 k1–k3 | Không bị phủ nhận chỉ vì ở dạng điện tử; chỉ chữ ký chuyên dùng **bảo đảm an toàn** và chữ ký số mới tương đương chữ ký tay và thay được yêu cầu "tổ chức xác nhận" | [Điều 23](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-23) | 21/10/2026 |
| Luật Giao dịch điện tử 2023 (20/2023/QH15) | Đ25 k1, k3 | Không được kinh doanh chữ ký chuyên dùng; dùng để giao dịch với bên ngoài hoặc muốn được công nhận bảo đảm an toàn thì phải đăng ký chứng nhận | [Điều 25](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-25) | 21/10/2026 |
| Nghị định 23/2025/NĐ-CP | Đ4, Đ5, Đ7 k4 | Chứng thư chữ ký điện tử chuyên dùng; 8 nội dung của chứng thư; thời hạn 10 năm. Dùng làm khung tham khảo cho tuyên bố khóa (25.3), **không** gọi tuyên bố khóa là chứng thư | [Nghị định 23/2025/NĐ-CP](https://thuvienphapluat.vn/van-ban/thue-phi-le-phi/decree-23-2025-nd-cp-digital-signatures-and-trust-services-649650.aspx) | 21/10/2026 |
| Nghị định 30/2020/NĐ-CP | Đ2 | Áp dụng cho cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước. Công ty tư nhân (tổ chức hư cấu "Công ty TNHH Sao Mai") **không** thuộc diện; App A chỉ **vận dụng** | [Nghị định 30/2020/NĐ-CP](https://thuvienphapluat.vn/van-ban/bo-may-hanh-chinh/decree-30-2020-nd-cp-records-management-472077.aspx) | 21/10/2026 |
| Nghị định 30/2020/NĐ-CP | Đ5 | Văn bản điện tử có giá trị như bản gốc giấy khi được **ký số**. App A không đạt mức này | [Nghị định 30/2020/NĐ-CP](https://thuvienphapluat.vn/van-ban/bo-may-hanh-chinh/decree-30-2020-nd-cp-records-management-472077.aspx) | 21/10/2026 |
| Nghị định 30/2020/NĐ-CP | Đ15 k1 | Số văn bản bắt đầu từ 01 mỗi năm, duy nhất trong năm (25.4) | [Nghị định 30/2020/NĐ-CP](https://thuvienphapluat.vn/van-ban/bo-may-hanh-chinh/decree-30-2020-nd-cp-records-management-472077.aspx) | 21/10/2026 |
| Nghị định 30/2020/NĐ-CP | Đ21 k2 điểm a | Văn thư kiểm tra tính xác thực và toàn vẹn của văn bản điện tử đến (25.4) | [Nghị định 30/2020/NĐ-CP](https://thuvienphapluat.vn/van-ban/bo-may-hanh-chinh/decree-30-2020-nd-cp-records-management-472077.aspx) | 21/10/2026 |
| Luật Bảo vệ dữ liệu cá nhân 2025 (91/2025/QH15) | Đ4 k1 điểm d; Đ14 k1–k6; Đ19 k1 | Quyền yêu cầu xóa; các trường hợp xóa và ngoại lệ; xóa an toàn; thông báo khi không xóa được (25.2) | [Luật 91/2025/QH15](https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Law-91-2025-QH15-Personal-Data-Protection-665440.aspx) | 21/10/2026 |

Hai link của Nghị định 23/2025 và 30/2020 là bản tiếng Anh trên thuvienphapluat.vn, đúng như spec 25.6 ghi; spec chưa
có link tới bản tiếng Việt của hai nghị định này.

## Ánh xạ 4 yêu cầu của Điều 22 khoản 2

Cột "Cơ chế" chép nguyên văn spec 25.1.

| Yêu cầu (Luật Giao dịch điện tử 2023, Đ22 k2) | Cơ chế của DX-OS Trust Core | Văn bản gốc | Ngày đối chiếu |
|---|---|---|---|
| (a) xác nhận chủ thể ký và sự chấp thuận | payload ghi `app_id`; ledger ghi người duyệt (`task.completed`). | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |
| (b) chỉ gắn với nội dung được chấp thuận | chữ ký phủ `record_digest` và sha256 các tệp. | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |
| (c) chỉ thuộc kiểm soát của chủ thể ký lúc ký | khóa ed25519 trong OpenBao, không xuất được; token lõi chỉ có `sign`/`verify`. Khi máy chủ bị chiếm quyền root, điều kiện này **không còn bảo đảm** cho các niêm phong sau thời điểm đó (4.2 E3; 11.6 X3). | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |
| (d) kiểm tra được theo điều kiện các bên thỏa thuận | cổng đối soát và `dxos-witness verify-bundle`. | [Điều 22](https://hethongphapluat.com/luat-giao-dich-dien-tu-2023/dieu-22) | 21/10/2026 |

Theo câu thống nhất, niêm phong do **tổ chức vận hành** tạo lập: tên tổ chức (`DXOS_ORG_NAME`) nằm trong tuyên bố khóa
`keys/seal-key/v<n>.json` đã neo (spec 25.3). Tuyên bố khóa không tự ký và không được gọi là chứng thư chữ ký điện tử.

## Không đạt

Những điều niêm phong số và App A **không** đạt được, nói rõ để không ai hiểu quá:

- **Không tương đương chữ ký tay.** Niêm phong chưa được chứng nhận "bảo đảm an toàn", nên không tương đương chữ ký
  tay (Luật Giao dịch điện tử 2023, Điều 23 khoản 2).
- **Không phải chữ ký số.** DX-OS Trust Core không phải hệ thống chứng thư số PKI và không phải dịch vụ chứng thực
  chữ ký số.
- **Chưa có chứng nhận để giao dịch với bên ngoài.** Muốn dùng niêm phong để giao dịch với tổ chức, cá nhân bên ngoài
  với giá trị pháp lý, tổ chức vận hành phải đăng ký chứng nhận (Điều 25 khoản 3). Đội chưa đăng ký và phần mềm không
  làm thay việc đó. Với người ngoài, cổng đối soát chỉ là công cụ kiểm tra toàn vẹn về kỹ thuật.
- **App A không có giá trị như bản gốc giấy.** Theo Nghị định 30/2020/NĐ-CP Điều 5, văn bản điện tử có giá trị như
  bản gốc giấy khi được ký số; App A không ký số.
- **App A chỉ "vận dụng" Nghị định 30/2020.** Nghị định áp dụng cho cơ quan, tổ chức nhà nước và doanh nghiệp nhà
  nước (Điều 2); tổ chức hư cấu "Công ty TNHH Sao Mai" là công ty tư nhân nên không thuộc diện. App A mượn cách đánh số
  (Điều 15 khoản 1) và cách văn thư kiểm văn bản đến (Điều 21 khoản 2 điểm a), không hơn.
- **Điều kiện (c) có giới hạn.** Khi máy chủ bị chiếm quyền root, điều kiện "chỉ thuộc kiểm soát của chủ thể ký lúc
  ký" không còn bảo đảm cho các niêm phong sau thời điểm đó (spec 4.2 E3, 11.6 X3).

## Giới hạn về dữ liệu cá nhân

Bất biến I5 (spec 4.1, 25.2) giữ giá trị trường có khai `pii`, chữ tự do ngoài `data` và salt của bản ghi **ngoài**
ledger, STH và các bảng chỉ thêm; nhờ vậy `:erase-pii` xóa được chúng mà niêm phong vẫn `VALID`. Phần **không thuộc**
I5, chép nguyên văn spec 25.2:

- Trường `public` đã niêm phong: được chép vào `seal_requests` và `seals.payload` đã ký. Đây là công bố có chủ đích, không xóa được, chỉ thu hồi được. Hướng dẫn manifest phải cảnh báo điều này.
- `sub` của nhân viên (định danh giả danh do Keycloak cấp) trong `task_intents`, `task_completions`, `pii_reviews`, `seal_revocations`, `pii_erasures`. Ledger chỉ giữ HMAC.
- Nội dung tệp PDF đã ban hành: là bản gốc văn bản, lưu theo nội dung, có thể dùng chung nhiều bản ghi.

Giới hạn thêm:

- **Lá ledger tạo trước bản 1.0.3** (dev stack, e2e của v0.1.0) vẫn mang cam kết không salt của `data`. Dữ liệu đó là
  hư cấu (spec 25.2).
- **App `DISABLED` phải được bật lại mới xóa được.** `:erase-pii` cần bản manifest ACTIVE (quyền theo
  `pii.erase_roles` của bản ACTIVE); app bị vô hiệu hóa trả 404 `app-not-active`. Muốn xóa, admin nộp một phiên bản
  mới hơn của app rồi duyệt bốn mắt (installer không cho nộp lại đúng phiên bản đã `DISABLED`), xóa xong có thể vô
  hiệu hóa lại. Phiên bản đó vẫn phải mới hơn và chỉ cộng thêm so với bản từng ACTIVE cao nhất (P2-D14 áp dụng cả
  khi app đang `DISABLED`): thường là bản cũ tăng số phiên bản, không bớt trường hay role.
- **Tên trường** đã xóa (không phải giá trị) được ghi ở `pii_erasures` và lá ledger `pii.erased`.
- Sau khi xóa, không ai còn kiểm lại được `record_digest` với dữ liệu, vì salt đã bị xóa.
- Bản cũ của hàng còn trên đĩa cho tới khi `VACUUM`, và còn trong backup tới hết thời hạn giữ: cách xử lý ở
  [`docs/runbook-pii-erasure.md`](runbook-pii-erasure.md).

## Thành viên đã đọc toàn văn

Spec 25 yêu cầu thành viên đội đọc lại toàn văn từng điều được dẫn trước khi đưa câu thống nhất vào README và slide.
Ai đã đọc thì tự ghi tên và ngày đọc (dd/mm/yyyy) vào dòng tương ứng; ô trống nghĩa là **chưa** có thành viên nào xác
nhận đã đọc.

| Văn bản, điều | Thành viên đã đọc | Ngày đọc |
|---|---|---|
| Luật Giao dịch điện tử 2023, Điều 22 | | |
| Luật Giao dịch điện tử 2023, Điều 23 | | |
| Luật Giao dịch điện tử 2023, Điều 25 | | |
| Nghị định 23/2025/NĐ-CP, Điều 4, Điều 5, Điều 7 khoản 4 | | |
| Nghị định 30/2020/NĐ-CP, Điều 2, Điều 5, Điều 15 khoản 1, Điều 21 khoản 2 điểm a | | |
| Luật Bảo vệ dữ liệu cá nhân 2025 (91/2025/QH15), Điều 4 khoản 1 điểm d, Điều 14, Điều 19 khoản 1 | | |
