<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Danh sách văn bản. Cột lấy nhãn từ manifest; "Văn bản mới" chỉ hiện khi có vai trò chuyên viên (tiện dụng, lõi mới quyết định).
import type { DxRecord } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { APP, COL, useSession } from '../session'
import { formatVn, statusLabel } from '../status'

const { client, roles, view } = useSession()

const rows = ref<DxRecord[]>([])
const loading = ref(true)
const error = ref<unknown>(null)

const canCreate = computed(() => roles.value.includes('chuyen_vien'))
const fields = computed(() => view.value?.collections[COL]?.fields ?? {})
const label = (name: string): string => fields.value[name]?.label ?? name

function text(r: DxRecord, name: string): string {
  const v = r.data[name]
  return v === undefined || v === null || v === '' ? '—' : String(v)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    rows.value = await client.listAll(APP, COL)
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="dx-toolbar">
    <h1>Văn bản</h1>
    <RouterLink v-if="canCreate" class="dx-button" to="/van-ban/moi">Văn bản mới</RouterLink>
  </div>

  <ProblemMessage :error="error" />
  <p v-if="loading" role="status">Đang tải…</p>
  <p v-else-if="!error && rows.length === 0">Chưa có văn bản nào.</p>
  <table v-else-if="rows.length > 0" class="dx-table">
    <thead>
      <tr>
        <th scope="col">{{ label('so_hieu') }}</th>
        <th scope="col">{{ label('loai_van_ban') }}</th>
        <th scope="col">{{ label('trich_yeu') }}</th>
        <th scope="col">Trạng thái</th>
        <th scope="col">Cập nhật (giờ VN)</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in rows" :key="r.id">
        <td>{{ text(r, 'so_hieu') }}</td>
        <td>{{ text(r, 'loai_van_ban') }}</td>
        <td><RouterLink :to="`/van-ban/${encodeURIComponent(r.id)}`">{{ text(r, 'trich_yeu') }}</RouterLink></td>
        <td><span class="dx-status">{{ statusLabel(r) }}</span></td>
        <td>{{ formatVn(r.updated_at) }}</td>
      </tr>
    </tbody>
  </table>
</template>
