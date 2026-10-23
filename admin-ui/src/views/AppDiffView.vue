<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Diff quyền của một phiên bản (GET apps/{id}/versions/{v}/diff) và nút duyệt (POST apps/{id}:approve {"version"}).
// Mọi dòng diff là VĂN BẢN (nội suy {{ }}, không chèn HTML): tên role/trường do người nộp đặt, có thể chứa mã HTML.
// Chỉ các chính sách an toàn của manifest (PII, niêm phong, đối soát) được làm nổi khi đổi: nhãn "Đổi" (hoặc "Mới" khi
// trước đó chưa có) bằng chữ cùng viền màu. Quyền `access` của bộ dữ liệu và `guards` của bước quy trình KHÔNG được làm nổi:
// chúng hiện như dòng thường, người duyệt phải đọc. Bốn mắt do máy chủ quyết định: SPA không tự chặn, chỉ hiện câu trả lời.
// Khi tham số route đổi, trang xóa sạch và tải lại; nút duyệt luôn gửi đúng phiên bản của diff đang hiện (`shown`).
import { formatVn } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAdminApi, type AppVersionRow, type InstalledView, type PermissionDiff } from '../api'
import StateBadge from '../StateBadge.vue'
import { appStatusState, short } from '../status'

const props = defineProps<{ id: string; version: string }>()
const api = useAdminApi()

const diff = ref<PermissionDiff | null>(null)
const row = ref<AppVersionRow | null>(null)
const error = ref<unknown>(null)
const loading = ref(false)
/** Phiên bản mà diff/dòng trạng thái đang hiện thuộc về; null khi chưa tải xong. Nút duyệt chỉ dùng giá trị này. */
const shown = ref<{ id: string; version: string } | null>(null)

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

async function load(): Promise<void> {
  const mine = ++run
  const id = props.id
  const version = props.version
  loading.value = true
  error.value = null
  // Danh sách trước, diff sau (thứ tự gọi cố định); hai lời gọi độc lập nhau.
  const [list, d] = await Promise.allSettled([api.apps(), api.appDiff(id, version)])
  if (mine !== run || !alive) return
  row.value = list.status === 'fulfilled'
    ? (list.value.find((r) => r.app_id === id && r.version === version) ?? null)
    : null
  diff.value = d.status === 'fulfilled' ? d.value : null
  shown.value = d.status === 'fulfilled' ? { id, version } : null // không có diff đã thấy thì không có gì để duyệt
  const failed = [d, list].find((r): r is PromiseRejectedResult => r.status === 'rejected')
  error.value = failed ? failed.reason : null
  loading.value = false
}
onMounted(() => { void load() })

// Đổi phiên bản khi trang còn mở: bỏ ngay diff cũ (không để diff cũ dưới tiêu đề mới) rồi tải lại; phản hồi của lần
// tải trước bị loại bởi `run`.
watch(() => [props.id, props.version], () => {
  diff.value = null
  row.value = null
  shown.value = null
  error.value = null
  approved.value = null
  approveError.value = null
  approveRun++          // POST đang bay của phiên bản cũ: bỏ kết quả của nó
  approving.value = false
  void load()
})

// ---- dòng diff -----------------------------------------------------------------------------------
interface Line {
  key: string
  text: string
  /** Chỉ cho chính sách an toàn: 'changed' (cũ khác mới) hoặc 'same'. */
  floor?: 'changed' | 'same'
  /** Dòng thêm mới (nhãn "Thêm"). */
  add?: boolean
  /** Chính sách chưa có giá trị cũ để so (bản đầu tiên): nhãn "Mới" thay cho "Đổi". */
  fresh?: boolean
}

function canon(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(canon)
  if (v && typeof v === 'object') {
    return Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => [k, canon(x)]))
  }
  return v
}

function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(canon(a)) === JSON.stringify(canon(b))
}

/** Giá trị hiển thị: null = chưa có, danh sách rỗng = "(trống)", danh sách = các phần tử cách nhau dấu phẩy. */
function show(v: unknown): string {
  if (v === null || v === undefined) return '(chưa có)'
  if (Array.isArray(v)) return v.length === 0 ? '(trống)' : v.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(', ')
  if (typeof v === 'object') return JSON.stringify(canon(v))
  return String(v)
}

const POLICIES = [
  ['pii_reveal_roles', 'Vai trò được xem dữ liệu cá nhân gốc'],
  ['pii_erase_roles', 'Vai trò được xóa dữ liệu cá nhân'],
  ['seal', 'Chính sách niêm phong'],
  ['verify', 'Chính sách đối soát công khai'],
] as const

