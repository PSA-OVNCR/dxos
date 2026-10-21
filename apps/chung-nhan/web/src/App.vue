<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung App B: phần chung (đầu trang, đăng xuất, tải manifest, màn hình lỗi đăng nhập) là AppShell của SDK;
// ở đây chỉ còn liên kết điều hướng theo vai trò (tiện dụng; lõi vẫn kiểm mọi lời gọi).
import { hasRole } from 'dxos-sdk-js'
import { AppShell } from 'dxos-sdk-js/vue'
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { COL, useSession } from './session'

const { roles, view } = useSession()

const ROLE_LABELS: Record<string, string> = { can_bo_clb: 'Cán bộ CLB', truong_clb: 'Trưởng CLB' }

const canImport = computed(() => hasRole(
  roles.value, (view.value?.collections[COL]?.access.create ?? []).filter((r) => r.startsWith('role:')).map((r) => r.slice(5)),
))
const showBatch = computed(() => hasRole(roles.value, Object.values(view.value?.workflow?.tasks ?? {}).map((t) => t.role)))
</script>

<template>
  <AppShell fallback-name="Chứng nhận số" :role-labels="ROLE_LABELS">
    <template #nav>
      <RouterLink to="/">Danh sách chứng nhận</RouterLink>
      <RouterLink v-if="canImport" to="/nhap-csv">Nhập từ CSV</RouterLink>
      <RouterLink v-if="showBatch" to="/duyet-lo">Duyệt theo lô</RouterLink>
    </template>
    <RouterView />
  </AppShell>
</template>
