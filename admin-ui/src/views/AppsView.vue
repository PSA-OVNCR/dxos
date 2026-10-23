<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Duyệt app: danh sách phiên bản (GET /admin/v1/apps), liên kết sang màn hình diff để duyệt, và "Vô hiệu hóa"
// (POST apps/{id}:disable) chỉ sau khi gõ đúng mã app. Mặc định chỉ hiện bản đang hoạt động và chờ duyệt.
// Người nộp/duyệt chỉ là mã ẩn (HMAC). Mọi lỗi hiện bằng ProblemMessage.
import { formatVn } from 'dxos-sdk-js'
import { ConfirmDialog, ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAdminApi, type AppVersionRow } from '../api'
import StateBadge from '../StateBadge.vue'
import { appStatusState, short } from '../status'

const api = useAdminApi()
const rows = ref<AppVersionRow[] | null>(null)
const error = ref<unknown>(null)
const loading = ref(false)
const show = ref<'open' | 'all'>('open')

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  error.value = null
  try {
    const r = await api.apps()
    if (mine === run && alive) rows.value = r
  } catch (e) {
    if (mine !== run || !alive) return
    rows.value = null
    error.value = e
  } finally {
    if (mine === run) loading.value = false
  }
}
onMounted(() => { void load() })

const visible = computed(() => (rows.value ?? []).filter((r) => show.value === 'all' || r.status !== 'DISABLED'))

// ---- vô hiệu hóa -------------------------------------------------------------------------------
const target = ref<string | null>(null)
const typed = ref('')
const disabling = ref(false)
const disableError = ref<unknown>(null)
const disabled = ref<string | null>(null)

function askDisable(appId: string): void {
  target.value = appId
  typed.value = ''
  disableError.value = null
  disabled.value = null
}

function cancelDisable(): void {
  target.value = null
  typed.value = ''
}

async function doDisable(): Promise<void> {
  const id = target.value
  if (id === null || disabling.value || typed.value.trim() !== id) return
  disabling.value = true
  disableError.value = null
  try {
    const r = await api.disableApp(id) // ghi: đúng một lần mỗi lần bấm, không tự thử lại
    disabled.value = `${r.app_id} ${r.version}`
    target.value = null
    typed.value = ''
    await load()
  } catch (e) {
    disableError.value = e
    target.value = null
    typed.value = ''
  } finally {
    disabling.value = false
  }
}
</script>

<template>
  <section>
    <div class="dx-toolbar">
      <h1>Ứng dụng</h1>
      <p class="dx-meta">
        Giờ hiển thị: Việt Nam (UTC+7)
        <button type="button" class="dx-secondary" :disabled="loading" @click="load">Tải lại</button>
      </p>
    </div>

    <ProblemMessage :error="error" />
    <p v-if="loading && !rows && !error" role="status">Đang tải…</p>

    <p v-if="disabled" role="status" class="dx-notice">
      Đã vô hiệu hóa {{ disabled }}. Dữ liệu, sổ cái và vai trò được giữ nguyên.
    </p>
    <ProblemMessage :error="disableError" />

    <ConfirmDialog
      v-if="target !== null"
      :title="`Vô hiệu hóa ${target}`"
      confirm-label="Vô hiệu hóa ứng dụng"
      :can-confirm="typed.trim() === target"
      :busy="disabling"
      @confirm="doDisable"
      @cancel="cancelDisable"
    >
      <p>
        Ứng dụng sẽ ngừng nhận thao tác mới. Dữ liệu và sổ cái không bị xóa. Gõ chính xác mã ứng dụng
        <code>{{ target }}</code> để xác nhận.
      </p>
      <label class="dx-field">Mã ứng dụng
        <input v-model="typed" name="confirm-app-id" type="text" autocomplete="off" spellcheck="false" />
      </label>
    </ConfirmDialog>

    <template v-if="rows">
      <p class="dx-filter">
        <label>Hiển thị
          <select v-model="show" name="status">
            <option value="open">Đang hoạt động và chờ duyệt</option>
            <option value="all">Tất cả (cả bản đã vô hiệu hóa)</option>
          </select>
        </label>
      </p>
      <div class="dx-scroll">
        <table class="dx-table">
          <thead>
            <tr>
              <th>Ứng dụng</th><th>Phiên bản</th><th>Trạng thái</th><th>Nộp lúc</th>
              <th>Người nộp (mã ẩn)</th><th>Người duyệt (mã ẩn)</th><th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in visible" :key="`${r.app_id}@${r.version}`" :data-app="r.app_id" :data-version="r.version">
              <td>{{ r.app_id }}</td>
              <td>{{ r.version }}</td>
              <td><StateBadge :state="appStatusState(r.status)" /></td>
              <td>{{ formatVn(r.created_at) }}</td>
              <td><code v-if="r.submitted_by_ref" :title="r.submitted_by_ref">{{ short(r.submitted_by_ref) }}</code><template v-else>—</template></td>
              <td><code v-if="r.approved_by_ref" :title="r.approved_by_ref">{{ short(r.approved_by_ref) }}</code><template v-else>—</template></td>
              <td class="dx-actions-cell">
                <a :href="`#/apps/${encodeURIComponent(r.app_id)}/versions/${encodeURIComponent(r.version)}`">
                  {{ r.status === 'PENDING' ? 'Xem diff và duyệt' : 'Xem diff' }}
                </a>
                <button v-if="r.status === 'ACTIVE'" type="button" class="dx-secondary" :disabled="disabling" @click="askDisable(r.app_id)">Vô hiệu hóa</button>
              </td>
            </tr>
            <tr v-if="rows.length === 0"><td colspan="7" class="dx-meta">Chưa có ứng dụng nào được nộp.</td></tr>
            <tr v-else-if="visible.length === 0"><td colspan="7" class="dx-meta">Không có phiên bản nào đang hoạt động hoặc chờ duyệt.</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
