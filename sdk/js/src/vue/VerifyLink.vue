<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
import { computed } from 'vue'
import { checkedVerifyUrl, VERIFY_INVALID } from './verifyUrl'

const props = defineProps<{ verifyUrl: string }>()
const href = computed(() => checkedVerifyUrl(props.verifyUrl))
</script>

<template>
  <a v-if="href" :href="href" class="dx-verify-link">Mở trang đối soát</a>
  <span v-else class="dx-verify-invalid">{{ VERIFY_INVALID }}</span>
</template>
