// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
// Xem trang tệp đính kèm bằng Viewer (Plan 04 Task 8, S2): trang PNG lấy bằng bearer token, hiện qua blob: URL, thu hồi
// khi đóng. Dữ liệu hư cấu.
import { Blob as NodeBlob } from 'node:buffer'
import { flushPromises } from '@vue/test-utils'
import { client as realClient, fakeFetch, problem } from 'dxos-sdk-js/testing'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import ViewerDialog from '../src/components/ViewerDialog.vue'
import VanBanDetail from '../src/views/VanBanDetail.vue'
import { att, click, detailClient, mountWith } from './helpers'

const SHA = 'e'.repeat(64)
// Blob của Node, không phải của jsdom: Response (undici) của Node không đọc được Blob của jsdom.
const PNG = () => new NodeBlob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: 'image/png' }) as unknown as Blob
const png = () => ({ blob: PNG(), contentType: 'image/png' })
const info = (pages: number) => ({ json: { pages } })

let created: string[]
let revoked: string[]
let seq: number

beforeEach(() => {
  created = []
  revoked = []
  seq = 0
  Object.assign(URL, {
    createObjectURL: vi.fn((b: Blob) => {
      expect(b.size).toBe(4)
      const u = `blob:dxos-${++seq}`
      created.push(u)
      return u
    }),
    revokeObjectURL: vi.fn((u: string) => { revoked.push(u) }),
  })
})
afterEach(() => { vi.restoreAllMocks() })

function mountDialog(f: ReturnType<typeof fakeFetch>, props: Record<string, unknown> = {}) {
  return mountWith(ViewerDialog, realClient(f), { sha256: SHA, variant: 'original', label: 'Tệp 1', ...props })
}

const imgSrc = (w: { find: (s: string) => { exists: () => boolean; attributes: (n: string) => string | undefined } }) =>
  w.find('img').exists() ? w.find('img').attributes('src') : null

