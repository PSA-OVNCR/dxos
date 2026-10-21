// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Máy chủ giả cho Playwright: /verify/v1/** trả dữ liệu dựng từ vector do dxos-witness sinh, __anchor/** trả
// tệp repo neo của vector. Mọi yêu cầu không lường trước trả 500 để test lộ ra.
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { test as base, type Page, type Route } from '@playwright/test'

export const SEAL_ID = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
/** Tệp gốc của vector (witness/tests/conftest.py ORIGINAL): sha256 của nó nằm trong `payload.attachments`. */
export const ORIGINAL = Buffer.from('tệp gốc của bản ghi')

interface Vector { bundle_text: string; anchor_files: Record<string, string> }
const vectorsDir = new URL('../../../sdk/js/test/vectors/', import.meta.url)
export const vector = (name: string): Vector =>
  JSON.parse(readFileSync(new URL(`${name}.json`, vectorsDir), 'utf8')) as Vector

export const sha256hex = (b: Buffer): string => createHash('sha256').update(b).digest('hex')

export interface MockOptions {
  requireFile: boolean
  /** Mã băm mà `:check` coi là khớp (mặc định: không tệp nào khớp). */
  sha256?: string
  bundleVector?: string
  /** Mã niêm phong mà trang sẽ hỏi (mặc định SEAL_ID); phản hồi vẫn là của SEAL_ID, như máy chủ bị chiếm. */
  routeId?: string
  anchoredRepo?: string
  /** Trường ghi đè lên phản hồi công khai. */
  view?: Record<string, unknown>
  /** Mã HTTP của GET công khai (mặc định 200). */
  viewStatus?: number
  /** vector: phục vụ tệp neo của vector; down: mạng đứt; empty: repo neo trả 404 cho mọi tệp. */
  anchor?: 'vector' | 'down' | 'empty'
}

export interface Calls { urls: string[] }

export async function mockVerifyApi(page: Page, o: MockOptions): Promise<Calls> {
  const v = vector(o.bundleVector ?? 'ok-anchored')
  const bundle = JSON.parse(v.bundle_text) as { payload: { app_id: string; issued_at: string; public_fields: object } }
  const view = {
    seal_id: SEAL_ID, status: 'VALID', app_id: bundle.payload.app_id, issued_at: bundle.payload.issued_at,
    key_version: 1, public_fields: bundle.payload.public_fields, require_file: o.requireFile, attachments_count: 1,
    signature_valid: true,
    inclusion: {
      leaf_index: 5, tree_size: 8, verified: true,
      anchored: { tree_size: 8, repo: o.anchoredRepo ?? 'PSA-OVNCR/dxos-transparency-log', commit_sha: 'abc123' },
    },
    issuer: { name: 'Trường Đại học Thử', id: 'TDHT-01' },
    public_labels: { ref: 'Số văn bản', title: 'Trích yếu' },
    ...o.view,
  }
  const calls: Calls = { urls: [] }
  const json = (route: Route, status: number, body: unknown) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const bundleReply = (route: Route) => route.fulfill({
    status: 200, contentType: 'application/json', body: v.bundle_text,
    headers: { 'Content-Disposition': `attachment; filename="dxos-seal-${SEAL_ID}.json"` },
  })

  await page.route(/\/verify\/v1\//, async (route) => {
    const req = route.request()
    const { pathname } = new URL(req.url())
    calls.urls.push(`${req.method()} ${pathname}`)
    const base = `/verify/v1/seals/${o.routeId ?? SEAL_ID}`
    if (req.method() === 'GET' && pathname === base) {
      if ((o.viewStatus ?? 200) !== 200) return json(route, o.viewStatus ?? 200, { title: 'x' })
      return json(route, 200, view)
    }
    if (req.method() === 'POST' && pathname === `${base}:check`) {
      const body = req.postDataJSON() as { sha256?: string }
      return json(route, 200, { match: o.sha256 !== undefined && body.sha256 === o.sha256 })
    }
    if (req.method() === 'POST' && pathname === `${base}:bundle`) {
      const body = req.postDataJSON() as { sha256?: string }
      if (!o.requireFile || body.sha256 !== o.sha256) return json(route, 404, { title: 'Not Found' })
      return bundleReply(route)
    }
    if (req.method() === 'GET' && pathname === `${base}/bundle`) {
      return o.requireFile ? json(route, 404, { title: 'Not Found' }) : bundleReply(route)
    }
    return json(route, 500, { title: `giả lập không lường trước ${req.method()} ${pathname}` })
  })

  await page.route(/\/__anchor\//, async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/__anchor\//, '')
    calls.urls.push(`ANCHOR ${path}`)
    if (o.anchor === 'down') return route.abort('failed')
    const file = o.anchor === 'empty' ? undefined : v.anchor_files[path]
    if (file === undefined) return route.fulfill({ status: 404, body: 'not found' })
    return route.fulfill({ status: 200, contentType: 'application/octet-stream', body: Buffer.from(file, 'base64') })
  })
  return calls
}

/** Mọi test chạy dưới CSP thật của cổng: vi phạm CSP hay lỗi JS chưa bắt đều làm test hỏng. */
export const test = base.extend<{ guard: void }>({
  guard: [async ({ page }, use) => {
    const problems: string[] = []
    page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
    page.on('console', (m) => {
      if (/Content Security Policy|violates/i.test(m.text())) problems.push(`csp: ${m.text()}`)
    })
    await use()
    if (problems.length) throw new Error(problems.join('\n'))
  }, { auto: true }],
})
export { expect } from '@playwright/test'
