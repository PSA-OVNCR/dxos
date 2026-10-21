<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Chi tiết văn bản: trường theo nhãn manifest, tệp đính kèm (lấy từ máy chủ), sửa, tải tệp, gửi duyệt.
// Ẩn nút theo chủ sở hữu/trạng thái chỉ là tiện dụng; lõi quyết định và mọi lỗi của lõi hiện bằng ProblemMessage.
// Không có yêu cầu ghi nào được tự thử lại; lỗi 409/412 thì báo và gợi ý tải lại.
import { ApiError, type AttachmentItem, type DxRecord, type UploadStatus } from 'dxos-sdk-js'
import { PiiPanel, ProblemMessage, QuarantineStatus, RecordForm, SealPanel } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { pdfFileName, saveBlob } from '../download'
import { APP, COL, useSession } from '../session'
import { formatVn, statusLabel } from '../status'

const props = defineProps<{ id: string }>()
const { client, view } = useSession()

const collection = computed(() => view.value?.collections[COL])
const maxMb = computed(() => collection.value?.attachments?.max_mb ?? 0)

const record = ref<DxRecord | null>(null)
const files = ref<AttachmentItem[]>([])
const loading = ref(true)
const loadError = ref<unknown>(null)
const filesError = ref<unknown>(null)
const actionError = ref<unknown>(null)
const notice = ref('')
const busy = ref(false)
const editing = ref(false)
const draft = ref<Record<string, unknown>>({})

// Mỗi lần tải lại tăng số này; phản hồi của lần cũ (đổi bản ghi giữa chừng) bị bỏ.
let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

/** Chủ bản ghi, chưa vào quy trình, chưa niêm phong: điều kiện để hiện nút ghi (tiện dụng, lõi vẫn kiểm lại). */
const canWrite = computed(() => {
  const r = record.value
  return !!r && r.is_owner && r.wf_state !== 'running' && r.seal_state === 'NONE'
})
const title = computed(() => {
  const n = show(record.value?.data.so_hieu)
  return n === '—' ? 'Văn bản' : n
})
const reloadHint = computed(() => {
  const e = actionError.value
  return e instanceof ApiError && (e.status === 409 || e.status === 412)
})

function show(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Có' : 'Không'
  return String(v)
}

function statusOf(a: AttachmentItem): UploadStatus {
  switch (a.status) {
    case 'CLEAN': return { status: 'CLEAN', sha256: a.sha256 ?? '' }
    case 'INFECTED': return { status: 'INFECTED', reason: a.reason }
    case 'REJECTED': return { status: 'REJECTED', reason: a.reason ?? '' }
    default: return { status: 'STAGING' }
  }
}

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  loadError.value = null
  filesError.value = null
  actionError.value = null // tải lại là cách thoát khỏi lỗi cũ (nhất là 409)
  notice.value = ''
  const [r, a] = await Promise.allSettled([
    client.get(APP, COL, props.id),
    client.attachments(APP, COL, props.id),
  ])
  if (mine !== run || !alive) return
  loading.value = false
  if (r.status === 'rejected') {
    record.value = null
    loadError.value = r.reason
    return
  }
  record.value = r.value
  if (a.status === 'fulfilled') files.value = a.value
  else {
    files.value = []
    filesError.value = a.reason
  }
}

async function reloadFiles(): Promise<void> {
  const mine = run
  try {
    const list = await client.attachments(APP, COL, props.id)
    if (mine === run && alive) {
      files.value = list
      filesError.value = null
    }
  } catch (e) {
    if (mine === run && alive) filesError.value = e
  }
}

/** Sau thao tác của PiiPanel/SealPanel: đọc lại bản ghi và tệp mà không dựng lại cả màn hình (giữ thông báo của hai khối). */
async function refresh(): Promise<void> {
  const mine = ++run
  try {
    const r = await client.get(APP, COL, props.id)
    if (mine !== run || !alive) return
    record.value = r
    await reloadFiles()
  } catch (e) {
    if (mine === run && alive) actionError.value = e
  }
}

watch(() => props.id, () => {
  editing.value = false
  void load()
}, { immediate: true })

/** Chạy một thao tác ghi đúng một lần; chặn bấm đúp bằng `busy`. */
async function act(fn: () => Promise<void>): Promise<void> {
  if (busy.value) return
  busy.value = true
  actionError.value = null
  notice.value = ''
  try {
    await fn()
  } catch (e) {
    if (alive) actionError.value = e
  } finally {
    busy.value = false
  }
}

function startEdit(): void {
  draft.value = { ...(record.value?.data ?? {}) }
  editing.value = true
  actionError.value = null
}

/** `changes` là payload `submit` của RecordForm (chỉ trường đã đổi), KHÔNG phải v-model: v-model chứa PII đã che. */
function save(changes: Record<string, unknown>): Promise<void> {
  return act(async () => {
    if (Object.keys(changes).length > 0) record.value = await client.patch(APP, COL, props.id, changes)
    editing.value = false
  })
}

function submitForApproval(): Promise<void> {
  return act(async () => {
    record.value = await client.start(APP, COL, props.id)
  })
}

