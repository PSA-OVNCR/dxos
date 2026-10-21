// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fakeClient, problem } from 'dxos-sdk-js/testing'
import type { SealInfo } from 'dxos-sdk-js'
import { afterEach, describe, expect, test, vi } from 'vitest'
import SoDangKy, { registerRows } from '../src/views/SoDangKy.vue'
import { click, mountWith, rec, sealInfo } from './helpers'

afterEach(() => { vi.restoreAllMocks() })

const sealed = (id: string, so_hieu: string, extra: Record<string, unknown> = {}, state: 'SEALED' | 'REVOKED' = 'SEALED') =>
  rec({ id, seal_state: state, data: { so_hieu, loai_van_ban: 'Quyết định', trich_yeu: `Trích yếu ${so_hieu}`, ...extra } })

describe('registerRows', () => {
  test('register sorts by year desc then number asc, sealed and revoked only', () => {
    const rows = registerRows([
      rec({ id: 'a', seal_state: 'SEALED', data: { so_hieu: '02/QĐ-SM' } }),
      rec({ id: 'b', seal_state: 'SEALED', data: { so_hieu: '10/QĐ-SM' } }),
      rec({ id: 'c', seal_state: 'NONE' }),
    ], new Map([
      ['a', sealInfo({ issued_at: '2026-11-02T03:00:00Z' })],
      ['b', sealInfo({ issued_at: '2026-11-03T03:00:00Z' })],
    ]))
    expect(rows.map((r) => r.so_hieu)).toEqual(['02/QĐ-SM', '10/QĐ-SM'])
  })

  test('numbers are compared as numbers, years descending, and a revoked record stays in the register', () => {
    const rows = registerRows([
      sealed('a', '9/QĐ-SM'), sealed('b', '10/QĐ-SM'), sealed('c', '01/QĐ-SM'), sealed('d', '03/QĐ-SM', {}, 'REVOKED'),
      rec({ id: 'e', seal_state: 'SEAL_PENDING', data: { so_hieu: '04/QĐ-SM' } }),
    ], new Map([
      ['a', sealInfo({ issued_at: '2026-03-01T00:00:00Z' })],
      ['b', sealInfo({ issued_at: '2026-04-01T00:00:00Z' })],
      ['c', sealInfo({ issued_at: '2027-01-05T00:00:00Z' })],
      ['d', sealInfo({ issued_at: '2026-05-01T00:00:00Z', seal_state: 'REVOKED' })],
    ]))
    expect(rows.map((r) => [r.nam, r.so_hieu, r.trang_thai])).toEqual([
      [2027, '01/QĐ-SM', 'Đã ban hành'],
      [2026, '03/QĐ-SM', 'Đã thu hồi'],
      [2026, '9/QĐ-SM', 'Đã ban hành'],
      [2026, '10/QĐ-SM', 'Đã ban hành'],
    ])
  })

  test('the year and the date are those of Vietnam (UTC+7), not UTC', () => {
    const [r] = registerRows([sealed('a', '01/QĐ-SM')], new Map([['a', sealInfo({ issued_at: '2026-12-31T18:00:00Z' })]]))
    expect(r?.nam).toBe(2027)
    expect(r?.ngay_ban_hanh).toBe('01/01/2027')
  })

  test('columns come from the record data', () => {
    const [r] = registerRows([sealed('a', '01/QĐ-SM', { chuc_vu_nguoi_ky: 'Giám đốc', noi_nhan: 'Các phòng' })],
      new Map([['a', sealInfo({ issued_at: '2026-10-22T01:00:00Z' })]]))
    expect(r).toEqual({
      so_hieu: '01/QĐ-SM', nam: 2026, ngay_ban_hanh: '22/10/2026', loai: 'Quyết định', trich_yeu: 'Trích yếu 01/QĐ-SM',
      chuc_vu: 'Giám đốc', noi_nhan: 'Các phòng', trang_thai: 'Đã ban hành',
    })
  })

  test('a sealed record whose seal could not be read is kept, last, with no year', () => {
    const rows = registerRows([sealed('a', '01/QĐ-SM'), sealed('b', '02/QĐ-SM')],
      new Map([['b', sealInfo({ issued_at: '2026-10-22T01:00:00Z' })]]))
    expect(rows.map((r) => [r.so_hieu, r.nam, r.ngay_ban_hanh])).toEqual([['02/QĐ-SM', 2026, '22/10/2026'], ['01/QĐ-SM', null, '—']])
  })
})

