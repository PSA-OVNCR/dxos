// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Cùng CSP với Caddy (deploy/caddy/Caddyfile, handle_path /apps/verify/*) khi DXOS_ANCHOR_RAW_ORIGIN để trống:
// Playwright chạy bản build dưới đúng chính sách này nên mọi mã nội tuyến, eval hay nguồn ngoài đều lộ ra.
// tests/deploy/test_verify_page_static.py giữ hai chuỗi này khớp nhau.
const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
  + "connect-src 'self' ; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

// Caddy phục vụ cổng ở /apps/verify/ (handle_path cắt tiền tố). Repo neo là biến BUILD (VITE_ANCHOR_RAW_BASE),
// không bao giờ đọc từ máy chủ lúc chạy.
export default defineConfig({
  base: '/apps/verify/',
  plugins: [vue()],
  preview: { headers: { 'Content-Security-Policy': CSP } },
  test: { include: ['test/**/*.test.ts'] },
})
