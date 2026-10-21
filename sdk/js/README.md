# sdk/js/: `dxos-sdk-js`

SDK TypeScript cho lập trình viên Tầng 2 (trình duyệt, Vue 3): đăng nhập OIDC Authorization Code + PKCE, client gọi
API của lõi (có `If-Match`), tự kiểm gói bằng chứng niêm phong ngay trên trình duyệt, thành phần Vue dùng chung và công cụ
test. Hợp đồng HTTP mà SDK bám theo: [docs/api/contract-tier2.md](../../docs/api/contract-tier2.md).

**Phạm vi và giới hạn (nói thẳng):**
- Gói `private: true`, **chưa công bố lên npm**. Ứng dụng trong repo dùng nó qua npm workspace
  (`"dxos-sdk-js": "0.3.0"` trong `package.json` của ứng dụng); `exports` trỏ thẳng vào mã nguồn `src/`. `npm run build -w dxos-sdk-js`
  tạo thêm bản thư viện `dist/` (`index`, `vue`) nhưng bản đó chưa được ai dùng.
- Đã kiểm bằng test đơn vị (Vitest + jsdom) và Playwright với API giả. **Chưa kiểm với Keycloak và lõi thật trên trình
  duyệt thật** (V27, xem `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 13).
- `verifyBundle` bám `dxos-witness verify-bundle` và chạy chung bộ vector, nhưng **không** hứa trùng tuyệt đối với Python. Hai khác biệt đã
  biết: JS chỉ nhận tối đa 2 dấu `=` đệm base64, và số nguyên dài hơn 4300 chữ số cho `MALFORMED` ở Python nhưng JS vẫn chấp nhận.
- SDK chỉ để hiển thị và gọi API cho tiện. Mọi quyết định về quyền, guard, niêm phong đều do lõi; vai trò trong token
  (`auth.roles()`) chỉ dùng để ẩn hiện nút.

Cài và kiểm (cần Node 22 và `npm@11.6.2`, xem [BUILD.md](../../BUILD.md)):
```bash
npm ci                          # ở thư mục gốc repo
npm run typecheck -w dxos-sdk-js
npm run test -w dxos-sdk-js
```

Bốn điểm vào:

| Import | Nội dung |
|---|---|
| `dxos-sdk-js` | `createAuth`, `DxosClient`, `ApiError`, `verifyBundle`, `rawAnchor`, `sha256Hex`, `formatVn`, kiểu dữ liệu |
| `dxos-sdk-js/vue` | thành phần Vue, `boot`, phiên làm việc (`connect`, `useSession`) |
| `dxos-sdk-js/testing` | `fakeFetch`, `fakeClient`, `problem`, dữ liệu mẫu; **chỉ dùng trong test** (nhập `vitest`) |
| `dxos-sdk-js/style.css` | CSS nền dùng chung |

## Đăng nhập: `createAuth`
Đăng nhập Keycloak bằng Authorization Code + PKCE (S256), client mặc định `dxos-spa`, issuer mặc định
`${location.origin}/auth/realms/dxos`. Token chỉ nằm trong `sessionStorage` (đóng tab là mất), làm mới tự động khi còn
không quá 30 giây và chỉ một lần làm mới chạy tại một thời điểm.

```ts
import { createAuth } from 'dxos-sdk-js'

const auth = createAuth({ appBase: '/apps/phong-ho-so/' })   // redirect_uri = origin + appBase
const loggedIn = await auth.init()    // xử lý ?code&state khi Keycloak chuyển về, xóa query, giữ fragment
if (!loggedIn) await auth.login(location.hash)   // chuyển sang Keycloak; hash được khôi phục sau khi về
const token = await auth.token()      // string | null; làm mới nếu sắp hết hạn
auth.roles()                          // realm roles trong access token (chỉ để hiển thị)
await auth.logout()
```
Gọi `auth.init()` **xong rồi mới** tạo router (`init` đổi URL bằng `history.replaceState`, không bắn `hashchange`). Hàm
`boot` trong `dxos-sdk-js/vue` làm đúng thứ tự này. `appRoles(roles, app)` lấy phần sau `app:<app>:` của các vai trò.

Client Keycloak `dxos-spa` phải cho `redirect_uri` và `post_logout_redirect_uri` dưới `/apps/*` (realm của repo cấu hình
sẵn `https://${DXOS_DOMAIN}/apps/*`).

## Gọi API: `DxosClient`
```ts
import { DxosClient, ApiError } from 'dxos-sdk-js'

const client = new DxosClient({
  getToken: () => auth.token(),
  onUnauthorized: () => { /* 401: ví dụ chuyển sang đăng nhập; gọi tối đa một lần mỗi phản hồi 401 */ },
  // baseUrl: ''   (mặc định, cùng origin)    fetch: (tùy chọn, để test)
})

