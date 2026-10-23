<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Nhãn trạng thái: dấu + CHỮ + màu. Không bao giờ chỉ có màu.
import { MARK, type StateText } from './status'

defineProps<{ state: StateText }>()
</script>

<template>
  <span class="dx-state" :class="`dx-state-${state.level}`">
    <span aria-hidden="true" class="dx-state-mark">{{ MARK[state.level] }}</span>
    <span>{{ state.text }}</span>
  </span>
</template>
