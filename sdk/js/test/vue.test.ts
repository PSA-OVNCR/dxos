// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { CollectionView, FieldView } from '../src/types'
import { CORE_SLUGS, messageFor } from '../src/vue/messages'
import ProblemMessage from '../src/vue/ProblemMessage.vue'
import QuarantineStatus from '../src/vue/QuarantineStatus.vue'
import RecordForm from '../src/vue/RecordForm.vue'
import SealQr from '../src/vue/SealQr.vue'
import VerifyLink from '../src/vue/VerifyLink.vue'
import { apiErr, fakeClient, problem } from '../src/testing'

afterEach(() => { vi.useRealTimers() })

const ID = 'A'.repeat(26)

// ---- messages ------------------------------------------------------------------------------

describe('messageFor', () => {
  test('every core problem slug has a Vietnamese message', () => {
    expect(CORE_SLUGS.length).toBeGreaterThan(40)
    for (const slug of CORE_SLUGS) {
      const m = messageFor(apiErr(slug, { title: 'Server title' }))
      expect(m, slug).not.toBe('')
      expect(m, slug).not.toBe('Server title') // đã có câu riêng, không rơi về title của máy chủ
    }
  })

  test('guard reason drives the message', () => {
    expect(messageFor(apiErr('guard-failed', { reason: 'same_actor' }))).toMatch(/không được duyệt/)
    expect(messageFor(apiErr('guard-failed', { reason: 'attachments_not_clean' })))
      .toBe('Tệp đính kèm chưa được kiểm dịch xong hoặc không sạch')
    expect(messageFor(apiErr('guard-failed', { reason: 'pii_not_reviewed' })))
      .toBe('Văn thư hoặc giám đốc chưa xác nhận đã rà dữ liệu cá nhân')
    expect(messageFor(apiErr('guard-failed', { reason: 'same_actor' })))
      .toBe('Người tạo hoặc người đã duyệt bước trước không được duyệt bước này')
  })

  test('every guard reason of the contract table, and an unknown one, give a non-empty text', () => {
    const reasons = ['same_actor', 'role_not_allowed', 'not_assignee', 'field_missing', 'attachments_not_clean',
      'pii_not_reviewed', 'record_sealed', 'something_new']
    const seen = new Set(reasons.map((reason) => messageFor(apiErr('guard-failed', { reason }))))
    expect(seen.size).toBe(reasons.length)
    expect(messageFor(apiErr('guard-failed'))).not.toBe('')
  })

  test('version-conflict and task-gone ask for a reload', () => {
    expect(messageFor(apiErr('version-conflict'))).toBe('Dữ liệu đã thay đổi, hãy tải lại')
    expect(messageFor(problem('task-gone'))).toBe('Dữ liệu đã thay đổi, hãy tải lại')
  })

  test('schema errors list the server-provided Vietnamese reasons', () => {
    const m = messageFor(apiErr('schema', { errors: [{ path: '/trich_yeu', msg: 'bắt buộc' }, { path: '', msg: 'sai' }] }))
    expect(m).toContain('trich_yeu')
    expect(m).toContain('bắt buộc')
  })

  test('gateway (non-JSON) errors map by status', () => {
    expect(messageFor(apiErr('http-401'))).toMatch(/đăng nhập/)
    expect(messageFor(apiErr('http-413'))).toMatch(/quá lớn/)
    expect(messageFor(apiErr('http-429'))).toMatch(/thử lại/)
  })

  test('unknown slug falls back to the server title, never to an empty string', () => {
    expect(messageFor(apiErr('brand-new-problem', { title: 'Máy chủ nói vậy' }))).toBe('Máy chủ nói vậy')
    expect(messageFor(apiErr('brand-new-problem', { title: '   ' })).trim()).not.toBe('')
    expect(messageFor(apiErr('brand-new-problem', { title: '' })).trim()).not.toBe('')
  })

  test('anything that is not an ApiError gets a generic Vietnamese message', () => {
    for (const e of [new Error('boom'), 'x', null, undefined, 42, {}]) {
      const m = messageFor(e)
      expect(m.trim()).not.toBe('')
      expect(m).not.toContain('boom')
    }
  })
})

