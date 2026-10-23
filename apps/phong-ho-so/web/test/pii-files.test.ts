// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
// Phát hiện dữ liệu cá nhân trong tệp đính kèm và tải bản che (Plan 04 Task 6, S1). Số liệu trong test đều hư cấu.
import { flushPromises } from '@vue/test-utils'
import type { AttachmentPii } from 'dxos-sdk-js'
import { problem } from 'dxos-sdk-js/testing'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { saveBlob } from '../src/download'
import VanBanDetail from '../src/views/VanBanDetail.vue'
import { att, click, detailClient, mountWith, rec } from './helpers'

vi.mock('../src/download', async (orig) => ({ ...(await orig<typeof import('../src/download')>()), saveBlob: vi.fn() }))

const SHA = 'd'.repeat(64)
const CV = ['app:phong-ho-so:chuyen_vien']
const GD = ['app:phong-ho-so:giam_doc']
const ID = { id: 'r1' }

beforeEach(() => { vi.mocked(saveBlob).mockClear() })
afterEach(() => { vi.useRealTimers() })

function pii(over: Partial<AttachmentPii> = {}): AttachmentPii {
  return { status: 'DONE', findings: 3, counts: { CCCD: 1, PHONE: 1, BANK_ACCOUNT: 1 }, redacted: true, ...over }
}
const pending = () => pii({ status: 'PENDING', findings: 0, counts: {}, redacted: false })
const file = (p: AttachmentPii | null, over = {}) => att({ upload_id: 'u1', sha256: SHA, pii: p, ...over })

