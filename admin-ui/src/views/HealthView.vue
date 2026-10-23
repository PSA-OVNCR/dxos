<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Sức khỏe hệ thống (GET /admin/v1/health, luôn HTTP 200). Mỗi thành phần có chữ trạng thái; mọi lỗi hiện bằng ProblemMessage.
import { formatVn } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAdminApi, type HealthReport } from '../api'
import StateBadge from '../StateBadge.vue'
import { ageText, probeState, sealKeyState, type StateText } from '../status'

const api = useAdminApi()
const report = ref<HealthReport | null>(null)
const error = ref<unknown>(null)
const loading = ref(false)
const loadedAt = ref('')

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  error.value = null
  try {
    const r = await api.health()
    if (mine !== run || !alive) return
    report.value = r
    loadedAt.value = formatVn(new Date().toISOString())
  } catch (e) {
    if (mine !== run || !alive) return
    report.value = null
    error.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}

onMounted(() => { void load() })

interface Dep { key: string; label: string; state: StateText }

const deps = computed<Dep[]>(() => {
  const r = report.value
  if (!r) return []
  return [
    { key: 'db', label: 'Cơ sở dữ liệu (PostgreSQL)', state: probeState(r.db) },
    { key: 'clamav', label: 'Kiểm dịch tệp (ClamAV)', state: probeState(r.clamav) },
    { key: 'openbao', label: 'Dịch vụ ký (OpenBao)', state: probeState(r.openbao) },
    { key: 'flowable', label: 'Quy trình (Flowable)', state: probeState(r.flowable) },
    { key: 'keycloak', label: 'Vai trò mặc định (Keycloak)', state: probeState(r.keycloak_default_roles, 'Đúng cấu hình') },
    { key: 'seal_key', label: 'Khóa niêm phong', state: sealKeyState(r.seal_key) },
    { key: 'org', label: 'Tên tổ chức niêm phong', state: probeState(r.org, 'Đã cấu hình') },
  ]
})

function countState(n: number | null, warnText: string): StateText {
  if (n === null) return { level: 'warn', text: 'Không đọc được' }
  return n > 0 ? { level: 'warn', text: warnText } : { level: 'ok', text: 'Không có' }
}

const counters = computed(() => {
  const r = report.value
  if (!r) return null
  const a = r.anchor
  const anchorState: StateText = a.last_tree_size === null || a.last_anchor_age_s === null
    ? { level: 'warn', text: 'Chưa neo lần nào' }
    : { level: 'ok', text: `Lần gần nhất: ${a.last_tree_size} mục, cách đây ${ageText(a.last_anchor_age_s)}` }
  return {
    sealPending: { value: r.seal_pending, state: countState(r.seal_pending, 'Đang chờ niêm phong') },
    stuck: { value: r.task_intents_stuck, state: countState(r.task_intents_stuck, 'Cần chạy đối soát quy trình') },
    anchor: anchorState,
  }
})
</script>

<template>
  <section>
    <div class="dx-toolbar">
      <h1>Sức khỏe hệ thống</h1>
      <p class="dx-meta">
        <span v-if="loadedAt">Cập nhật lúc {{ loadedAt }} (giờ Việt Nam) </span>
        <button type="button" class="dx-secondary" :disabled="loading" @click="load">Tải lại</button>
      </p>
    </div>

    <ProblemMessage :error="error" />
    <p v-if="loading && !report && !error" role="status">Đang tải…</p>

    <template v-if="report && counters">
      <table class="dx-table">
        <caption class="dx-meta">Trạng thái từng thành phần</caption>
        <thead><tr><th>Thành phần</th><th>Trạng thái</th></tr></thead>
        <tbody>
          <tr v-for="d in deps" :key="d.key" :data-dep="d.key">
            <th scope="row">{{ d.label }}</th>
            <td><StateBadge :state="d.state" /></td>
          </tr>
        </tbody>
      </table>

      <table class="dx-table">
        <caption class="dx-meta">Hàng đợi và lần neo</caption>
        <thead><tr><th>Mục</th><th>Giá trị</th></tr></thead>
        <tbody>
          <tr data-counter="seal_pending">
            <th scope="row">Hồ sơ chờ niêm phong</th>
            <td>{{ counters.sealPending.value ?? '?' }} <StateBadge :state="counters.sealPending.state" /></td>
          </tr>
          <tr data-counter="task_intents_stuck">
            <th scope="row">Bước quy trình kẹt (chưa có kết quả quá 2 phút)</th>
            <td>{{ counters.stuck.value ?? '?' }} <StateBadge :state="counters.stuck.state" /></td>
          </tr>
          <tr data-counter="anchor">
            <th scope="row">Neo gần nhất</th>
            <td><StateBadge :state="counters.anchor" /></td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>
