<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung trang quản trị: đầu trang, đăng xuất, màn hình lỗi đăng nhập là AppShell của SDK; ở đây chỉ còn điều hướng.
import { AppShell } from 'dxos-sdk-js/vue'
import { RouterLink, RouterView } from 'vue-router'
import { ROLE_LABELS } from './session'
</script>

<template>
  <AppShell fallback-name="Quản trị DX-OS" :role-labels="ROLE_LABELS">
    <template #nav>
      <RouterLink to="/health">Sức khỏe hệ thống</RouterLink>
      <RouterLink to="/ledger">Sổ cái</RouterLink>
    </template>
    <RouterView />
  </AppShell>
</template>
