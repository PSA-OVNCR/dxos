<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Tạo văn bản. Form sinh từ manifest; "Tên loại văn bản" bắt nhập ở giao diện (spec 25.4) dù manifest để tùy chọn.
import { ProblemMessage, RecordForm } from 'dxos-sdk-js/vue'
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { APP, COL, useSession } from '../session'

const { client, view } = useSession()
const router = useRouter()

const collection = computed(() => view.value?.collections[COL])
const data = ref<Record<string, unknown>>({})
const error = ref<unknown>(null)
const busy = ref(false)

async function submit(payload: Record<string, unknown>): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = null
  try {
    // Một lần duy nhất: ghi không bao giờ tự thử lại (nếu lỗi mạng, người dùng tự quyết định gửi lại).
    const created = await client.create(APP, COL, payload)
    await router.push(`/van-ban/${encodeURIComponent(created.id)}`)
  } catch (e) {
    error.value = e
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <h1>Văn bản mới</h1>
  <RecordForm
    v-if="collection"
    v-model="data"
    :view="collection"
    mode="create"
    :required-extra="['loai_van_ban']"
    @submit="submit"
  >
    <template #actions>
      <ProblemMessage :error="error" />
      <div class="dx-actions">
        <button type="submit" :disabled="busy">Tạo văn bản</button>
        <RouterLink class="dx-button dx-secondary" to="/">Hủy</RouterLink>
      </div>
    </template>
  </RecordForm>
</template>