describe('ProblemMessage', () => {
  test('is an alert showing the message', () => {
    const w = mount(ProblemMessage, { props: { error: apiErr('task-gone') } })
    expect(w.find('[role="alert"]').text()).toBe('Dữ liệu đã thay đổi, hãy tải lại')
  })
  test('renders nothing without an error', () => {
    const w = mount(ProblemMessage, { props: { error: null } })
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })
  test('shows server text as text, never as markup', () => {
    const w = mount(ProblemMessage, { props: { error: apiErr('brand-new', { title: '<b>x</b>' }) } })
    expect(w.find('b').exists()).toBe(false)
    expect(w.text()).toBe('<b>x</b>')
  })
})

// ---- SealQr / VerifyLink -------------------------------------------------------------------

describe('SealQr', () => {
  test('refuses a foreign origin', () => {
    const w = mount(SealQr, { props: { verifyUrl: 'https://evil.example/apps/verify/#' + ID } })
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toMatch(/không hợp lệ/)
  })

  test('renders an SVG data URL for a same-origin verify link', async () => {
    const w = mount(SealQr, { props: { verifyUrl: location.origin + '/apps/verify/#' + ID } })
    await flushPromises()
    const src = w.find('img').attributes('src')!
    expect(src).toMatch(/^data:image\/svg\+xml;charset=utf-8,/)
    expect(decodeURIComponent(src.split(',')[1]!)).toContain('<svg')
    expect(w.find('img').attributes('alt')).toBeTruthy()
  })

  test.each([
    ['wrong path', () => location.origin + '/apps/other/#' + ID],
    ['path prefix trick', () => location.origin + '/apps/verify/x/#' + ID],
    ['no trailing slash', () => location.origin + '/apps/verify#' + ID],
    ['lowercase fragment', () => location.origin + '/apps/verify/#' + 'a'.repeat(26)],
    ['short fragment', () => location.origin + '/apps/verify/#' + 'A'.repeat(25)],
    ['long fragment', () => location.origin + '/apps/verify/#' + 'A'.repeat(27)],
    ['digit 1 is not base32', () => location.origin + '/apps/verify/#' + '1'.repeat(26)],
    ['no fragment', () => location.origin + '/apps/verify/'],
    ['query string', () => location.origin + '/apps/verify/?next=x#' + ID],
    ['credentials', () => location.origin.replace('://', '://u:p@') + '/apps/verify/#' + ID],
    ['javascript scheme', () => 'javascript:alert(1)'],
    ['relative', () => '/apps/verify/#' + ID],
    ['empty', () => ''],
  ])('refuses %s', async (_n, url) => {
    const w = mount(SealQr, { props: { verifyUrl: url() } })
    await flushPromises()
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toMatch(/Liên kết đối soát không hợp lệ/)
  })

  test('re-validates when the URL changes', async () => {
    const w = mount(SealQr, { props: { verifyUrl: location.origin + '/apps/verify/#' + ID } })
    await flushPromises()
    expect(w.find('img').exists()).toBe(true)
    await w.setProps({ verifyUrl: 'https://evil.example/apps/verify/#' + ID })
    await flushPromises()
    expect(w.find('img').exists()).toBe(false)
  })

  test('size drives the image box', async () => {
    const w = mount(SealQr, { props: { verifyUrl: location.origin + '/apps/verify/#' + ID, size: 128 } })
    await flushPromises()
    expect(w.find('img').attributes('width')).toBe('128')
  })
})

