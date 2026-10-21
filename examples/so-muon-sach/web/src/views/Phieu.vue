<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Danh sách phiếu và biểu mẫu tạo phiếu. Cả hai sinh từ manifest (`view`): không chép tay trường hay nhãn nào,
// và cột dữ liệu cá nhân (pii) không bao giờ lên danh sách.
import { formatVn, formatVnDate, sealLabel, type DxRecord } from 'dxos-sdk-js'
import { ProblemMessage, RecordForm, SealPanel, useSession } from 'dxos-sdk-js/vue'
import { computed, onMounted, ref } from 'vue'
import { APP, COL } from '../session'

const { client, view } = useSession()
const col = computed(() => view.value!.collections[COL]!)
const columns = computed(() => Object.entries(col.value.fields).filter(([, f]) => !f.pii))
const rows = ref<DxRecord[]>([])
const error = ref<unknown>(null)
const formKey = ref(0)
const empty = {} // giá trị đầu cố định: biểu mẫu tự giữ dữ liệu đang gõ, mỗi lần tạo xong thì đổi `key` để làm trống
const WORKFLOW: Record<string, string> = { running: 'Chờ thủ thư duyệt', 'ended:rejected': 'Bị từ chối' }

const status = (r: DxRecord): string => r.seal_state !== 'NONE' ? sealLabel(r.seal_state)
  : r.wf_state ? WORKFLOW[r.wf_state] ?? 'Đã dừng' : 'Chưa gửi duyệt'
const cell = (type: string, v: unknown): string =>
  v == null || v === '' ? '—' : (type === 'date' ? formatVnDate(String(v)) : null) ?? String(v)

/** Chạy một thao tác ghi rồi tải lại danh sách; lỗi của lõi hiện bằng ProblemMessage. Không tự thử lại. */
async function act(job: () => Promise<unknown> = async () => {}): Promise<void> {
  error.value = null
  try {
    await job()
    rows.value = await client.listAll(APP, COL)
  } catch (e) {
    error.value = e
  }
}

const create = (data: Record<string, unknown>): Promise<void> => act(async () => {
  await client.create(APP, COL, data)
  formKey.value++
})

onMounted(() => act())
</script>

<template>
  <h1>Phiếu mượn</h1>
  <RecordForm :key="formKey" :view="col" :model-value="empty" mode="create" @submit="create" />
  <ProblemMessage :error="error" />
  <p v-if="rows.length === 0">Chưa có phiếu mượn nào.</p>
  <table v-else class="dx-table">
    <thead>
      <tr>
        <th v-for="[name, f] in columns" :key="name" scope="col">{{ f.label ?? name }}</th>
        <th scope="col">Trạng thái</th>
        <th scope="col">Cập nhật (giờ VN)</th>
        <th scope="col">Thao tác</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in rows" :key="r.id">
        <td v-for="[name, f] in columns" :key="name">{{ cell(f.type, r.data[name]) }}</td>
        <td><span class="dx-status">{{ status(r) }}</span></td>
        <td>{{ formatVn(r.updated_at) }}</td>
        <td>
          <button v-if="!r.wf_state && r.seal_state === 'NONE'" type="button" @click="act(() => client.start(APP, COL, r.id))">Gửi duyệt</button>
          <SealPanel v-if="r.seal_state !== 'NONE'" :app="APP" :col="COL" :record="r" @changed="act()" />
        </td>
      </tr>
    </tbody>
  </table>
</template>
