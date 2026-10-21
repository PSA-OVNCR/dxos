# Viết app DX-OS trong 30 phút

> Hướng dẫn H13 (R-5; Design Spec, bảng hạng mục H) và là tài liệu duy nhất bạn cần cho phép thử AT-26: một người **ngoài đội** làm theo,
> tạo được một app mới chỉ bằng manifest, **không sửa `core/`**. Nếu bạn vướng ở đâu, đó là lỗi của tài liệu: hãy ghi lại
> (mẫu biên bản ở [docs/at26-checklist.md](at26-checklist.md)).

Bạn sẽ dựng **"Sổ mượn sách"** của một thư viện nhỏ: bạn đọc tạo phiếu mượn, thủ thư duyệt (người tạo phiếu không tự duyệt
phiếu của mình), phiếu được duyệt thì được **niêm phong** và có mã QR để ai cũng đối soát được. Toàn bộ là:

| Tệp | Vai trò | Dòng |
|---|---|---|
| [`examples/so-muon-sach/manifest.yaml`](../examples/so-muon-sach/manifest.yaml) | khai báo dữ liệu, vai trò, quyền, chính sách | 23 (cả phần đầu tệp) |
| [`examples/so-muon-sach/bpmn/duyet-muon.bpmn`](../examples/so-muon-sach/bpmn/duyet-muon.bpmn) | quy trình một bước | 1 `userTask` + 1 cổng |
| [`examples/so-muon-sach/web/`](../examples/so-muon-sach/web/) | giao diện (tùy chọn), form **sinh từ manifest** | dưới 150 dòng mã của đội |

Lõi (`core/`) **không có một dòng nào** về sách, phiếu hay thủ thư (bất biến I3, kiểm bằng AT-14): mọi hành vi riêng của app
đến từ manifest đã được hai quản trị viên duyệt.

## Cần gì trước khi bắt đầu

- Git, GNU Make, Python 3.12 (`python -m venv .venv && . .venv/bin/activate && make dev-install`), Docker với Compose v2
  (≥ 2.24). Hồ sơ `dev-lite` chạy trên laptop (xem [BUILD.md](../BUILD.md)). **Không cần cài Node**: `make web-build` build
  giao diện trong một container Node dùng một lần.
- Hai tài khoản quản trị (`dxos-admin`) để duyệt bốn mắt. Trong realm dev có sẵn `admin1` và `admin2`, mật khẩu
  `dev-only-password` (chỉ ở hồ sơ `dev-lite`).
- Đồng hồ chính xác: đăng nhập OIDC lệch đồng hồ sẽ bị từ chối.

**Dấu kiểm.** Hướng dẫn này soạn trong môi trường cloud **không có Docker**, nên mỗi khối lệnh ghi rõ một trong hai:

- **Đã kiểm** — lệnh đã được chạy thật và kết quả in kèm bên dưới;
- **chưa kiểm ở cloud — kiểm trong AT-26** — cần stack đang chạy; người thử AT-26 là người kiểm đầu tiên và ghi kết quả vào biên bản.

## (0–5') Dựng stack dev-lite

Theo [BUILD.md](../BUILD.md), mục "Chạy toàn bộ hệ thống". Ghi lại commit gốc trước khi làm gì khác, để cuối bài kiểm P1:

```bash
git clone https://github.com/PSA-OVNCR/dxos.git && cd dxos
git rev-parse HEAD                  # GHI LẠI dòng này: "commit trước khi bắt đầu"
cp .env.example .env                # giá trị mẫu chạy được trên localhost
make pin-images                     # lần đầu: ghim digest image (cần mạng tới Docker Hub, quay.io)
make up PROFILE=dev-lite           # dựng stack; ClamAV được thay bằng fake-av (chỉ để phát triển)
make ps                             # chờ các container "healthy"
```

*Trạng thái: chưa kiểm ở cloud — kiểm trong AT-26* (cloud không có Docker. Stack đã từng dựng thành công trên Docker Desktop
với hồ sơ p16 và overlay e2e, xem `docs/progress/2026-10-22-e2e-m2-docker-desktop.md`; riêng `make up PROFILE=dev-lite` theo
hướng dẫn này thì chưa ai chạy).

