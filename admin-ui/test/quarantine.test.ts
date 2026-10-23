// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { ApiError } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import QuarantineView from '../src/views/QuarantineView.vue'
import { click, fakeApi, mountView, quarantineItem } from './helpers'

describe('QuarantineView', () => {
  test('QuarantineView lists items newest first with VN time', async () => {
    const api = fakeApi({
      quarantine: async () => [
        quarantineItem({ upload_id: 'old', created_at: '2026-10-20T16:30:00Z', status: 'REJECTED', reason: 'type_mismatch' }),
        quarantineItem({ upload_id: 'new', created_at: '2026-10-22T03:00:00Z' }),
        quarantineItem({ upload_id: 'mid', created_at: '2026-10-21T00:00:00Z', app_id: 'test-app' }),
      ],
    })
    const w = await mountView(QuarantineView, api)
    expect(api.quarantine).toHaveBeenCalledTimes(1)
    const rows = w.findAll('tbody tr[data-upload]')
    expect(rows.map((r) => r.attributes('data-upload'))).toEqual(['new', 'mid', 'old'])
    // 03:00 UTC = 10:00 giờ Việt Nam; 16:30 UTC ngày 20 = 23:30 cùng ngày.
    expect(rows[0]?.text()).toContain('22/10/2026')
    expect(rows[0]?.text()).toContain('10:00')
    expect(rows[2]?.text()).toContain('20/10/2026')
    expect(rows[2]?.text()).toContain('23:30')
    // Trạng thái bằng chữ + mức; mã băm rút gọn, đầy đủ trong title; không có tên tệp.
    expect(rows[0]?.find('.dx-state').text()).toContain('Nhiễm mã độc')
    expect(rows[0]?.find('.dx-state').classes()).toContain('dx-state-bad')
    expect(rows[2]?.find('.dx-state').text()).toContain('Bị từ chối')
    expect(rows[0]?.text()).toContain('Eicar-Test-Signature')
    expect(rows[0]?.text()).toContain('so-muon-sach')
    expect(rows[0]?.find('code[title]').attributes('title')).toBe('ef'.repeat(32))
    expect(rows[0]?.text()).toContain('efefefefefef')
  })

  test('an empty quarantine says so; reload fetches again', async () => {
    const api = fakeApi({ quarantine: async () => [] })
    const w = await mountView(QuarantineView, api)
    expect(w.text()).toContain('Không có tệp nào bị cách ly')
    await click(w, 'Tải lại')
    expect(api.quarantine).toHaveBeenCalledTimes(2)
  })

  test('an error is shown through ProblemMessage', async () => {
    const w = await mountView(QuarantineView, fakeApi({
      quarantine: async () => { throw new ApiError(403, 'not-admin', 'Tài khoản này không có quyền quản trị', undefined, null) },
    }))
    expect(w.find('.dx-problem').text()).toBe('Tài khoản này không có quyền quản trị')
    expect(w.find('tbody tr[data-upload]').exists()).toBe(false)
  })

  test('the limit is passed to the API', async () => {
    const api = fakeApi()
    const w = await mountView(QuarantineView, api)
    expect(api.quarantine).toHaveBeenLastCalledWith(100)
    await w.find('select[name="limit"]').setValue('500')
    await Promise.resolve()
    expect(api.quarantine).toHaveBeenLastCalledWith(500)
  })
})
