<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung App A: phần chung (đầu trang, đăng xuất, tải manifest, màn hình lỗi đăng nhập) là AppShell của SDK;
// ở đây chỉ còn liên kết điều hướng theo vai trò (tiện dụng; lõi vẫn kiểm mọi lời gọi).
import { AppShell } from 'dxos-sdk-js/vue'
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { COL, useSession } from './session'
import { hasRole } from './status'

const { roles, view } = useSession()

const ROLE_LABELS: Record<string, string> = {
  chuyen_vien: 'Chuyên viên',
  truong_phong: 'Trưởng phòng',
  giam_doc: 'Giám đốc',
  van_thu: 'Văn thư',
  nhan_vien: 'Nhân viên',
}

const showInbox = computed(() => hasRole(roles.value, Object.values(view.value?.workflow?.tasks ?? {}).map((t) => t.role)))
const showRegister = computed(() => hasRole(
  roles.value, (view.value?.collections[COL]?.access.read ?? []).filter((r) => r.startsWith('role:')).map((r) => r.slice(5)),
))
</script>

<template>
  <AppShell fallback-name="Phòng hồ sơ số" :role-labels="ROLE_LABELS">
    <template #nav>
      <RouterLink to="/">Danh sách văn bản</RouterLink>
      <RouterLink v-if="showInbox" to="/hop-viec">Hộp việc</RouterLink>
      <RouterLink v-if="showRegister" to="/so-dang-ky">Sổ đăng ký văn bản đi</RouterLink>
    </template>
    <RouterView />
  </AppShell>
</template>
