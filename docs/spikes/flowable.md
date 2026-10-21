# Spike: Flowable REST (Plan 01 Task 6, story S1.5)

*Thực hiện 20/10/2026. Mã spike chỉ giữ lại script smoke: `flowable_smoke.py` và `flowable-smoke.sh`.*

## Kết luận nhanh
- **Giữ ADR-09**: dùng image chính thức `flowable/flowable-rest:7.1.0` (ghim digest), chạy độc lập, không cần tự build.
- Smoke **đạt** ở 2 nơi: (1) bản phát hành `flowable-7.1.0.zip` (H2) trên máy phát triển; (2) stack dev-lite trên Docker Desktop (PostgreSQL riêng `flowable-db`), gọi từ trong mạng `net-wf`.
- **Bản OSS 7.x không có console quản trị.** Trạng thái quy trình phải hiển thị qua admin của DX-OS (CLI bắt buộc, UI admin nên có), xem mục 5.

## 1. Image, phiên bản, giấy phép
| Hạng mục | Giá trị | Cách kiểm |
|---|---|---|
| Image | `flowable/flowable-rest:7.1.0@sha256:b7ae2875…db44` | `docker buildx imagetools inspect`; nhãn image `maintainer: Flowable <info@flowable.org>` |
| Phiên bản engine | 7.1.0 | `GET /management/engine` trả `version: 7.1.0` |
| Nền | Alpine Linux, OpenJDK 21.0.4 | `docker exec … java -version`, `/etc/os-release` |
| Giấy phép | **Apache-2.0** | Tệp `license.txt` trong bản phát hành chính thức `flowable-7.1.0.zip` (GitHub `flowable/flowable-engine`, tag `flowable-7.1.0`) là Apache License 2.0; MANIFEST của `flowable-rest.war`: `Implementation-Title: Flowable - REST - APP`, `Implementation-Version: 7.1.0` |

**Giới hạn kiểm chứng:** image chứa ứng dụng ở dạng giải nén (`/app/WEB-INF/...`), không phải tệp war, nên không so được mã băm với war chính thức. Bằng chứng hiện có là nhãn nhà phát hành, phiên bản engine và giấy phép của bản phát hành cùng phiên bản. Image có thêm driver PostgreSQL (bản war phát hành chỉ có H2).

## 2. Khởi động và RAM
| Đo | Hồ sơ dev-lite (`-Xmx384m`) |
|---|---|
| Thời gian khởi động | `Started FlowableRestApplication in 11.386 seconds` (lần đầu tạo 62 bảng trong `flowable-db`) |
| RAM khi rảnh (`docker stats`) | flowable **393 MiB**, flowable-db **43 MiB** |
| Bản phát hành chạy trực tiếp (`-Xmx512m`, H2) | khởi động 10,2 s |

`JAVA_TOOL_OPTIONS` được JVM nhận (`Picked up JAVA_TOOL_OPTIONS: -Xmx384m`), nên các hồ sơ p8/p16 chỉnh heap bằng biến này. Số đo p8/p16 ghi ở Task 7 (`docs/capacity.md`).

## 3. Endpoint REST (gốc `http://flowable:8080/flowable-rest/service`, Basic auth)
| Thao tác | Endpoint | Đã chạy trong smoke |
|---|---|---|
| Deploy BPMN | `POST /repository/deployments` (multipart, trường `file`, tên tệp `*.bpmn20.xml`) | ✔ |
| Start theo key | `POST /runtime/process-instances` `{"processDefinitionKey", "businessKey", "variables":[{name,value,type}]}` | ✔ |
| Task theo nhóm | `GET /runtime/tasks?candidateGroup=<g>&processInstanceId=<id>` | ✔ |
| Task theo người | `GET /runtime/tasks?assignee=<u>` | ✔ |
| Complete kèm biến | `POST /runtime/tasks/{id}` `{"action":"complete","variables":[…]}` | ✔ |
| Trạng thái instance | `GET /runtime/process-instances/{id}` (404 khi đã kết thúc) + `GET /history/historic-process-instances/{id}` (`endTime`) | ✔ |
| Biến lịch sử | `GET /history/historic-variable-instances?processInstanceId=<id>` | ✔ |
| Xóa deployment | `DELETE /repository/deployments/{id}?cascade=true` | ✔ |
| Thông tin engine | `GET /management/engine` | ✔ |

Sai mật khẩu → 401 (đã kiểm). Toàn bộ chuỗi smoke chạy trong 1,9 s trên stack.

### Kiểm lại Plan 02 Task 4 (21/10/2026, Flowable 7.1.0 bản phát hành, H2)

Mọi dòng dưới đây đã chạy trên Flowable thật rồi mới viết client (`core/src/dxos_core/workflow/flowable.py`); test sống: `core/tests/integration/test_flowable_live.py`.

