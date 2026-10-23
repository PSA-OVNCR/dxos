// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils'
import { problem } from 'dxos-sdk-js/testing'
import { SealQr, VerifyLink } from 'dxos-sdk-js/vue'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { saveBlob } from '../src/download'
import VanBanDetail from '../src/views/VanBanDetail.vue'
import { att, click, detailClient, mountWith, rec, sealInfo } from './helpers'

vi.mock('../src/download', async (orig) => ({ ...(await orig<typeof import('../src/download')>()), saveBlob: vi.fn() }))

const GD = ['app:phong-ho-so:giam_doc']
const VT = ['app:phong-ho-so:van_thu']
const SHA = 'b'.repeat(64)

beforeEach(() => { vi.mocked(saveBlob).mockClear() })

/** Mọi ô nhập trong vùng có nhãn: <label for=id> hoặc nằm trong <label>. */
function allControlsLabelled(root: { element: Element }): boolean {
  const controls = [...root.element.querySelectorAll('input, select, textarea')]
  return controls.length > 0 && controls.every((el) => {
    const id = el.getAttribute('id')
    return el.closest('label') !== null || (id !== null && root.element.querySelector(`label[for="${id}"]`) !== null)
  })
}

// ---- niêm phong ----------------------------------------------------------------------------

