<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Niêm phong của một bản ghi: trạng thái, mã QR và liên kết đối soát, thu hồi (vai trò trong policies.seal.revoke_roles).
// Nút riêng của ứng dụng (ví dụ tải bản PDF đã ban hành) đi vào slot "actions", dùng `run` để có chung trạng thái bận và lỗi.
// Ẩn/hiện nút theo vai trò và trạng thái chỉ là tiện dụng; lõi quyết định. Ghi một lần, không tự thử lại.
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { ApiError } from '../errors'
import { formatVn, hasRole, sealLabel } from '../format'
import type { DxRecord, SealInfo } from '../types'
import ConfirmDialog from './ConfirmDialog.vue'
import ProblemMessage from './ProblemMessage.vue'
import { REVOKE_REASONS } from './reasons'
import SealQr from './SealQr.vue'
import { useSession } from './session'
import VerifyLink from './VerifyLink.vue'

const props = defineProps<{ app: string; col: string; record: DxRecord }>()
const emit = defineEmits<{ changed: [] }>()
const { client, roles, view } = useSession()

const seal = ref<SealInfo | null>(null)
const sealError = ref<unknown>(null)
const actionError = ref<unknown>(null)
const notice = ref('')
const busy = ref(false)
const revoking = ref(false)
const reason = ref('')
const note = ref('')
const reasonId = useId()
const noteId = useId()

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

const hasSeal = computed(() => props.record.seal_state !== 'NONE')
const canRevoke = computed(() =>
  props.record.seal_state === 'SEALED' && hasRole(roles.value, view.value?.policies.seal?.revoke_roles))
const reloadHint = computed(() => {
  const e = actionError.value
  return e instanceof ApiError && (e.status === 409 || e.status === 412)
})

async function loadSeal(): Promise<void> {
  const mine = ++run
  sealError.value = null
  if (!hasSeal.value) {
    seal.value = null
    return
  }
  try {
    const s = await client.seal(props.app, props.col, props.record.id)
    if (mine === run && alive) seal.value = s
  } catch (e) {
    if (mine === run && alive) {
      seal.value = null
      sealError.value = e
    }
  }
}

watch(() => [props.record.id, props.record.seal_state, props.record.version] as const, () => { void loadSeal() }, { immediate: true })

async function act(fn: () => Promise<void>): Promise<boolean> {
  if (busy.value) return false
  busy.value = true
  actionError.value = null
  notice.value = ''
  try {
    await fn()
    return true
  } catch (e) {
    if (alive) actionError.value = e
    return false
  } finally {
    busy.value = false
  }
}

function startRevoke(): void {
  reason.value = ''
  note.value = ''
  actionError.value = null
  revoking.value = true
}

async function confirmRevoke(): Promise<void> {
  const n = note.value.trim()
  const ok = await act(async () => {
    await client.revoke(props.app, props.col, props.record.id, reason.value, n === '' ? undefined : n)
  })
  if (!ok || !alive) return
  revoking.value = false
  notice.value = 'Đã thu hồi niêm phong.'
  emit('changed')
}
</script>

<template>
  <section v-if="hasSeal" aria-labelledby="dx-seal-h" class="dx-seal">
    <h2 id="dx-seal-h">Niêm phong</h2>
    <ProblemMessage :error="sealError" />
    <div v-if="sealError" class="dx-actions"><button type="button" class="dx-secondary" @click="loadSeal()">Tải lại</button></div>
    <template v-if="seal">
      <p>Trạng thái: <span class="dx-status">{{ sealLabel(seal.seal_state) }}</span></p>
      <p v-if="seal.seal_state === 'SEAL_PENDING'" class="dx-meta">Văn bản đang được niêm phong, hãy tải lại sau ít phút.</p>
      <dl class="dx-fields">
        <dt>Mã niêm phong</dt>
        <dd>{{ seal.seal_id }}</dd>
        <template v-if="seal.issued_at">
          <dt>Thời điểm niêm phong (giờ VN)</dt>
          <dd>{{ formatVn(seal.issued_at) }}</dd>
        </template>
      </dl>
      <div class="dx-seal-verify">
        <SealQr :verify-url="seal.verify_url" />
        <p><VerifyLink :verify-url="seal.verify_url" /></p>
      </div>
      <div v-if="seal.seal_state === 'SEAL_PENDING'" class="dx-actions">
        <button type="button" class="dx-secondary" @click="emit('changed')">Tải lại</button>
      </div>
    </template>

    <ProblemMessage :error="actionError" />
    <div v-if="reloadHint" class="dx-actions"><button type="button" class="dx-secondary" @click="emit('changed')">Tải lại</button></div>
    <p v-if="notice" role="status">{{ notice }}</p>

    <div class="dx-actions">
      <slot name="actions" :sealed="seal?.seal_state === 'SEALED'" :busy="busy" :run="act" />
      <button v-if="canRevoke && !revoking" type="button" class="dx-secondary" :disabled="busy" @click="startRevoke">Thu hồi niêm phong</button>
    </div>

    <ConfirmDialog
      v-if="revoking"
      title="Thu hồi niêm phong?"
      confirm-label="Xác nhận thu hồi"
      :can-confirm="reason !== ''"
      :busy="busy"
      @confirm="confirmRevoke"
      @cancel="revoking = false"
    >
      <p>Thu hồi là trạng thái cuối, không thể hoàn tác. Trang đối soát công khai sẽ báo văn bản đã bị thu hồi.</p>
      <div class="dx-field">
        <label :for="reasonId">Lý do thu hồi</label>
        <select :id="reasonId" v-model="reason" name="reason_code" required>
          <option v-for="r in REVOKE_REASONS" :key="r.code" :value="r.code">{{ r.label }}</option>
        </select>
      </div>
      <div class="dx-field">
        <label :for="noteId">Ghi chú (không bắt buộc, tối đa 500 ký tự)</label>
        <textarea :id="noteId" v-model="note" name="note" rows="3" maxlength="500" />
      </div>
    </ConfirmDialog>
  </section>
</template>