Hai việc một lần để **niêm phong** chạy được (không có chúng thì phiếu đã duyệt dừng ở `SEAL_PENDING` và lõi trả 503
`org-not-configured` hoặc `kms-unavailable`, xem [docs/runbook-openbao.md](runbook-openbao.md)):

1. Trong `.env`, đặt `DXOS_ORG_NAME` thành một tên thật (ví dụ `Thư viện Sao Mai`, **không** để `changeme...`): tên này được
   ghi vĩnh viễn vào tuyên bố khóa ở lần niêm phong đầu. Sau đó `make up PROFILE=dev-lite` lại.
2. Khởi tạo và mở khóa OpenBao đúng [BUILD.md](../BUILD.md), mục "E2E" bước 2 (một lần cho mỗi volume).

Stack có từ trước: chạy `python ops/keycloak_upgrade.py --profile dev-lite` để có `admin2` và client `dxos-cli`.

Lấy CA nội bộ của Caddy để CLI tin chứng chỉ `localhost` (BUILD.md, mục E2E bước 4):

```bash
docker compose -p dxos cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

*Trạng thái: chưa kiểm ở cloud — kiểm trong AT-26.*

## (5–15') Viết manifest và BPMN

Tạo thư mục app gồm `manifest.yaml` và `bpmn/duyet-muon.bpmn`. Bạn có thể gõ lại từ đầu (khuyến nghị cho AT-26) hoặc xem
bản có sẵn ở `examples/so-muon-sach/`. Manifest đầy đủ:

```yaml
apiVersion: dxos/v1
app: { id: so-muon-sach, version: 1.0.0, name: "Sổ mượn sách", spaces: [P, D] }
roles: [ban_doc, thu_thu]
collections:
  phieu_muon:
    fields:
      so_phieu:   { type: sequence, format: "{n}/PM", public: true, label: "Số phiếu" }
      ten_sach:   { type: string, required: true, public: true, label: "Tên sách" }
      nguoi_muon: { type: string, required: true, pii: NAME, label: "Người mượn" }
      ngay_muon:  { type: date, required: true, label: "Ngày mượn" }
      email:      { type: string, pii: EMAIL, label: "Email" }
    access: { read: [owner, "role:thu_thu"], create: ["role:ban_doc"] }
policies:
  pii:    { reveal_roles: [thu_thu], erase_roles: [thu_thu] }
  seal:   { on_event: "process.completed:approved", target: [record], public_fields: [so_phieu, ten_sach], revoke_roles: [thu_thu] }
  verify: { public: true, require_file: false }
workflow:
  bpmn: bpmn/duyet-muon.bpmn
  tasks:
    duyet_muon: { role: thu_thu, guards: [not_same_actor:creator] }