const lines = computed<Line[]>(() => {
  const d = diff.value
  if (!d) return []
  const out: Line[] = []
  if (d.roles_added.length) out.push({ key: 'roles_added', add: true, text: `Vai trò mới: ${show(d.roles_added)}` })
  if (d.collections_added.length) out.push({ key: 'collections_added', add: true, text: `Bộ dữ liệu mới: ${show(d.collections_added)}` })
  for (const [c, fields] of Object.entries(d.fields_added)) {
    out.push({ key: 'fields_added', add: true, text: `Trường mới trong ${c}: ${show(fields)}` })
  }
  for (const [c, a] of Object.entries(d.access)) {
    out.push({ key: 'access', text: `Quyền truy cập ${c}: đọc [${show(a.read)}]; tạo [${show(a.create)}]; sửa [${show(a.update)}]` })
  }
  for (const [k, label] of POLICIES) {
    const p = d[k]
    out.push({
      key: k, floor: sameValue(p.old, p.new) ? 'same' : 'changed', fresh: p.old === null,
      text: `${label}: ${show(p.old)} → ${show(p.new)}`,
    })
  }
  for (const [t, spec] of Object.entries(d.tasks)) {
    out.push({ key: 'tasks', text: `Bước quy trình ${t}: vai trò ${spec.role}; điều kiện kiểm soát [${show(spec.guards)}]` })
  }
  for (const [c, fields] of Object.entries(d.labels)) {
    for (const [f, p] of Object.entries(fields)) out.push({ key: 'labels', text: `Nhãn ${c}.${f}: ${show(p.old)} → ${show(p.new)}` })
  }
  for (const [c, fields] of Object.entries(d.sequences)) {
    for (const [f, p] of Object.entries(fields)) out.push({ key: 'sequences', text: `Số thứ tự ${c}.${f}: ${show(p.old)} → ${show(p.new)}` })
  }
  return out
})

const nothingChanged = computed(() => lines.value.every((l) => l.floor === 'same'))

// ---- duyệt -----------------------------------------------------------------------------------------
const approving = ref(false)
/** Tăng khi route đổi: kết quả của một lần duyệt thuộc về lần route cũ thì bị bỏ. */
let approveRun = 0
const approveError = ref<unknown>(null)
const approved = ref<InstalledView | null>(null)

async function approve(): Promise<void> {
  const target = shown.value
  if (approving.value || !target || !diff.value) return
  const mine = approveRun
  approving.value = true
  approveError.value = null
  approved.value = null
  try {
    // Ghi: đúng một lần mỗi lần bấm; gửi phiên bản của diff đang hiện, không phải tham số route hiện tại.
    const result = await api.approveApp(target.id, target.version)
    if (mine === approveRun) { // trang chưa chuyển sang phiên bản khác trong lúc chờ
      approved.value = result
      await load()
    }
  } catch (e) {
    if (mine === approveRun) approveError.value = e
  } finally {
    if (mine === approveRun) approving.value = false
  }
}
</script>

<template>
  <section>
    <p><a href="#/apps">← Danh sách ứng dụng</a></p>
    <div class="dx-toolbar">
      <h1>Diff quyền: {{ id }} {{ version }}</h1>
      <p class="dx-meta">
        <button type="button" class="dx-secondary" :disabled="loading" @click="load">Tải lại</button>
      </p>
    </div>

    <ProblemMessage :error="error" />
    <p v-if="loading && !diff && !error" role="status">Đang tải…</p>

    <dl v-if="diff || row" class="dx-fields">
      <template v-if="row">
        <dt>Trạng thái</dt>
        <dd data-field="status"><StateBadge :state="appStatusState(row.status)" /></dd>
        <dt>Nộp lúc</dt>
        <dd>{{ formatVn(row.created_at) }}</dd>
        <dt>Người nộp (mã ẩn)</dt>
        <dd><code v-if="row.submitted_by_ref" :title="row.submitted_by_ref">{{ short(row.submitted_by_ref) }}</code><template v-else>—</template></dd>
      </template>
      <template v-if="diff">
        <dt>So với</dt>
        <dd data-field="against">
          <template v-if="diff.against">bản {{ diff.against }} (mốc nâng cấp của ứng dụng này)</template>
          <template v-else>Chưa có bản đang hoạt động để so sánh: mọi mục dưới đây là mới.</template>
        </dd>
      </template>
    </dl>

    <template v-if="diff">
      <ul class="dx-diff">
        <li
          v-for="(l, i) in lines"
          :key="i"
          :data-key="l.key"
          :data-floor="l.floor"
          :class="{ 'dx-diff-floor': l.floor === 'changed', 'dx-diff-add': l.add }"
        >
          <span v-if="l.floor === 'changed'" class="dx-diff-tag">{{ l.fresh ? 'Mới' : 'Đổi' }}</span>
          <span v-else-if="l.floor === 'same'" class="dx-diff-tag dx-diff-tag-same">Không đổi</span>
          <span v-else-if="l.add" class="dx-diff-tag">Thêm</span>
          <span class="dx-wrap">{{ l.text }}</span>
        </li>
        <li data-key="bpmn_sha256">
          <template v-if="diff.bpmn_sha256">
            BPMN (sha256): <code :title="diff.bpmn_sha256">{{ short(diff.bpmn_sha256) }}</code>
          </template>
          <template v-else>Phiên bản này không có quy trình BPMN.</template>
        </li>
      </ul>
      <p v-if="nothingChanged" class="dx-meta">Không có thay đổi nào về quyền hay chính sách so với bản đối chiếu.</p>
    </template>

    <template v-if="diff && row && row.status === 'PENDING'">
      <div class="dx-actions">
        <button type="button" :disabled="approving" :aria-busy="approving" @click="approve">Duyệt phiên bản này</button>
        <span class="dx-meta">Cần người duyệt khác người nộp (bốn mắt); máy chủ kiểm tra.</span>
      </div>
    </template>
    <p v-if="approved" role="status" class="dx-notice">
      Đã duyệt {{ approved.app_id }} {{ approved.version }}: ứng dụng đang hoạt động.
      <template v-if="approved.self_approved"> Lưu ý: người duyệt là chính người nộp (máy chủ đang cho phép tự duyệt).</template>
    </p>
    <ProblemMessage :error="approveError" />
  </section>
</template>
