<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Trang in chứng nhận, dựng tại client chỉ từ `public_fields` của niêm phong: không đọc bản ghi nên không thể lộ email,
// và chỉ hiện các trường manifest đã khai là công khai. Có mã QR đối soát và tuyên bố phạm vi (spec 14). A4 ngang khi in.
import { formatVn, type SealInfo } from 'dxos-sdk-js'
import { ProblemMessage, SealQr } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { SCOPE_STATEMENT } from '../scope'
import { APP, COL, useSession } from '../session'
import { dateVn, show } from '../status'

const props = defineProps<{ id: string }>()
const { client, view } = useSession()

const seal = ref<SealInfo | null>(null)
const error = ref<unknown>(null)
const loading = ref(true)

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

const rows = computed(() => {
  const fields = view.value?.collections[COL]?.fields ?? {}
  const pub = seal.value?.public_fields ?? {}
  return (view.value?.policies.seal?.public_fields ?? [])
    .filter((name) => Object.hasOwn(pub, name))
    .map((name) => ({
      name,
      label: fields[name]?.label ?? name,
      text: fields[name]?.type === 'date' ? dateVn(pub[name]) : show(pub[name]),
    }))
})

function print(): void {
  window.print()
}

watch(() => props.id, async (id) => {
  const mine = ++run
  loading.value = true
  error.value = null
  seal.value = null
  try {
    const s = await client.seal(APP, COL, id)
    if (mine === run && alive) seal.value = s
  } catch (e) {
    if (mine === run && alive) error.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}, { immediate: true })
</script>

<template>
  <div class="dx-actions dx-no-print">
    <RouterLink class="dx-button dx-secondary" :to="`/chung-nhan/${encodeURIComponent(id)}`">Quay lại chi tiết</RouterLink>
    <button v-if="seal?.seal_state === 'SEALED'" type="button" class="dx-no-print" @click="print">In chứng nhận</button>
  </div>

  <p v-if="loading" role="status">Đang tải…</p>
  <ProblemMessage :error="error" />

  <article v-if="seal?.seal_state === 'SEALED'" class="dx-cert">
    <h1>Chứng nhận tham gia sự kiện</h1>
    <dl class="dx-cert-fields">
      <template v-for="r in rows" :key="r.name">
        <dt>{{ r.label }}</dt>
        <dd>{{ r.text }}</dd>
      </template>
    </dl>
    <div class="dx-cert-seal">
      <SealQr :verify-url="seal.verify_url" :size="160" />
      <div>
        <p>Mã niêm phong: {{ seal.seal_id }}</p>
        <p v-if="seal.issued_at">Thời điểm niêm phong (giờ VN): {{ formatVn(seal.issued_at) }}</p>
        <p>Đối soát tại: <span class="dx-cert-url">{{ seal.verify_url }}</span></p>
      </div>
    </div>
    <p class="dx-scope">{{ SCOPE_STATEMENT }}</p>
  </article>
  <p v-else-if="seal?.seal_state === 'REVOKED'" class="dx-problem" role="status">
    Chứng nhận này đã bị thu hồi nên không được in. Trang đối soát công khai báo trạng thái thu hồi.
  </p>
  <p v-else-if="seal" class="dx-meta" role="status">Chứng nhận đang chờ niêm phong; hãy quay lại sau ít phút để in.</p>
</template>
