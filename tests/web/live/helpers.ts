// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Dùng chung cho bộ kiểm đầu-cuối trên trình duyệt thật (Plan 03 Task 10). Chỉ chạy khi DXOS_WEB_LIVE=1 và stack
// dev-lite đang chạy (ops/web_live.sh). Mật khẩu người dùng dev chỉ có ở realm dev.
import { expect, type Browser, type BrowserContextOptions, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'

export const LIVE = process.env.DXOS_WEB_LIVE === '1'
export const SKIP_REASON = 'đặt DXOS_WEB_LIVE=1 và dựng stack dev-lite (ops/web_live.sh) để chạy bộ kiểm trình duyệt thật'
export const BASE_URL = process.env.DXOS_BASE_URL ?? 'https://localhost'
export const PASSWORD = process.env.DXOS_E2E_PASSWORD ?? 'dev-only-password'
export const OUT_DIR = resolve(process.env.DXOS_WEB_LIVE_OUT ?? 'test-results/web-live') // tính từ thư mục chạy lệnh
export const SHOT_DIR = process.env.DXOS_SHOT_DIR ?? join(OUT_DIR, 'shots')
export const STATE_DIR = join(OUT_DIR, 'state')
/** Tệp PDF sạch dùng cho cả E2E Python (core/tests/fixtures/files). */
export const PDF_PATH = process.env.DXOS_FIXTURE_PDF ?? resolve(__dirname, '../../../core/tests/fixtures/files/clean-text.pdf')
/** PDF có 3 dữ liệu cá nhân hư cấu (1 CCCD, 1 SĐT, 1 STK) cho luồng dò PII của App A (Plan 04 Task 6, V39). */
export const PII_PDF_PATH = process.env.DXOS_FIXTURE_PII_PDF
  ?? resolve(__dirname, '../../../core/tests/fixtures/files/pii-fictional.pdf')

export const APP_A = '/apps/phong-ho-so/'
export const APP_B = '/apps/chung-nhan/'

/** Ngữ cảnh trình duyệt dựng tay không thừa hưởng `use` của cấu hình, nên các tuỳ chọn nằm ở đây và cấu hình dùng lại. */
export const CONTEXT_OPTIONS: BrowserContextOptions = {
  baseURL: BASE_URL,
  // CA nội bộ của Caddy (dev) không có trong kho tin cậy của Chromium. Không tắt kiểm chứng chỉ: playwright.config.ts
  // truyền --ignore-certificate-errors-spki-list với SPKI của CA đó (DXOS_CADDY_SPKI, do ops/web_live.sh tính), nên
  // chứng chỉ của bên khác vẫn bị từ chối. NODE_EXTRA_CA_CERTS chỉ lo phía Node.
  locale: 'vi-VN',
  timezoneId: 'Asia/Ho_Chi_Minh',
  acceptDownloads: true,
}

/** Mã định danh ngắn, khác nhau mỗi lần chạy, để lọc dữ liệu của lần chạy này giữa dữ liệu cũ trong stack dev. */
export function runTag(): string {
  return Date.now().toString(36)
}

/** Vi phạm CSP gom được từ console của mọi trang đã mở bằng `open()`/`login()`. */
export const cspViolations: string[] = []

export function watchCsp(page: Page): void {
  page.on('console', (msg) => {
    if (/content security policy/i.test(msg.text())) cspViolations.push(`${page.url()} :: ${msg.text()}`)
  })
  page.on('pageerror', (err) => cspViolations.push(`${page.url()} :: pageerror ${err.message}`))
}

export function expectNoCspViolations(): void {
  expect(cspViolations, 'CSP của /apps/* bị vi phạm').toEqual([])
}

/** Trang ẩn danh (cổng đối soát là công khai). */
export async function open(browser: Browser, path: string): Promise<Page> {
  const page = await (await browser.newContext(CONTEXT_OPTIONS)).newPage()
  watchCsp(page)
  await page.goto(path)
  return page
}

/** Đăng nhập trên form Keycloak bằng người dùng dev rồi chờ khung ứng dụng hiện nút Đăng xuất. */
export async function login(browser: Browser, user: string, appPath: string, hash = ''): Promise<Page> {
  const page = await (await browser.newContext(CONTEXT_OPTIONS)).newPage()
  watchCsp(page)
  await page.goto(appPath + hash)
  await page.waitForURL(/\/auth\/realms\/dxos\//)
  await page.locator('#username').fill(user)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await page.waitForURL((u) => u.pathname === appPath)
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible()
  return page
}

export async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(SHOT_DIR, { recursive: true })
  await page.screenshot({ path: join(SHOT_DIR, `${name}.png`), fullPage: true })
}

/** Tải lại trang cho đến khi `check` đạt (niêm phong và công bố STH chạy nền nên trạng thái đến muộn). */
export async function reloadUntil(page: Page, check: () => Promise<void>, timeout = 240_000): Promise<void> {
  await expect(async () => {
    await page.reload()
    await check()
  }).toPass({ timeout, intervals: [2_000, 5_000, 10_000] })
}