| Việc | Endpoint và tham số **đã kiểm** | Ghi chú |
|---|---|---|
| Deploy có tên | `POST /repository/deployments?deploymentName=<tên>` (multipart, trường `file`, tên tệp `*.bpmn20.xml`) → 201 `{"id","name",…}` | Tên deployment mặc định lấy từ **tên tệp** (bỏ đuôi); trường form `deploymentName`/`name` **bị bỏ qua**, chỉ tham số **query** `deploymentName` có tác dụng. `deploymentCategory` không có tác dụng. |
| Deploy idempotent | `GET /repository/deployments?name=<tên>&sort=deployTime&order=asc&size=1` | `name` là so khớp đúng; có thì trả id đầu tiên, không POST lại. Flowable tự không loại trùng: POST lại cùng tên tạo deployment mới và tăng `version` của definition. |
| Definition của deployment | `GET /repository/process-definitions?deploymentId=<id>` → `data[0].id` (dạng `key:phiên-bản:uuid`) | `category` = `targetNamespace` của BPMN. |
| Start theo definition | `POST /runtime/process-instances` `{"processDefinitionId","businessKey","variables":[{name,value,type:"string"}]}` → 201 | `variables: []` được. definition lạ → 400. |
| Instance đang chạy theo (definition, business key) | `GET /runtime/process-instances?processDefinitionId=<id>&businessKey=<k>` | Chỉ trả instance chưa kết thúc. |
| Hủy instance | `DELETE /runtime/process-instances/{id}?deleteReason=<lý do>` → 204; gọi lại hoặc id lạ → 404 | Lịch sử ghi `deleteReason`, **`endActivityId` = null**, có `endTime`. |
| Task theo nhóm | `GET /runtime/tasks?candidateGroups=<g1,g2>&processDefinitionKeyLike=<prefix>%` | **`candidateGroupIn` bị bỏ qua IM LẶNG** (trả mọi task, kể cả của nhóm khác): đã thử với nhóm không tồn tại vẫn ra task. Tên đúng là `candidateGroups`, phân cách dấu phẩy, nghĩa OR; `candidateGroups=` rỗng ra 0 task; `candidateGroup` (số ít) cũng lọc đúng cho một nhóm. `processDefinitionKeyLike` lọc đúng (LIKE, `_` và `%` là ký tự đại diện nên client lọc lại `startswith`). |
| Phân trang | `size`, `start`; phản hồi có `total` | **Mặc định `size=10`**: 12 task chỉ ra 10. Client phân trang với `size=100`. |
| Task đơn | `GET /runtime/tasks/{id}` (404 khi không còn); trường dùng: `taskDefinitionKey`, `processInstanceId`, `processDefinitionId`, `assignee`, `createTime`; `name` là `null` vì bản dựng chuẩn của Task 3 bỏ tên | Không có `processDefinitionKey`: client lấy phần trước dấu `:` của `processDefinitionId`. |
| Complete | `POST /runtime/tasks/{id}` `{"action":"complete","variables":[…]}` → 200; task không còn → 404 | Biến có `"scope":"local"` gắn vào **chính task** (đã kiểm: `dxos_intent_id` local không xuất hiện ở biến instance, chỉ ở lịch sử của task). Biến không `scope` là toàn cục của instance. |
| Đua hoàn thành cùng lúc | 6 request song song cùng task: 1 × 200, còn lại 404 **hoặc 500** | Flowable **không** trả 409 như giả định ban đầu. Đo 60 vòng × 6: 60 × 200, 262 × 404, 38 × 500 với 3 thông điệp khác nhau (`… was updated by another transaction concurrently` cho Execution hoặc ProcessInstance, và một `NullPointerException … processInstanceExecution is null`). Client không so khớp thông điệp: gặp 500 thì hỏi `historic_task_done`; task đã xong (bên thắng đã commit) → `TaskGone`, chưa xong → `WorkflowUnavailable`. 404/409 → `TaskGone`. |
| Complete sai dữ liệu | `decision` không khớp điều kiện cổng, hoặc thiếu biến điều kiện → 500 (`No outgoing sequence flow…` / `Unknown property used in expression`); task **vẫn còn** | Bridge (Task 6) phải kiểm quyết định hợp lệ trước khi gọi Flowable. |
| Task đã xong | `GET /history/historic-task-instances/{id}` → `endTime` khác null khi đã xong, null khi còn mở; id lạ → 404 | |
| Biến `dxos_intent_id` lúc hoàn thành | `GET /history/historic-variable-instances?taskId=<id>&variableName=dxos_intent_id` → `data[0].variable.value`, kèm `taskId` | Task chưa hoàn thành hoặc không có biến → `data: []`. |
| Kết quả | `GET /runtime/process-instances/{id}` (200 = đang chạy; 404 = đã kết thúc) rồi `GET /history/historic-process-instances/{id}` → `endTime`, `endActivityId` (vd. `approved`), `deleteReason`, `businessKey` | Id lạ ở cả hai nơi → 404 cả hai. |
| Xác thực | Sai mật khẩu hoặc thiếu → 401 (`WWW-Authenticate: Basic`) | Client coi 401 và 403 là `WorkflowUnavailable`. |

