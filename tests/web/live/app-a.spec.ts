// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// App A "Phòng hồ sơ số" trên trình duyệt thật: tạo văn bản, tải PDF, qua kiểm dịch, duyệt hai cấp, rà PII, ban hành,
// QR, đối soát tệp ở cổng công khai, sổ đăng ký văn bản đi. Mỗi người dùng một ngữ cảnh trình duyệt riêng.
import { expect, test } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  APP_A, LIVE, PDF_PATH, SKIP_REASON, STATE_DIR, expectNoCspViolations, login, open, reloadUntil, runTag, shot,
} from './helpers'

test.skip(!LIVE, SKIP_REASON)

const TAG = runTag()
const TRICH_YEU = `Quyết định thử nghiệm trình duyệt thật ${TAG}`
const NOTICE_APPROVED = /Đã duyệt văn bản/

let docHash = '' // "#/van-ban/<id>"
let verifyUrl = ''
let soHieu = ''

test.describe.serial('App A: từ nháp đến văn bản ban hành', () => {
  test.afterAll(() => { expectNoCspViolations() })

  test('chuyen_vien_tp1 tạo văn bản, tải PDF, chờ "Sạch" rồi gửi duyệt', async ({ browser }) => {
    const page = await login(browser, 'chuyen_vien_tp1', APP_A)
    await page.getByRole('link', { name: 'Văn bản mới' }).click()
    await page.getByLabel('Tên loại văn bản').fill('Quyết định')
    await page.getByLabel('Trích yếu nội dung').fill(TRICH_YEU)
    await page.getByLabel('Chức vụ người ký').fill('Giám đốc')
    await page.getByRole('button', { name: 'Tạo văn bản' }).click()
    await expect(page).toHaveURL(/#\/van-ban\/[^/]+$/)
    docHash = new URL(page.url()).hash

    await page.setInputFiles('#dx-file', PDF_PATH)
    await expect(page.locator('.dx-quarantine')).toHaveText('Sạch', { timeout: 120_000 })
    await shot(page, 'app-a-1-sach')
    await page.getByRole('button', { name: 'Gửi duyệt', exact: true }).click()
    await expect(page.locator('.dx-toolbar .dx-status')).toHaveText('Đang duyệt')
  })

  test('truong_phong1 duyệt bước duyệt nội dung', async ({ browser }) => {
    const page = await login(browser, 'truong_phong1', APP_A, '#/hop-viec')
    const item = page.locator('ul.dx-tasks > li').filter({ hasText: TRICH_YEU })
    await expect(item).toHaveCount(1)
    await item.getByRole('button', { name: 'Duyệt', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: NOTICE_APPROVED })).toBeVisible()
  })

  test('van_thu1 xác nhận đã rà dữ liệu cá nhân', async ({ browser }) => {
    const page = await login(browser, 'van_thu1', APP_A, docHash)
    await page.getByRole('button', { name: 'Xác nhận đã rà dữ liệu cá nhân' }).click()
    await expect(page.getByText('Đã ghi nhận xác nhận rà dữ liệu cá nhân.')).toBeVisible()
    await shot(page, 'app-a-2-ra-pii')
  })

  test('giam_doc1 duyệt bước ban hành và thấy mã QR', async ({ browser }) => {
    const page = await login(browser, 'giam_doc1', APP_A, '#/hop-viec')
    const item = page.locator('ul.dx-tasks > li').filter({ hasText: TRICH_YEU })
    await expect(item).toHaveCount(1)
    await item.getByRole('button', { name: 'Duyệt', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: NOTICE_APPROVED })).toBeVisible()

    await page.goto(APP_A + docHash)
    await reloadUntil(page, async () => {
      await expect(page.locator('.dx-toolbar .dx-status')).toHaveText('Đã ban hành', { timeout: 3_000 })
    })
    await expect(page.getByAltText('Mã QR dẫn tới trang đối soát chứng nhận')).toBeVisible()
    verifyUrl = (await page.getByRole('link', { name: 'Mở trang đối soát' }).getAttribute('href')) ?? ''
    expect(verifyUrl).toMatch(/\/apps\/verify\/#[A-Z2-7]{26}$/)
    soHieu = (await page.locator('dt', { hasText: 'Số, ký hiệu' }).locator('+ dd').textContent())?.trim() ?? ''
    expect(soHieu).toMatch(/^\d{2}\/QĐ-SM$/)
    await shot(page, 'app-a-3-ban-hanh-qr')

    mkdirSync(STATE_DIR, { recursive: true })
    writeFileSync(join(STATE_DIR, 'app-a.json'), JSON.stringify({ verifyUrl, soHieu, trichYeu: TRICH_YEU }), 'utf8')
  })

  test('mở verify_url, chọn đúng tệp PDF và thấy "Hợp lệ"', async ({ browser }) => {
    const page = await open(browser, verifyUrl)
    // Gói chỉ có khi STH phủ lá: chờ worker công bố STH ("Chữ ký hợp lệ — đang chờ..." chưa phải "Hợp lệ").
    await reloadUntil(page, async () => {
      await expect(page.getByTestId('verdict')).toHaveText(/^Hợp lệ/, { timeout: 3_000 })
    })
    await page.setInputFiles('#file-input', PDF_PATH)
    await expect(page.getByText('Khớp: tệp này đúng là tệp đã được niêm phong.')).toBeVisible()
    await expect(page.getByTestId('verdict')).toHaveText(/^Hợp lệ/)
    await expect(page.getByRole('heading', { name: 'Trình duyệt tự kiểm' })).toBeVisible()
    await shot(page, 'app-a-4-doi-soat-hop-le')
  })

  test('Sổ đăng ký văn bản đi có số mới', async ({ browser }) => {
    const page = await login(browser, 'giam_doc1', APP_A, '#/so-dang-ky')
    const row = page.locator('table.dx-register tbody tr').filter({ hasText: TRICH_YEU })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText(soHieu)
    await expect(row).toContainText('Đã ban hành')
    await shot(page, 'app-a-5-so-dang-ky')
  })
})
