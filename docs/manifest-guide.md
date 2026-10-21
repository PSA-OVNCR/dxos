# Hướng dẫn viết manifest ứng dụng (bản 1.0.3)

Ứng dụng Tầng 2 cắm vào DX-OS Trust Core **chỉ** bằng một `manifest.yaml` và (nếu có quy trình) một tệp BPMN. Lõi không
có dòng mã nào riêng cho ứng dụng (bất biến I3): cài app không cần sửa `core/`, không cần build lại image (AT-13).

- Nguồn chuẩn: spec mục 9 và 25.4 (`docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md`); JSON Schema
  `core/src/dxos_core/registry/manifest.schema.json`; bộ kiểm `core/src/dxos_core/registry/validator.py` (manifest),
  `bpmn.py` (BPMN), `upgrade.py` (nâng phiên bản).
- Ví dụ xuyên suốt: app tổng hợp `test-flow` (`core/tests/fixtures/manifest-test-flow.yaml`,
  `core/tests/fixtures/bpmn/test-review.bpmn`), là app lõi dùng để tự kiểm. Hai app thật: `apps/phong-ho-so`,
  `apps/chung-nhan`.
- Lỗi khi nộp (422 `manifest-invalid`, kèm `code` và `path` dạng JSON Pointer): `FLOOR_WEAKENED`,
  `NAMESPACE_VIOLATION`, `SCHEMA_INVALID`, `UNKNOWN_GUARD`, `BPMN_INVALID`, `UPGRADE_NOT_ADDITIVE`.

## Cấu trúc manifest

Manifest `test-flow` đầy đủ:

```yaml
apiVersion: dxos/v1
app: { id: test-flow, version: 0.1.0, name: "Test flow", spaces: [D] }
roles: [author, reviewer, approver]
collections:
  doc:
    fields:
      title: { type: string, required: true, public: true, label: "Tiêu đề" }
      ref:   { type: sequence, format: "{n:02}/TF", reset: yearly, public: true }
      cccd:  { type: string, pii: CCCD }
    attachments: { kinds: [pdf], max_mb: 1, min: 1 }
    access: { read: [owner, "role:reviewer", "role:approver"], create: ["role:author"] }
policies:
  pii: { reveal_roles: [approver], erase_roles: [approver] }
  seal: { on_event: "process.completed:approved", target: [record, attachments], public_fields: [ref, title], revoke_roles: [approver] }
  verify: { public: true, require_file: true }
workflow:
  bpmn: bpmn/test-review.bpmn
  tasks:
    review:  { role: reviewer, guards: [attachments_clean, "not_same_actor:creator"] }
    approve: { role: approver, guards: [attachments_clean, pii_reviewed, "not_same_actor:creator", "not_same_actor:review"] }
```