describe('SealPanel', () => {
  test('seal panel shows QR, verify link and pending state', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEAL_PENDING' }), seal: sealInfo({ seal_state: 'SEAL_PENDING', issued_at: null, key_version: null }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(c.seal).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1')
    expect(w.text()).toMatch(/Chờ niêm phong/)
    expect(w.findComponent(SealQr).exists()).toBe(true)
    expect(w.findComponent(VerifyLink).exists()).toBe(true)
    expect(w.text()).not.toContain('Tải bản PDF đã ban hành')
  })

  test('a record without a seal request never asks for a seal', async () => {
    const c = detailClient({ get: rec({ seal_state: 'NONE' }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(c.seal).not.toHaveBeenCalled()
    expect(w.findComponent(SealQr).exists()).toBe(false)
    expect(w.text()).not.toContain('Niêm phong')
  })

  test('a sealed record shows the seal id, issue time in Vietnam time and the verify link', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo({ issued_at: '2026-11-02T03:00:00Z', key_version: 2 }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.text()).toContain('Đã niêm phong')
    expect(w.text()).toContain('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    expect(w.text()).toContain('10:00 02/11/2026')
    expect(w.find('a.dx-verify-link').attributes('href')).toBe(sealInfo().verify_url)
  })

  test('a seal that cannot be loaded shows the server problem and a reload button', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: [problem('not-found'), sealInfo()] })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.find('[role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    await click(w, 'Tải lại')
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(w.findComponent(SealQr).exists()).toBe(true)
  })

  test('download fetches the CLEAN file and saves it as <so_hieu>.pdf with "/" replaced by "-"', async () => {
    const blob = new Blob(['%PDF-1.7'])
    const c = detailClient({
      get: rec({ seal_state: 'SEALED', data: { so_hieu: '02/QĐ-SM' } }), seal: sealInfo(), downloadObject: blob,
      attachments: [att({ upload_id: 'u0', status: 'INFECTED', sha256: null }), att({ upload_id: 'u1', sha256: SHA })],
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Tải bản PDF đã ban hành')
    expect(c.downloadObject).toHaveBeenCalledTimes(1)
    expect(c.downloadObject).toHaveBeenCalledWith(SHA, 'original')
    expect(saveBlob).toHaveBeenCalledWith(blob, '02-QĐ-SM.pdf')
  })

  test('several CLEAN files get one numbered button each, never one name for two files', async () => {
    const c = detailClient({
      get: rec({ seal_state: 'SEALED', data: { so_hieu: '02/QĐ-SM' } }), seal: sealInfo(), downloadObject: new Blob(['x']),
      attachments: [att({ upload_id: 'u1', sha256: SHA }), att({ upload_id: 'u2', sha256: 'c'.repeat(64) })],
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    expect(w.findAll('button').map((b) => b.text()).filter((t) => t.startsWith('Tải bản PDF')))
      .toEqual(['Tải bản PDF đã ban hành (tệp 1)', 'Tải bản PDF đã ban hành (tệp 2)'])
    await click(w, 'Tải bản PDF đã ban hành (tệp 2)')
    expect(c.downloadObject).toHaveBeenCalledWith('c'.repeat(64), 'original')
    expect(vi.mocked(saveBlob).mock.calls[0]?.[1]).toBe('02-QĐ-SM-2.pdf')
  })

  test('no download button for a revoked record or when no file is CLEAN', async () => {
    const revoked = await mountWith(VanBanDetail, detailClient({
      get: rec({ seal_state: 'REVOKED' }), seal: sealInfo({ seal_state: 'REVOKED' }), attachments: [att({ sha256: SHA })],
    }), { id: 'r1' })
    expect(revoked.text()).toContain('Đã thu hồi')
    expect(revoked.text()).not.toContain('Tải bản PDF đã ban hành')
    const none = await mountWith(VanBanDetail, detailClient({
      get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), attachments: [att({ status: 'STAGING', sha256: null })],
    }), { id: 'r1' })
    expect(none.text()).not.toContain('Tải bản PDF đã ban hành')
  })

  test('a failed download shows the server problem and is not retried', async () => {
    const c = detailClient({
      get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), attachments: [att({ sha256: SHA })], downloadObject: problem('integrity-error'),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' })
    await click(w, 'Tải bản PDF đã ban hành')
    expect(w.find('[role=alert]').text()).toBe('Tệp lưu trữ không qua được kiểm tra toàn vẹn, hãy báo quản trị viên')
    expect(c.downloadObject).toHaveBeenCalledTimes(1)
    expect(saveBlob).not.toHaveBeenCalled()
  })

  test('revoke requires a reason code from the fixed list', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo() })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: GD })
    await click(w, 'Thu hồi niêm phong')
    expect(w.findAll('select[name="reason_code"] option').map((o) => o.attributes('value')))
      .toEqual(['superseded', 'issued_in_error', 'content_error', 'legal_order', 'other'])
    expect(c.revoke).not.toHaveBeenCalled()
  })

  test.each([
    ['not giam_doc', ['app:phong-ho-so:van_thu'], 'SEALED'],
    ['pending', GD, 'SEAL_PENDING'],
    ['already revoked', GD, 'REVOKED'],
  ])('no revoke button when %s (convenience only, the core decides)', async (_n, roleStrings, state) => {
    const c = detailClient({ get: rec({ seal_state: state as 'SEALED' }), seal: sealInfo({ seal_state: state as 'SEALED' }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings })
    expect(w.text()).not.toContain('Thu hồi niêm phong')
  })

  test('revoke needs a reason, then sends it once with the trimmed note and refreshes the record', async () => {
    const c = detailClient({
      get: [rec({ seal_state: 'SEALED', version: 3 }), rec({ seal_state: 'REVOKED', version: 4 })],
      seal: [sealInfo(), sealInfo({ seal_state: 'REVOKED' })],
      revoke: rec({ seal_state: 'REVOKED', version: 4 }),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: GD })
    await click(w, 'Thu hồi niêm phong')
    const confirm = w.findAll('button').find((b) => b.text() === 'Xác nhận thu hồi')!
    expect(confirm.attributes('disabled')).toBeDefined()
    expect(w.find('textarea[name="note"]').attributes('maxlength')).toBe('500')
    await w.find('select[name="reason_code"]').setValue('content_error')
    await w.find('textarea[name="note"]').setValue('  Sai số liệu ở điều 2  ')
    await click(w, 'Xác nhận thu hồi')
    expect(c.revoke).toHaveBeenCalledTimes(1)
    expect(c.revoke).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1', 'content_error', 'Sai số liệu ở điều 2')
    expect(c.get).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('Đã thu hồi')
    expect(w.text()).not.toContain('Thu hồi niêm phong')
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
  })

  test('revoke without a note sends no note; the dialog fields are labelled', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), revoke: rec({ seal_state: 'REVOKED' }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: GD })
    await click(w, 'Thu hồi niêm phong')
    expect(allControlsLabelled(w.find('[role=alertdialog]'))).toBe(true)
    expect(w.find('[role=alertdialog]').text()).toContain('không thể hoàn tác')
    await w.find('select[name="reason_code"]').setValue('superseded')
    await click(w, 'Xác nhận thu hồi')
    expect(c.revoke).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1', 'superseded', undefined)
  })

  test('a refused revoke keeps the dialog, shows the problem with a reload hint and never retries', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), revoke: problem('version-conflict') })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: GD })
    await click(w, 'Thu hồi niêm phong')
    await w.find('select[name="reason_code"]').setValue('other')
    await click(w, 'Xác nhận thu hồi')
    expect(w.find('[role=alert]').text()).toBe('Dữ liệu đã thay đổi, hãy tải lại')
    expect(w.text()).toContain('Tải lại')
    expect(c.revoke).toHaveBeenCalledTimes(1)
  })

  test('cancelling the revoke dialog does not call the API', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo() })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: GD })
    await click(w, 'Thu hồi niêm phong')
    await click(w, 'Hủy')
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
    expect(c.revoke).not.toHaveBeenCalled()
  })
})

// ---- dữ liệu cá nhân -----------------------------------------------------------------------

