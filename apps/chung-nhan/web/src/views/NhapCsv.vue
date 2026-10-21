<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Nhập chứng nhận từ CSV Excel: (1) chọn tệp và xem bảng mã nhận diện, (2) xem trước 20 dòng và danh sách lỗi theo dòng,
// (3) tạo bằng `bulk` theo lô 500 dòng, (4) gửi duyệt từng bản ghi vừa tạo, tuần tự, có tiến độ.
// SPA chỉ chuẩn bị dữ liệu (csv.ts); lõi kiểm tra lại từng dòng và là bên quyết định. Mọi lời gọi ghi chạy đúng một lần,
// không bao giờ tự thử lại; lỗi của một dòng hay một mục không làm dừng các mục còn lại (trừ khi cả lời gọi `bulk` hỏng).
import { ApiError, slugOf } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, ref, useId } from 'vue'
import { CsvError, decodeCsv, mapRows, parseCsvWithLines, type CsvEncoding, type MappedRows } from '../csv'
import { APP, COL, useSession } from '../session'
import { dateVn, show } from '../status'

const BATCH = 500 // giới hạn một lời gọi bulk của lõi
const PREVIEW = 20

interface Created { id: string; line: number; name: string }
interface RowError { line: number; error: unknown }
interface StartError { id: string; line: number; name: string; error: unknown }

const { client, view } = useSession()
const fileId = useId()
const createProgressId = useId()
const startProgressId = useId()

const collection = computed(() => view.value?.collections[COL])
/** Cột nhập được, theo thứ tự manifest (trường số thứ tự do lõi cấp nên không có). */
const columns = computed(() => Object.entries(collection.value?.fields ?? {})
  .filter(([, f]) => f.type !== 'sequence')
  .map(([name, f]) => ({ name, label: f.label ?? name, date: f.type === 'date' })))

const ENCODING_TEXT: Record<CsvEncoding, string> = {
  'utf-8': 'UTF-8',
  'utf-16le': 'UTF-16 LE (Excel "Unicode Text")',
  'utf-16be': 'UTF-16 BE',
  'windows-1258': 'Windows-1258 (đã đọc theo bảng mã Windows-1258, dấu tiếng Việt được ghép về dạng chuẩn)',
}

const encoding = ref<CsvEncoding | null>(null)
const readError = ref('')
const mapped = ref<MappedRows | null>(null)

const phase = ref<'idle' | 'creating' | 'created'>('idle')
const busy = ref(false)
const sent = ref(0)
const created = ref<Created[]>([])
const rowErrors = ref<RowError[]>([])
const createFailure = ref<{ error: unknown; from: number; to: number } | null>(null)

const started = ref<string[]>([])
const startErrors = ref<StartError[]>([])
const startDone = ref(0)
const startTotal = ref(0)

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

const preview = computed(() => (mapped.value?.ok ?? []).slice(0, PREVIEW))
const canCreate = computed(() =>
  !busy.value && phase.value === 'idle' && !!mapped.value && mapped.value.errors.length === 0 && mapped.value.ok.length > 0)
const pending = computed(() => created.value.filter((c) => !started.value.includes(c.id)))

function reset(): void {
  encoding.value = null
  readError.value = ''
  mapped.value = null
  phase.value = 'idle'
  sent.value = 0
  created.value = []
  rowErrors.value = []
  createFailure.value = null
  started.value = []
  startErrors.value = []
  startDone.value = 0
  startTotal.value = 0
}

async function onFile(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  const mine = ++run
  reset()
  if (!file || !collection.value) return
  try {
    const decoded = decodeCsv(new Uint8Array(await file.arrayBuffer()))
    if (mine !== run || !alive) return
    encoding.value = decoded.encoding
    const { rows, lines } = parseCsvWithLines(decoded.text)
    mapped.value = mapRows(rows, collection.value, lines)
  } catch (e) {
    if (mine !== run || !alive) return
    readError.value = e instanceof CsvError ? e.message : 'Không đọc được tệp này. Hãy lưu lại từ Excel dưới dạng CSV rồi chọn lại.'
  }
}

