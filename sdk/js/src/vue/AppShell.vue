<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Khung ứng dụng Tầng 2: đầu trang (tên, vai trò, đăng xuất), tải manifest một lần, màn hình lỗi đăng nhập.
// Liên kết điều hướng (slot "nav") và nội dung (slot mặc định, thường là <RouterView/>) do ứng dụng cấp, nên SDK không
// phụ thuộc vue-router. Ẩn/hiện theo vai trò chỉ là tiện dụng; mọi quyết định do lõi, mọi lỗi của lõi hiện bằng ProblemMessage.
import { computed, onMounted } from 'vue'
import ProblemMessage from './ProblemMessage.vue'
import { useSession } from './session'

const props = defineProps<{ fallbackName: string; roleLabels?: Record<string, string> }>()

const session = useSession()
const { auth, guard, roles, view, viewError } = session

const who = computed(() => auth.profile()?.name ?? '')
const roleText = computed(() => roles.value.map((r) => props.roleLabels?.[r] ?? r).join(', '))

onMounted(() => { if (!guard.redirecting.value && !guard.rejected.value) void session.load() })

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

  <p v-else-if="guard.redirecting.value" role="status" class="dx-fatal">Đang chuyển sang trang đăng nhập…</p>

  <template v-else>
    <header class="dx-header">
      <p class="dx-brand">{{ view?.app.name ?? fallbackName }}</p>
      <nav aria-label="Điều hướng chính" class="dx-nav">
        <slot name="nav" />
      </nav>
      <p class="dx-who">
        <span>{{ who }}</span>
        <span v-if="roleText" class="dx-roles"> · {{ roleText }}</span>
        <button type="button" @click="logout">Đăng xuất</button>
      </p>
    </header>

    <main class="dx-main">
      <template v-if="view">
        <slot />
      </template>
      <template v-else-if="viewError">
        <ProblemMessage :error="viewError" />
        <button type="button" @click="session.load()">Tải lại</button>
      </template>
      <p v-else role="status">Đang tải…</p>
    </main>
  </template>
</template>
