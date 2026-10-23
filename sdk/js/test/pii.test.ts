// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
// Hiển thị phát hiện dữ liệu cá nhân trong tệp đính kèm (Plan 04 Task 6, S1): PiiFileStatus, usePoll, PiiPanel.
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import type { AttachmentPii, ManifestView } from '../src/types'
import { att, apiErr, fakeClient, problem } from '../src/testing'
import { messageFor } from '../src/vue/messages'
import PiiFileStatus from '../src/vue/PiiFileStatus.vue'
import PiiPanel from '../src/vue/PiiPanel.vue'
import { SESSION_KEY } from '../src/vue/session'
import { usePoll } from '../src/vue/usePoll'

afterEach(() => { vi.useRealTimers() })

function pii(over: Partial<AttachmentPii> = {}): AttachmentPii {
  return { status: 'DONE', findings: 3, counts: { CCCD: 1, PHONE: 1, BANK_ACCOUNT: 1 }, redacted: true, ...over }
}

describe('guard reason pii_scan_pending', () => {
  test('has its own Vietnamese text', () => {
    const t = messageFor(apiErr('guard-failed', { reason: 'pii_scan_pending' }))
    expect(t).toMatch(/dò dữ liệu cá nhân/)
    expect(t).not.toBe(messageFor(apiErr('guard-failed', { reason: 'pii_not_reviewed' })))
    expect(t).not.toBe(messageFor(apiErr('guard-failed')))
  })
})