```

Đọc từng khối:

| Khối | Nghĩa | Vì sao |
|---|---|---|
| `app` | `id` là tên định danh; `version` phải tăng mỗi lần nộp lại; `spaces: [P, D]` = các không gian năng lực H-P-D-I mà app thuộc về (như App A và App B, Design Spec mục 5) | `id` khớp `^[a-z][a-z0-9-]{1,30}$` |
| `roles` | `ban_doc`, `thu_thu`. **Không** tự thêm tiền tố: lõi tạo realm role `app:so-muon-sach:ban_doc` và `app:so-muon-sach:thu_thu` lúc duyệt | tên có `:` hoặc bắt đầu bằng `app_` bị chặn (`NAMESPACE_VIOLATION`) |
| `collections.phieu_muon.fields` | `so_phieu` là `sequence`: **lõi cấp số** `1/PM`, `2/PM`, … nên form không có ô này. `nguoi_muon` và `email` có `pii`: trả về dạng che, chỉ `reveal_roles` thấy bản rõ | một trường không thể vừa `pii` vừa `public` |
| `public: true` | trường được đưa vào niêm phong và hiện trên trang đối soát công khai: **công bố vĩnh viễn**, chỉ đánh cho `so_phieu` và `ten_sach` | [manifest-guide](manifest-guide.md), mục "Trường công khai là công bố vĩnh viễn" |
| `label` | nhãn tiếng Việt; **SPA lấy nhãn từ đây**, không chép tay | |
| `access` | ai đọc, ai tạo. `owner` = chủ bản ghi. `thu_thu` đọc được phiếu của mọi người để duyệt | `ban_doc` chỉ tạo và đọc phiếu của chính mình |
| `policies.pii` | `thu_thu` xem bản rõ và xóa được dữ liệu cá nhân | mỗi lần xem bản rõ lõi ghi sổ cái |
| `policies.seal` | khi quy trình kết thúc ở `approved` thì niêm phong bản ghi; `thu_thu` thu hồi được | `public_fields` phải là trường `public` |
| `policies.verify` | `public: true`: có trang đối soát công khai; `require_file: false`: không bắt người đối soát nộp kèm tệp | |
| `workflow.tasks.duyet_muon` | vai trò `thu_thu` hoàn thành; guard `not_same_actor:creator` = **người tạo phiếu không tự duyệt** (nguyên tắc bốn mắt) | guard lấy từ danh mục chung của lõi ([manifest-guide](manifest-guide.md), "Danh mục guard"); guard lạ → `UNKNOWN_GUARD` |

Quy trình BPMN **viết tay** (đừng xuất từ modeler: phần tử thừa như `<incoming>`, `extensionElements`, script đều bị từ chối).
Phần `process` của `bpmn/duyet-muon.bpmn`:

```xml
<process id="so-muon-sach.duyet-muon" name="Duyệt phiếu mượn" isExecutable="true">
    <startEvent id="start" name="Bắt đầu"/>
    <sequenceFlow id="f_start" sourceRef="start" targetRef="duyet_muon"/>
    <userTask id="duyet_muon" name="Duyệt mượn" flowable:candidateGroups="app:so-muon-sach:thu_thu"/>
    <sequenceFlow id="f_duyet_muon" sourceRef="duyet_muon" targetRef="gw_duyet_muon"/>
    <exclusiveGateway id="gw_duyet_muon" name="Kết quả duyệt"/>
    <sequenceFlow id="f_duyet_muon_ok" sourceRef="gw_duyet_muon" targetRef="approved">
      <conditionExpression xsi:type="tFormalExpression">${decision == 'approve'}</conditionExpression>
    </sequenceFlow>
    <sequenceFlow id="f_duyet_muon_no" sourceRef="gw_duyet_muon" targetRef="rejected">
      <conditionExpression xsi:type="tFormalExpression">${decision == 'reject'}</conditionExpression>
    </sequenceFlow>
    <endEvent id="approved" name="Đã duyệt"/>
    <endEvent id="rejected" name="Từ chối"/>
  </process>
```

Luật tối thiểu (đủ ở [manifest-guide](manifest-guide.md), mục "Luật BPMN"): chỉ `startEvent`, `userTask`, `exclusiveGateway`,
`sequenceFlow`, `endEvent`; `process id` dạng `<app_id>.<tên>`; `userTask` có đúng một nhóm `app:<app_id>:<role>` và **trùng
tên** với một task trong `workflow.tasks`; điều kiện của cổng chỉ có dạng `${decision == '<giá trị>'}`; phải có end event
`approved` vì `policies.seal.on_event` trỏ tới nó. Id `guard_failed` và `cancelled` dành riêng cho lõi.

Phần `bpmndi:BPMNDiagram` (tọa độ vẽ) trong tệp thật chỉ để mở bằng công cụ vẽ; lõi bỏ nó khi dựng lại BPMN.

### Sàn chính sách: thứ manifest không nới được

Lõi có tám chính sách sàn (spec 9.2 trong [Design Spec](superpowers/specs/2026-10-20-dxos-trust-core-design.md), F1 đến F8): mọi tệp đều qua kiểm dịch; bản ghi đã niêm phong là bất biến;
mọi lần bị từ chối đều thành sự kiện sổ cái; PII luôn được che; endpoint công khai chỉ trả trường `public`; tài nguyên app
nằm trong namespace `app:<id>`; không có API sửa sổ cái; lỗi ở ClamAV, OpenBao hay PDP thì từ chối. Manifest chỉ **siết thêm**
được, không **nới** được. Thử ngay: nới kiểm dịch của tệp đính kèm sang `optional`:

```bash
python - <<'PY'
import yaml
from dxos_core.registry.validator import ManifestError, validate_manifest