/** Lỗi của một dòng do lõi báo trong `bulk` (không có status HTTP riêng) thành ApiError để ProblemMessage hiện câu tiếng Việt. */
function rowProblem(e: { type: string; title: string; errors?: { path: string; msg: string }[] }): ApiError {
  return new ApiError(422, slugOf(e.type), e.title, undefined, e as unknown as Record<string, unknown>)
}

async function create(): Promise<void> {
  const m = mapped.value
  if (!canCreate.value || !m) return
  busy.value = true
  phase.value = 'creating'
  const rows = m.ok
  const lineAt = (i: number): number => m.lines[i] ?? i + 2
  try {
    for (let from = 0; from < rows.length; from += BATCH) {
      const chunk = rows.slice(from, from + BATCH)
      let results
      try {
        results = await client.bulk(APP, COL, chunk)
      } catch (e) {
        // Lô này không rõ đã ghi được bao nhiêu dòng: dừng, không tự thử lại, không gửi các lô sau.
        if (alive) createFailure.value = { error: e, from: lineAt(from), to: lineAt(from + chunk.length - 1) }
        break
      }
      if (!alive) return
      results.forEach((r, i) => {
        if (r.ok) created.value.push({ id: r.id, line: lineAt(from + i), name: String(chunk[i]?.ho_ten ?? '') })
        else rowErrors.value.push({ line: lineAt(from + i), error: rowProblem(r.error) })
      })
      sent.value = from + chunk.length
    }
  } finally {
    phase.value = 'created'
    busy.value = false
  }
}

