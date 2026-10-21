<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Dữ liệu cá nhân của một văn bản: xác nhận đã rà (giám đốc, văn thư, khi đang duyệt) và xóa trường pii (văn thư).
// Vai trò và trạng thái chỉ quyết định nút hiện hay ẩn; lõi kiểm lại. Ghi một lần, không tự thử lại.
import { ApiError, type CollectionView, type DxRecord } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, ref, useId } from 'vue'
import { APP, COL, useSession } from '../session'
import { ERASE_REASONS } from '../reasons'
import { hasRole } from '../status'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps<{ record: DxRecord; collection: CollectionView }>()
const emit = defineEmits<{ changed: [] }>()
const { client, roles, view } = useSession()

const actionError = ref<unknown>(null)
const notice = ref('')
const busy = ref(false)
const erasing = ref(false)
const chosen = ref<string[]>([])
const reason = ref('')
const reasonId = useId()

let alive = true
onBeforeUnmount(() => { alive = false })

const piiFields = computed(() =>
  Object.entries(props.collection.fields).filter(([, f]) => f.pii !== null).map(([name, f]) => ({ name, label: f.label ?? name })))
const canReview = computed(() =>
  props.record.wf_state === 'running' && hasRole(roles.value, view.value?.policies.pii.reveal_roles))
const canErase = computed(() =>
  piiFields.value.length > 0 && props.record.wf_state !== 'running' && props.record.seal_state !== 'SEAL_PENDING'
  && hasRole(roles.value, view.value?.policies.pii.erase_roles))
const reloadHint = computed(() => {
  const e = actionError.value
  return e instanceof ApiError && (e.status === 409 || e.status === 412)
})

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

async function review(): Promise<void> {
  if (!(await act(async () => { await client.piiReview(APP, COL, props.record.id) })) || !alive) return
  notice.value = 'Đã ghi nhận xác nhận rà dữ liệu cá nhân.'
  emit('changed')
}

function startErase(): void {
  chosen.value = []
  reason.value = ''
  actionError.value = null
  erasing.value = true
}

async function confirmErase(): Promise<void> {
  const fields = [...chosen.value]
  if (!(await act(async () => { await client.erasePii(APP, COL, props.record.id, fields, reason.value) })) || !alive) return
  erasing.value = false
  notice.value = 'Đã xóa dữ liệu cá nhân đã chọn.'
  emit('changed')
}
</script>

<template>
  <section v-if="canReview || canErase || notice || actionError" aria-labelledby="dx-pii-h" class="dx-pii">
    <h2 id="dx-pii-h">Dữ liệu cá nhân</h2>
    <ProblemMessage :error="actionError" />
    <div v-if="reloadHint" class="dx-actions"><button type="button" class="dx-secondary" @click="emit('changed')">Tải lại</button></div>
    <p v-if="notice" role="status">{{ notice }}</p>
    <div class="dx-actions">
      <button v-if="canReview" type="button" :disabled="busy" @click="review">Xác nhận đã rà dữ liệu cá nhân</button>
      <button v-if="canErase && !erasing" type="button" class="dx-secondary" :disabled="busy" @click="startErase">Xóa dữ liệu cá nhân</button>
    </div>

    <ConfirmDialog
      v-if="erasing"
      title="Xóa dữ liệu cá nhân?"
      confirm-label="Xác nhận xóa"
      :can-confirm="chosen.length > 0 && reason !== ''"
      :busy="busy"
      @confirm="confirmErase"
      @cancel="erasing = false"
    >
      <p>
        Các trường được chọn bị xóa khỏi hồ sơ, kể cả hồ sơ đã niêm phong; không thể hoàn tác. Tệp PDF và các trường đã công bố
        trong niêm phong không bị xóa.
      </p>
      <fieldset class="dx-field">
        <legend>Trường cần xóa</legend>
        <label v-for="f in piiFields" :key="f.name" class="dx-check">
          <input v-model="chosen" type="checkbox" name="fields" :value="f.name"> {{ f.label }}
        </label>
      </fieldset>
      <div class="dx-field">
        <label :for="reasonId">Lý do xóa (Điều 14 khoản 1 Luật 91/2025)</label>
        <select :id="reasonId" v-model="reason" name="reason_code" required>
          <option v-for="r in ERASE_REASONS" :key="r.code" :value="r.code">{{ r.label }}</option>
        </select>
      </div>
    </ConfirmDialog>
  </section>
</template>