const view = await client.manifest('phong-ho-so')              // nhãn, trường, giới hạn tệp, vai trò, decision của task
const rec = await client.create('phong-ho-so', 'van_ban', { tieu_de: 'Công văn 12' })
await client.patch('phong-ho-so', 'van_ban', rec.id, { tieu_de: 'Công văn 12 (sửa)' })   // tự GET lấy version làm If-Match
const { upload_id } = await client.upload('phong-ho-so', 'van_ban', rec.id, file, file.name)
const status = await client.uploadStatus(upload_id)             // STAGING | CLEAN | INFECTED | REJECTED
const rows = await client.listAll('phong-ho-so', 'van_ban')    // theo trang, tối đa 2000 dòng mặc định
const seal = await client.seal('phong-ho-so', 'van_ban', rec.id)   // seal_id, verify_url, public_fields

try {
  await client.start('phong-ho-so', 'van_ban', rec.id)
} catch (e) {
  if (e instanceof ApiError) console.log(e.status, e.slug, e.problem)   // slug: 'guard-failed', 'not-found'...
}
```
Quy tắc của client (đã có test):
- Mọi ghi cần `If-Match` (`patch`, `start`, `complete`, `piiReview`, `revoke`, `erasePii`) **GET bản ghi ngay trước đó** để
  lấy `version`, rồi gửi `If-Match: "<version>"`. Nếu bản ghi đổi giữa hai bước thì lõi trả 409/412 và SDK ném lỗi.
- **Không bao giờ tự thử lại** yêu cầu ghi. `bulk` từ chối trước khi gửi nếu quá 500 dòng.
- Lỗi `application/problem+json` thành `ApiError { status, slug, title, detail, problem }`. Phản hồi không phải JSON của
  gateway (401, 413, 429...) có slug `http-<status>`.
- Đoạn đường dẫn được mã hóa, kể cả dấu `.`, nên `..` không đi lên thư mục cha.
- Gọi công khai (`publicSeal`, `checkHash`, `bundle`) là ẩn danh: không gửi token, 401 không kích hoạt `onUnauthorized`.

Các phương thức khác: `whoami`, `list`, `get`, `bulk`, `attachments`, `download`, `tasks`, `complete`, `piiReview`, `revoke`,
`erasePii`. Kiểu trả về nằm trong `src/types.ts`.

## Tự kiểm gói bằng chứng: `verifyBundle`
Bản dịch từng bước của `dxos-witness verify-bundle` sang TypeScript, dùng WebCrypto (Ed25519, SHA-256); hai bên chạy chung
một bộ vector trong test để phát hiện lệch kết quả (còn hai khác biệt đã biết ở mục "Phạm vi và giới hạn"). Tệp gốc của người dùng chỉ được băm tại máy, không được tải lên.

```ts
import { DxosClient, rawAnchor, sha256Hex, verifyBundle } from 'dxos-sdk-js'

const client = new DxosClient({ getToken: async () => null })      // đối soát công khai: không cần đăng nhập
const sealId = location.hash.slice(1)
const fileSha256 = await sha256Hex(file)                           // file: File người dùng chọn
const check = await client.checkHash(sealId, fileSha256)           // chỉ gửi hash, không gửi tệp
if (!check.match) throw new Error('Tệp không khớp niêm phong')
const text = await client.bundle(sealId, fileSha256)              // văn bản gói JSON thô (niêm phong không đòi tệp: client.bundle(sealId))

const res = await verifyBundle(text, {
  fileSha256,
  anchor: rawAnchor('https://raw.githubusercontent.com/<tổ-chức>/<repo-neo>/main'),   // bỏ trường này = không đối chiếu repo neo
})
if (res.ok) console.log(res.pinned ? 'đã đối chiếu repo neo' : 'chưa đối chiếu repo neo', res.issuer)
else console.log(res.code, res.message)    // res.code là FailCode: FORMAT, SIGNATURE, INCLUSION, NOT_ANCHORED...
```
- `verifyBundle` không ném lỗi: mọi lỗi bất ngờ thành `MALFORMED`; môi trường thiếu Ed25519 trong WebCrypto thành
  `UNSUPPORTED_CRYPTO`. Trường `status` trong gói không được ký nên bị bỏ qua.
- Có `anchor` thì khóa, tuyên bố khóa và STH lấy từ repo neo (kết quả `pinned: true`, kể cả khi không hợp lệ). `rawAnchor`
  không theo chuyển hướng và chỉ gọi đúng host của `base`.
- Người gọi phải giải mã gói bằng UTF-8 nghiêm ngặt (`new TextDecoder('utf-8', { fatal: true, ignoreBOM: true })`) nếu tự
  đọc từ tệp. `client.bundle` đã trả văn bản.
- Cổng đối soát đầy đủ (rơi về không ghim khi repo neo không truy cập được, nhãn kết quả): `verify-portal/app/src/verify.ts`.

## Thành phần Vue (`dxos-sdk-js/vue`)
| Thành phần | Dùng để |
|---|---|
| `QuarantineStatus` | Hiện trạng thái kiểm dịch của một tệp (`client`, `uploadId`; `initial` bỏ qua thăm dò khi đã biết kết quả). Thăm dò đến khi xong, lỗi tạm thời (408, 429, 5xx, mạng) thì thử tiếp; phát `settled` |
| `SealQr` | Mã QR cho `verify_url` (chỉ nhận URL cùng origin, đường dẫn `/apps/verify/` và fragment là mã niêm phong; URL khác thì không vẽ) |
| `VerifyLink` | Liên kết "Mở trang đối soát" (cùng kiểm URL) |
| `RecordForm` | Biểu mẫu sinh từ `CollectionView` của manifest; `v-model` và sự kiện `submit` (payload chỉ gồm trường đã đổi: **PATCH bằng `submit`, không bằng `v-model`**) |
| `ProblemMessage` | Hiện lỗi API thành câu tiếng Việt (`messageFor`) |
| `AppShell`, `ConfirmDialog` | Khung ứng dụng (đăng nhập, tải manifest, màn hình lỗi, thanh trên) và hộp xác nhận |
| `SealPanel`, `PiiPanel` | Panel niêm phong (QR, thu hồi) và rà soát/xóa PII dùng chung cho App A, App B |
| `boot`, `connect`, `createSession`, `useSession` | Khởi động ứng dụng và phiên làm việc (client, vai trò, manifest) |

```ts
// main.ts của một ứng dụng
import { createAuth } from 'dxos-sdk-js'
import { boot, connect } from 'dxos-sdk-js/vue'
import 'dxos-sdk-js/style.css'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'

