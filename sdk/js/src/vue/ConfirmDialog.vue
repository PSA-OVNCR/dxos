<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Hộp xác nhận nội tuyến cho thao tác không hoàn tác (trả lại, thu hồi, xóa). Nút xác nhận là type=button:
// chỉ lời gọi API của nơi dùng mới ghi dữ liệu. Esc hoặc "Hủy" thì đóng, không gọi gì.
import { onMounted, ref, useId } from 'vue'

withDefaults(defineProps<{ title: string; confirmLabel: string; canConfirm?: boolean; busy?: boolean }>(), {
  canConfirm: true, busy: false,
})
const emit = defineEmits<{ confirm: []; cancel: [] }>()

const titleId = useId()
const root = ref<HTMLElement | null>(null)
onMounted(() => { root.value?.querySelector<HTMLElement>('select, input, textarea, button')?.focus() })
</script>

<template>
  <div ref="root" class="dx-dialog" role="alertdialog" aria-modal="true" :aria-labelledby="titleId" @keydown.esc="emit('cancel')">
    <h3 :id="titleId">{{ title }}</h3>
    <slot />
    <div class="dx-actions">
      <button type="button" :disabled="busy || !canConfirm" @click="emit('confirm')">{{ confirmLabel }}</button>
      <button type="button" class="dx-secondary" :disabled="busy" @click="emit('cancel')">Hủy</button>
    </div>
  </div>
</template>
