// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Caddy phục vụ trang quản trị ở /ui/ trên host admin (Task 10); API cùng origin (/admin/v1) nên không cần CORS.
export default defineConfig({
  base: '/ui/',
  plugins: [vue()],
  test: { include: ['test/**/*.test.ts'] },
})