doc = yaml.safe_load(open("examples/so-muon-sach/manifest.yaml", encoding="utf-8"))
doc["collections"]["phieu_muon"]["attachments"] = {"kinds": ["pdf"], "max_mb": 5, "min": 0, "quarantine": "optional"}
try:
    validate_manifest(doc)
except ManifestError as e:
    print(e.code, e.path)
PY
```

Kết quả (**đã kiểm**, chạy ngày 22/10/2026 với `validate_manifest` của lõi):

```text
FLOOR_WEAKENED /collections/phieu_muon/attachments/quarantine
```

Khi nộp thật, lõi trả `422 manifest-invalid` kèm đúng `code` và `path` này, và manifest **không được lưu**. Hai lỗi thường gặp
khác, cũng **đã kiểm** bằng cách sửa bản ví dụ: thêm role `app_admin` → `NAMESPACE_VIOLATION /roles/2`; đổi guard thành
`tu_duyet` → `UNKNOWN_GUARD /workflow/tasks/duyet_muon/guards/0`.

Trước khi nộp, kiểm cục bộ manifest và BPMN bằng cùng bộ kiểm mà lõi dùng (không cần stack):

```bash
python - <<'PY'
import yaml
from dxos_core.registry.bpmn import check_against_manifest
from dxos_core.registry.validator import validate_manifest

m = validate_manifest(yaml.safe_load(open("examples/so-muon-sach/manifest.yaml", encoding="utf-8")))
pm = check_against_manifest(open("examples/so-muon-sach/bpmn/duyet-muon.bpmn", "rb").read(), m)
print("OK", m.app.id, m.app.version, sorted(pm.end_events), pm.user_tasks)
PY
```

**Đã kiểm**, kết quả: `OK so-muon-sach 1.0.0 ['approved', 'rejected'] {'duyet_muon': 'thu_thu'}`.

## (15–20') Nộp, xem diff quyền, duyệt bốn mắt

Admin thứ nhất đăng nhập (device flow: CLI in một liên kết, mở bằng trình duyệt, đăng nhập `admin1`) rồi nộp:

```bash
dxos login --server https://admin.localhost --ca-file caddy-root.crt
dxos app install examples/so-muon-sach
```

`install` đọc `manifest.yaml` và tệp BPMN, nộp cho lõi (kết quả `202`, bản `PENDING`) và in **diff quyền** để người duyệt xem.
Với một app mới, diff liệt kê toàn bộ cái được thêm. Phần đầu của diff (mô phỏng bằng `permission_diff` của lõi và hàm in của
CLI, **đã kiểm**; bản in thật qua server là *chưa kiểm ở cloud — kiểm trong AT-26*):

```text
So với: chưa có phiên bản ACTIVE (cài mới)
- Vai trò thêm: ["ban_doc", "thu_thu"]
- Collection thêm: ["phieu_muon"]
- Trường thêm: phieu_muon: email, ngay_muon, nguoi_muon, so_phieu, ten_sach
- Quyền truy cập (giá trị mới): phieu_muon: create role:ban_doc; read owner, role:thu_thu; update owner
- Vai trò xem PII / xóa PII: thu_thu
- Niêm phong: process.completed:approved; công khai: so_phieu, ten_sach; thu hồi: thu_thu
- Xác minh công khai: public=true, require_file=false
- Task quy trình (giá trị mới): duyet_muon: role thu_thu, guards not_same_actor:creator
```

(Rút gọn cho dễ đọc; CLI in JSON gọn cho từng mục.) Đây là thứ người duyệt phải đọc: **ai được đọc, ai được tạo, ai thấy PII,
trường nào thành công khai vĩnh viễn**.

**Admin thứ hai** (người khác, máy khác; nếu cùng một máy, mở shell khác và đặt `export XDG_CONFIG_HOME="$HOME/.config-admin2"`
trước khi đăng nhập `admin2`) xem lại diff rồi duyệt:

```bash
dxos login --server https://admin.localhost --ca-file caddy-root.crt
dxos app diff so-muon-sach 1.0.0
dxos app approve so-muon-sach 1.0.0
dxos app list
```

Người duyệt **phải khác** người nộp, nếu không lõi trả 403 `self_approval` (`DXOS_ALLOW_SELF_APPROVAL` chỉ dành cho demo một
người). Khi duyệt, lõi kiểm lại toàn bộ, tạo hai realm role `app:so-muon-sach:ban_doc` và `app:so-muon-sach:thu_thu` trong
Keycloak, deploy BPMN lên Flowable, rồi chuyển app sang `ACTIVE`.

Đã kiểm ở cloud: `dxos app install --help`, `approve --help`, `diff --help` (đúng cú pháp trên); chạy `dxos app install
examples/so-muon-sach` khi chưa đăng nhập trả `Chưa đăng nhập: chạy dxos login --server https://admin.<miền>` và mã thoát 3.
*Trạng thái các lệnh nộp, diff, duyệt với server thật: chưa kiểm ở cloud — kiểm trong AT-26.*