const BASE = '/apps/so-muon-sach/'
await boot({
  auth: createAuth({ appBase: BASE }),
  mount: '#app',
  root: App,
  connect: (auth) => connect(auth, { app: 'so-muon-sach', marker: 'dxos:so-muon-sach:login-attempt' }),
  makeRouter: () => createRouter({ history: createWebHashHistory(), routes: [/* ... */] }),   // router băm: không cần cấu hình try_files
})
```
```vue
<script setup lang="ts">
import { QuarantineStatus, RecordForm, ProblemMessage } from 'dxos-sdk-js/vue'
// client: DxosClient từ useSession(); collection: CollectionView lấy từ client.manifest()
</script>
<template>
  <RecordForm v-model="draft" :view="collection" mode="create" @submit="save" />
  <QuarantineStatus :client="client" :upload-id="uploadId" @settled="reload" />
  <ProblemMessage :error="error" />
</template>
```
Ví dụ đầy đủ chạy được: [examples/so-muon-sach](../../examples/so-muon-sach/) và hướng dẫn
[docs/tutorial-app-30-phut.md](../../docs/tutorial-app-30-phut.md). Mọi chuỗi giao diện bằng tiếng Việt;
`messageFor` có câu riêng cho mọi mã lỗi của lõi (test `CORE_SLUGS` đối chiếu với mã nguồn lõi).

## Công cụ test (`dxos-sdk-js/testing`)
Chỉ import trong test (nó nhập `vitest`; hai `index.ts` không bao giờ nhắc tới nó, có test kiểm).

```ts
import type { ManifestView } from 'dxos-sdk-js'
import { fakeClient, fakeFetch, problem, rec, sealInfo } from 'dxos-sdk-js/testing'

const view = {} as ManifestView        // thay bằng manifest mẫu của ứng dụng (kiểu trả về của client.manifest())
const record1 = rec({ id: 'r1' })       // bản ghi mẫu

// Client giả: mỗi phương thức của DxosClient là vi.fn.
const client = fakeClient({
  manifest: view,                                // giá trị: trả cho mọi lần gọi
  create: [record1, problem('guard-failed', { reason: 'pii_not_reviewed' })],   // mảng: lần lượt từng lần gọi (lần cuối lặp lại)
  seal: async (app, col, id) => sealInfo(),      // hàm: nhận đối số
  whoamiRoles: ['app:phong-ho-so:chuyen_vien'],  // vai trò của whoami()
})
// Phương thức không cấu hình sẽ từ chối với lỗi rõ ràng, không im lặng trả undefined.

// fetch giả cho DxosClient thật:
const f = fakeFetch([{ json: { items: [] } }, { status: 403, problem: { type: 'https://dxos.dev/problems/guard-failed', title: 'x', status: 403 } }])
```
Ngoài ra có `client` (DxosClient thật trên fetch giả), `rec`, `task`, `att`, `sealInfo` (dữ liệu mẫu) và `apiErr` (tên khác của `problem`).
Với phương thức trả mảng (`listAll`, `attachments`, `tasks`, `bulk`), một mảng phẳng là *giá trị*, không phải chuỗi
kết quả lần lượt; muốn lần lượt thì bọc mỗi lần trong một mảng.

## Cấu trúc thư mục
`src/client.ts` (client), `src/auth.ts` (OIDC), `src/proof/` (JSON chuẩn hóa, Merkle, gói bằng chứng, repo neo),
`src/vue/` (thành phần), `src/testing.ts`, `test/` (Vitest). Quy tắc mã web (cấm `v-html`, `innerHTML`, `eval`,
`localStorage`, phiên bản npm ghim chính xác, header SPDX): `tests/repo/test_web_hygiene.py`.
