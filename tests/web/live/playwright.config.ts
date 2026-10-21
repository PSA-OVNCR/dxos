// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Bộ kiểm đầu-cuối trên Chromium thật cho App A, App B và cổng đối soát (Plan 03 Task 10). Chạy bằng
// `make web-live` (ops/web_live.sh, trong container Playwright cạnh stack dev-lite). Không có DXOS_WEB_LIVE=1 thì
// mọi test được bỏ qua.
import { defineConfig } from '@playwright/test'
import { join } from 'node:path'
import { BASE_URL, CONTEXT_OPTIONS, LIVE, OUT_DIR } from './helpers'

// Chromium luôn coi `localhost` là loopback, bỏ qua /etc/hosts. Trong container, ops/web_live.sh đặt DXOS_GATEWAY_IP
// (địa chỉ host.docker.internal) để ép `localhost` và `admin.localhost` về máy chủ Docker.
const gateway = process.env.DXOS_GATEWAY_IP
const args = gateway ? [`--host-resolver-rules=MAP localhost ${gateway}, MAP admin.localhost ${gateway}`] : []

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  workers: 1, // ba tệp spec nối tiếp nhau: app-a và app-b ghi seal_id, verify.spec đọc lại
  retries: 0,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  forbidOnly: !!process.env.CI,
  // Không ghi tệp nào khi bị bỏ qua (npm run test:live ngoài container).
  reporter: LIVE ? [['list'], ['junit', { outputFile: join(OUT_DIR, 'web-live-junit.xml') }]] : [['list']],
  outputDir: join(OUT_DIR, 'artifacts'),
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: CONTEXT_OPTIONS.ignoreHTTPSErrors,
    trace: 'retain-on-failure',
    launchOptions: { args },
  },
})