describe('PII findings in the attachment list', () => {
  test("shows 'Đang dò dữ liệu cá nhân' while PENDING and polls until DONE", async () => {
    vi.useFakeTimers()
    const c = detailClient({ attachments: [[file(pending())], [file(pending())], [file(pii())]] })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).toContain('Đang dò dữ liệu cá nhân')
    expect(w.findAll('button').map((b) => b.text())).not.toContain('Tải bản che')
    expect(c.attachments).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(3100)
    expect(c.attachments).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('Đang dò dữ liệu cá nhân')
    await vi.advanceTimersByTimeAsync(3100)
    expect(c.attachments).toHaveBeenCalledTimes(3)
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
    expect(w.text()).not.toContain('Đang dò dữ liệu cá nhân')
    await vi.advanceTimersByTimeAsync(20_000)
    expect(c.attachments).toHaveBeenCalledTimes(3) // xong rồi thì thôi hỏi
    expect(c.get).toHaveBeenCalledTimes(1)         // thăm dò chỉ đọc danh sách tệp
    w.unmount()
  })

  test.each([[503], [429]])('a transient %i while polling is retried and nothing breaks', async (status) => {
    vi.useFakeTimers()
    const c = detailClient({ attachments: [[file(pending())], problem('unavailable', { status }), [file(pii())]] })
    const w = await mountWith(VanBanDetail, c, ID)
    await vi.advanceTimersByTimeAsync(3100)
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(w.text()).toContain('Đang dò dữ liệu cá nhân')   // danh sách cũ vẫn hiện, không trắng
    await vi.advanceTimersByTimeAsync(3100)
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân')
    w.unmount()
  })

  test('a definitive error while polling is shown by ProblemMessage and polling stops', async () => {
    vi.useFakeTimers()
    const c = detailClient({ attachments: [[file(pending())], problem('not-found')] })
    const w = await mountWith(VanBanDetail, c, ID)
    await vi.advanceTimersByTimeAsync(3100)
    expect(w.find('[role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    const n = c.attachments.mock.calls.length
    await vi.advanceTimersByTimeAsync(20_000)
    expect(c.attachments.mock.calls.length).toBe(n)
    w.unmount()
  })

  test('a scan that never finishes ends with an honest "unusually slow" note, not a spinner forever', async () => {
    vi.useFakeTimers()
    const c = detailClient({ attachments: [file(pending())] })
    const w = await mountWith(VanBanDetail, c, ID)
    await vi.advanceTimersByTimeAsync(310_000)
    expect(w.text()).toContain('Việc dò dữ liệu cá nhân lâu bất thường')
    const n = c.attachments.mock.calls.length
    await vi.advanceTimersByTimeAsync(60_000)
    expect(c.attachments.mock.calls.length).toBe(n)
    w.unmount()
  })

  test("DONE with 3 findings shows the counts and a 'Tải bản che' button that saves the redacted copy", async () => {
    const blob = new Blob(['%PDF-che'])
    const c = detailClient({
      get: rec({ is_owner: true, data: { so_hieu: '02/QĐ-SM' } }), attachments: [file(pii())], downloadObject: blob,
    })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
    expect(c.uploadStatus).not.toHaveBeenCalled()
    await click(w, 'Tải bản che')
    expect(c.downloadObject).toHaveBeenCalledTimes(1)
    expect(c.downloadObject).toHaveBeenCalledWith(SHA, 'redacted')
    expect(saveBlob).toHaveBeenCalledWith(blob, '02-QĐ-SM-che.pdf')
  })

  test('with several files the saved names are numbered', async () => {
    const c = detailClient({
      get: rec({ is_owner: true, data: { so_hieu: '02/QĐ-SM' } }),
      attachments: [file(pii(), { upload_id: 'u1', sha256: 'a'.repeat(64) }), file(pii(), { upload_id: 'u2', sha256: 'b'.repeat(64) })],
      downloadObject: new Blob(['x']),
    })
    const w = await mountWith(VanBanDetail, c, ID)
    await w.findAll('button').filter((b) => b.text() === 'Tải bản che')[1]!.trigger('click')
    await flushPromises()
    expect(c.downloadObject).toHaveBeenCalledWith('b'.repeat(64), 'redacted')
    expect(vi.mocked(saveBlob).mock.calls[0]![1]).toBe('02-QĐ-SM-che-2.pdf')
  })

  test('the original is requested with variant original and saved under the document name', async () => {
    const blob = new Blob(['%PDF'])
    const c = detailClient({
      get: rec({ is_owner: true, data: { so_hieu: '02/QĐ-SM' } }), attachments: [file(pii({ findings: 0, counts: {}, redacted: false }))],
      downloadObject: blob,
    })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).toContain('Không phát hiện dữ liệu cá nhân')
    await click(w, 'Tải bản gốc')
    expect(c.downloadObject).toHaveBeenCalledWith(SHA, 'original')
    expect(saveBlob).toHaveBeenCalledWith(blob, '02-QĐ-SM.pdf')
  })

  test('original download 404 shows ProblemMessage, never a blank, and is not retried', async () => {
    const c = detailClient({ attachments: [file(pii())], downloadObject: problem('not-found') })
    const w = await mountWith(VanBanDetail, c, ID, { roleStrings: CV })
    await click(w, 'Tải bản gốc')
    expect(c.downloadObject).toHaveBeenCalledTimes(1)
    expect(c.downloadObject).toHaveBeenCalledWith(SHA, 'original')
    expect(saveBlob).not.toHaveBeenCalled()
    const alert = w.find('.dx-files-section [role=alert]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân') // trang không trắng, danh sách vẫn đó
    expect(w.findAll('button').map((b) => b.text())).toContain('Tải bản che') // và còn đường tải bản che
  })

  test('a failed download clears on the next download and can be redacted instead', async () => {
    const blob = new Blob(['%PDF-che'])
    const c = detailClient({ attachments: [file(pii())], downloadObject: [problem('not-found'), blob] })
    const w = await mountWith(VanBanDetail, c, ID, { roleStrings: CV })
    await click(w, 'Tải bản gốc')
    expect(w.find('[role=alert]').exists()).toBe(true)
    await click(w, 'Tải bản che')
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(saveBlob).toHaveBeenCalledTimes(1)
  })

  test('buttons are locked while a download runs (no double request)', async () => {
    let release!: (b: Blob) => void
    const c = detailClient({ attachments: [file(pii())], downloadObject: () => new Promise<Blob>((r) => { release = r }) })
    const w = await mountWith(VanBanDetail, c, ID)
    await w.findAll('button').find((b) => b.text() === 'Tải bản che')!.trigger('click')
    expect(w.findAll('button').find((b) => b.text() === 'Tải bản che')!.attributes('disabled')).toBeDefined()
    await w.findAll('button').find((b) => b.text() === 'Tải bản che')!.trigger('click')
    expect(c.downloadObject).toHaveBeenCalledTimes(1)
    release(new Blob(['x']))
    await flushPromises()
    expect(w.findAll('button').find((b) => b.text() === 'Tải bản che')!.attributes('disabled')).toBeUndefined()
  })

  test('DONE with findings but no redacted copy explains who can open the file', async () => {
    const c = detailClient({ attachments: [file(pii({ redacted: false }))] })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).toContain('chỉ người có quyền xem dữ liệu cá nhân mới mở được tệp')
    expect(w.findAll('button').map((b) => b.text())).not.toContain('Tải bản che')
  })

  test.each([['TOO_LARGE', 'quá 200 trang'], ['FAILED', 'bị lỗi']] as const)('%s asks for a manual review', async (status, part) => {
    const c = detailClient({ attachments: [file(pii({ status, findings: 0, counts: {}, redacted: false }))] })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).toContain(part)
    expect(w.text()).toContain('cần rà thủ công')
  })

  test('a file in quarantine or without pii state shows no PII text and no PII download', async () => {
    const c = detailClient({ attachments: [att({ upload_id: 'u1', status: 'CLEAN', pii: null }), att({ upload_id: 'u2', status: 'INFECTED', sha256: null, reason: 'Eicar' })] })
    const w = await mountWith(VanBanDetail, c, ID)
    expect(w.text()).not.toContain('dữ liệu cá nhân')
    expect(w.findAll('button').map((b) => b.text())).not.toContain('Tải bản gốc')
    expect(c.downloadObject).not.toHaveBeenCalled()
  })

  test('a file that turns CLEAN after quarantine starts the PII poll when its scan is pending', async () => {
    vi.useFakeTimers()
    const c = detailClient({
      attachments: [[att({ upload_id: 'u1', status: 'STAGING', sha256: null })], [file(pending())], [file(pii())]],
      uploadStatus: { status: 'CLEAN', sha256: SHA },
    })
    const w = await mountWith(VanBanDetail, c, ID)
    await vi.advanceTimersByTimeAsync(2100)          // QuarantineStatus hỏi, thấy CLEAN, tải lại danh sách
    expect(w.text()).toContain('Đang dò dữ liệu cá nhân')
    await vi.advanceTimersByTimeAsync(3100)
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân')
    w.unmount()
  })
})

