<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Dữ liệu cá nhân phát hiện trong một tệp đính kèm và các nút tải (bản che, bản gốc). Không tự gọi API: chỉ phát
// `download` với bản cần tải, ứng dụng tải và hiện lỗi (ProblemMessage). Quyền do máy chủ quyết định (không có quyền
// xem PII thì bản gốc của tệp còn khóa trả 404); `canReveal=false` (người dùng không thuộc `reveal_roles`) chỉ để không
// bày một nút chắc chắn hỏng: bản gốc của tệp còn khóa bị ẩn, tệp không phát hiện gì vẫn tải được.
import { computed } from 'vue'
import type { AttachmentItem, ObjectVariant } from '../types'
import { originalLocked, piiLabel } from './piiText'

const props = withDefaults(
  defineProps<{ item: AttachmentItem; busy?: boolean; timedOut?: boolean; canReveal?: boolean }>(),
  { canReveal: true },
)
const emit = defineEmits<{ download: [variant: ObjectVariant] }>()

const pii = computed(() => props.item.pii ?? null)
const pending = computed(() => pii.value?.status === 'PENDING')
const label = computed(() => {
  const p = pii.value
  if (!p) return ''
  if (pending.value && props.timedOut) return 'Việc dò dữ liệu cá nhân lâu bất thường — hãy tải lại trang sau ít phút'
  return piiLabel(p)
})
const note = computed(() => {
  const p = pii.value
  if (!p || p.status !== 'DONE' || p.findings <= 0) return ''
  if (p.redacted) {
    return 'Bản gốc chỉ mở được với người có quyền xem dữ liệu cá nhân. Bản che là PDF dạng ảnh, ô đen thay cho số đã phát hiện; '
      + 'nó không thay cho việc rà của người có thẩm quyền.'
  }
  return 'Chưa có bản che (có thể đang được dựng, hãy tải lại sau ít phút; tệp quá lớn thì không có bản che): '
    + 'chỉ người có quyền xem dữ liệu cá nhân mới mở được tệp gốc.'
})
const showOriginal = computed(() => props.canReveal || !originalLocked(pii.value))
const canDownload = computed(() =>
  !!props.item.sha256 && !!pii.value && !pending.value && (showOriginal.value || !!pii.value.redacted))
</script>

<template>
  <div v-if="pii" class="dx-pii-file">
    <p role="status" :data-pii-status="pending && timedOut ? 'TIMEOUT' : pii.status">{{ label }}</p>
    <p v-if="note" class="dx-meta">{{ note }}</p>
    <div v-if="canDownload" class="dx-actions">
      <button v-if="pii.redacted" type="button" :disabled="busy" @click="emit('download', 'redacted')">Tải bản che</button>
      <button v-if="showOriginal" type="button" class="dx-secondary" :disabled="busy" @click="emit('download', 'original')">Tải bản gốc</button>
    </div>
  </div>
</template>
