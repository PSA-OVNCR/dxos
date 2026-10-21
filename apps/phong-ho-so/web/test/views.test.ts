// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils'
import { fakeClient, problem } from 'dxos-sdk-js/testing'
import { afterEach, describe, expect, test, vi } from 'vitest'
import VanBanDetail from '../src/views/VanBanDetail.vue'
import VanBanList from '../src/views/VanBanList.vue'
import VanBanNew from '../src/views/VanBanNew.vue'
import { att, click, detailClient, fill, mountWith, pickFile, rec } from './helpers'

afterEach(() => { vi.useRealTimers() })

const MB = 1024 * 1024
const pdf = (name: string, bytes = 1024) => new File([new Uint8Array(bytes)], name, { type: 'application/pdf' })

// ---- danh sách -----------------------------------------------------------------------------

describe('VanBanList', () => {
  const rows = [
    rec({ id: 'r1', data: { so_hieu: '01/QĐ-SM', loai_van_ban: 'Quyết định', trich_yeu: 'Bổ nhiệm' }, seal_state: 'SEALED',
      updated_at: '2026-10-22T00:00:00Z' }),
    rec({ id: 'r2', data: { trich_yeu: 'Nháp thư' }, updated_at: '2026-10-21T17:30:00Z' }),
  ]

  test('lists records with manifest labels, status and Vietnam time', async () => {
    const c = fakeClient({ listAll: rows })
    const w = await mountWith(VanBanList, c)
    expect(c.listAll).toHaveBeenCalledWith('phong-ho-so', 'van_ban')
    const heads = w.findAll('th').map((x) => x.text())
    expect(heads).toEqual(['Số, ký hiệu', 'Tên loại văn bản', 'Trích yếu nội dung', 'Trạng thái', 'Cập nhật (giờ VN)'])
    const cells = w.findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()))
    expect(cells).toEqual([
      ['01/QĐ-SM', 'Quyết định', 'Bổ nhiệm', 'Đã ban hành', '07:00 22/10/2026'],
      ['—', '—', 'Nháp thư', 'Nháp', '00:30 22/10/2026'],
    ])
    expect(w.find('tbody a').attributes('href')).toBe('/van-ban/r1')
  })

  test('"Văn bản mới" is shown to chuyen_vien only (convenience, the core decides)', async () => {
    const yes = await mountWith(VanBanList, fakeClient({ listAll: [] }), {}, { roleStrings: ['app:phong-ho-so:chuyen_vien'] })
    expect(yes.text()).toContain('Văn bản mới')
    expect(yes.find('a.dx-button').attributes('href')).toBe('/van-ban/moi')
    const no = await mountWith(VanBanList, fakeClient({ listAll: [] }), {}, { roleStrings: ['app:phong-ho-so:truong_phong'] })
    expect(no.text()).not.toContain('Văn bản mới')
  })

  test('empty list and server error', async () => {
    const empty = await mountWith(VanBanList, fakeClient({ listAll: [] }))
    expect(empty.text()).toContain('Chưa có văn bản nào')
    const bad = await mountWith(VanBanList, fakeClient({ listAll: problem('forbidden') }))
    expect(bad.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
    expect(bad.find('table').exists()).toBe(false)
  })
})

// ---- tạo mới -------------------------------------------------------------------------------

describe('VanBanNew', () => {
  test('requires loai_van_ban in the UI and posts the data unwrapped, then opens the record', async () => {
    const c = fakeClient({ create: rec({ id: 'r1' }) })
    const w = await mountWith(VanBanNew, c)
    expect(w.find('input[name="loai_van_ban"]').attributes('required')).toBeDefined()
    expect(w.find('input[name="so_hieu"]').exists()).toBe(false) // số do lõi cấp
    await fill(w, { trich_yeu: 'Quyết định', loai_van_ban: 'Quyết định', chuc_vu_nguoi_ky: 'Giám đốc' })
    expect(c.create).toHaveBeenCalledTimes(1)
    expect(c.create).toHaveBeenCalledWith('phong-ho-so', 'van_ban', {
      trich_yeu: 'Quyết định', loai_van_ban: 'Quyết định', chuc_vu_nguoi_ky: 'Giám đốc',
    })
    expect(w.vm.$route.fullPath).toBe('/van-ban/r1')
  })

  test('does not submit while loai_van_ban is empty', async () => {
    const c = fakeClient({ create: rec() })
    const w = await mountWith(VanBanNew, c)
    await fill(w, { trich_yeu: 'Chỉ có trích yếu' })
    expect(c.create).not.toHaveBeenCalled()
  })

  test('shows the server problem and never retries the write', async () => {
    const c = fakeClient({ create: problem('schema', { errors: [{ path: '/trich_yeu', msg: 'quá dài' }] }) })
    const w = await mountWith(VanBanNew, c)
    await fill(w, { trich_yeu: 'x', loai_van_ban: 'y' })
    expect(w.find('[role=alert]').text()).toBe('Dữ liệu chưa hợp lệ: trich_yeu: quá dài')
    expect(c.create).toHaveBeenCalledTimes(1)
    expect(w.vm.$route.fullPath).toBe('/')
  })
})