describe('VerifyLink', () => {
  test('links to a valid same-origin verify page', () => {
    const url = location.origin + '/apps/verify/#' + ID
    const w = mount(VerifyLink, { props: { verifyUrl: url } })
    expect(w.find('a').attributes('href')).toBe(url)
    expect(w.find('a').text()).toBe('Mở trang đối soát')
  })
  test('refuses a foreign origin and renders no anchor', () => {
    const w = mount(VerifyLink, { props: { verifyUrl: 'https://evil.example/apps/verify/#' + ID } })
    expect(w.find('a').exists()).toBe(false)
    expect(w.text()).toMatch(/Liên kết đối soát không hợp lệ/)
  })
  test('refuses a javascript: URL', () => {
    const w = mount(VerifyLink, { props: { verifyUrl: 'javascript:alert(1)' } })
    expect(w.find('a').exists()).toBe(false)
  })
})

// ---- QuarantineStatus ----------------------------------------------------------------------

describe('QuarantineStatus', () => {
  test('polls until CLEAN then stops', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: [{ status: 'STAGING' }, { status: 'CLEAN', sha256: 'a'.repeat(64) }] })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    expect(w.text()).toMatch(/Đang kiểm dịch…/)
    await vi.advanceTimersByTimeAsync(50)
    expect(w.text()).toMatch(/Sạch/)
    expect(c.uploadStatus).toHaveBeenCalledTimes(2)
    expect(c.uploadStatus).toHaveBeenCalledWith('u')
    await vi.advanceTimersByTimeAsync(200)
    expect(c.uploadStatus).toHaveBeenCalledTimes(2)
    expect(w.emitted('settled')).toEqual([[{ status: 'CLEAN', sha256: 'a'.repeat(64) }]])
  })

  test('INFECTED is labelled as quarantined', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: { status: 'INFECTED', reason: 'Eicar' } })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(20)
    expect(w.text()).toContain('Nhiễm mã độc — đã cách ly')
    expect(w.emitted('settled')).toHaveLength(1)
  })

  test.each([
    ['EMPTY', 'tệp rỗng'], ['TOO_LARGE', 'tệp quá lớn'], ['BAD_MAGIC', 'không phải PDF'],
    ['ENCRYPTED', 'PDF có mật khẩu'], ['PARSE_ERROR', 'PDF hỏng'],
    ['NO_TEXT_LAYER', 'PDF không có lớp chữ (bản scan)'], ['SOMETHING_NEW', 'SOMETHING_NEW'],
  ])('REJECTED %s explains why', async (reason, text) => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: { status: 'REJECTED', reason } })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(20)
    expect(w.text()).toContain(`Bị từ chối: ${text}`)
  })

  test('gives up after timeoutMs with the scanner-may-be-stopped message', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: { status: 'STAGING' } })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10, timeoutMs: 100 } })
    await vi.advanceTimersByTimeAsync(150)
    expect(w.text()).toContain('Kiểm dịch lâu bất thường — máy quét có thể đang dừng')
    const n = c.uploadStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(500)
    expect(c.uploadStatus.mock.calls.length).toBe(n)
    expect(w.emitted('settled')).toBeUndefined()
  })

  test('an API error stops polling and is shown', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: problem('not-found') })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(100)
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(c.uploadStatus).toHaveBeenCalledTimes(1)
  })

  test.each([[503], [500], [429], [408]])('a transient %i is retried until CLEAN', async (status) => {
    vi.useFakeTimers()
    const c = fakeClient({
      uploadStatus: [problem('unavailable', { status }), problem('unavailable', { status }),
        { status: 'CLEAN', sha256: 'c'.repeat(64) }],
    })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(10)
    expect(w.find('[role="alert"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(60)
    expect(w.text()).toMatch(/Sạch/)
    expect(c.uploadStatus).toHaveBeenCalledTimes(3)
    expect(w.emitted('settled')).toHaveLength(1)
  })

  test.each([[400], [401], [403], [404], [410]])('a definitive %i stops polling and is shown', async (status) => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: problem('forbidden', { status }) })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(100)
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(c.uploadStatus).toHaveBeenCalledTimes(1)
  })

  test('keeps retrying a transient error only until the deadline', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: problem('unavailable', { status: 503 }) })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10, timeoutMs: 100 } })
    await vi.advanceTimersByTimeAsync(150)
    expect(w.text()).toContain('Kiểm dịch lâu bất thường')
    expect(c.uploadStatus.mock.calls.length).toBeGreaterThan(3)
    const n = c.uploadStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(500)
    expect(c.uploadStatus.mock.calls.length).toBe(n)
  })

  test('a network failure is retried', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: [new TypeError('Failed to fetch'), { status: 'CLEAN', sha256: 'b'.repeat(64) }] })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(50)
    expect(w.text()).toMatch(/Sạch/)
  })

  test('stops polling when unmounted', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: { status: 'STAGING' } })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(25)
    w.unmount()
    const n = c.uploadStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(200)
    expect(c.uploadStatus.mock.calls.length).toBe(n)
  })

  test('restarts for a new uploadId', async () => {
    vi.useFakeTimers()
    const c = fakeClient({ uploadStatus: (id: string) => (id === 'u1' ? { status: 'CLEAN' as const, sha256: 'a'.repeat(64) } : { status: 'STAGING' as const }) })
    const w = mount(QuarantineStatus, { props: { client: c, uploadId: 'u1', intervalMs: 10 } })
    await vi.advanceTimersByTimeAsync(20)
    expect(w.text()).toMatch(/Sạch/)
    await w.setProps({ uploadId: 'u2' })
    await vi.advanceTimersByTimeAsync(20)
    expect(w.text()).toMatch(/Đang kiểm dịch…/)
    expect(c.uploadStatus).toHaveBeenLastCalledWith('u2')
  })
})