Hệ quả cho các task sau:
- Task 6 (bridge) gửi `dxos_intent_id` bằng `complete(task_id, vars, local_variables={"dxos_intent_id": …})` và đối soát bằng `historic_task_done` + `historic_intent_id`.
- Không dùng `candidateGroupIn` ở bất kỳ đâu; test sống `test_candidate_group_filter_really_filters` canh việc lọc nhóm có hiệu lực.
- Mô hình BPMN của app phải đặt `decision` ở mỗi cổng; người gọi `complete` chịu trách nhiệm chỉ gửi giá trị nằm trong `decisions_by_task` (Task 3).

## 4. Kết nối `flowable-db` bằng tài khoản riêng
```yaml
SPRING_DATASOURCE_URL: jdbc:postgresql://flowable-db:5432/flowable
SPRING_DATASOURCE_USERNAME: flowable
SPRING_DATASOURCE_PASSWORD: ${FLOWABLE_DB_PASSWORD}
FLOWABLE_REST_APP_ADMIN_USER-ID: rest-admin        # tên biến có dấu gạch nối là đúng
FLOWABLE_REST_APP_ADMIN_PASSWORD: ${FLOWABLE_REST_PASSWORD}
```
Kiểm cô lập (I1): `flowable-db` có 62 bảng `act_*`/`flw_*`, **core-db có 0**; vai trò đăng nhập duy nhất trên `flowable-db` là `flowable`. Kết hợp netcheck (Task 4): `net-wf` và `net-fldb` không tới được core-db, OpenBao, SeaweedFS.

## 5. Console quản trị trong bản OSS
**Không có.** Flowable 7.0 đã loại các ứng dụng UI (Modeler, Admin, Task, IDM) khỏi bản nguồn mở. Thông báo phát hành 7.0.0 ghi rõ việc này, và trên stack `/flowable-ui/` và `/flowable-admin/` đều trả 404.

Hệ quả cho ma trận UI admin (R7):
- **Không** trình diễn console Flowable.
- Trạng thái quy trình hiển thị qua trust-core: `dxos` CLI (MUST) và UI admin Tầng 1 (SHOULD) đọc từ workflow-bridge.
- Thiết kế BPMN bằng tay (XML) hoặc công cụ vẽ BPMN bên ngoài (ví dụ bpmn-js của bpmn.io: giấy phép riêng của bpmn.io, không phải MIT thuần, yêu cầu giữ watermark). Phải kiểm giấy phép trước khi đưa vào sản phẩm.

`/flowable-rest/docs/` (Swagger) trả 200 **không cần xác thực**, nhưng chỉ trong `net-wf`, nơi duy nhất trust-core-api thấy được. Chấp nhận được; ghi vào mô hình đe dọa.

## 6. Đề xuất
**Giữ ADR-09** (Flowable REST chạy độc lập, trust-core là bên gọi duy nhất qua workflow-bridge). Không cần phương án lùi tự build image.

Ghi chú cho workflow-bridge (S5.1):
- Flowable chỉ có **một** tài khoản REST (`rest-admin`). Phân quyền theo vai trò nằm ở trust-core (PDP và danh mục guard), không dựa vào IDM của Flowable. `candidateGroups` trong BPMN dùng chuỗi vai trò ứng dụng `app:<id>:<role>`.
- Gắn `businessKey` = mã bản ghi DX-OS để tra ngược.
- Thời điểm kết thúc lấy từ API lịch sử. Runtime trả 404 cho instance đã kết thúc là bình thường, không phải lỗi.
- **Flowable history level phải ≥ audit (mặc định); bridge dùng lịch sử Flowable để đối soát.** Task đã xong,
  biến task-local `dxos_intent_id` lúc hoàn thành và end event của instance đều đọc từ `/history/...` (P2-D20, bất
  biến "task đã xong ⇒ có bản ghi hoàn thành"). Hạ xuống `activity`/`none` thì đối soát mất căn cứ: task đã xong
  trông như chưa xong, ý định có thể bị bỏ nhầm sau biên commit muộn và bất biến hoàn thành không còn kiểm được gì.
  Lõi **không** tự phát hiện cấu hình này; không được đổi. Ghi chú tương ứng ở dịch vụ `flowable` trong
  `deploy/compose.yaml`.

## Nguồn
- [Flowable Open Source 7.0.0 release](https://flowable.com/blog/releases/flowable-open-source-7-0-0-release): loại bỏ UI applications.
- Bản phát hành `flowable-7.1.0.zip` tại GitHub `flowable/flowable-engine`: `license.txt`, `wars/flowable-rest.war`.
