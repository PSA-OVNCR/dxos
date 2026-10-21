// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// App B "Chứng nhận số" trên trình duyệt thật: nhập CSV 3 dòng (UTF-8 có BOM), gửi duyệt, duyệt theo lô, trang in.
import { expect, test } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  APP_B, LIVE, SKIP_REASON, STATE_DIR, expectNoCspViolations, login, reloadUntil, runTag, shot,
} from './helpers'

test.skip(!LIVE, SKIP_REASON)

const TAG = runTag()
const EVENT = `Sự kiện trình duyệt thật ${TAG}`
const EMAIL_DOMAIN = `live-${TAG}.example.test` // PII: không được xuất hiện trên trang in
const PEOPLE = ['Nguyễn Văn An', 'Trần Thị Bình', 'Lê Hoàng Cường']
const CSV = '﻿' + [
  'Họ và tên,Sự kiện,Ngày cấp,Email',
  ...PEOPLE.map((name, i) => `${name},${EVENT},1${i}/11/2026,nguoi${i}@${EMAIL_DOMAIN}`),
].join('\r\n') + '\r\n'

test.describe.serial('App B: nhập CSV, duyệt lô, trang in', () => {
  test.afterAll(() => { expectNoCspViolations() })

  test('can_bo_clb1 nhập CSV 3 dòng (UTF-8 BOM) và gửi duyệt', async ({ browser }) => {
    const page = await login(browser, 'can_bo_clb1', APP_B, '#/nhap-csv')
    await page.setInputFiles('input[type=file]', {
      name: 'dot-live.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV, 'utf8'),
    })
    await expect(page.getByText('Bảng mã nhận diện: UTF-8.')).toBeVisible()
    await expect(page.getByText('3 dòng hợp lệ, 0 dòng lỗi.')).toBeVisible()
    await page.getByRole('button', { name: 'Tạo chứng nhận' }).click()
    await expect(page.getByText('Đã tạo 3 chứng nhận, 0 dòng lỗi.')).toBeVisible()
    await page.getByRole('button', { name: 'Gửi duyệt', exact: true }).click()
    await expect(page.getByText('Đã gửi duyệt 3, lỗi 0.')).toBeVisible()
    await shot(page, 'app-b-1-nhap-csv')
  })

  test('truong_clb1 duyệt lô 3 mục', async ({ browser }) => {
    const page = await login(browser, 'truong_clb1', APP_B, '#/duyet-lo')
    const boxes = page.locator('label.dx-check').filter({ hasText: EVENT })
    await expect(boxes).toHaveCount(3)
    for (let i = 0; i < 3; i++) await boxes.nth(i).locator('input[type=checkbox]').check()
    await shot(page, 'app-b-2-duyet-lo')
    await page.getByRole('button', { name: 'Duyệt các mục đã chọn' }).click()
    await expect(page.getByText('3 đã duyệt, 0 lỗi.')).toBeVisible()
  })

  test('trang in có họ tên và QR, không có email', async ({ browser }) => {
    const page = await login(browser, 'truong_clb1', APP_B, '#/')
    const seals: Record<string, string> = {}
    for (const name of PEOPLE) {
      const row = page.locator('table.dx-table tbody tr').filter({ hasText: EVENT }).filter({ hasText: name })
      await reloadUntil(page, async () => {
        await expect(row.locator('.dx-status')).toHaveText('Đã cấp', { timeout: 3_000 })
      })
      await row.getByRole('link', { name }).click()
      await page.getByRole('link', { name: 'Trang in chứng nhận' }).click()
      const cert = page.locator('article.dx-cert')
      await expect(cert.getByRole('heading', { name: 'Chứng nhận tham gia sự kiện' })).toBeVisible()
      await expect(cert).toContainText(name)
      await expect(cert).toContainText(EVENT)
      await expect(cert.getByAltText('Mã QR dẫn tới trang đối soát chứng nhận')).toBeVisible()
      await expect(page.locator('body')).not.toContainText(EMAIL_DOMAIN)
      const text = (await cert.textContent()) ?? ''
      seals[name] = /Mã niêm phong: ([A-Z2-7]{26})/.exec(text)?.[1] ?? ''
      expect(seals[name]).toMatch(/^[A-Z2-7]{26}$/)
      await shot(page, `app-b-3-trang-in-${PEOPLE.indexOf(name) + 1}`)
      await page.goto(APP_B + '#/')
    }
    mkdirSync(STATE_DIR, { recursive: true })
    writeFileSync(join(STATE_DIR, 'app-b.json'), JSON.stringify({ event: EVENT, seals }), 'utf8')
  })
})
