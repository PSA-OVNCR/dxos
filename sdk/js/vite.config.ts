// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vitest/config'

// Chế độ thư viện: hai điểm vào, thư viện ngoài để ứng dụng tự gói.
export default defineConfig({
  build: {
    lib: {
      entry: {
        index: 'src/index.ts',
        vue: 'src/vue/index.ts',
      },
      formats: ['es'],
    },
    rollupOptions: { external: ['vue', 'oidc-client-ts', 'qrcode'] },
  },
  test: { include: ['test/**/*.test.ts'] },
})
