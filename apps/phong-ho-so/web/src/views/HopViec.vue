<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Hộp việc: các bước duyệt giao cho vai trò của tôi. Mục hộp việc không kèm dữ liệu bản ghi nên mỗi mục tự đọc bản ghi
// để hiện số hiệu và trích yếu. "Duyệt"/"Trả lại" gọi `complete` đúng một lần (SDK tự đọc version mới nhất);
// quyết định thật do lõi, mọi lỗi hiện bằng ProblemMessage. Không tự thử lại; 409/412 thì gợi ý tải lại.
import { ApiError, type DxRecord, type TaskItem } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { RouterLink } from 'vue-router'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { APP, useSession } from '../session'
import { formatVn } from '../status'

interface Item { task: TaskItem; record: DxRecord | null; error: unknown }

const { client } = useSession()
const items = ref<Item[]>([])
const loading = ref(true)
const loadError = ref<unknown>(null)
const actionError = ref<unknown>(null)
const notice = ref('')
const busy = ref(false)
const rejecting = ref<string | null>(null) // task_id đang mở hộp xác nhận trả lại
const comment = ref('')
const commentId = useId()

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

const reloadHint = computed(() => {
  const e = actionError.value
  return e instanceof ApiError && (e.status === 409 || e.status === 412)
})

function text(r: DxRecord | null, name: string): string {
  const v = r?.data[name]
  return v === undefined || v === null || v === '' ? '—' : String(v)
}

async function load(keepNotice = false): Promise<void> {
  const mine = ++run
  loading.value = true
  loadError.value = null
  actionError.value = null
  if (!keepNotice) notice.value = ''
  try {
    const tasks = await client.tasks(APP)
    const records = await Promise.allSettled(tasks.map((t) => client.get(APP, t.collection, t.record_id)))
    if (mine !== run || !alive) return
    items.value = tasks.map((task, i): Item => {
      const r = records[i]
      if (r?.status === 'fulfilled') return { task, record: r.value, error: null }
      return { task, record: null, error: r?.reason }
    })
  } catch (e) {
    if (mine !== run || !alive) return
    items.value = []
    loadError.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}

onMounted(() => { void load() })

function outcome(decision: string, sealState: string): string {
  if (decision === 'reject') return 'Đã trả lại văn bản.'
  if (sealState === 'SEALED') return 'Đã duyệt văn bản. Văn bản đã được niêm phong.'
  if (sealState === 'SEAL_PENDING') return 'Đã duyệt văn bản. Văn bản đang chờ niêm phong.'
  return 'Đã duyệt văn bản.'
}

/** Hoàn thành một bước đúng một lần; chặn bấm đúp bằng `busy`. Xong thì tải lại hộp việc. */
async function complete(task: TaskItem, decision: 'approve' | 'reject', note?: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  actionError.value = null
  notice.value = ''
  let done = false
  try {
    const r = await client.complete(APP, task, decision, note)
    notice.value = outcome(decision, r.seal_state)
    done = true
  } catch (e) {
    if (alive) actionError.value = e
  } finally {
    rejecting.value = null
    busy.value = false
  }
  if (done && alive) await load(true)
}

function startReject(task: TaskItem): void {
  comment.value = ''
  actionError.value = null
  rejecting.value = task.task_id
}

function confirmReject(task: TaskItem): Promise<void> {
  const note = comment.value.trim()
  return complete(task, 'reject', note === '' ? undefined : note)
}
</script>

<template>
  <div class="dx-toolbar">
    <h1>Hộp việc</h1>
    <button type="button" class="dx-secondary" :disabled="busy" @click="load()">Tải lại</button>
  </div>

  <ProblemMessage :error="loadError" />
  <ProblemMessage :error="actionError" />
  <p v-if="notice" role="status">{{ notice }}</p>
  <p v-if="reloadHint" class="dx-meta">Bấm "Tải lại" để xem hộp việc mới nhất.</p>

  <p v-if="loading" role="status">Đang tải…</p>
  <p v-else-if="!loadError && items.length === 0">Không có việc nào đang chờ bạn.</p>
  <ul v-else class="dx-tasks">
    <li v-for="it in items" :key="it.task.task_id">
      <h2>{{ it.task.name }}</h2>
      <p>
        <strong>{{ text(it.record, 'so_hieu') }}</strong> · {{ text(it.record, 'trich_yeu') }}
        <span class="dx-meta"> · giao lúc {{ formatVn(it.task.created) }}</span>
      </p>
      <ProblemMessage :error="it.error" />
      <div class="dx-actions">
        <button type="button" :disabled="busy" @click="complete(it.task, 'approve')">Duyệt</button>
        <button type="button" class="dx-secondary" :disabled="busy" @click="startReject(it.task)">Trả lại</button>
        <RouterLink :to="`/van-ban/${encodeURIComponent(it.task.record_id)}`">Mở văn bản</RouterLink>
      </div>
      <ConfirmDialog
        v-if="rejecting === it.task.task_id"
        title="Trả lại văn bản này?"
        confirm-label="Xác nhận trả lại"
        :busy="busy"
        @confirm="confirmReject(it.task)"
        @cancel="rejecting = null"
      >
        <p>Quy trình của văn bản kết thúc ở trạng thái bị trả lại. Ghi chú không được lưu: hãy báo lý do trực tiếp cho người tạo văn bản.</p>
        <div class="dx-field">
          <label :for="commentId">Ghi chú (không bắt buộc)</label>
          <textarea :id="commentId" v-model="comment" name="comment" rows="3" maxlength="1000" />
        </div>
      </ConfirmDialog>
    </li>
  </ul>
</template>