| Khóa | Ý nghĩa và luật chính |
|---|---|
| `apiVersion` | luôn `dxos/v1` |
| `app.id` | `^[a-z][a-z0-9-]{1,30}$`, không chứa `:` |
| `app.version` | `X.Y.Z`; mỗi lần nộp lại phải tăng (xem [Nâng phiên bản](#nâng-phiên-bản)) |
| `app.spaces` | tập con của `H`, `P`, `D`, `I` |
| `roles` | tên `^[a-z][a-z0-9_]{0,30}$`. **Không** tự đặt tiền tố: lõi tự thêm `app:<id>:` khi tạo realm role Keycloak. Tên chứa `:`, là `app` hoặc bắt đầu bằng `app_` → `NAMESPACE_VIOLATION` (AT-12) |
| `collections.<c>.fields.<f>.type` | `string`, `sequence`, `integer`, `boolean`, `date` |
| `…required` | trường bắt buộc khi tạo bản ghi |
| `…public` | trường được đưa vào niêm phong và hiện trên cổng đối soát công khai. Đọc kỹ [Trường công khai là công bố vĩnh viễn](#trường-công-khai-là-công-bố-vĩnh-viễn) |
| `…pii` | `CCCD`, `PHONE`, `BANK_ACCOUNT`, `EMAIL`, `NAME`: trả về dạng che, chỉ `reveal_roles` thấy bản rõ (mỗi lần có ghi ledger), xóa được bằng `:erase-pii`. Một trường không được vừa `pii` vừa `public: true` |
| `…label` | nhãn hiển thị 1–64 ký tự, không ký tự điều khiển; trang đối soát hiện nhãn thay tên kỹ thuật |
| `…format`, `…reset` | chỉ cho `sequence`: xem [Đánh số theo năm](#đánh-số-theo-năm) |
| `attachments` | `kinds: [pdf]`, `max_mb` 1..100, `min` (số tệp `CLEAN` tối thiểu). Có khóa `quarantine` thì chỉ được là `required`; giá trị khác → `FLOOR_WEAKENED` (AT-11): mọi tệp luôn qua kiểm dịch |
| `access` | `read`, `create`, `update` (mặc định `[owner]`); phần tử là `owner` hoặc `role:<role>` |
| `policies.pii` | `reveal_roles`, `erase_roles` (ai được `:erase-pii`), `document_detect` (loại PII dò trong PDF); các role phải có trong `roles` |
| `policies.seal` | `on_event: "process.completed:<id end event>"`, `target` (`record`, `attachments`), `public_fields` (phải là trường `public`), `revoke_roles` (mặc định `[]`: không ai thu hồi được). Khai `seal` thì bắt buộc có `workflow` |
| `policies.verify` | `public` (có cổng đối soát công khai), `require_file` (đối soát bắt buộc kèm hash tệp) |
| `workflow.bpmn` | `bpmn/<tên>.bpmn`, tương đối trong thư mục app |
| `workflow.tasks.<t>` | tên `^[a-z][a-z0-9_]{0,30}$`, khác `creator`; `role` (phải có trong `roles`) và `guards` |

## Danh mục guard

Guard là kiểm tra **chung** do lõi cài sẵn (spec 9.3); manifest chỉ tham chiếu. Thêm guard mới là thay đổi lõi và chỉ
được thêm guard chung, không bao giờ thêm guard mang tên nghiệp vụ. Lõi kiểm guard và khóa lạc quan (`If-Match`)
**trước** khi gọi Flowable (PEP 4).

| Guard | Tham số | Đạt khi | Lý do khi trượt | Mã |
|---|---|---|---|---|
| `attachments_clean` | không | không còn upload `STAGING` của bản ghi, và số tệp `CLEAN` ≥ `attachments.min` | `attachments_not_clean` | 409 (AT-08) |
| `pii_reviewed` | không | collection không có trường `pii` và không có `document_detect`, hoặc xác nhận rà PII mới nhất khớp đúng tập hiện tại (dữ liệu, tệp `CLEAN`, `pii_findings`) | `pii_not_reviewed` | 409 |
| `not_same_actor:creator` | `creator` | người gọi khác chủ bản ghi | `same_actor` | 403 (AT-07) |
| `not_same_actor:<task>` | một task trong `workflow.tasks` | người gọi chưa từng hoàn thành `<task>` trong instance hiện tại | `same_actor` | 403 |
| `role_in:<r1>,<r2>` | các role đã khai (có hoặc không có `[...]`) | người gọi có ít nhất một role trong danh sách | `role_not_allowed` | 403 |
| `field_required:<f>` | trường của ít nhất một collection | `data[f]` khác `null` và khác `""` | `field_missing` | 409 |
| `record_not_sealed` | không | `seal_state = NONE` | `record_sealed` | 409 |
| `assignee_is_caller` | không | task có assignee và đó là người gọi | `not_assignee` | 403 |

- Guard ngoài danh mục hoặc tham số sai → `UNKNOWN_GUARD` (AT-11).
- `assignee_is_caller`: Plan 02 **chưa có API nhận việc (claim)**, nên task không bao giờ có assignee và guard này
  hiện **luôn trượt**. Đừng dùng cho tới khi có API claim.
- Bốn mắt hai bước: `test-flow` đặt `not_same_actor:review` cho `approve`, nên người đã duyệt bước `review` không tự
  phê duyệt được, kể cả khi giữ cả hai role.

## Luật BPMN

BPMN là đầu vào **không tin cậy** (Flowable tính biểu thức JUEL, gọi được mã Java). Lõi chỉ nhận một tập con rất hẹp,
đọc bằng `defusedxml` (cấm DTD, entity, tham chiếu ngoài), rút ra mô hình rồi **tự dựng lại** XML (`render_bpmn`).
Flowable chỉ bao giờ nhận bản do lõi dựng, không bao giờ nhận tệp bạn tải lên. Mọi lỗi là `BPMN_INVALID`.

**Viết BPMN bằng tay** theo mẫu `test-review.bpmn`. Tệp xuất từ modeler (Camunda Modeler, Flowable Modeler…) thường có
phần tử con `<incoming>`/`<outgoing>` trong mỗi nút, `extensionElements`, listener hay script: tất cả bị từ chối vì
không nằm trong danh sách cho phép.

```xml
<process id="test-flow.review" name="Xem xét và phê duyệt" isExecutable="true">
  <startEvent id="start" name="Bắt đầu"/>
  <sequenceFlow id="f_start" sourceRef="start" targetRef="review"/>
  <userTask id="review" name="Xem xét" flowable:candidateGroups="app:test-flow:reviewer"/>
  <sequenceFlow id="f_review" sourceRef="review" targetRef="gw_review"/>
  <exclusiveGateway id="gw_review" name="Kết quả xem xét"/>
  <sequenceFlow id="f_review_ok" sourceRef="gw_review" targetRef="approve">
    <conditionExpression xsi:type="tFormalExpression">${decision == 'approve'}</conditionExpression>
  </sequenceFlow>
  <sequenceFlow id="f_review_no" sourceRef="gw_review" targetRef="rejected">
    <conditionExpression xsi:type="tFormalExpression">${decision == 'reject'}</conditionExpression>
  </sequenceFlow>
  <!-- … approve, gw_approve tương tự … -->
  <endEvent id="approved" name="Đã duyệt"/>
  <endEvent id="rejected" name="Từ chối"/>
</process>
```

Luật:
- Phần tử được phép: `definitions` → đúng một `process` (`isExecutable="true"`, `id` dạng `<app_id>.<tên>`) và tùy chọn
  `bpmndi:BPMNDiagram` (chỉ hình học, lõi bỏ khi dựng lại). Trong `process` chỉ có `startEvent`, `endEvent`,
  `userTask`, `exclusiveGateway`, `sequenceFlow` (con duy nhất được phép: một `conditionExpression`).
- Thuộc tính được phép: `id`, `name` trên nút; `sourceRef`, `targetRef` trên flow; `flowable:candidateGroups` trên
  `userTask`. Không thuộc tính nào được chứa `${` hay `#{`. Cổng không có `default`.
- `userTask`: `flowable:candidateGroups` là **đúng một** nhóm `app:<app_id>:<role>`; tập `userTask` phải trùng
  `workflow.tasks` và đúng role khai trong manifest; không task nào tên `creator`.
- Id `guard_failed` và `cancelled` **dành riêng cho lõi**; không nút nào được dùng. Id không trùng nhau.
- Đúng một `startEvent`, không có flow vào, đúng một flow ra tới một `userTask`. Có ít nhất một `endEvent`, không có
  flow ra.
- `userTask` có đúng một flow ra, tới `endEvent` hoặc cổng. Mọi flow ra khỏi cổng có điều kiện đúng dạng
  `${decision == '<giá trị>'}` (giá trị `^[a-z][a-z0-9_]{0,31}$`, không trùng trong một cổng); điều kiện chỉ đặt trên
  flow ra khỏi cổng. Cổng chỉ dẫn tới `userTask` hoặc `endEvent`.
- Mọi nút tới được từ `startEvent`; từ mọi `userTask` tới được một `endEvent`. End event trong `policies.seal.on_event`
  phải có trong BPMN.
- Tệp tối đa 256 KiB.

## Vòng đời cài ứng dụng

Dùng CLI `dxos` (`cli/README.md`) trên host quản trị `https://admin.<miền>`, vai trò `dxos-admin`:

```bash
dxos login --server https://admin.<miền>        # mỗi admin tự đăng nhập (device flow)
dxos app install ./test-flow                    # thư mục có manifest.yaml + bpmn/; admin A nộp: 202 PENDING
dxos app diff test-flow 0.1.0                   # admin B xem lại diff
dxos app approve test-flow 0.1.0                # admin B (KHÁC admin A) duyệt: ACTIVE
dxos app list
dxos app disable test-flow                      # gỡ: chỉ vô hiệu hóa, giữ dữ liệu và ledger
```

1. **Nộp** (`POST /admin/v1/apps`): kiểm JSON Schema, namespace, chính sách sàn, guard, BPMN, luật nâng phiên bản; lưu
   bản `PENDING`, ghi ledger `app.submitted`. Nộp lại y hệt bản đang `PENDING` trả cùng kết quả.
2. **Xem diff quyền**: role, collection, trường mới; `access`, `reveal_roles`, `erase_roles`, `seal`, `verify`, task,
   nhãn, định dạng số thay đổi so với bản ACTIVE (app đang `DISABLED` thì so với bản từng ACTIVE có version cao
   nhất — cùng mốc với luật nâng phiên bản).
3. **Duyệt bốn mắt** (`POST /admin/v1/apps/{id}:approve`): người duyệt phải khác người nộp, nếu không → 403
   `self_approval` (P2-D21). Lõi kiểm lại toàn bộ so với bản ACTIVE **lúc duyệt** (app đang `DISABLED` thì so
   với bản từng ACTIVE có version cao nhất), rồi:
   - tạo realm role `app:<id>:<role>` trong Keycloak (service account `dxos-installer`);
   - deploy BPMN do lõi dựng lại lên Flowable, tên deployment `id@version#hash16` (16 ký tự đầu của sha256 bản
     dựng lại);
   - chuyển `ACTIVE`, ghi ledger `app.installed` (kèm hash manifest, BPMN, deployment).
4. **Vô hiệu hóa** (`:disable`): app thành `DISABLED`; quy trình đang chạy bị đóng băng; dữ liệu, niêm phong và ledger
   giữ nguyên. Không có lệnh xóa app. Bật lại = nộp và duyệt một version mới hơn; luật nâng phiên bản vẫn so với bản
   từng ACTIVE cao nhất, nên vô hiệu hóa không phải đường vòng để bớt trường hay hạ version.

Lỗi thường gặp:

| Mã | Khi nào | Làm gì |
|---|---|---|
| 409 `install-in-progress` | đang có lần nộp/duyệt/vô hiệu hóa khác của cùng app | CLI tự thử lại 5 lần, cách 2 giây; sau đó chạy lại |
| 409 `version-not-newer` | version không lớn hơn bản ACTIVE, hoặc khi app đang `DISABLED` là bản từng ACTIVE cao nhất (so semver, `0.10.0` > `0.2.0`) | tăng `app.version` |
| 409 `app-version-conflict` | version đó đã nộp với nội dung khác, hoặc đã `ACTIVE`/`DISABLED` | tăng `app.version` |
| 403 `self_approval` | người duyệt là người nộp | admin khác duyệt |
| 422 `manifest-invalid` | manifest/BPMN sai, hoặc nâng phiên bản không hợp lệ | xem `code`, `path` |
| 503 `idp-admin-unavailable`, `workflow-unavailable` | Keycloak hoặc Flowable không tới được | kiểm `dxos health`, thử lại |

`DXOS_ALLOW_SELF_APPROVAL=true` cho phép một người tự duyệt (lá `app.installed` ghi `self_approved: true`). Chỉ dùng
khi demo một người; **không** bật khi lấy minh chứng AT-13.

## Nâng phiên bản

Nâng phiên bản chỉ được **cộng thêm hoặc siết chặt** (spec 9.5, P2-D14). Lõi kiểm lúc nộp và kiểm lại lúc duyệt,
so với bản ACTIVE; app đang `DISABLED` (không còn bản ACTIVE) thì so với bản từng ACTIVE có version cao nhất.
Vi phạm → `UPGRADE_NOT_ADDITIVE`, `path` trỏ vào chỗ sai.

- Version mới phải lớn hơn bản ACTIVE, hoặc bản từng ACTIVE cao nhất (`version-not-newer`).
- Collection cũ, trường cũ còn nguyên và giữ `type`. Trường cũ không được chuyển sang `required`; trường mới của
  collection cũ không được `required` (collection mới thì tự do).
- Trường cũ có `pii` thì giữ đúng loại `pii` (thêm `pii` vào trường cũ là siết, được phép).
- Tập role mới chứa tập role cũ; `pii.reveal_roles` mới là tập con của cũ.
- Bản cũ có `workflow` thì bản mới cũng có; task cũ còn, giữ `role`, tập guard mới chứa tập guard cũ.
- `policies.seal` (gồm `public_fields`, `revoke_roles`) và `policies.verify`: **không đổi** khi app đã từng có yêu cầu
  niêm phong hoặc đang có bản ghi `running`. Khi app **chưa từng niêm phong** thì được đổi (spec 25.4; App A/B
  1.0.0 → 1.1.0 dùng ngoại lệ này).
- Đổi tự do: `pii.erase_roles`, `label`, `format` và `reset` của trường `sequence`, `access`, `app.name`. Các thay đổi
  `access` hiện trong diff quyền để người duyệt xem.

Ví dụ: `test-flow` 0.2.0 thêm role `observer` và guard `role_in:approver` cho `approve` là hợp lệ; bỏ guard
`pii_reviewed` của `approve`, hoặc bỏ trường `cccd`, là `UPGRADE_NOT_ADDITIVE`.

## Trường công khai là công bố vĩnh viễn

Trường có `public: true` nằm trong `policies.seal.public_fields` được chép vào yêu cầu niêm phong (`seal_requests`) và
vào **payload đã ký** (`seals.payload`) lúc niêm phong. Từ đó:

- giá trị ấy hiện trên cổng đối soát công khai và nằm trong mọi gói bằng chứng đã tải về;
- **không xóa được**, kể cả bằng `:erase-pii`: chỉ **thu hồi** được niêm phong (`:revoke`); sau khi thu hồi, API
  công khai vẫn trả các trường đó kèm trạng thái `REVOKED`;
- đây là công bố có chủ đích, nằm ngoài phạm vi I5 (spec 25.2).

Vì vậy chỉ đánh `public` cho những gì tổ chức **chủ động công bố** (số hiệu, trích yếu, tên loại văn bản). Không đánh
`public` cho CCCD, số điện thoại, email, địa chỉ, ngày sinh. Họ tên trên chứng nhận (App B) là công khai có chủ đích;
người được cấp phải được báo trước. Một trường không thể vừa `pii` vừa `public: true` (validator chặn).

## Đánh số theo năm

Trường `sequence` cấp số tự động khi tạo bản ghi (Nghị định 30/2020 Điều 15 khoản 1: số văn bản bắt đầu từ 01 mỗi năm,
duy nhất trong năm; spec 25.4).

- `format` chứa **đúng một** token `{n}` hoặc `{n:0W}` (W từ 2 đến 9: đệm số 0 đủ W chữ số) và không dấu ngoặc nhọn
  nào khác. Ví dụ `test-flow`: `format: "{n:02}/TF"` cho `01/TF`, `02/TF`, …, `10/TF`.
- `reset: never` (mặc định) đếm mãi; `reset: yearly` đếm lại từ 1 mỗi năm.
- Năm tính theo `DXOS_TIMEZONE` của triển khai (mặc định `Asia/Ho_Chi_Minh`), không theo giờ UTC của máy chủ.
- Chuyển một trường từ `never` sang `yearly` khi nâng phiên bản: bộ đếm của năm hiện tại **tiếp nối** giá trị cũ, nên
  không trùng số trong năm; từ năm sau mới đếm lại từ 1.
- Đổi `format`, `reset` là thay đổi tự do khi nâng phiên bản (không phải đổi kiểu).

## Mã lỗi và lý do từ chối

Mọi lỗi của API là `application/problem+json` với `type = https://dxos.dev/problems/<slug>`. Mọi lần bị từ chối vì
quyền hay chính sách đều ghi một lá ledger `policy.denied {action, reason}` (F3; chỉ có `actor_ref`, không có dữ liệu).
Danh sách dưới đây khớp mã lõi; test `tests/repo/test_docs_m2.py` đỏ khi lõi thêm hay bỏ một tên mà mục này chưa sửa.

### Lý do từ chối (`reason` trong `policy.denied`)

Ghi bởi `pdp.deny` (từ chối ngoài bảng quyền, Plan 02):

| Lý do | `action` | Ý nghĩa | HTTP |
|---|---|---|---|
| `guard:<guard>:<lý do>` | `complete` | guard của task trượt; `<lý do>` là một trong `attachments_not_clean`, `pii_not_reviewed`, `same_actor`, `role_not_allowed`, `field_missing`, `record_sealed`, `not_assignee` (bảng [Danh mục guard](#danh-mục-guard)) | 403 hoặc 409 theo guard (`guard-failed`); guard sai **sau** khi Flowable đã chạy thì 409 và instance bị hủy |
| `not_task_role` | `complete` | người gọi không giữ role của task theo bản manifest đã ghim | 404 |
| `kms_unavailable` | `complete` | R-1: OpenBao không ký được trước task niêm phong; Flowable chưa bị gọi | 503 `kms-unavailable` |
| `seal_key_expired` | `complete` | R-1: tuyên bố khóa `seal-key` hết hạn | 503 `seal-key-expired` |
| `key_statement_invalid` | `complete` | R-1: tuyên bố khóa `seal-key` trong DB không qua kiểm hash/phiên bản (bị sửa) | 503 `key-statement-invalid` |
| `org_not_configured` | `complete` | R-1: `DXOS_ORG_NAME` chưa đặt thật | 503 `org-not-configured` |
| `not_pii_reviewer` | `pii_review` | người gọi không thuộc `pii.reveal_roles` | 404 |
| `not_revoker` | `revoke` | người gọi không thuộc `seal.revoke_roles` của bản đã niêm phong | 404 |
| `not_eraser` | `erase_pii` | người gọi không thuộc `pii.erase_roles` của bản ACTIVE | 404 |
| `self_approval` | `approve` | người duyệt app là người nộp (bốn mắt) | 403 `forbidden`, kèm `reason: self_approval` |
| `no_app_role` | `list_tasks` | người gọi không có role nào của app | 403 `forbidden` |
| `admin_no_data_access` | `list_tasks` | người gọi là `dxos-admin` nhưng không có role của app (admin không mặc nhiên đọc dữ liệu app) | 403 `forbidden` |

Ghi bởi `pdp.enforce` (bảng quyền `access` của manifest, Plan 01); `read`/`update` trả 404 (không lộ bản ghi có tồn
tại), `list`/`create` trả 403:

| Lý do | `action` | Ý nghĩa |
|---|---|---|
| `no_app_role` | `list`, `read`, `create`, `update` | không có role nào của app |
| `admin_no_data_access` | `list`, `read`, `create`, `update` | `dxos-admin` không có role của app |
| `unknown_collection` | `list`, `read`, `create`, `update` | collection không có trong manifest |
| `not_in_access_list` | `list`, `read`, `create`, `update` | role của người gọi không có trong `access`, và không phải chủ bản ghi khi `owner` được phép |

`reveal_pii` chỉ được hỏi (`decide`), không ghi `policy.denied`: người không thuộc `reveal_roles` nhận bản che.

### Problem type (`type` của lỗi)

| Slug | HTTP | Ý nghĩa |
|---|---|---|
| `already-running` | 409 | bản ghi đã có quy trình đang chạy |
| `app-not-active` | 404 | app không có phiên bản ACTIVE (chưa cài hoặc đã vô hiệu hóa) |
| `app-not-deployed` | 409 | phiên bản ACTIVE chưa có BPMN đã deploy |
| `app-version-conflict` | 409 | version đã nộp với nội dung khác, hoặc đã ACTIVE/DISABLED |
| `app-version-not-found` | 404 | không có phiên bản app đó |
| `app-version-not-pending` | 409 | phiên bản không còn PENDING (đã DISABLED) nên không duyệt được |
| `attachments-not-clean` | 409 | chưa đủ tệp `CLEAN` để bắt đầu quy trình |
| `attachments-pending` | 409 | còn tệp đang quét (`STAGING`) |
| `bad-request` | 400 | request sai dạng (JSON hỏng, `If-Match` sai dạng, cursor sai…) |
| `deployment-mismatch` | 409 | phiên bản đã có bản deploy khác hash |
| `forbidden` | 403 | không có quyền (list/create, tự duyệt app, hộp việc không có role) |
| `guard-failed` | 403, 409 | guard trượt; thân lỗi có `guard` và `reason` |
| `idp-admin-unavailable` | 503 | không gọi được Admin API Keycloak, hoặc chưa cấu hình secret của `dxos-installer` |
| `idp-unavailable` | 503 | không lấy được JWKS của Keycloak để kiểm token |
| `install-in-progress` | 409 | đang có thao tác cài đặt khác của cùng app; thử lại sau (CLI tự thử lại) |
| `integrity-error` | 500 | tệp trong kho không khớp sha256 khi đọc |
| `internal` | 500 | lỗi không lường trước |
| `invalid-comment` | 422 | `comment` của `:complete` sai kiểu hoặc quá 1000 ký tự |
| `invalid-decision` | 422 | `decision` sai dạng hoặc không thuộc các giá trị của cổng sau task |
| `invalid-note` | 422 | ghi chú thu hồi sai kiểu hoặc dài quá |
| `invalid-reason-code` | 422 | mã lý do thu hồi không thuộc danh sách |
| `invalid-request` | 422 | thân request sai cấu trúc (`:erase-pii`, `:revoke`, `:check`, nộp app…), có surrogate lẻ (không mã hóa UTF-8 được) hoặc lồng quá 64 mức |
| `key-statement-invalid` | 503 | tuyên bố khóa `seal-key` trong DB không qua kiểm hash; không niêm phong, admin điều tra |
| `keys-unavailable` | 503 | OpenBao khóa và phiên bản khóa công khai cần dùng chưa có trong cache |
| `kms-unavailable` | 503 | OpenBao không ký được |
| `length-required` | 411 | upload thiếu `Content-Length` |
| `manifest-invalid` | 422 | manifest/BPMN/nâng phiên bản sai; thân lỗi có `code` và `path` |
| `no-workflow` | 409 | app không khai `workflow` |
| `not-found` | 404 | không có, hoặc không được phép biết là có |
| `not-ready` | 503 | `/readyz`: DB chưa sẵn sàng hoặc chưa chạy migration |
| `not-sealed` | 409 | thu hồi bản ghi chưa niêm phong hoặc đã thu hồi |
| `org-not-configured` | 503 | `DXOS_ORG_NAME` chưa đặt thật; không niêm phong |
| `payload-too-large` | 413 | thân request vượt trần |
| `precondition-required` | 428 | thiếu `If-Match` |
| `record-in-workflow` | 409 | bản ghi đang trong quy trình (sửa, xóa PII) |
| `record-not-open` | 409 | bản ghi không còn nhận tệp đính kèm (đang chạy quy trình hoặc đã niêm phong) |
| `record-sealed` | 409 | bản ghi đã niêm phong |
| `schema` | 422 | dữ liệu bản ghi không khớp collection |
| `seal-key-expired` | 503 | tuyên bố khóa `seal-key` hết hạn; cần xoay khóa |
| `seal-pending` | 409 | bản ghi đang chờ niêm phong |
| `storage-unavailable` | 503 | không tới được kho đối tượng |
| `task-gone` | 409 | task không còn mở (đã có người hoàn thành) |
| `task-unknown` | 409 | task không có trong bản manifest đã ghim |
| `unauthenticated` | 401 | thiếu hoặc sai token |
| `unsupported-media-type` | 415 | `Content-Type` không được nhận |
| `version-conflict` | 409 | `If-Match` khác version hiện tại |
| `version-not-newer` | 409 | version nộp không lớn hơn bản ACTIVE (hoặc bản từng ACTIVE cao nhất khi app đang DISABLED) |
| `workflow-finalize-failed` | 500 | Flowable đã hoàn thành task nhưng lõi chưa ghi xong; sẽ được đối soát |
| `workflow-inconsistent` | 409 | Flowable và bản ghi hoàn thành của lõi lệch nhau; admin phải đối soát |
| `workflow-model-mismatch` | 500 | BPMN đã deploy không khớp manifest đã ghim |
| `workflow-pending` | 503 | kết quả lần hoàn thành trước chưa rõ; thử lại sau |
| `workflow-unavailable` | 503 | Flowable không tới được hoặc chưa cấu hình |

Lỗi HTTP chung (`HTTPException` của FastAPI, ví dụ route không có) dùng slug theo mã: `bad-request`, `unauthorized`,
`forbidden`, `not-found`, `method-not-allowed`, `not-acceptable`, `conflict`, `precondition-failed`,
`payload-too-large`, `unsupported-media-type`, `invalid-request`, `precondition-required`, `rate-limited`,
`internal`, `unavailable`; mã khác dùng `http-error`. Gateway (APISIX) trả 429 riêng khi vượt rate-limit `/verify`.
