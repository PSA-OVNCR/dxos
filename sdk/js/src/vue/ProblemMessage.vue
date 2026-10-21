<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
import { computed } from 'vue'
import { messageFor } from './messages'

const props = defineProps<{ error: unknown }>()
const text = computed(() => (props.error == null ? '' : messageFor(props.error)))
</script>

<template>
  <p v-if="error != null" role="alert" class="dx-problem">{{ text }}</p>
</template>
