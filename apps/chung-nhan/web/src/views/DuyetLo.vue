<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Duyệt theo lô: lõi không có API lô riêng, SPA gọi `complete` lần lượt cho từng mục đã chọn. Một mục lỗi (ví dụ task-gone)
// không làm dừng các mục còn lại; kết quả báo riêng từng mục; không bao giờ tự thử lại một lời gọi ghi.
// Quyết định thật (kể cả "người tạo không được tự duyệt") do lõi; mọi lỗi hiện bằng ProblemMessage.
import { formatVn, type DxRecord, type TaskItem } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { APP, useSession } from '../session'
import { show } from '../status'

interface Item { task: TaskItem; record: DxRecord | null; error: unknown }
interface Report { approved: number; failed: { label: string; error: unknown }[] }

const { client } = useSession()
const items = ref<Item[]>([])
const selected = ref<string[]>([])
const loading = ref(true)
const loadError = ref<unknown>(null)
const busy = ref(false)
const report = ref<Report | null>(null)

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

function title(it: Item): string {
  return it.record ? `${show(it.record.data.ho_ten)} · ${show(it.record.data.su_kien)}` : it.task.name
}

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  loadError.value = null
  try {
    const tasks = await client.tasks(APP)
    const records = await Promise.allSettled(tasks.map((t) => client.get(APP, t.collection, t.record_id)))
    if (mine !== run || !alive) return
    items.value = tasks.map((task, i): Item => {
      const r = records[i]
      return r?.status === 'fulfilled' ? { task, record: r.value, error: null } : { task, record: null, error: r?.reason }
    })
    selected.value = selected.value.filter((id) => tasks.some((t) => t.task_id === id))
  } catch (e) {
    if (mine !== run || !alive) return
    items.value = []
    selected.value = []
    loadError.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}

onMounted(() => { void load() })

function selectAll(): void {
  selected.value = items.value.map((it) => it.task.task_id)
}

async function approveSelected(): Promise<void> {
  if (busy.value || selected.value.length === 0) return
  busy.value = true
  report.value = null
  const picked = items.value.filter((it) => selected.value.includes(it.task.task_id))
  const result: Report = { approved: 0, failed: [] }
  try {
    for (const it of picked) {
      try {
        await client.complete(APP, it.task, 'approve')
        result.approved += 1
      } catch (e) {
        result.failed.push({ label: title(it), error: e })
      }
    }
  } finally {
    busy.value = false
  }
  if (!alive) return
  report.value = result
  selected.value = []
  await load()
}
</script>

<template>
  <div class="dx-toolbar">
    <h1>Duyệt theo lô</h1>
    <button type="button" class="dx-secondary" :disabled="busy" @click="load()">Tải lại</button>
  </div>

  <ProblemMessage :error="loadError" />
  <template v-if="report">
    <p role="status">{{ report.approved }} đã duyệt, {{ report.failed.length }} lỗi.</p>
    <ul v-if="report.failed.length > 0" class="dx-csv-errors">
      <li v-for="(f, i) in report.failed" :key="i"><strong>{{ f.label }}</strong> <ProblemMessage :error="f.error" /></li>
    </ul>
  </template>

  <p v-if="loading" role="status">Đang tải…</p>
  <p v-else-if="!loadError && items.length === 0">Không có việc nào đang chờ bạn.</p>
  <template v-else-if="items.length > 0">
    <div class="dx-actions">
      <button type="button" class="dx-secondary" :disabled="busy" @click="selectAll">Chọn tất cả</button>
      <button type="button" class="dx-secondary" :disabled="busy" @click="selected = []">Bỏ chọn tất cả</button>
      <button type="button" :disabled="busy || selected.length === 0" @click="approveSelected">Duyệt các mục đã chọn</button>
    </div>
    <ul class="dx-tasks">
      <li v-for="it in items" :key="it.task.task_id">
        <label class="dx-check">
          <input v-model="selected" type="checkbox" name="task" :value="it.task.task_id" :disabled="busy">
          <strong>{{ title(it) }}</strong>
          <span class="dx-meta"> · giao lúc {{ formatVn(it.task.created) }}</span>
        </label>
        <ProblemMessage :error="it.error" />
        <RouterLink :to="`/chung-nhan/${encodeURIComponent(it.task.record_id)}`">Mở chứng nhận</RouterLink>
      </li>
    </ul>
  </template>
</template>
