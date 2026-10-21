<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
import QRCode from 'qrcode'
import { ref, watch } from 'vue'
import { checkedVerifyUrl, VERIFY_INVALID } from './verifyUrl'

const props = withDefaults(defineProps<{ verifyUrl: string; size?: number }>(), { size: 192 })

const valid = ref(false)
const src = ref('')
let run = 0

watch(() => props.verifyUrl, async (raw) => {
  const mine = ++run
  const url = checkedVerifyUrl(raw)
  valid.value = url !== null
  src.value = ''
  if (!url) return
  try {
    const svg = await QRCode.toString(url, { type: 'svg', errorCorrectionLevel: 'M' })
    if (mine === run) src.value = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
  } catch {
    if (mine === run) valid.value = false
  }
}, { immediate: true })
</script>

<template>
  <span v-if="!valid" class="dx-verify-invalid">{{ VERIFY_INVALID }}</span>
  <img
    v-else-if="src"
    :src="src"
    :width="size"
    :height="size"
    alt="Mã QR dẫn tới trang đối soát chứng nhận"
    class="dx-seal-qr"
  >
</template>
