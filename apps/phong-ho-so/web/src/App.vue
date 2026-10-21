<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung ứng dụng: đầu trang (tên, vai trò, đăng xuất), tải manifest một lần, màn hình lỗi đăng nhập.
// Ẩn/hiện theo vai trò chỉ là tiện dụng; mọi quyết định do lõi, mọi lỗi của lõi hiện bằng ProblemMessage.
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useSession } from './session'

const session = useSession()
const { auth, guard, roles, view, viewError } = session

const ROLE_LABELS: Record<string, string> = {
  chuyen_vien: 'Chuyên viên',
  truong_phong: 'Trưởng phòng',
  giam_doc: 'Giám đốc',
  van_thu: 'Văn thư',
  nhan_vien: 'Nhân viên',
}

const who = computed(() => auth.profile()?.name ?? '')
const roleText = computed(() => roles.value.map((r) => ROLE_LABELS[r] ?? r).join(', '))

onMounted(() => { void session.load() })

async function logout(): Promise<void> {
  guard.succeeded() // đăng xuất chủ động không phải là vòng lặp đăng nhập
  await auth.logout()
}
</script>

<template>
  <section v-if="guard.rejected.value" class="dx-fatal" role="alert">
    <h1>Phiên đăng nhập không được máy chủ chấp nhận</h1>
    <p>Bạn đã đăng nhập nhưng máy chủ vẫn từ chối phiên này. Hãy kiểm tra đồng hồ của máy rồi đăng nhập lại; nếu vẫn lỗi, hãy báo quản trị viên.</p>
    <button type="button" @click="guard.retry()">Đăng nhập lại</button>
  </section>

  <template v-else>
    <header class="dx-header">
      <p class="dx-brand">{{ view?.app.name ?? 'Phòng hồ sơ số' }}</p>
      <nav aria-label="Điều hướng chính">
        <RouterLink to="/">Danh sách văn bản</RouterLink>
      </nav>
      <p class="dx-who">
        <span>{{ who }}</span>
        <span v-if="roleText" class="dx-roles"> · {{ roleText }}</span>
        <button type="button" @click="logout">Đăng xuất</button>
      </p>
    </header>

    <main class="dx-main">
      <template v-if="view">
        <RouterView />
      </template>
      <template v-else-if="viewError">
        <ProblemMessage :error="viewError" />
        <button type="button" @click="session.load()">Tải lại</button>
      </template>
      <p v-else role="status">Đang tải…</p>
    </main>
  </template>
</template>