// ---- RecordForm ----------------------------------------------------------------------------

function f(type: FieldView['type'], over: Partial<FieldView> = {}): FieldView {
  return { type, required: false, public: false, pii: null, format: null, label: null, ...over }
}

const VIEW: CollectionView = {
  fields: {
    so_hieu: f('sequence'),
    trich_yeu: f('string', { required: true, label: 'Trích yếu' }),
    loai_van_ban: f('string'),
    ngay: f('date', { label: 'Ngày ban hành' }),
    so_trang: f('integer'),
    mat: f('boolean', { label: 'Tài liệu mật' }),
    cccd: f('string', { pii: 'CCCD', label: 'Số CCCD' }),
  },
  attachments: null,
  access: { read: [], create: [], update: [] },
}

describe('RecordForm', () => {
  test('edit mode emits only changed fields (never masked PII)', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', cccd: '07********34' } } })
    await w.find('input[name="trich_yeu"]').setValue('b')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ trich_yeu: 'b' })
  })

  test('edit mode with no change emits an empty patch', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', cccd: '07********34' } } })
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({})
  })

  test('edit mode sends a PII field only when the user typed a new value', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', cccd: '07********34' } } })
    await w.find('input[name="cccd"]').setValue('079123456789')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ cccd: '079123456789' })
  })

  test('editing a value back to the original is not a change', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a' } } })
    await w.find('input[name="trich_yeu"]').setValue('b')
    await w.find('input[name="trich_yeu"]').setValue('a')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({})
  })

  test('edit mode deletes a cleared optional field with null', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', loai_van_ban: 'QĐ' } } })
    await w.find('input[name="loai_van_ban"]').setValue('')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ loai_van_ban: null })
  })

  test('create mode emits typed values and skips empty ones', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} } })
    await w.find('input[name="trich_yeu"]').setValue('Quyết định')
    await w.find('input[name="ngay"]').setValue('2026-10-22')
    await w.find('input[name="so_trang"]').setValue('12')
    await w.find('input[name="mat"]').setValue(true)
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ trich_yeu: 'Quyết định', ngay: '2026-10-22', so_trang: 12, mat: true })
  })

  test('create mode does not send an untouched optional boolean', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} } })
    await w.find('input[name="trich_yeu"]').setValue('x')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ trich_yeu: 'x' })
  })

  test('renders one input per field type, skips sequence, marks required', () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {}, requiredExtra: ['loai_van_ban'] } })
    expect(w.find('input[name="so_hieu"]').exists()).toBe(false)
    expect(w.find('input[name="loai_van_ban"]').attributes('required')).toBeDefined()
    expect(w.find('input[name="trich_yeu"]').attributes('required')).toBeDefined()
    expect(w.find('input[name="ngay"]').attributes('required')).toBeUndefined()
    expect(w.find('input[name="trich_yeu"]').attributes('type')).toBe('text')
    expect(w.find('input[name="ngay"]').attributes('type')).toBe('date')
    expect(w.find('input[name="so_trang"]').attributes('type')).toBe('number')
    expect(w.find('input[name="so_trang"]').attributes('step')).toBe('1')
    expect(w.find('input[name="mat"]').attributes('type')).toBe('checkbox')
  })

  test('every input has a label (label ?? field name) and PII is annotated', () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} } })
    for (const input of w.findAll('input')) {
      const id = input.attributes('id')!
      expect(id).toBeTruthy()
      expect(w.find(`label[for="${id}"]`).exists(), input.attributes('name')).toBe(true)
    }
    const labelOf = (name: string) => w.find(`label[for="${w.find(`input[name="${name}"]`).attributes('id')}"]`).text()
    expect(labelOf('trich_yeu')).toContain('Trích yếu')
    expect(labelOf('loai_van_ban')).toContain('loai_van_ban')
    expect(w.text()).toContain('dữ liệu cá nhân')
    expect(w.findAll('small').filter((s) => s.text().includes('dữ liệu cá nhân'))).toHaveLength(1)
  })

  test('a non-integer is not coerced: the form refuses to submit', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} }, attachTo: document.body })
    await w.find('input[name="trich_yeu"]').setValue('x')
    await w.find('input[name="so_trang"]').setValue('1.5')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')).toBeUndefined()
    w.unmount()
  })

  test('an integer too large for a JS number is refused, not rounded', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} }, attachTo: document.body })
    await w.find('input[name="trich_yeu"]').setValue('x')
    await w.find('input[name="so_trang"]').setValue('9007199254740993')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')).toBeUndefined()
    w.unmount()
  })

  test('required field left empty blocks submit', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'create', modelValue: {} }, attachTo: document.body })
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')).toBeUndefined()
    w.unmount()
  })

  test('emits update:modelValue with the merged data as the user types', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', cccd: '07********34' } } })
    await w.find('input[name="trich_yeu"]').setValue('b')
    expect(w.emitted('update:modelValue')!.at(-1)![0]).toEqual({ trich_yeu: 'b', cccd: '07********34' })
  })

  test('works under v-model: echoing the emitted value does not lose the change set', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', cccd: '07********34' } } })
    await w.find('input[name="trich_yeu"]').setValue('b')
    await w.setProps({ modelValue: w.emitted('update:modelValue')!.at(-1)![0] as Record<string, unknown> })
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({ trich_yeu: 'b' })
  })

  test('a different record from the parent resets the baseline', async () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a' } } })
    await w.find('input[name="trich_yeu"]').setValue('b')
    await w.setProps({ modelValue: { trich_yeu: 'z', loai_van_ban: 'QĐ' } })
    expect((w.find('input[name="trich_yeu"]').element as HTMLInputElement).value).toBe('z')
    await w.find('form').trigger('submit')
    expect(w.emitted('submit')![0]![0]).toEqual({})
  })

  test('shows existing values in the inputs', () => {
    const w = mount(RecordForm, { props: { view: VIEW, mode: 'edit', modelValue: { trich_yeu: 'a', so_trang: 3, mat: true } } })
    expect((w.find('input[name="trich_yeu"]').element as HTMLInputElement).value).toBe('a')
    expect((w.find('input[name="so_trang"]').element as HTMLInputElement).value).toBe('3')
    expect((w.find('input[name="mat"]').element as HTMLInputElement).checked).toBe(true)
  })
})
