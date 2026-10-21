// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Cổng đối soát công khai /apps/verify/ với niêm phong thật của App B (do app-b.spec.ts ghi seal_id): trình duyệt tự
// kiểm gói bằng chứng, không cần đăng nhập, không có tệp.
import { expect, test } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { LIVE, SKIP_REASON, STATE_DIR, expectNoCspViolations, open, reloadUntil, shot } from './helpers'

test.skip(!LIVE, SKIP_REASON)

test('cổng đối soát cho niêm phong của App B: kết quả tự kiểm của trình duyệt', async ({ browser }) => {
  const stateFile = join(STATE_DIR, 'app-b.json')
  expect(existsSync(stateFile), 'chạy app-b.spec.ts trước (nó ghi seal_id vào ' + stateFile + ')').toBe(true)
  const { seals } = JSON.parse(readFileSync(stateFile, 'utf8')) as { seals: Record<string, string> }
  const sealId = Object.values(seals)[0]
  expect(sealId).toMatch(/^[A-Z2-7]{26}$/)

  const page = await open(browser, `/apps/verify/#${sealId}`)
  // Chờ STH phủ lá niêm phong (worker công bố định kỳ): trước đó cổng báo "Chữ ký hợp lệ — đang chờ công bố".
  await reloadUntil(page, async () => {
    await expect(page.getByTestId('verdict')).toHaveText(/^Hợp lệ/, { timeout: 3_000 })
  })
  await expect(page.getByRole('heading', { name: 'Máy chủ báo' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Trình duyệt tự kiểm' })).toBeVisible()
  await expect(page.getByText('Đơn vị niêm phong')).toBeVisible()
  // Kết quả tự kiểm không báo lỗi (mã lỗi hiện trong thẻ .mono kèm lời giải thích).
  await expect(page.locator('p.msg.bad')).toHaveCount(0)
  await shot(page, 'verify-1-app-b')
  expectNoCspViolations()
})
