<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Chi tiết chứng nhận: trường theo nhãn manifest, gửi duyệt, niêm phong (QR, đối soát, thu hồi) và dữ liệu cá nhân (xóa email).
// Ẩn/hiện nút theo chủ sở hữu, trạng thái và vai trò chỉ là tiện dụng; lõi quyết định và mọi lỗi của lõi hiện bằng ProblemMessage.
// Không có yêu cầu ghi nào được tự thử lại; lỗi 409/412 thì báo và gợi ý tải lại.
import { ApiError, formatVn, type DxRecord } from 'dxos-sdk-js'
import { PiiPanel, ProblemMessage, SealPanel } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { APP, COL, useSession } from '../session'
import { dateVn, show, statusLabel } from '../status'

const props = defineProps<{ id: string }>()
const { client, view } = useSession()

const collection = computed(() => view.value?.collections[COL])
const record = ref<DxRecord | null>(null)
const loading = ref(true)
const loadError = ref<unknown>(null)
const actionError = ref<unknown>(null)
const busy = ref(false)

// Mỗi lần tải lại tăng số này; phản hồi của lần cũ (đổi bản ghi giữa chừng) bị bỏ.
let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

/** Chủ bản ghi, chưa vào quy trình, chưa niêm phong: điều kiện để hiện nút gửi duyệt (tiện dụng, lõi vẫn kiểm lại). */
const canSubmit = computed(() => {
  const r = record.value
  return !!r && r.is_owner && r.wf_state !== 'running' && r.seal_state === 'NONE'
})
const title = computed(() => {
  const n = show(record.value?.data.so_chung_nhan)
  return n === '—' ? 'Chứng nhận' : n
})
const reloadHint = computed(() => {
  const e = actionError.value
  return e instanceof ApiError && (e.status === 409 || e.status === 412)
})

function value(name: string, type: string): string {
  const v = record.value?.data[name]
  return type === 'date' ? dateVn(v) : show(v)
}

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  loadError.value = null
  actionError.value = null
  try {
    const r = await client.get(APP, COL, props.id)
    if (mine !== run || !alive) return
    record.value = r
  } catch (e) {
    if (mine !== run || !alive) return
    record.value = null
    loadError.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}

/** Sau thao tác của SealPanel/PiiPanel: đọc lại bản ghi mà không dựng lại cả màn hình (giữ thông báo của hai khối). */
async function refresh(): Promise<void> {
  const mine = ++run
  try {
    const r = await client.get(APP, COL, props.id)
    if (mine === run && alive) record.value = r
  } catch (e) {
    if (mine === run && alive) actionError.value = e
  }
}

watch(() => props.id, () => { void load() }, { immediate: true })

async function submitForApproval(): Promise<void> {
  if (busy.value) return
  busy.value = true
  actionError.value = null
  try {
    record.value = await client.start(APP, COL, props.id)
  } catch (e) {
    if (alive) actionError.value = e
  } finally {
    busy.value = false
  }
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
    <div v-if="reloadHint" class="dx-actions">
      <button type="button" class="dx-secondary" @click="load()">Tải lại</button>
    </div>

    <dl class="dx-fields">
      <template v-for="(f, name) in collection.fields" :key="name">
        <dt>{{ f.label ?? name }}</dt>
        <dd>{{ value(name, f.type) }}</dd>
      </template>
      <dt>Cập nhật (giờ VN)</dt>
      <dd>{{ formatVn(record.updated_at) }}</dd>
    </dl>

    <div v-if="canSubmit || record.seal_state === 'SEALED'" class="dx-actions">
      <button v-if="canSubmit" type="button" :disabled="busy" @click="submitForApproval">Gửi duyệt</button>
      <RouterLink v-if="record.seal_state === 'SEALED'" class="dx-button dx-secondary" :to="`/chung-nhan/${encodeURIComponent(record.id)}/in`">
        Trang in chứng nhận
      </RouterLink>
    </div>

    <SealPanel :app="APP" :col="COL" :record="record" @changed="refresh()" />
    <PiiPanel :app="APP" :col="COL" :record="record" :collection="collection" @changed="refresh()" />
  </template>
</template>