describe('PiiPanel in the document screen', () => {
  const running = () => rec({ wf_state: 'running', is_owner: false })

  test('PiiPanel lists per-file counts and blocks confirm text until scans are DONE', async () => {
    vi.useFakeTimers()
    const c = detailClient({
      get: running(),
      attachments: [[file(pending(), { upload_id: 'u1' })], [file(pii(), { upload_id: 'u1' })]],
    })
    const w = await mountWith(VanBanDetail, c, ID, { roleStrings: GD })
    const panel = () => w.find('.dx-pii')
    expect(panel().text()).toContain('Tệp 1: Đang dò dữ liệu cá nhân')
    expect(panel().text()).toContain('Hãy đợi dò xong rồi mới xác nhận đã rà')
    await vi.advanceTimersByTimeAsync(3100)
    expect(panel().find('.dx-pii-files').text()).toBe('Tệp 1: Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
    expect(panel().text()).not.toContain('Hãy đợi dò xong')
    w.unmount()
  })

  test('the confirm text is guidance only: the button works and the server has the last word', async () => {
    const c = detailClient({
      get: running(), attachments: [file(pending())],
      piiReview: problem('guard-failed', { reason: 'pii_scan_pending' }),
    })
    const w = await mountWith(VanBanDetail, c, ID, { roleStrings: GD })
    await click(w, 'Xác nhận đã rà dữ liệu cá nhân')
    expect(c.piiReview).toHaveBeenCalledTimes(1)
    expect(w.find('.dx-pii [role=alert]').text()).toMatch(/dò dữ liệu cá nhân/)
  })

  test('a user who cannot review sees the file state in the list but no review panel', async () => {
    const c = detailClient({ get: running(), attachments: [file(pii())] })
    const w = await mountWith(VanBanDetail, c, ID, { roleStrings: CV })
    expect(w.find('.dx-pii').exists()).toBe(false)
    expect(w.text()).toContain('Phát hiện 3 dữ liệu cá nhân (CCCD 1, SĐT 1, STK 1)')
  })
})
