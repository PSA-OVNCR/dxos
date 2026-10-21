<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung ứng dụng là AppShell của SDK; ở đây chỉ có liên kết điều hướng. Ẩn "Hộp việc" theo vai trò chỉ là tiện dụng:
// lõi vẫn kiểm mọi lời gọi.
import { hasRole } from 'dxos-sdk-js'
import { AppShell, useSession } from 'dxos-sdk-js/vue'
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

const { roles, view } = useSession()
const canReview = computed(() => hasRole(roles.value, Object.values(view.value?.workflow?.tasks ?? {}).map((t) => t.role)))
</script>

<template>
  <AppShell fallback-name="Sổ mượn sách">
    <template #nav>
      <RouterLink to="/">Phiếu mượn</RouterLink>
      <RouterLink v-if="canReview" to="/duyet">Hộp việc</RouterLink>
    </template>
    <RouterView />
  </AppShell>
</template>