describe('PiiFileStatus', () => {
  const show = (p: AttachmentPii | null, props: Record<string, unknown> = {}) =>
    mount(PiiFileStatus, { props: { item: att({ pii: p }), ...props } })
  const buttons = (w: ReturnType<typeof show>) => w.findAll('button').map((b) => b.text())

  test('renders nothing when the collection does not detect (pii null)', () => {
    const w = show(null)
    expect(w.text()).toBe('')
    expect(w.findAll('button')).toHaveLength(0)
  })

  test('PENDING says the file is being scanned and offers no download', () => {
    const w = show(pii({ status: 'PENDING', findings: 0, counts: {}, redacted: false }))
    expect(w.text()).toContain('Đang dò dữ liệu cá nhân')
    expect(w.find('[role=status]').attributes('data-pii-status')).toBe('PENDING')
    expect(buttons(w)).toEqual([])
  })

  test('PENDING that polling gave up on says it is unusually slow', () => {
    const w = show(pii({ status: 'PENDING', findings: 0, counts: {}, redacted: false }), { timedOut: true })
    expect(w.text()).toContain('Việc dò dữ liệu cá nhân lâu bất thường')
  })

  test('DONE with 3 findings lists the counts per type and offers both downloads', async () => {
    const w = show(pii())
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
    expect(buttons(w)).toEqual(['Tải bản che', 'Tải bản gốc'])
    await w.findAll('button')[0]!.trigger('click')
    await w.findAll('button')[1]!.trigger('click')
    expect(w.emitted('download')).toEqual([['redacted'], ['original']])
  })

  test('counts come in a fixed order and unknown types keep their code', () => {
    const w = show(pii({ findings: 4, counts: { PHONE: 2, EMAIL: 1, CCCD: 1 } }))
    expect(w.text()).toContain('Phát hiện 4 dữ liệu cá nhân (CCCD 1, SĐT 2, EMAIL 1)')
  })

  test('findings without a breakdown (older server) still read well', () => {
    const w = show({ status: 'DONE', findings: 2, redacted: true } as AttachmentPii)
    expect(w.text()).toContain('Phát hiện 2 dữ liệu cá nhân')
    expect(w.text()).not.toContain('(')
  })

  test('DONE with no findings says so and only the original is offered', () => {
    const w = show(pii({ findings: 0, counts: {}, redacted: false }))
    expect(w.text()).toContain('Không phát hiện dữ liệu cá nhân')
    expect(buttons(w)).toEqual(['Tải bản gốc'])
  })

  test('DONE with findings but no redacted copy explains who can open the file', () => {
    const w = show(pii({ redacted: false }))
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
    expect(w.text()).toContain('Chưa có bản che')
    expect(w.text()).toContain('chỉ người có quyền xem dữ liệu cá nhân mới mở được tệp')
    expect(buttons(w)).toEqual(['Tải bản gốc'])
  })

  test('the redacted copy is explained as a picture-only PDF that does not replace review', () => {
    const w = show(pii())
    expect(w.text()).toContain('Bản gốc chỉ mở được với người có quyền xem dữ liệu cá nhân')
    expect(w.text()).toContain('Bản che là PDF dạng ảnh')
  })

  test.each([
    ['TOO_LARGE', 'quá 200 trang'],
    ['FAILED', 'bị lỗi'],
  ] as const)('%s says manual review is required', (status, part) => {
    const w = show(pii({ status, findings: 0, counts: {}, redacted: false }))
    expect(w.text()).toContain(part)
    expect(w.text()).toContain('cần rà thủ công')
    expect(buttons(w)).toEqual(['Tải bản gốc'])
  })

  test('a file without a hash (not CLEAN) offers nothing to download', () => {
    const w = mount(PiiFileStatus, { props: { item: att({ sha256: null, pii: pii() }) } })
    expect(buttons(w as never)).toEqual([])
  })

  test('busy disables the buttons', () => {
    const w = show(pii(), { busy: true })
    expect(w.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })
})

describe('usePoll', () => {
  function host(opts: { tick: () => Promise<void>, intervalMs?: number, timeoutMs?: number }) {
    const active = ref(true)
    let api!: ReturnType<typeof usePoll>
    const C = defineComponent({
      setup() {
        api = usePoll({ active: () => active.value, ...opts })
        return () => h('p', { id: 'x' }, api.timedOut.value ? 'timeout' : api.failure.value ? 'failed' : 'ok')
      },
    })
    const w = mount(C)
    return { w, active, api: () => api }
  }

  test('ticks every interval while active and stops once inactive', async () => {
    vi.useFakeTimers()
    const tick = vi.fn(async () => {})
    const { active } = host({ tick, intervalMs: 10 })
    await vi.advanceTimersByTimeAsync(35)
    expect(tick).toHaveBeenCalledTimes(3)
    active.value = false
    await vi.advanceTimersByTimeAsync(100)
    expect(tick).toHaveBeenCalledTimes(3)
  })

  test.each([[503], [500], [429], [408]])('a transient %i is retried', async (status) => {
    vi.useFakeTimers()
    const tick = vi.fn().mockRejectedValueOnce(problem('unavailable', { status })).mockResolvedValue(undefined)
    const { api } = host({ tick, intervalMs: 10 })
    await vi.advanceTimersByTimeAsync(35)
    expect(tick.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(api().failure.value).toBeNull()
  })

  test('a network failure (not an ApiError) is retried', async () => {
    vi.useFakeTimers()
    const tick = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValue(undefined)
    const { api } = host({ tick, intervalMs: 10 })
    await vi.advanceTimersByTimeAsync(35)
    expect(tick.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(api().failure.value).toBeNull()
  })

  test.each([[400], [401], [403], [404]])('a definitive %i stops polling and is exposed', async (status) => {
    vi.useFakeTimers()
    const tick = vi.fn().mockRejectedValue(problem('not-found', { status }))
    const { api } = host({ tick, intervalMs: 10 })
    await vi.advanceTimersByTimeAsync(100)
    expect(tick).toHaveBeenCalledTimes(1)
    expect(api().failure.value?.status).toBe(status)
  })

  test('gives up at timeoutMs', async () => {
    vi.useFakeTimers()
    const tick = vi.fn(async () => {})
    const { api, w } = host({ tick, intervalMs: 10, timeoutMs: 55 })
    await vi.advanceTimersByTimeAsync(200)
    expect(api().timedOut.value).toBe(true)
    expect(w.text()).toBe('timeout')
    const n = tick.mock.calls.length
    await vi.advanceTimersByTimeAsync(200)
    expect(tick.mock.calls.length).toBe(n)
  })

  test('restart clears a timeout or failure and polls again', async () => {
    vi.useFakeTimers()
    const tick = vi.fn(async () => {})
    const { api } = host({ tick, intervalMs: 10, timeoutMs: 35 })
    await vi.advanceTimersByTimeAsync(100)
    expect(api().timedOut.value).toBe(true)
    const n = tick.mock.calls.length
    api().restart()
    expect(api().timedOut.value).toBe(false)
    await vi.advanceTimersByTimeAsync(25)
    expect(tick.mock.calls.length).toBeGreaterThan(n)
  })

  test('stops when the component unmounts', async () => {
    vi.useFakeTimers()
    const tick = vi.fn(async () => {})
    const { w } = host({ tick, intervalMs: 10 })
    await vi.advanceTimersByTimeAsync(25)
    w.unmount()
    const n = tick.mock.calls.length
    await vi.advanceTimersByTimeAsync(100)
    expect(tick.mock.calls.length).toBe(n)
  })
})

describe('PiiPanel (per-file findings)', () => {
  const VIEW = {
    app: { id: 'a', version: '1', name: 'A' }, roles: ['rev'], collections: {},
    workflow: { tasks: { ban_hanh: { role: 'rev', guards: ['pii_reviewed'] } }, decisions: {} },
    policies: { pii: { reveal_roles: ['rev'], erase_roles: [] }, seal: { public_fields: [], revoke_roles: [] },
      verify: { public: true, require_file: true } },
  } as unknown as ManifestView
  const COLLECTION = { fields: {}, access: { read: [], create: [], update: [] } }
  const RECORD = { id: 'r1', app_id: 'a', collection: 'c', data: {}, is_owner: true, version: 1, seal_state: 'NONE',
    wf_state: 'running', created_at: 'z', updated_at: 'z' }

  function mountPanel(files: unknown, roles = ['rev']) {
    const session = { client: fakeClient(), roles: ref(roles), view: ref(VIEW) }
    return mount(PiiPanel, {
      props: { app: 'a', col: 'c', record: RECORD as never, collection: COLLECTION as never, files: files as never },
      global: { provide: { [SESSION_KEY as symbol]: session } },
    })
  }

  test('lists per-file counts', () => {
    const w = mountPanel([att({ upload_id: 'u1', pii: pii() }), att({ upload_id: 'u2', pii: pii({ findings: 0, counts: {} }) })])
    const items = w.findAll('.dx-pii-files li').map((li) => li.text())
    expect(items).toEqual([
      'Tệp 1: Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)',
      'Tệp 2: Không phát hiện dữ liệu cá nhân',
    ])
  })

  test('files without pii state are not listed and no list shows without files', () => {
    expect(mountPanel([att({ pii: null })]).find('.dx-pii-files').exists()).toBe(false)
    expect(mountPanel(undefined).find('.dx-pii-files').exists()).toBe(false)
  })

  test('while a scan is PENDING it tells the reviewer to wait; the button stays (the server decides)', () => {
    const w = mountPanel([att({ pii: pii({ status: 'PENDING', findings: 0, counts: {}, redacted: false }) })])
    expect(w.text()).toContain('Còn tệp đang được dò dữ liệu cá nhân')
    expect(w.text()).toContain('đợi dò xong rồi mới xác nhận')
    const confirm = w.findAll('button').find((b) => b.text() === 'Xác nhận đã rà dữ liệu cá nhân')!
    expect(confirm.attributes('disabled')).toBeUndefined()
  })

  test.each(['TOO_LARGE', 'FAILED'] as const)('a %s scan asks for a manual review', (status) => {
    const w = mountPanel([att({ pii: pii({ status, findings: 0, counts: {}, redacted: false }) })])
    expect(w.text()).toContain('chưa dò được')
    expect(w.text()).toContain('rà thủ công')
  })

  test('no hint when every scan is DONE', () => {
    const w = mountPanel([att({ pii: pii() })])
    expect(w.text()).not.toContain('đợi dò xong')
    expect(w.text()).not.toContain('chưa dò được')
  })

  test('a reader without the reveal role gets no review hint', async () => {
    const w = mountPanel([att({ pii: pii({ status: 'PENDING', findings: 0, counts: {}, redacted: false }) })], ['other'])
    await flushPromises()
    expect(w.find('.dx-pii-files').exists()).toBe(false)
    expect(w.text()).not.toContain('đợi dò xong')
  })
})
