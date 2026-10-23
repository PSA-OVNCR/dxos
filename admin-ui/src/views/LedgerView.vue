<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Sổ cái: trạng thái (GET ledger/status), các mục gần nhất (GET ledger/entries), "Neo ngay" (POST anchor:run).
// Giờ hiện theo Asia/Ho_Chi_Minh. Admin không có thao tác nào sửa hay xóa ledger. Mọi lỗi hiện bằng ProblemMessage.
import { formatVn } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAdminApi, type AnchorRunResult, type LedgerEntry, type LedgerStatus } from '../api'
import StateBadge from '../StateBadge.vue'
import { EVENT_TYPES, short, type StateText } from '../status'

const api = useAdminApi()
const status = ref<LedgerStatus | null>(null)
const entries = ref<LedgerEntry[] | null>(null)
const error = ref<unknown>(null)
const loading = ref(false)
const type = ref('')
const limit = ref(20)

const anchoring = ref(false)
const anchorError = ref<unknown>(null)
const anchored = ref<AnchorRunResult | null>(null)

let run = 0
let entriesRun = 0
let alive = true
onBeforeUnmount(() => { alive = false })

async function loadStatus(mine: number): Promise<void> {
  try {
    const s = await api.ledgerStatus()
    if (mine === run && alive) status.value = s
  } catch (e) {
    if (mine !== run || !alive) throw e
    status.value = null
    throw e
  }
}

async function loadEntries(): Promise<void> {
  const mine = ++entriesRun
  try {
    const r = await api.ledgerEntries({ type: type.value || undefined, limit: limit.value })
    if (mine === entriesRun && alive) entries.value = r.items
  } catch (e) {
    if (mine !== entriesRun || !alive) return
    entries.value = null
    error.value = e
  }
}

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  error.value = null
  const results = await Promise.allSettled([loadStatus(mine), loadEntries()])
  if (mine !== run || !alive) return
  const failed = results.find((r): r is PromiseRejectedResult => r.status === 'rejected')
  // Hai lời gọi cùng bị từ chối (ví dụ thiếu quyền) chỉ hiện một thông báo.
  if (failed) error.value = failed.reason
  loading.value = false
}

onMounted(() => { void load() })
watch([type, limit], () => { error.value = null; void loadEntries() })

async function anchorNow(): Promise<void> {
  if (anchoring.value) return
  anchoring.value = true
  anchorError.value = null
  anchored.value = null
  try {
    anchored.value = await api.anchorRun() // ghi: đúng một lần mỗi lần bấm, không tự thử lại
    const mine = ++run
    await Promise.allSettled([loadStatus(mine), loadEntries()])
  } catch (e) {
    anchorError.value = e
  } finally {
    anchoring.value = false
  }
}

const queued = computed(() => status.value?.pending_anchor_jobs ?? 0)
const verifyState = computed<StateText | null>(() => {
  const v = status.value?.verify
  if (!v) return null
  return v.ok
    ? { level: 'ok', text: 'Sổ cái toàn vẹn (đã kiểm lại cả chuỗi băm)' }
    : { level: 'bad', text: `Phát hiện lệch tại mục #${v.first_bad_idx ?? '?'}` }
})
</script>

<template>
  <section>
    <div class="dx-toolbar">
      <h1>Sổ cái</h1>
      <p class="dx-meta">
        Giờ hiển thị: Việt Nam (UTC+7)
        <button type="button" class="dx-secondary" :disabled="loading" @click="load">Tải lại</button>
      </p>
    </div>

    <ProblemMessage :error="error" />
    <p v-if="loading && !status && !error" role="status">Đang tải…</p>

    <template v-if="status">
      <dl class="dx-fields">
        <dt>Số mục trong sổ cái</dt>
        <dd data-field="tree_size">{{ status.tree_size }} mục</dd>

        <dt>Chữ ký cây gần nhất (STH)</dt>
        <dd data-field="sth_time">
          <template v-if="status.latest_sth">
            {{ formatVn(status.latest_sth.ts) }}
            <span class="dx-meta">
              · {{ status.latest_sth.tree_size }} mục · khóa phiên bản {{ status.latest_sth.key_version }}
              · gốc <code :title="status.latest_sth.root_hash">{{ short(status.latest_sth.root_hash) }}</code>
            </span>
          </template>
          <template v-else>Chưa có STH nào</template>
        </dd>

        <dt>Lần neo gần nhất</dt>
        <dd data-field="anchor">
          <template v-if="status.last_anchor">
            commit <code :title="status.last_anchor.commit_sha">{{ short(status.last_anchor.commit_sha) }}</code>
            vào <span>{{ status.last_anchor.repo }}</span>
            <span class="dx-meta">
              · {{ status.last_anchor.tree_size }} mục · {{ formatVn(status.last_anchor.anchored_at) }}
            </span>
          </template>
          <template v-else>Chưa có lần neo nào</template>
        </dd>

        <dt>Việc neo đang chờ</dt>
        <dd data-field="pending">{{ queued }} việc</dd>

        <dt>Kiểm tra toàn vẹn</dt>
        <dd data-field="verify"><StateBadge v-if="verifyState" :state="verifyState" /></dd>
      </dl>

      <div class="dx-actions">
        <button type="button" :disabled="anchoring || queued > 0" :aria-busy="anchoring" @click="anchorNow">Neo ngay</button>
        <span v-if="queued > 0" class="dx-meta">Đang có việc neo chờ xử lý; đợi xong rồi neo tiếp.</span>
      </div>
      <p v-if="anchored" role="status" class="dx-notice">
        Đã ký STH cho {{ anchored.tree_size }} mục và xếp việc neo (mã {{ anchored.anchor_job_id }}). Việc đẩy lên kho neo chạy nền.
      </p>
      <ProblemMessage :error="anchorError" />
    </template>

    <template v-if="entries">
      <h2>Các mục gần nhất</h2>
      <p class="dx-filter">
        <label>Loại sự kiện
          <select v-model="type" name="type">
            <option value="">Tất cả</option>
            <option v-for="t in EVENT_TYPES" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label>Số mục
          <select v-model.number="limit" name="limit">
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </label>
      </p>
      <div class="dx-scroll">
        <table class="dx-table">
          <thead>
            <tr><th>#</th><th>Thời gian</th><th>Loại</th><th>Ứng dụng</th><th>Đối tượng</th><th>Người thực hiện (mã ẩn)</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in entries" :key="e.idx">
              <td>{{ e.idx }}</td>
              <td>{{ formatVn(e.ts) }}</td>
              <td><code>{{ e.type }}</code></td>
              <td>{{ e.app_id ?? '—' }}</td>
              <td class="dx-wrap">{{ e.subject ?? '—' }}</td>
              <td><code v-if="e.actor_ref" :title="e.actor_ref">{{ short(e.actor_ref) }}</code><template v-else>—</template></td>
            </tr>
            <tr v-if="entries.length === 0"><td colspan="6" class="dx-meta">Không có mục nào.</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