/** Tệp đã qua kiểm dịch sạch: chỉ bản đã niêm phong mới đưa tải về. */
function sealedFiles(sealed: boolean): AttachmentItem[] {
  return sealed ? files.value.filter((f) => f.status === 'CLEAN' && f.sha256) : []
}

/** `run` là hàm chạy-một-lần của SealPanel: chung trạng thái bận và khung báo lỗi với các nút của nó. */
function download(run: (fn: () => Promise<void>) => Promise<boolean>, f: AttachmentItem, index: number, count: number): Promise<boolean> {
  return run(async () => {
    const blob = await client.download(f.sha256 ?? '')
    saveBlob(blob, pdfFileName(record.value?.data.so_hieu, props.id, count > 1 ? index + 1 : undefined))
  })
}

function isPdf(f: File): boolean {
  return f.type === 'application/pdf' || (f.type === '' && /\.pdf$/i.test(f.name))
}

async function onFile(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  notice.value = ''
  actionError.value = null
  // Kiểm trước để khỏi tốn một lần tải; máy chủ vẫn kiểm lại và là bên quyết định.
  if (!isPdf(file)) notice.value = 'Chỉ nhận tệp PDF.'
  else if (file.size === 0) notice.value = 'Tệp rỗng.'
  else if (file.size > maxMb.value * 1024 * 1024) notice.value = `Tệp lớn hơn ${maxMb.value} MB, hãy chọn tệp nhỏ hơn.`
  else {
    await act(async () => {
      await client.upload(APP, COL, props.id, file, file.name)
      await reloadFiles()
    })
  }
  input.value = ''
}
</script>

<template>
  <p v-if="loading" role="status">Đang tải…</p>
  <template v-else-if="loadError">
    <ProblemMessage :error="loadError" />
    <div class="dx-actions"><button type="button" @click="load()">Tải lại</button></div>
  </template>

  <template v-else-if="record && collection">
    <div class="dx-toolbar">
      <h1>{{ title }}</h1>
      <span class="dx-status">{{ statusLabel(record) }}</span>
    </div>

    <ProblemMessage :error="actionError" />
    <p v-if="notice" class="dx-problem" role="alert">{{ notice }}</p>
    <div v-if="reloadHint" class="dx-actions">
      <button type="button" class="dx-secondary" @click="load()">Tải lại</button>
    </div>

    <RecordForm v-if="editing" v-model="draft" :view="collection" mode="edit" :required-extra="['loai_van_ban']" @submit="save">
      <template #actions>
        <div class="dx-actions">
          <button type="submit" :disabled="busy">Lưu thay đổi</button>
          <button type="button" class="dx-secondary" @click="editing = false">Hủy</button>
        </div>
      </template>
    </RecordForm>
    <dl v-else class="dx-fields">
      <template v-for="(f, name) in collection.fields" :key="name">
        <dt>{{ f.label ?? name }}</dt>
        <dd>{{ show(record.data[name]) }}</dd>
      </template>
      <dt>Cập nhật (giờ VN)</dt>
      <dd>{{ formatVn(record.updated_at) }}</dd>
    </dl>

    <div v-if="canWrite && !editing" class="dx-actions">
      <button type="button" class="dx-secondary" :disabled="busy" @click="startEdit">Sửa</button>
      <button type="button" :disabled="busy" @click="submitForApproval">Gửi duyệt</button>
    </div>

    <SealPanel :app="APP" :col="COL" :record="record" @changed="refresh()">
      <template #actions="{ sealed, busy: sealBusy, run }">
        <button
          v-for="(f, i) in sealedFiles(sealed)"
          :key="f.upload_id"
          type="button"
          :disabled="sealBusy"
          @click="download(run, f, i, sealedFiles(sealed).length)"
        >
          Tải bản PDF đã ban hành{{ sealedFiles(sealed).length > 1 ? ` (tệp ${i + 1})` : '' }}
        </button>
      </template>
    </SealPanel>
    <PiiPanel :app="APP" :col="COL" :record="record" :collection="collection" @changed="refresh()" />

    <section aria-labelledby="dx-files-h">
      <h2 id="dx-files-h">Tệp đính kèm</h2>
      <ProblemMessage :error="filesError" />
      <p v-if="files.length === 0 && !filesError">Chưa có tệp nào.</p>
      <ul v-else class="dx-files">
        <li v-for="(a, i) in files" :key="a.upload_id">
          <p>Tệp {{ i + 1 }} <span class="dx-meta">· tải lên {{ formatVn(a.created_at) }}</span></p>
          <QuarantineStatus
            :client="client"
            :upload-id="a.upload_id"
            :initial="statusOf(a)"
            @settled="reloadFiles()"
          />
        </li>
      </ul>
      <div v-if="canWrite && collection.attachments" class="dx-field">
        <label for="dx-file">Chọn tệp PDF để tải lên</label>
        <input id="dx-file" type="file" name="file" accept="application/pdf" :disabled="busy" @change="onFile">
        <small class="dx-meta">
          Tối đa {{ collection.attachments.max_mb }} MB mỗi tệp; cần ít nhất {{ collection.attachments.min }} tệp đã qua kiểm dịch để gửi duyệt.
        </small>
      </div>
    </section>
  </template>
</template>
