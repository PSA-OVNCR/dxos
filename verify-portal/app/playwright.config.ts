// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from '@playwright/test'

const PORT = 4173
const ORIGIN = `http://127.0.0.1:${PORT}`
// Trong sandbox không tải được trình duyệt: PW_CHROMIUM trỏ tới tệp chạy Chromium có sẵn. CI cài bằng
// `npx playwright install --with-deps chromium` nên không cần biến này.
const executablePath = process.env.PW_CHROMIUM

export default defineConfig({
  testDir: 'e2e',
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  use: { baseURL: ORIGIN, ...(executablePath ? { launchOptions: { executablePath } } : {}) },
  // Bản build dùng repo neo GIẢ cùng origin (`__anchor`), do page.route phục vụ từ tệp của vector.
  webServer: {
    command: `npx vite build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `${ORIGIN}/apps/verify/`,
    env: { VITE_ANCHOR_RAW_BASE: `${ORIGIN}/__anchor` },
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