## (20–25') Gán vai trò trong console Keycloak

Realm role vừa được tạo, nhưng chưa ai giữ. Việc gán nằm ngoài lõi, trong **console quản trị Keycloak thật**, chỉ mở trên host
quản trị (host công khai trả 404 cho `/auth/admin`):

1. Mở `https://admin.localhost/auth/admin/` (trên VPS: `https://admin.<miền>/auth/admin/`). Đăng nhập tài khoản `admin` với
   mật khẩu `KEYCLOAK_ADMIN_PASSWORD` trong `.env`. Chọn realm **dxos** ở góc trên bên trái.
2. **Users** → `nhan_vien1` → tab **Role mapping** → **Assign role** → đổi bộ lọc sang *Filter by realm roles* → chọn
   `app:so-muon-sach:ban_doc` → **Assign**.
3. Tương tự cho `van_thu1` với `app:so-muon-sach:thu_thu`.
4. Muốn thử "người tạo tự duyệt" thì gán thêm `app:so-muon-sach:thu_thu` cho `nhan_vien1`.

Hai người dùng này là người dùng dev của App A (mật khẩu `dev-only-password`); bạn cũng có thể tạo người dùng mới ở **Users →
Add user** rồi đặt mật khẩu ở tab **Credentials**. Vai trò nằm trong token lúc đăng nhập, nên ai đã đăng nhập từ trước phải
đăng xuất rồi đăng nhập lại.

Lưu ý: `dxos-admin` **không** tự đọc được dữ liệu app (lõi từ chối `admin_no_data_access`); người dùng thật cần vai trò của app.

*Trạng thái: chưa kiểm ở cloud — kiểm trong AT-26.*

## (25–30') Dựng giao diện, tạo phiếu, duyệt bằng người khác, quét QR

```bash
make web-build
```

`make web-build` chạy `npm ci` và build mọi SPA trong một container Node, rồi chép vào volume `apps-static` mà Caddy phục vụ
(`ops/build_web.sh`; `so-muon-sach` nằm trong danh sách cố định của script). Mở `https://localhost/apps/so-muon-sach/`
(trình duyệt cảnh báo chứng chỉ nội bộ của Caddy: chấp nhận cho `localhost`).

1. Đăng nhập `nhan_vien1`. Form "Phiếu mượn" có **bốn ô** (Tên sách, Người mượn, Ngày mượn, Email): không có ô "Số phiếu"
   vì lõi cấp số. Điền và bấm **Tạo**. Phiếu hiện trong danh sách với số `1/PM`. Bấm **Gửi duyệt**.
2. Mở cửa sổ ẩn danh, đăng nhập `van_thu1` → **Hộp việc** → **Duyệt**. (Nếu `nhan_vien1` có cả vai trò `thu_thu` và tự bấm duyệt
   phiếu của mình, lõi trả 403 `guard-failed` kèm lý do `same_actor`; giao diện hiện thông báo tiếng Việt.)
