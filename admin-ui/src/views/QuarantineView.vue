<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Cách ly: các upload bị ClamAV đánh dấu nhiễm (INFECTED) hoặc bị từ chối (REJECTED), mới nhất trước
// (GET /admin/v1/quarantine). Chỉ xem: không có tên tệp (lõi chỉ lưu mã băm nội dung) và không thao tác ghi nào.
import { formatVn } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAdminApi, type QuarantineItem } from '../api'
import StateBadge from '../StateBadge.vue'
import { short, uploadStatusState } from '../status'

const api = useAdminApi()
const items = ref<QuarantineItem[] | null>(null)
const error = ref<unknown>(null)
const loading = ref(false)
const limit = ref(100)

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  error.value = null
  try {
    const r = await api.quarantine(limit.value)
    if (mine === run && alive) items.value = r
  } catch (e) {
    if (mine !== run || !alive) return
    items.value = null
    error.value = e
  } finally {
    if (mine === run) loading.value = false
  }
}
onMounted(() => { void load() })
watch(limit, () => { void load() })

// Máy chủ đã sắp mới nhất trước; sắp lại ở đây để màn hình đúng dù thứ tự trả về đổi. Thời điểm là chuỗi ISO
// cùng múi giờ UTC nên so theo thời điểm thật (Date), không theo chuỗi.
const newestFirst = computed(() =>
  [...(items.value ?? [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)))
</script>

<template>
  <section data-quarantine>
    <div class="dx-toolbar">
      <h1>Cách ly</h1>
      <p class="dx-meta">
        Giờ hiển thị: Việt Nam (UTC+7)
        <button type="button" class="dx-secondary" :disabled="loading" @click="load">Tải lại</button>
      </p>
    </div>
    <p class="dx-meta">
      Các tệp tải lên bị phát hiện mã độc hoặc bị từ chối, mới nhất trước. Tệp không bao giờ được đọc ra từ đây;
      lõi chỉ lưu mã băm nội dung nên không có tên tệp.
    </p>

    <ProblemMessage :error="error" />
    <p v-if="loading && !items && !error" role="status">Đang tải…</p>

    <template v-if="items">
      <p class="dx-filter">
        <label>Số mục tối đa
          <select v-model.number="limit" name="limit">
            <option :value="100">100</option>
            <option :value="500">500</option>
            <option :value="1000">1000</option>
          </select>
        </label>
      </p>
      <div class="dx-scroll">
        <table class="dx-table">
          <thead>
            <tr><th>Thời gian</th><th>Trạng thái</th><th>Lý do</th><th>Ứng dụng</th><th>Mã băm nội dung</th><th>Mã tải lên</th></tr>
          </thead>
          <tbody>
            <tr v-for="u in newestFirst" :key="u.upload_id" :data-upload="u.upload_id">
              <td>{{ formatVn(u.created_at) }}</td>
              <td><StateBadge :state="uploadStatusState(u.status)" /></td>
              <td class="dx-wrap">{{ u.reason ?? '—' }}</td>
              <td>{{ u.app_id }}</td>
              <td><code :title="u.sha256">{{ short(u.sha256) }}</code></td>
              <td class="dx-wrap"><code>{{ u.upload_id }}</code></td>
            </tr>
            <tr v-if="items.length === 0"><td colspan="6" class="dx-meta">Không có tệp nào bị cách ly.</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