describe('PiiPanel', () => {
  test.each([
    ['giam_doc', GD],
    ['van_thu', VT],
  ])('%s sees the PII review button while the workflow runs and one click calls the API once', async (_n, roleStrings) => {
    const c = detailClient({ get: rec({ wf_state: 'running' }), piiReview: rec({ wf_state: 'running', version: 2 }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings })
    await click(w, 'Xác nhận đã rà dữ liệu cá nhân')
    expect(c.piiReview).toHaveBeenCalledTimes(1)
    expect(c.piiReview).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1')
    expect(w.text()).toContain('Đã ghi nhận xác nhận rà dữ liệu cá nhân.')
    expect(c.get).toHaveBeenCalledTimes(2) // tải lại bản ghi để số phiên bản và dữ liệu hiển thị khớp máy chủ
  })

  test.each([
    ['other role', ['app:phong-ho-so:truong_phong'], 'running'],
    ['not running', VT, 'ended:rejected'],
  ])('no PII review button for %s', async (_n, roleStrings, wf) => {
    const c = detailClient({ get: rec({ wf_state: wf }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings })
    expect(w.text()).not.toContain('Xác nhận đã rà dữ liệu cá nhân')
  })

  test('a refused PII review shows the server problem and is not retried', async () => {
    const c = detailClient({ get: rec({ wf_state: 'running' }), piiReview: problem('forbidden') })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: VT })
    await click(w, 'Xác nhận đã rà dữ liệu cá nhân')
    expect(w.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
    expect(c.piiReview).toHaveBeenCalledTimes(1)
  })

  test('erase PII offers only pii fields and the five legal reason codes', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo() })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: VT })
    await click(w, 'Xóa dữ liệu cá nhân')
    expect(w.findAll('input[name="fields"]').map((i) => i.attributes('value'))).toEqual(['nguoi_lien_he_cccd'])
    expect(w.findAll('select[name="reason_code"] option').map((o) => o.attributes('value')))
      .toEqual(['data_subject_request', 'purpose_completed', 'retention_expired', 'authority_decision', 'agreement'])
    expect(w.find('[role=alertdialog]').text()).toContain('Điều 14 khoản 1 Luật 91/2025')
    expect(w.find('[role=alertdialog]').text()).toContain('CCCD người liên hệ')
    expect(allControlsLabelled(w.find('[role=alertdialog]'))).toBe(true)
  })

  test('erase needs at least one field and a reason, then sends them once', async () => {
    const c = detailClient({
      get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), erasePii: rec({ seal_state: 'SEALED', version: 2 }),
    })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: VT })
    await click(w, 'Xóa dữ liệu cá nhân')
    const confirm = () => w.findAll('button').find((b) => b.text() === 'Xác nhận xóa')!
    expect(confirm().attributes('disabled')).toBeDefined()
    await w.find('input[name="fields"]').setValue(true)
    expect(confirm().attributes('disabled')).toBeDefined() // thiếu mã lý do
    await w.find('select[name="reason_code"]').setValue('data_subject_request')
    expect(confirm().attributes('disabled')).toBeUndefined()
    await click(w, 'Xác nhận xóa')
    expect(c.erasePii).toHaveBeenCalledTimes(1)
    expect(c.erasePii).toHaveBeenCalledWith('phong-ho-so', 'van_ban', 'r1', ['nguoi_lien_he_cccd'], 'data_subject_request')
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
    expect(w.text()).toContain('Đã xóa dữ liệu cá nhân đã chọn.')
  })

  test.each([
    ['giam_doc is not an eraser', GD, { seal_state: 'SEALED' as const }],
    ['workflow running', VT, { wf_state: 'running' }],
    ['seal pending', VT, { seal_state: 'SEAL_PENDING' as const }],
  ])('no erase button when %s', async (_n, roleStrings, over) => {
    const c = detailClient({ get: rec(over), seal: sealInfo({ seal_state: 'SEAL_PENDING' }) })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings })
    expect(w.text()).not.toContain('Xóa dữ liệu cá nhân')
  })

  test('a refused erase keeps the dialog open with the server problem and is not retried', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo(), erasePii: problem('seal-pending') })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: VT })
    await click(w, 'Xóa dữ liệu cá nhân')
    await w.find('input[name="fields"]').setValue(true)
    await w.find('select[name="reason_code"]').setValue('agreement')
    await click(w, 'Xác nhận xóa')
    expect(w.find('[role=alert]').text()).toBe('Hồ sơ đang chờ niêm phong, hãy thử lại sau')
    expect(w.find('[role=alertdialog]').exists()).toBe(true)
    expect(c.erasePii).toHaveBeenCalledTimes(1)
  })

  test('cancelling the erase dialog does not call the API', async () => {
    const c = detailClient({ get: rec({ seal_state: 'SEALED' }), seal: sealInfo() })
    const w = await mountWith(VanBanDetail, c, { id: 'r1' }, { roleStrings: VT })
    await click(w, 'Xóa dữ liệu cá nhân')
    await click(w, 'Hủy')
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
    expect(c.erasePii).not.toHaveBeenCalled()
    await flushPromises()
  })
})
