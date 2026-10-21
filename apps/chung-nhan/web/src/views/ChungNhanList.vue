<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Danh sách chứng nhận. Cột lấy nhãn từ manifest; không có cột email (dữ liệu cá nhân chỉ ở màn chi tiết).
import { formatVn, type DxRecord } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { APP, COL, useSession } from '../session'
import { dateVn, show, statusLabel } from '../status'

const { client, view } = useSession()

const rows = ref<DxRecord[]>([])
const loading = ref(true)
const error = ref<unknown>(null)

const fields = computed(() => view.value?.collections[COL]?.fields ?? {})
const label = (name: string): string => fields.value[name]?.label ?? name

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
    <h1>Chứng nhận</h1>
    <button type="button" class="dx-secondary" :disabled="loading" @click="load()">Tải lại</button>
  </div>

  <ProblemMessage :error="error" />
  <p v-if="loading" role="status">Đang tải…</p>
  <p v-else-if="!error && rows.length === 0">Chưa có chứng nhận nào.</p>
  <table v-else-if="rows.length > 0" class="dx-table">
    <thead>
      <tr>
        <th scope="col">{{ label('so_chung_nhan') }}</th>
        <th scope="col">{{ label('ho_ten') }}</th>
        <th scope="col">{{ label('su_kien') }}</th>
        <th scope="col">{{ label('ngay_cap') }}</th>
        <th scope="col">Trạng thái</th>
        <th scope="col">Cập nhật (giờ VN)</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in rows" :key="r.id">
        <td>{{ show(r.data.so_chung_nhan) }}</td>
        <td><RouterLink :to="`/chung-nhan/${encodeURIComponent(r.id)}`">{{ show(r.data.ho_ten) }}</RouterLink></td>
        <td>{{ show(r.data.su_kien) }}</td>
        <td>{{ dateVn(r.data.ngay_cap) }}</td>
        <td><span class="dx-status">{{ statusLabel(r) }}</span></td>
        <td>{{ formatVn(r.updated_at) }}</td>
      </tr>
    </tbody>
  </table>
</template>