describe('ViewerDialog', () => {
  test('fetches pages as blobs with bearer token and revokes object URLs on close', async () => {
    const f = fakeFetch([info(2), png(), png()])
    const w = await mountDialog(f)
    expect(f.calls.map((c) => c.url)).toEqual([
      `/view/v1/objects/${SHA}/info?variant=original`, `/view/v1/objects/${SHA}/pages/1.png?variant=original`,
    ])
    for (const c of f.calls) {
      expect(c.method).toBe('GET')
      expect(c.headers.get('Authorization')).toBe('Bearer tok')
    }
    expect(imgSrc(w)).toBe('blob:dxos-1')
    expect(w.text()).toContain('Trang 1 / 2')
    expect(w.find('img').attributes('alt')).toContain('Trang 1')

    await click(w, 'Trang sau')
    expect(f.calls[2]!.url).toBe(`/view/v1/objects/${SHA}/pages/2.png?variant=original`)
    expect(imgSrc(w)).toBe('blob:dxos-2')
    expect(revoked).toEqual(['blob:dxos-1'])        // mỗi lúc chỉ giữ ảnh của trang đang xem

    await click(w, 'Đóng')
    expect(w.emitted('close')).toHaveLength(1)
    expect(revoked).toEqual(['blob:dxos-1', 'blob:dxos-2'])
    w.unmount()
    expect(revoked).toEqual(['blob:dxos-1', 'blob:dxos-2']) // không thu hồi hai lần
    expect(created).toEqual(['blob:dxos-1', 'blob:dxos-2'])
  })

  test('unmounting without pressing Đóng (the parent removed it) also revokes the URL', async () => {
    const w = await mountDialog(fakeFetch([info(1), png()]))
    expect(created).toEqual(['blob:dxos-1'])
    w.unmount()
    expect(revoked).toEqual(['blob:dxos-1'])
  })

  test('Esc closes the dialog and releases the page', async () => {
    const w = await mountDialog(fakeFetch([info(1), png()]))
    await w.find('[role=dialog]').trigger('keydown.esc')
    expect(w.emitted('close')).toHaveLength(1)
    expect(revoked).toEqual(['blob:dxos-1'])
  })

  test('a page that arrives after the dialog was closed is never turned into an object URL', async () => {
    let release: (r: Response) => void = () => {}
    const late = new Promise<Response>((res) => { release = res })
    let n = 0
    const f = vi.fn(async () => {
      n += 1
      if (n === 1) return new Response(JSON.stringify({ pages: 3 }), { headers: { 'Content-Type': 'application/json' } })
      return late
    }) as unknown as typeof fetch
    const w = await mountWith(ViewerDialog, realClient(f), { sha256: SHA, variant: 'original', label: 'Tệp 1' })
    expect(created).toEqual([])
    w.unmount()
    release(new Response(PNG(), { headers: { 'Content-Type': 'image/png' } }))
    await flushPromises()
    expect(created).toEqual([])
  })

  test('the variant is passed through to the viewer', async () => {
    const f = fakeFetch([info(1), png()])
    const w = await mountDialog(f, { variant: 'redacted', label: 'Tệp 1 (bản che)' })
    expect(f.calls.map((c) => c.url)).toEqual([
      `/view/v1/objects/${SHA}/info?variant=redacted`, `/view/v1/objects/${SHA}/pages/1.png?variant=redacted`,
    ])
    expect(w.text()).toContain('bản che')
  })

  test('page error shows ProblemMessage', async () => {
    const f = fakeFetch([info(2), { status: 404, problem: { type: 'https://dxos.dev/problems/not-found', title: 'Not Found', status: 404 } }])
    const w = await mountDialog(f)
    expect(w.find('[role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    expect(w.find('img').exists()).toBe(false)
    expect(created).toEqual([])
    expect(f.calls).toHaveLength(2)                 // không tự thử lại
  })

  test('a failing info call is shown by ProblemMessage and no page is requested', async () => {
    const f = fakeFetch([{ status: 503, problem: { type: 'https://dxos.dev/problems/busy', title: 'Service Busy', status: 503 } }])
    const w = await mountDialog(f)
    expect(w.find('[role=alert]').text()).toMatch(/thử lại/)
    expect(f.calls).toHaveLength(1)
    expect(w.find('img').exists()).toBe(false)
  })

  test('a network failure is shown by ProblemMessage too', async () => {
    const f = (async () => { throw new TypeError('Failed to fetch') }) as unknown as typeof fetch
    const w = await mountWith(ViewerDialog, realClient(f), { sha256: SHA, variant: 'original', label: 'Tệp 1' })
    expect(w.find('[role=alert]').text()).toBe('Đã xảy ra lỗi, hãy thử lại')
  })

  test('an error on page 2 keeps the buttons usable but shows no stale image', async () => {
    const f = fakeFetch([info(3), png(), { status: 422, problem: { type: 'https://dxos.dev/problems/unreadable-document', title: 'x', status: 422 } }, png()])
    const w = await mountDialog(f)
    await click(w, 'Trang sau')
    expect(w.find('[role=alert]').exists()).toBe(true)
    expect(w.find('img').exists()).toBe(false)
    expect(revoked).toEqual(['blob:dxos-1'])
    await click(w, 'Trang trước')                   // thử lại bằng thao tác của người dùng, không tự động
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(imgSrc(w)).toBe('blob:dxos-2')
  })

  test('previous is off on page 1, next is off on the last page, and the page counter follows', async () => {
    const f = fakeFetch([info(2), png(), png()])
    const w = await mountDialog(f)
    const btn = (label: string) => w.findAll('button').find((b) => b.text() === label)!
    expect(btn('Trang trước').attributes('disabled')).toBeDefined()
    expect(btn('Trang sau').attributes('disabled')).toBeUndefined()
    await click(w, 'Trang sau')
    expect(btn('Trang sau').attributes('disabled')).toBeDefined()
    expect(btn('Trang trước').attributes('disabled')).toBeUndefined()
    expect(w.text()).toContain('Trang 2 / 2')
  })

  test('says in plain words that the watermark only deters', async () => {
    const w = await mountDialog(fakeFetch([info(1), png()]))
    expect(w.text()).toContain('chỉ để răn đe')
  })
})

describe('"Xem" in the attachment list of VanBanDetail', () => {
  const ID = { id: 'r1' }
  const clean = (over = {}) => att({ upload_id: 'u1', sha256: SHA, status: 'CLEAN', ...over })
  const buttons = (w: { findAll: (s: string) => { text: () => string }[] }) => w.findAll('button').map((b) => b.text())

  test('shown for a clean file when GET /view/v1/healthz answers 200', async () => {
    const c = detailClient({ attachments: [clean()], viewerAvailable: true })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(c.viewerAvailable).toHaveBeenCalledTimes(1)
    expect(buttons(w)).toContain('Xem')
  })

  test('hidden when healthz fails', async () => {
    const c = detailClient({ attachments: [clean()], viewerAvailable: false })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(buttons(w)).not.toContain('Xem')
    expect(w.find('[role=alert]').exists()).toBe(false)    // viewer vắng mặt (p8) không phải lỗi
  })

  test('hidden when the health call itself blows up', async () => {
    const c = detailClient({ attachments: [clean()], viewerAvailable: new Error('mạng') })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(buttons(w)).not.toContain('Xem')
    expect(w.find('[role=alert]').exists()).toBe(false)
  })

  test('not offered for a file that is not clean yet or has no hash', async () => {
    const c = detailClient({
      attachments: [clean({ upload_id: 'u2', status: 'STAGING', sha256: null }), clean({ upload_id: 'u3', status: 'INFECTED' })],
      viewerAvailable: true,
    })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(buttons(w).filter((b) => b.startsWith('Xem'))).toEqual([])
  })

  test('opens the viewer on the original and, when a redacted copy exists, also on the redacted one', async () => {
    const pii = { status: 'DONE' as const, findings: 3, counts: { CCCD: 1, PHONE: 1, BANK_ACCOUNT: 1 }, redacted: true }
    const c = detailClient({ attachments: [clean({ pii })], viewerAvailable: true,
      viewInfo: { pages: 1 }, viewPage: PNG() })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(buttons(w)).toEqual(expect.arrayContaining(['Xem', 'Xem bản che']))
    await click(w, 'Xem bản che')
    expect(c.viewInfo).toHaveBeenCalledWith(SHA, 'redacted')
    expect(c.viewPage).toHaveBeenCalledWith(SHA, 1, 'redacted')
    expect(w.find('img').attributes('src')).toBe('blob:dxos-1')
    await click(w, 'Đóng')
    expect(w.find('[role=dialog]').exists()).toBe(false)
    expect(revoked).toEqual(['blob:dxos-1'])
    await click(w, 'Xem')
    expect(c.viewInfo).toHaveBeenLastCalledWith(SHA, 'original')
  })

  test('a 404 from the viewer on the original (no right to read PII) shows ProblemMessage inside the dialog', async () => {
    const c = detailClient({ attachments: [clean()], viewerAvailable: true, viewInfo: problem('not-found') })
    const w = await mountWith(VanBanDetail, c, ID)
    await click(w, 'Xem')
    expect(w.find('[role=dialog] [role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
  })

  test('does not break the detail screen when the record cannot be loaded', async () => {
    const c = detailClient({ get: problem('not-found'), viewerAvailable: true })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.find('[role=alert]').exists()).toBe(true)
  })
})