describe('SoDangKy', () => {
  const records = [
    sealed('a', '02/QĐ-SM', { noi_nhan: 'Các phòng', chuc_vu_nguoi_ky: 'Giám đốc' }),
    sealed('b', '01/QĐ-SM'),
    sealed('c', '05/QĐ-SM', {}, 'REVOKED'),
    rec({ id: 'd', seal_state: 'NONE', data: { trich_yeu: 'Nháp' } }),
  ]
  const seals: Record<string, SealInfo> = {
    a: sealInfo({ issued_at: '2026-11-02T03:00:00Z' }),
    b: sealInfo({ issued_at: '2025-12-30T03:00:00Z' }),
    c: sealInfo({ issued_at: '2026-12-01T03:00:00Z', seal_state: 'REVOKED' }),
  }
  const client = (over = {}) => fakeClient({ listAll: records, seal: (_a: string, _c: string, id: string) => Promise.resolve(seals[id] as SealInfo), ...over })

  test('loads the records, asks the seal of each sealed or revoked one only, and fills the table', async () => {
    const c = client()
    const w = await mountWith(SoDangKy, c)
    expect(c.listAll).toHaveBeenCalledWith('phong-ho-so', 'van_ban')
    expect(c.seal.mock.calls.map((x) => x[2]).sort()).toEqual(['a', 'b', 'c'])
    expect(w.find('h1').text()).toBe('Sổ đăng ký văn bản đi')
    expect(w.findAll('th').map((x) => x.text())).toEqual([
      'Số, ký hiệu', 'Ngày ban hành', 'Tên loại văn bản', 'Trích yếu nội dung', 'Chức vụ người ký', 'Nơi nhận', 'Trạng thái',
    ])
    const cells = w.findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()))
    expect(cells).toEqual([
      ['02/QĐ-SM', '02/11/2026', 'Quyết định', 'Trích yếu 02/QĐ-SM', 'Giám đốc', 'Các phòng', 'Đã ban hành'],
      ['05/QĐ-SM', '01/12/2026', 'Quyết định', 'Trích yếu 05/QĐ-SM', '—', '—', 'Đã thu hồi'],
      ['01/QĐ-SM', '30/12/2025', 'Quyết định', 'Trích yếu 01/QĐ-SM', '—', '—', 'Đã ban hành'],
    ])
  })

  test('states the legal scope note verbatim', async () => {
    const w = await mountWith(SoDangKy, client())
    expect(w.text()).toContain('Ứng dụng vận dụng Nghị định 30/2020; Công ty TNHH Sao Mai không thuộc diện áp dụng')
  })

  test('filters by year with a labelled select', async () => {
    const w = await mountWith(SoDangKy, client())
    const select = w.find('select[name="nam"]')
    expect(w.find(`label[for="${select.attributes('id')}"]`).text()).toBe('Năm')
    expect(select.findAll('option').map((o) => [o.attributes('value'), o.text()])).toEqual([['', 'Tất cả các năm'], ['2026', '2026'], ['2025', '2025']])
    await select.setValue('2025')
    expect(w.findAll('tbody tr').map((tr) => tr.find('td').text())).toEqual(['01/QĐ-SM'])
    await select.setValue('')
    expect(w.findAll('tbody tr')).toHaveLength(3)
  })

  test('"In" calls window.print()', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const w = await mountWith(SoDangKy, client())
    await click(w, 'In')
    expect(print).toHaveBeenCalledTimes(1)
  })

  test('print styles hide the navigation and the controls', () => {
    const css = readFileSync(resolve(import.meta.dirname, '../src/style.css'), 'utf8')
    const printBlock = /@media print\s*\{([\s\S]*?\n)\}/.exec(css)?.[1] ?? ''
    expect(printBlock).toMatch(/\.dx-header[\s\S]*display:\s*none/)
    expect(printBlock).toMatch(/\.dx-no-print/)
  })

  test('the controls carry the no-print class', async () => {
    const w = await mountWith(SoDangKy, client())
    expect(w.find('.dx-no-print select[name="nam"]').exists()).toBe(true)
    expect(w.findAll('button').find((b) => b.text() === 'In')!.classes()).toContain('dx-no-print')
  })

  test('a seal that cannot be read is reported and the rest of the register still shows', async () => {
    const c = client({ seal: (_a: string, _c: string, id: string) => (id === 'b' ? Promise.reject(problem('not-found')) : Promise.resolve(seals[id] as SealInfo)) })
    const w = await mountWith(SoDangKy, c)
    expect(w.find('[role=alert]').text()).toContain('Không đọc được thông tin niêm phong của 1 văn bản')
    expect(w.findAll('tbody tr')).toHaveLength(3)
    expect(w.findAll('tbody tr').at(-1)!.find('td').text()).toBe('01/QĐ-SM')
  })

  test('empty register and a listing error', async () => {
    const empty = await mountWith(SoDangKy, fakeClient({ listAll: [rec({ seal_state: 'NONE' })] }))
    expect(empty.text()).toContain('Chưa có văn bản nào được ban hành.')
    expect(empty.find('table').exists()).toBe(false)
    const bad = await mountWith(SoDangKy, fakeClient({ listAll: problem('forbidden') }))
    expect(bad.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
  })
})
