// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Caddy phục vụ ứng dụng ở /apps/chung-nhan/ (handle_path cắt tiền tố); API cùng origin nên không cần CORS.
export default defineConfig({
  base: '/apps/chung-nhan/',
  plugins: [vue()],
  test: { include: ['test/**/*.test.ts'] },
})