// ---- chi tiết ------------------------------------------------------------------------------

describe('VanBanDetail', () => {
  test('shows fields by manifest label and PII exactly as the server returned it', async () => {
    const c = detailClient({
      get: rec({ data: { so_hieu: '02/QĐ-SM', trich_yeu: 'Bổ nhiệm', nguoi_lien_he_cccd: '07********34' }, wf_state: 'running' }),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(c.get).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1')
    const dl = w.find('dl').text()
    expect(dl).toContain('Trích yếu nội dung')
    expect(dl).toContain('Bổ nhiệm')
    expect(dl).toContain('CCCD người liên hệ')
    expect(dl).toContain('07********34')
    expect(w.find('h1').text()).toBe('02/QĐ-SM')
    expect(w.text()).toContain('Đang duyệt')
  })

  test('lists attachments from the server after reload', async () => {
    const c = detailClient({ attachments: [att({ upload_id: 'u1', status: 'CLEAN' }), att({ upload_id: 'u2', status: 'INFECTED', reason: 'Eicar' })] })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(c.attachments).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1')
    expect(w.text()).toMatch(/Sạch/)
    expect(w.text()).toMatch(/Nhiễm mã độc/)
    expect(c.uploadStatus).not.toHaveBeenCalled() // đã chốt trên máy chủ thì không thăm dò lại
  })

  test('a not-yet-settled attachment is polled by QuarantineStatus', async () => {
    const c = detailClient({
      attachments: [att({ upload_id: 'u9', status: 'STAGING', sha256: null })],
      uploadStatus: { status: 'STAGING' },
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.text()).toContain('Đang kiểm dịch…')
    expect(c.uploadStatus).toHaveBeenCalledWith('u9')
    w.unmount()
  })

  test('a record that cannot be loaded shows the problem and a reload button', async () => {
    const c = fakeClient({ get: [problem('not-found'), rec({ data: { trich_yeu: 'Có rồi' } })], attachments: [] })
    const w = await mountWith(VanBanDetail, c, { id: 'rx' })
    expect(w.find('[role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    await click(w, 'Tải lại')
    expect(w.text()).toContain('Có rồi')
  })

  test('upload pre-checks type and size before calling the API', async () => {
    const c = detailClient()
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.find('input[type="file"]').attributes('accept')).toBe('application/pdf')
    await pickFile(w, pdf('big.pdf', 16 * MB))
    expect(c.upload).not.toHaveBeenCalled()
    expect(w.text()).toMatch(/15 MB/)
    await pickFile(w, new File(['x'], 'a.docx', { type: 'application/vnd.openxmlformats' }))
    expect(c.upload).not.toHaveBeenCalled()
    expect(w.text()).toContain('Chỉ nhận tệp PDF')
    await pickFile(w, pdf('empty.pdf', 0))
    expect(c.upload).not.toHaveBeenCalled()
    expect(w.text()).toContain('Tệp rỗng')
  })

  test('a valid PDF is uploaded once, then the list is reloaded from the server', async () => {
    const file = pdf('quyet-dinh.pdf', 15 * MB)
    const c = detailClient({
      upload: { upload_id: 'u1' },
      attachments: [[], [att({ upload_id: 'u1', status: 'STAGING', sha256: null })]],
      uploadStatus: { status: 'STAGING' },
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.text()).toContain('Chưa có tệp nào')
    await pickFile(w, file)
    expect(c.upload).toHaveBeenCalledTimes(1)
    expect(c.upload).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1', file, 'quyet-dinh.pdf')
    expect(c.attachments).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('Đang kiểm dịch…')
    w.unmount()
  })

  test('an upload failure shows the server problem and is not retried', async () => {
    const c = detailClient({ upload: problem('record-not-open') })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await pickFile(w, pdf('a.pdf'))
    expect(w.find('[role=alert]').text()).toBe('Hồ sơ không còn ở trạng thái cho phép đính kèm tệp')
    expect(c.upload).toHaveBeenCalledTimes(1)
  })

  test.each([
    ['not the owner', { is_owner: false }],
    ['already running', { wf_state: 'running' }],
    ['seal pending', { seal_state: 'SEAL_PENDING' as const }],
    ['sealed', { seal_state: 'SEALED' as const }],
  ])('no write buttons or upload when %s', async (_n, over) => {
    const w = await mountWith(VanBanDetail, detailClient({ get: rec(over) }), { id: 'r1' })
    expect(w.text()).not.toContain('Gửi duyệt')
    expect(w.text()).not.toContain('Sửa')
    expect(w.find('input[type="file"]').exists()).toBe(false)
  })

  test('start shows the server problem (attachments-not-clean)', async () => {
    const c = detailClient({ start: problem('attachments-not-clean') })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Gửi duyệt')
    expect(w.find('[role=alert]').text()).toBe('Chưa đủ tệp đính kèm đã kiểm dịch sạch')
    expect(c.start).toHaveBeenCalledTimes(1)
  })

  test('start success moves the record into approval and hides the button', async () => {
    const c = detailClient({ start: rec({ wf_state: 'running', version: 2 }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Gửi duyệt')
    expect(c.start).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1')
    expect(w.text()).toContain('Đang duyệt')
    expect(w.text()).not.toContain('Gửi duyệt')
  })

  test('a 409 shows the message with a reload hint, never retries, and reload clears it', async () => {
    const c = detailClient({
      get: [rec({ version: 1 }), rec({ version: 2, data: { trich_yeu: 'Đã đổi' } })],
      start: problem('version-conflict'),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Gửi duyệt')
    expect(w.find('[role=alert]').text()).toBe('Dữ liệu đã thay đổi, hãy tải lại')
    expect(c.start).toHaveBeenCalledTimes(1)
    await click(w, 'Tải lại')
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(w.text()).toContain('Đã đổi')
    expect(c.start).toHaveBeenCalledTimes(1)
  })

  test('edit sends ONLY the changed fields, never the masked PII from the form data', async () => {
    const c = detailClient({
      get: rec({ data: { trich_yeu: 'Cũ', loai_van_ban: 'Quyết định', nguoi_lien_he_cccd: '07********34' } }),
      patch: rec({ version: 2, data: { trich_yeu: 'Mới', loai_van_ban: 'Quyết định', nguoi_lien_he_cccd: '07********34' } }),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Sửa')
    expect((w.find('input[name="nguoi_lien_he_cccd"]').element as HTMLInputElement).value).toBe('07********34')
    await fill(w, { trich_yeu: 'Mới' })
    expect(c.patch).toHaveBeenCalledTimes(1)
    expect(c.patch).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1', { trich_yeu: 'Mới' })
    expect(w.find('form').exists()).toBe(false)
    expect(w.find('dl').text()).toContain('Mới')
  })

  test('saving without any change does not call the API', async () => {
    const c = detailClient({ get: rec({ data: { trich_yeu: 'Cũ', loai_van_ban: 'Quyết định', nguoi_lien_he_cccd: '07********34' } }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Sửa')
    await fill(w, {}, { submit: true })
    expect(c.patch).not.toHaveBeenCalled()
    expect(w.find('form').exists()).toBe(false)
  })

  test('an edit refused by the server stays in the form with the problem', async () => {
    const c = detailClient({
      get: rec({ data: { trich_yeu: 'Cũ', loai_van_ban: 'Quyết định' } }),
      patch: problem('record-in-workflow'),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Sửa')
    await fill(w, { trich_yeu: 'Mới' })
    expect(w.find('[role=alert]').text()).toBe('Hồ sơ đang trong quy trình xử lý, không thể sửa hoặc xoá dữ liệu lúc này')
    expect(w.find('form').exists()).toBe(true)
    expect(c.patch).toHaveBeenCalledTimes(1)
  })

  test('switching to another record reloads and ignores the stale response', async () => {
    let releaseOld: (r: ReturnType<typeof rec>) => void = () => {}
    const old = new Promise<ReturnType<typeof rec>>((res) => { releaseOld = res })
    const c = detailClient({
      get: (_a: string, _c: string, id: string) => (id === 'old' ? old : Promise.resolve(rec({ id: 'new', data: { trich_yeu: 'Mới' } }))),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'old' })
    await w.setProps({ id: 'new' })
    await flushPromises()
    releaseOld(rec({ id: 'old', data: { trich_yeu: 'Cũ' } }))
    await flushPromises()
    expect(w.text()).toContain('Mới')
    expect(w.text()).not.toContain('Cũ')
  })
})