3. Quay lại danh sách của `nhan_vien1`: phiếu **Đã niêm phong**, kèm **mã QR** và liên kết **Mở trang đối soát**. Quét QR bằng điện
   thoại (với `localhost` điện thoại không tới được: bấm liên kết trên chính máy này) và đối soát.

Muốn chạy riêng kiểm thử của giao diện (cần Node 22 và npm 11.6.2, đã `npm ci` ở thư mục gốc): lệnh dưới **đã kiểm** ở cloud
(10 test đạt; `npm run build -w dxos-example-so-muon-sach` cũng đã chạy được):

```bash
npm run test -w dxos-example-so-muon-sach
```

Giao diện dưới 150 dòng mã của đội vì mọi thứ dùng chung nằm trong `dxos-sdk-js`: `boot` (đăng nhập OIDC, chống vòng lặp đăng
nhập), `AppShell`, `RecordForm` (**form sinh từ `client.manifest('so-muon-sach')`**, nhãn và kiểu ô lấy từ manifest),
`SealPanel` (trạng thái niêm phong, QR, đối soát), `ProblemMessage` (mọi lỗi của lõi thành câu tiếng Việt). Giờ hiển thị luôn
theo `Asia/Ho_Chi_Minh`.

*Trạng thái: chưa kiểm ở cloud — kiểm trong AT-26* (cloud không có Docker nên chưa dựng stack; `npm run build` của ví dụ đã
chạy được).

## Kiểm lại P1

P1 (Design Spec mục 1.2): app mới dùng **cùng một Trust Core, không sửa mã lõi, không sửa cấu hình gateway**. Sau khi làm xong,
chạy lệnh dưới đây với commit bạn ghi ở bước đầu. **Kết quả phải rỗng**:

```bash
git diff --stat <commit trước khi bắt đầu> -- core/ deploy/apisix/
git status --short -- core/ deploy/apisix/
```

Cả hai lệnh không in gì nghĩa là bạn đã thêm một app mới mà không sửa lõi hay gateway. Dòng nào hiện ra là P1 bị vi phạm:
dừng lại và báo trưởng nhóm. Thay đổi ở `examples/`, `ops/` (danh sách build SPA) hay `package.json` (khai báo workspace) **không**
phải là sửa lõi.

*Trạng thái: chưa kiểm ở cloud — kiểm trong AT-26* (lệnh `git diff --stat` là git thuần; cần commit gốc thật của người thử).

## Khi gặp lỗi

| Thấy | Nghĩa | Làm gì |
|---|---|---|
| `dxos`: "Chưa đăng nhập" (mã 3) | chưa có token hoặc đã hết hạn | `dxos login --server ...` |
| `422 manifest-invalid` + `code`, `path` | manifest hay BPMN sai | sửa đúng chỗ `path` chỉ; bảng mã ở [manifest-guide](manifest-guide.md) |
| `409 version-not-newer` | version không lớn hơn bản ACTIVE | tăng `app.version` |
| `403 self_approval` | người duyệt là người nộp | admin khác duyệt |
| SPA: "Phiên đăng nhập không được máy chủ chấp nhận" | token bị lõi từ chối (thường lệch đồng hồ) | chỉnh đồng hồ, **Đăng nhập lại** |
| SPA: danh sách trống, form báo 403 | người dùng chưa có vai trò của app, hoặc token cũ | gán vai trò ở Keycloak rồi đăng nhập lại |
| Phiếu đã duyệt kẹt ở "Chờ niêm phong" | OpenBao còn khóa hoặc `DXOS_ORG_NAME` chưa đặt | xem bước (0–5') và [runbook-openbao](runbook-openbao.md) |

## Tiếp theo

- Thêm tệp đính kèm: `attachments: { kinds: [pdf], max_mb: 5, min: 1 }` và guard `attachments_clean` cho task. Mọi tệp tự động qua kiểm dịch.
- Nâng phiên bản chỉ được **cộng thêm hoặc siết chặt** ([manifest-guide](manifest-guide.md), mục "Nâng phiên bản").
- Hai app thật dùng đúng cách này: [`apps/phong-ho-so`](../apps/phong-ho-so) và [`apps/chung-nhan`](../apps/chung-nhan).