async function submit(): Promise<void> {
  if (busy.value || pending.value.length === 0) return
  busy.value = true
  const todo = [...pending.value]
  startTotal.value = todo.length
  startDone.value = 0
  startErrors.value = startErrors.value.filter((e) => !todo.some((t) => t.id === e.id))
  try {
    for (const item of todo) {
      try {
        await client.start(APP, COL, item.id)
        if (alive) started.value.push(item.id)
      } catch (e) {
        if (alive) startErrors.value.push({ id: item.id, line: item.line, name: item.name, error: e })
      }
      if (alive) startDone.value += 1
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <h1>Nhập chứng nhận từ CSV</h1>

  <section aria-labelledby="dx-csv-1">
    <h2 id="dx-csv-1">Bước 1. Chọn tệp</h2>
    <p class="dx-meta">
      Tệp CSV lưu từ Excel (UTF-8, Windows-1258 hoặc UTF-16; phân cách dấu phẩy, chấm phẩy hoặc TAB). Dòng đầu là tiêu đề
      gồm các cột: {{ columns.map((c) => c.label).join(', ') }}. Ngày dạng DD/MM/YYYY.
    </p>
    <div class="dx-field">
      <label :for="fileId">Tệp CSV</label>
      <input :id="fileId" type="file" name="file" accept=".csv,.txt,text/csv,text/plain" :disabled="busy" @change="onFile">
    </div>
    <p v-if="encoding" role="status">Bảng mã nhận diện: {{ ENCODING_TEXT[encoding] }}.</p>
    <p v-if="readError" class="dx-problem" role="alert">{{ readError }}</p>
  </section>

  <section v-if="mapped" aria-labelledby="dx-csv-2">
    <h2 id="dx-csv-2">Bước 2. Xem trước</h2>
    <p>{{ mapped.ok.length }} dòng hợp lệ, {{ mapped.errors.length }} dòng lỗi.</p>
    <template v-if="mapped.errors.length > 0">
      <p class="dx-problem" role="alert">Hãy sửa các dòng lỗi trong tệp rồi chọn lại tệp; chưa có gì được gửi lên máy chủ.</p>
      <ul class="dx-csv-errors">
        <li v-for="(e, i) in mapped.errors" :key="i">Dòng {{ e.line }}: {{ e.message }}</li>
      </ul>
    </template>
    <p v-else-if="mapped.ok.length === 0">Tệp không có dòng dữ liệu nào.</p>
    <template v-if="preview.length > 0">
      <p v-if="mapped.ok.length > PREVIEW" class="dx-meta">Hiển thị {{ PREVIEW }} dòng đầu trong {{ mapped.ok.length }} dòng.</p>
      <div class="dx-scroll">
        <table class="dx-table">
          <thead>
            <tr><th v-for="c in columns" :key="c.name" scope="col">{{ c.label }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in preview" :key="i">
              <td v-for="c in columns" :key="c.name">{{ c.date ? dateVn(r[c.name]) : show(r[c.name]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>

  <section v-if="mapped" aria-labelledby="dx-csv-3">
    <h2 id="dx-csv-3">Bước 3. Tạo chứng nhận</h2>
    <p class="dx-meta">Mỗi lần gửi tối đa {{ BATCH }} dòng. Dòng nào lõi từ chối thì được báo riêng, các dòng còn lại vẫn được tạo.</p>
    <div class="dx-actions">
      <button type="button" :disabled="!canCreate" @click="create">Tạo chứng nhận</button>
    </div>
    <div v-if="phase !== 'idle'" class="dx-field">
      <label :for="createProgressId">Tiến độ tạo</label>
      <progress :id="createProgressId" :value="sent" :max="mapped.ok.length" />
      <span class="dx-meta">{{ sent }}/{{ mapped.ok.length }} dòng</span>
    </div>
    <template v-if="phase === 'created'">
      <p role="status">Đã tạo {{ created.length }} chứng nhận, {{ rowErrors.length }} dòng lỗi.</p>
      <ul v-if="rowErrors.length > 0" class="dx-csv-errors">
        <li v-for="e in rowErrors" :key="e.line">Dòng {{ e.line }}: <ProblemMessage :error="e.error" /></li>
      </ul>
      <template v-if="createFailure">
        <ProblemMessage :error="createFailure.error" />
        <p class="dx-problem" role="alert">
          Lô gồm các dòng {{ createFailure.from }} đến {{ createFailure.to }} không rõ đã tạo được bao nhiêu; các lô sau chưa được gửi.
          Hệ thống không tự thử lại. Hãy kiểm tra danh sách chứng nhận trước khi nhập lại.
        </p>
      </template>
    </template>
  </section>

  <section v-if="created.length > 0" aria-labelledby="dx-csv-4">
    <h2 id="dx-csv-4">Bước 4. Gửi duyệt</h2>
    <p class="dx-meta">Mỗi chứng nhận vừa tạo được đưa vào quy trình phê duyệt của trưởng CLB, lần lượt từng cái.</p>
    <div class="dx-actions">
      <button type="button" :disabled="busy || pending.length === 0" @click="submit">Gửi duyệt</button>
    </div>
    <div v-if="startTotal > 0" class="dx-field">
      <label :for="startProgressId">Tiến độ gửi duyệt</label>
      <progress :id="startProgressId" :value="startDone" :max="startTotal" />
      <span class="dx-meta">{{ startDone }}/{{ startTotal }}</span>
    </div>
    <template v-if="startTotal > 0 && !busy">
      <p role="status">Đã gửi duyệt {{ started.length }}, lỗi {{ startErrors.length }}.</p>
      <ul v-if="startErrors.length > 0" class="dx-csv-errors">
        <li v-for="e in startErrors" :key="e.id">Dòng {{ e.line }}: <strong>{{ e.name }}</strong> <ProblemMessage :error="e.error" /></li>
      </ul>
      <p v-if="startErrors.length > 0" class="dx-meta">Bấm "Gửi duyệt" lần nữa để gửi lại riêng các mục lỗi.</p>
    </template>
  </section>
</template>
