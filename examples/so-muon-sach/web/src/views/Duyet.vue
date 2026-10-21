<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Hộp việc của thủ thư. Nút quyết định lấy từ manifest (các giá trị `decision` mà cổng của quy trình chấp nhận).
// Quyết định thật, kể cả "người tạo phiếu không tự duyệt" (not_same_actor:creator), do lõi.
import { formatVn, type DxRecord, type TaskItem } from 'dxos-sdk-js'
import { ProblemMessage, useSession } from 'dxos-sdk-js/vue'
import { onMounted, ref } from 'vue'
import { APP } from '../session'

const { client, view } = useSession()
const items = ref<{ task: TaskItem; record: DxRecord }[]>([])
const error = ref<unknown>(null)
const ready = ref(false)
const LABEL: Record<string, string> = { approve: 'Duyệt', reject: 'Từ chối' }

function decisions(t: TaskItem): string[] {
  const allowed = view.value?.workflow?.decisions[t.task_key] ?? []
  return allowed.length > 0 ? allowed : ['approve', 'reject'] // [] = manifest không hạn chế
}

async function load(): Promise<void> {
  error.value = null
  try {
    const tasks = await client.tasks(APP)
    items.value = await Promise.all(tasks.map(async (task) => ({ task, record: await client.get(APP, task.collection, task.record_id) })))
  } catch (e) {
    error.value = e
  }
  ready.value = true
}

async function decide(task: TaskItem, decision: string): Promise<void> {
  try {
    await client.complete(APP, task, decision)
    await load()
  } catch (e) {
    error.value = e
  }
}

onMounted(load)
</script>

<template>
  <h1>Hộp việc</h1>
  <ProblemMessage :error="error" />
  <p v-if="!ready" role="status">Đang tải…</p>
  <p v-else-if="items.length === 0 && !error">Không có việc nào đang chờ bạn.</p>
  <ul class="dx-tasks">
    <li v-for="{ task, record } in items" :key="task.task_id">
      <strong>{{ record.data.ten_sach }}</strong>
      <span class="dx-meta"> · giao lúc {{ formatVn(task.created) }}</span>
      <div class="dx-actions">
        <button v-for="d in decisions(task)" :key="d" type="button" @click="decide(task, d)">{{ LABEL[d] ?? d }}</button>
      </div>
    </li>
  </ul>
</template>
