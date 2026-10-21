// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises } from '@vue/test-utils'
import type { BulkResult } from 'dxos-sdk-js'
import { problem } from 'dxos-sdk-js/testing'
import { SealQr, VerifyLink } from 'dxos-sdk-js/vue'
import { afterEach, describe, expect, test, vi } from 'vitest'
import ChungNhanDetail from '../src/views/ChungNhanDetail.vue'
import ChungNhanList from '../src/views/ChungNhanList.vue'
import DuyetLo from '../src/views/DuyetLo.vue'
import NhapCsv from '../src/views/NhapCsv.vue'
import TrangIn from '../src/views/TrangIn.vue'
import { click, fakeClient, mountWith, pickFile, rec, sealInfo, task, type Mounted } from './helpers'

afterEach(() => { vi.restoreAllMocks() })

const fixtureFile = (name: string): File =>
  new File([new Uint8Array(readFileSync(resolve(import.meta.dirname, 'fixtures', name)))], name)

const OK = (i: number): BulkResult => ({ ok: true, id: `r${i}` })
const bad = (i: number): BulkResult => ({
  ok: false, row: i,
  error: { type: 'https://dxos.dev/problems/schema', title: 'Record data does not match the collection schema', errors: [{ path: '/ho_ten', msg: 'bắt buộc' }] },
})

/** Tệp CSV Excel vi-VN (dấu `;`, ngày DD/MM/YYYY) với `n` dòng dữ liệu. */
function csvWith(n: number): File {
  const lines = ['Họ và tên;Sự kiện;Ngày cấp;Email']
  for (let i = 1; i <= n; i++) lines.push(`Người ${i};Hội thảo;10/11/2026;`)
  return new File([lines.join('\r\n') + '\r\n'], 'ds.csv')
}

async function importFile(w: Mounted, file: File): Promise<void> {
  await pickFile(w, file)
  await click(w, 'Tạo chứng nhận')
}

const CAN_BO = ['app:chung-nhan:can_bo_clb']
const TRUONG = ['app:chung-nhan:truong_clb']

// ---- nhập CSV ------------------------------------------------------------------------------

describe('NhapCsv', () => {
  test('import sends at most 500 rows per bulk call and shows per-row server errors', async () => {
    const c = fakeClient({ bulk: (_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => (i === 1 ? bad(i) : OK(i))) })
    const w = await mountWith(NhapCsv, c)
    await importFile(w, csvWith(1201))
    await flushPromises()
    expect(c.bulk.mock.calls.map((x) => x[2].length)).toEqual([500, 500, 201])
    expect(c.bulk).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', expect.any(Array))
    expect(w.text()).toMatch(/Dòng 3/) // hàng 1 của lô đầu = dòng 3 của tệp (dòng 1 là tiêu đề)
    expect(w.text()).toMatch(/Dòng 503/)
    expect(w.text()).toMatch(/Dòng 1003/)
    expect(w.text()).toContain('Đã tạo 1198 chứng nhận, 3 dòng lỗi')
    expect(w.findAll('[role=alert]').some((a) => /ho_ten: bắt buộc/.test(a.text()))).toBe(true)
  })

  test.each([
    ['cp1258.csv', 'Windows-1258'], ['utf16le-bom.csv', 'UTF-16'], ['utf8-bom.csv', 'UTF-8'],
  ])('%s: the detected encoding is shown and the preview has the right text, nothing is sent yet', async (name, label) => {
    const c = fakeClient({ bulk: [] })
    const w = await mountWith(NhapCsv, c)
    await pickFile(w, fixtureFile(name))
    expect(w.text()).toContain(label)
    if (name === 'cp1258.csv') expect(w.text()).toContain('đã đọc theo bảng mã Windows-1258')
    else expect(w.text()).not.toContain('đã đọc theo bảng mã Windows-1258')
    expect(w.find('table').text()).toContain('Nguyễn Văn An')
    expect(w.find('table').text()).toContain('10/11/2026')
    expect(w.text()).toContain('3 dòng hợp lệ')
    expect(c.bulk).not.toHaveBeenCalled()
  })

  test('the rows sent are the mapped data: NFC text, ISO dates, empty optional cells left out', async () => {
    const c = fakeClient({ bulk: (_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => OK(i)) })
    const w = await mountWith(NhapCsv, c)
    await importFile(w, fixtureFile('cp1258.csv'))
    expect(c.bulk.mock.calls[0]?.[2]).toEqual([
      { ho_ten: 'Nguyễn Văn An', su_kien: 'Hội thảo Phần mềm nguồn mở', ngay_cap: '2026-11-10', email: 'an@example.vn' },
      { ho_ten: 'Lê, Thị "Bình"', su_kien: 'Ngày hội Git, GitHub', ngay_cap: '2026-11-10' },
      { ho_ten: 'Phạm Đức Thịnh', su_kien: 'Tập huấn Ứng dụng Chứng nhận số', ngay_cap: '2026-11-12', email: 'thinh@example.vn' },
    ])
  })

  test('the preview shows at most 20 rows but all of them are imported', async () => {
    const c = fakeClient({ bulk: (_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => OK(i)) })
    const w = await mountWith(NhapCsv, c)
    await pickFile(w, csvWith(45))
    expect(w.findAll('tbody tr')).toHaveLength(20)
    expect(w.text()).toContain('45 dòng hợp lệ')
    expect(w.text()).toMatch(/20 dòng đầu/)
    await click(w, 'Tạo chứng nhận')
    expect(c.bulk.mock.calls[0]?.[2]).toHaveLength(45)
  })

  test('errors are listed by file line and nothing can be sent until the file is fixed', async () => {
    const c = fakeClient({ bulk: [] })
    const w = await mountWith(NhapCsv, c)
    const text = 'Họ và tên;Sự kiện;Ngày cấp\r\nA;HT;10/11/2026\r\n;HT;10/11/2026\r\nB;HT;31/02/2026\r\n'
    await pickFile(w, new File([text], 'x.csv'))
    expect(w.text()).toMatch(/Dòng 3: .*Họ và tên/)
    expect(w.text()).toMatch(/Dòng 4: .*Ngày cấp/)
    expect(w.text()).toContain('1 dòng hợp lệ')
    expect(w.text()).toContain('2 dòng lỗi')
    const create = w.findAll('button').find((b) => b.text() === 'Tạo chứng nhận')!
    expect(create.attributes('disabled')).toBeDefined()
    await create.trigger('click')
    expect(c.bulk).not.toHaveBeenCalled()
  })

  test('a wrong header or an unknown column is reported and blocks the import', async () => {
    const c = fakeClient({ bulk: [] })
    const w = await mountWith(NhapCsv, c)
    await pickFile(w, new File(['Họ và tên;Lớp\r\nA;10A1\r\n'], 'x.csv'))
    expect(w.text()).toMatch(/Dòng 1: Cột "Lớp"/)
    expect(w.text()).toMatch(/Dòng 1: Thiếu cột bắt buộc/)
    expect(w.findAll('button').find((b) => b.text() === 'Tạo chứng nhận')!.attributes('disabled')).toBeDefined()
  })

  test('broken text (wrong encoding) never reaches the server', async () => {
    const c = fakeClient({ bulk: [] })
    const w = await mountWith(NhapCsv, c)
    const head = new TextEncoder().encode('Họ và tên;Sự kiện;Ngày cấp\r\nNguy')
    const tail = new TextEncoder().encode(';HT;10/11/2026\r\n')
    // BOM UTF-8 rồi một byte 0xFF không hợp lệ: bộ giải mã thay bằng U+FFFD
    await pickFile(w, new File([new Uint8Array([0xef, 0xbb, 0xbf]), head, new Uint8Array([0xff]), tail], 'x.csv'))
    expect(w.text()).toMatch(/Dòng 2: .*không đọc được/)
    expect(w.findAll('button').find((b) => b.text() === 'Tạo chứng nhận')!.attributes('disabled')).toBeDefined()
    expect(c.bulk).not.toHaveBeenCalled()
  })

  test('a file with an unterminated quote is refused with its line', async () => {
    const w = await mountWith(NhapCsv, fakeClient({ bulk: [] }))
    await pickFile(w, new File(['Họ và tên;Sự kiện;Ngày cấp\r\n"A;HT;10/11/2026\r\n'], 'x.csv'))
    expect(w.text()).toMatch(/dòng 2/)
    expect(w.find('table').exists()).toBe(false)
  })

  test('the file input is labelled', async () => {
    const w = await mountWith(NhapCsv, fakeClient({ bulk: [] }))
    const input = w.find('input[type="file"]')
    expect(w.find(`label[for="${input.attributes('id')}"]`).text()).toBe('Tệp CSV')
  })

  test('a whole-call failure stops the import, shows the problem and does not retry', async () => {
    const c = fakeClient({
      bulk: [(_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => OK(i)), problem('internal'), (_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => OK(i))],
    })
    const w = await mountWith(NhapCsv, c)
    await importFile(w, csvWith(1201))
    expect(c.bulk).toHaveBeenCalledTimes(2)
    expect(w.find('[role=alert]').text()).toBe('Máy chủ gặp sự cố, hãy thử lại sau ít phút')
    expect(w.text()).toMatch(/Đã tạo 500 chứng nhận/)
    expect(w.text()).toMatch(/dòng 502 đến 1001/)
    expect(w.text()).toMatch(/Hãy kiểm tra danh sách/)
  })

  test('creating twice is impossible: a double click sends one batch, and the button stays off afterwards', async () => {
    let release: (v: BulkResult[]) => void = () => {}
    const pending = new Promise<BulkResult[]>((res) => { release = res })
    const c = fakeClient({ bulk: () => pending })
    const w = await mountWith(NhapCsv, c)
    await pickFile(w, csvWith(2))
    const btn = w.findAll('button').find((b) => b.text() === 'Tạo chứng nhận')!
    await btn.trigger('click')
    await btn.trigger('click')
    expect(c.bulk).toHaveBeenCalledTimes(1)
    release([OK(0), OK(1)])
    await flushPromises()
    expect(w.findAll('button').find((b) => b.text() === 'Tạo chứng nhận')!.attributes('disabled')).toBeDefined()
    expect(c.bulk).toHaveBeenCalledTimes(1)
  })

  test('submit for approval starts each created record in turn, with progress, and keeps going after a failure', async () => {
    const order: string[] = []
    const c = fakeClient({
      bulk: (_a: string, _c: string, rows: unknown[]) => rows.map((_, i) => OK(i)),
      start: (_a: string, _c: string, id: string) => {
        order.push(`start ${id}`)
        return id === 'r1' ? Promise.reject(problem('already-running')) : Promise.resolve(rec({ id }))
      },
    })
    const w = await mountWith(NhapCsv, c)
    await importFile(w, csvWith(3))
    expect(c.start).not.toHaveBeenCalled()
    await click(w, 'Gửi duyệt')
    expect(order).toEqual(['start r0', 'start r1', 'start r2'])
    expect(c.start).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r0')
    expect(w.text()).toContain('Đã gửi duyệt 2, lỗi 1')
    expect(w.find('progress').attributes('value')).toBe('3')
    expect(w.find('progress').attributes('max')).toBe('3')
    expect(w.text()).toMatch(/Dòng 3: .*Hồ sơ này đã được đưa vào quy trình/)
    // chỉ mục lỗi mới được gửi lại, do người dùng bấm
    const startedBefore = c.start.mock.calls.length
    await click(w, 'Gửi duyệt')
    expect(c.start.mock.calls.slice(startedBefore).map((x) => x[2])).toEqual(['r1'])
  })

  test('only created rows are submitted (rows the server refused are not)', async () => {
    const c = fakeClient({ bulk: [[OK(0), bad(1), OK(2)]], start: rec() })
    const w = await mountWith(NhapCsv, c)
    await importFile(w, csvWith(3))
    await click(w, 'Gửi duyệt')
    expect(c.start.mock.calls.map((x) => x[2])).toEqual(['r0', 'r2'])
  })
})

// ---- duyệt lô ------------------------------------------------------------------------------

describe('DuyetLo', () => {
  const ok = () => ({ record: rec(), seal_state: 'SEALED' as const, seal_id: 'X' })
  const named = (id: string, ho_ten: string) => rec({ id, data: { ho_ten, su_kien: 'Hội thảo' } })

  test('batch approve continues after one item fails and reports it', async () => {
    const c = fakeClient({
      tasks: [task({ task_id: 't1', record_id: 'a' }), task({ task_id: 't2', record_id: 'b' }), task({ task_id: 't3', record_id: 'c' })],
      get: rec(), complete: [ok(), problem('task-gone'), ok()],
    })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    await click(w, 'Chọn tất cả')
    await click(w, 'Duyệt các mục đã chọn')
    expect(c.complete).toHaveBeenCalledTimes(3)
    expect(w.text()).toMatch(/2 đã duyệt, 1 lỗi/)
    expect(w.text()).toContain('Dữ liệu đã thay đổi, hãy tải lại') // lý do của mục lỗi, qua ProblemMessage
    expect(c.complete.mock.calls.map((x) => [x[1].task_id, x[2]])).toEqual([['t1', 'approve'], ['t2', 'approve'], ['t3', 'approve']])
  })

  test('items show the person and the event, with a labelled checkbox each', async () => {
    const c = fakeClient({
      tasks: [task({ task_id: 't1', record_id: 'a', created: '2026-10-21T13:14:30.393+07:00' }), task({ task_id: 't2', record_id: 'b' })],
      get: (_a: string, _c: string, id: string) => Promise.resolve(id === 'a' ? named('a', 'Nguyễn Văn An') : named('b', 'Lê Thị Bình')),
    })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    expect(w.findAll('li')).toHaveLength(2)
    expect(w.text()).toContain('Nguyễn Văn An')
    expect(w.text()).toContain('Hội thảo')
    expect(w.text()).toContain('13:14 21/10/2026')
    for (const box of w.findAll('input[type="checkbox"]')) {
      expect(box.element.closest('label')).not.toBeNull()
    }
    expect(w.find('li a').attributes('href')).toBe('/chung-nhan/a')
  })

  test('nothing is approved without a selection; select all / clear work', async () => {
    const c = fakeClient({ tasks: [task({ task_id: 't1' }), task({ task_id: 't2', record_id: 'b' })], get: rec(), complete: ok() })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    const go = () => w.findAll('button').find((b) => b.text() === 'Duyệt các mục đã chọn')!
    expect(go().attributes('disabled')).toBeDefined()
    await click(w, 'Chọn tất cả')
    expect(w.findAll('input[type="checkbox"]').every((b) => (b.element as HTMLInputElement).checked)).toBe(true)
    expect(go().attributes('disabled')).toBeUndefined()
    await click(w, 'Bỏ chọn tất cả')
    expect(w.findAll('input[type="checkbox"]').some((b) => (b.element as HTMLInputElement).checked)).toBe(false)
    await w.findAll('input[type="checkbox"]')[1]!.setValue(true)
    await click(w, 'Duyệt các mục đã chọn')
    expect(c.complete).toHaveBeenCalledTimes(1)
    expect(c.complete.mock.calls[0]?.[1].task_id).toBe('t2')
  })

  test('items are approved one at a time, in list order, and a failed write is never retried', async () => {
    const started: string[] = []
    const releases: (() => void)[] = []
    const c = fakeClient({
      tasks: [task({ task_id: 't1', record_id: 'a' }), task({ task_id: 't2', record_id: 'b' })], get: rec(),
      complete: (_a: string, t: { task_id: string }) => {
        started.push(t.task_id)
        return new Promise((res, rej) => { releases.push(() => (t.task_id === 't1' ? rej(problem('internal')) : res(ok()))) })
      },
    })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    await click(w, 'Chọn tất cả')
    void click(w, 'Duyệt các mục đã chọn')
    await flushPromises()
    expect(started).toEqual(['t1']) // t2 only after t1 has finished
    releases[0]?.()
    await flushPromises()
    expect(started).toEqual(['t1', 't2'])
    releases[1]?.()
    await flushPromises()
    expect(started).toEqual(['t1', 't2']) // no retry of t1
    expect(w.text()).toMatch(/1 đã duyệt, 1 lỗi/)
    expect(w.text()).toContain('Máy chủ gặp sự cố')
  })

  test('the inbox is reloaded after the batch and the report stays', async () => {
    const c = fakeClient({ tasks: [[task()], []], get: named('r1', 'Nguyễn Văn An'), complete: ok() })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    await click(w, 'Chọn tất cả')
    await click(w, 'Duyệt các mục đã chọn')
    expect(c.tasks).toHaveBeenCalledTimes(2)
    expect(w.findAll('li input[type="checkbox"]')).toHaveLength(0)
    expect(w.text()).toMatch(/1 đã duyệt, 0 lỗi/)
    expect(w.text()).toContain('Không có việc nào đang chờ bạn.')
  })

  test('a record that cannot be read does not hide the other tasks, and a failing inbox is shown', async () => {
    const c = fakeClient({
      tasks: [task({ task_id: 't1', record_id: 'a' }), task({ task_id: 't2', record_id: 'b' })],
      get: (_a: string, _c: string, id: string) => (id === 'a' ? Promise.reject(problem('not-found')) : Promise.resolve(named('b', 'Lê Thị Bình'))),
    })
    const w = await mountWith(DuyetLo, c, {}, { roleStrings: TRUONG })
    expect(w.findAll('li')).toHaveLength(2)
    expect(w.text()).toContain('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    expect(w.text()).toContain('Lê Thị Bình')
    const bad = await mountWith(DuyetLo, fakeClient({ tasks: problem('forbidden') }), {}, { roleStrings: TRUONG })
    expect(bad.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
  })
})

// ---- danh sách, chi tiết -------------------------------------------------------------------

describe('ChungNhanList', () => {
  test('rows show the number, person, event, date and status; the email is never listed', async () => {
    const records = [
      rec({ id: 'a', seal_state: 'SEALED', data: { so_chung_nhan: '7/CN-CLB', ho_ten: 'Nguyễn Văn An', su_kien: 'Hội thảo', ngay_cap: '2026-11-10', email: 'a***@example.vn' } }),
      rec({ id: 'b', wf_state: 'running', data: { ho_ten: 'Lê Thị Bình', su_kien: 'Hội thảo', ngay_cap: '2026-11-12' } }),
      rec({ id: 'c', seal_state: 'REVOKED', data: { ho_ten: 'C', su_kien: 'S', ngay_cap: '2026-01-02' } }),
      rec({ id: 'd', data: { ho_ten: 'D', su_kien: 'S', ngay_cap: '2026-01-03' } }),
    ]
    const c = fakeClient({ listAll: records })
    const w = await mountWith(ChungNhanList, c)
    expect(c.listAll).toHaveBeenCalledWith('chung-nhan', 'chung_nhan')
    const rows = w.findAll('tbody tr').map((r) => r.findAll('td').map((d) => d.text()))
    expect(rows[0]?.slice(0, 5)).toEqual(['7/CN-CLB', 'Nguyễn Văn An', 'Hội thảo', '10/11/2026', 'Đã cấp'])
    expect(rows[1]?.[4]).toBe('Chờ duyệt')
    expect(rows[2]?.[4]).toBe('Đã thu hồi')
    expect(rows[3]?.[4]).toBe('Chưa gửi duyệt')
    expect(w.text()).not.toContain('example.vn')
    expect(w.findAll('th').map((h) => h.text())).toContain('Số chứng nhận')
    expect(w.find('tbody a').attributes('href')).toBe('/chung-nhan/a')
  })

  test('empty list and a listing error', async () => {
    const empty = await mountWith(ChungNhanList, fakeClient({ listAll: [] }))
    expect(empty.text()).toContain('Chưa có chứng nhận nào.')
    const bad = await mountWith(ChungNhanList, fakeClient({ listAll: problem('forbidden') }))
    expect(bad.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
  })
})

describe('ChungNhanDetail', () => {
  const sealed = rec({
    id: 'r1', seal_state: 'SEALED', is_owner: false, version: 3,
    data: { so_chung_nhan: '7/CN-CLB', ho_ten: 'Nguyễn Văn An', su_kien: 'Hội thảo', ngay_cap: '2026-11-10', email: 'a***@example.vn' },
  })
  const client = (over = {}) => fakeClient({ get: sealed, seal: sealInfo(), ...over })

  test('shows the fields by manifest label, the seal QR and the verify link', async () => {
    const c = client()
    const w = await mountWith(ChungNhanDetail, c, { id: 'r1' }, { roleStrings: CAN_BO })
    expect(c.get).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r1')
    expect(c.seal).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r1')
    expect(w.find('dl').text()).toContain('Họ và tên')
    expect(w.find('dl').text()).toContain('Nguyễn Văn An')
    expect(w.find('dl').text()).toContain('10/11/2026')
    expect(w.find('dl').text()).toContain('Email')
    expect(w.findComponent(SealQr).exists()).toBe(true)
    expect(w.findComponent(VerifyLink).exists()).toBe(true)
    expect(w.find('a[href="/chung-nhan/r1/in"]').text()).toBe('Trang in chứng nhận')
  })

  test('the print link only appears for a sealed certificate', async () => {
    const w = await mountWith(ChungNhanDetail, client({ get: rec({ id: 'r1', seal_state: 'NONE', data: {} }) }), { id: 'r1' })
    expect(w.find('a[href="/chung-nhan/r1/in"]').exists()).toBe(false)
  })

  test('the head can revoke and erase the email; a clerk sees neither', async () => {
    const head = await mountWith(ChungNhanDetail, client(), { id: 'r1' }, { roleStrings: TRUONG })
    const labels = head.findAll('button').map((b) => b.text())
    expect(labels).toContain('Thu hồi niêm phong')
    expect(labels).toContain('Xóa dữ liệu cá nhân')
    const clerk = await mountWith(ChungNhanDetail, client(), { id: 'r1' }, { roleStrings: CAN_BO })
    const clerkLabels = clerk.findAll('button').map((b) => b.text())
    expect(clerkLabels).not.toContain('Thu hồi niêm phong')
    expect(clerkLabels).not.toContain('Xóa dữ liệu cá nhân')
    expect(clerkLabels).not.toContain('Xác nhận đã rà dữ liệu cá nhân') // App B không có điều kiện pii_reviewed
  })

  test('revoke asks for a reason and calls the core once', async () => {
    const c = client({ revoke: rec({ seal_state: 'REVOKED' }) })
    const w = await mountWith(ChungNhanDetail, c, { id: 'r1' }, { roleStrings: TRUONG })
    await click(w, 'Thu hồi niêm phong')
    await w.find('select[name="reason_code"]').setValue('issued_in_error')
    await click(w, 'Xác nhận thu hồi')
    expect(c.revoke).toHaveBeenCalledTimes(1)
    expect(c.revoke).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r1', 'issued_in_error', undefined)
  })

  test('erasing the email sends the pii field and a reason', async () => {
    const c = client({ erasePii: rec() })
    const w = await mountWith(ChungNhanDetail, c, { id: 'r1' }, { roleStrings: TRUONG })
    await click(w, 'Xóa dữ liệu cá nhân')
    expect(w.find('[role=alertdialog]').text()).toContain('Email')
    await w.find('input[name="fields"]').setValue(true)
    await w.find('select[name="reason_code"]').setValue('data_subject_request')
    await click(w, 'Xác nhận xóa')
    expect(c.erasePii).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r1', ['email'], 'data_subject_request')
  })

  test('the owner can submit a draft for approval; the core decides the rest', async () => {
    const draft = rec({ id: 'r1', is_owner: true, seal_state: 'NONE', wf_state: null, data: { ho_ten: 'A', su_kien: 'S', ngay_cap: '2026-11-10' } })
    const c = fakeClient({ get: draft, start: rec({ id: 'r1', wf_state: 'running' }) })
    const w = await mountWith(ChungNhanDetail, c, { id: 'r1' })
    expect(w.text()).toContain('Chưa gửi duyệt')
    await click(w, 'Gửi duyệt')
    expect(c.start).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('Chờ duyệt')
    const running = await mountWith(ChungNhanDetail, fakeClient({ get: rec({ is_owner: true, wf_state: 'running' }) }), { id: 'r1' })
    expect(running.findAll('button').map((b) => b.text())).not.toContain('Gửi duyệt')
  })

  test('a record that cannot be read shows the problem with a reload button', async () => {
    const w = await mountWith(ChungNhanDetail, fakeClient({ get: [problem('not-found'), sealed], seal: sealInfo() }), { id: 'r1' })
    expect(w.find('[role=alert]').text()).toBe('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    await click(w, 'Tải lại')
    expect(w.text()).toContain('Nguyễn Văn An')
  })
})

// ---- trang in ------------------------------------------------------------------------------

describe('TrangIn', () => {
  const PUBLIC = { so_chung_nhan: '7/CN-CLB', ho_ten: 'Nguyễn A', su_kien: 'HT', ngay_cap: '2026-11-10' }

  test('print page renders only public fields and the scope statement', async () => {
    const c = fakeClient({ seal: sealInfo({ public_fields: PUBLIC }) })
    const w = await mountWith(TrangIn, c, { id: 'r1' })
    expect(w.text()).toMatch(/không phải chữ ký số/)
    expect(w.text()).not.toMatch(/@/)
    expect(c.seal).toHaveBeenCalledWith('chung-nhan', 'chung_nhan', 'r1')
    expect(c.get).not.toHaveBeenCalled() // không đọc bản ghi nên không thể lộ email
    expect(w.text()).toContain('7/CN-CLB')
    expect(w.text()).toContain('Nguyễn A')
    expect(w.text()).toContain('10/11/2026')
    expect(w.findComponent(SealQr).exists()).toBe(true)
  })

  test('the scope statement is the one in the App B README (spec 14), word for word', async () => {
    const readme = readFileSync(resolve(import.meta.dirname, '../../README.md'), 'utf8')
    const quote = readme.split('\n').filter((l) => l.startsWith('> ')).map((l) => l.slice(2)).join(' ').replaceAll('**', '')
    expect(quote.length).toBeGreaterThan(200)
    const w = await mountWith(TrangIn, fakeClient({ seal: sealInfo({ public_fields: PUBLIC }) }), { id: 'r1' })
    expect(w.find('.dx-scope').text()).toBe(quote)
  })

  test('only the manifest public fields are shown, even if the seal carries more', async () => {
    const w = await mountWith(TrangIn, fakeClient({ seal: sealInfo({ public_fields: { ...PUBLIC, email: 'an@example.vn', ghi_chu: 'bí mật' } }) }), { id: 'r1' })
    expect(w.text()).not.toContain('example.vn')
    expect(w.text()).not.toContain('bí mật')
    expect(w.text()).not.toMatch(/@/)
  })

  test('a revoked or pending seal is not printed as a valid certificate', async () => {
    const revoked = await mountWith(TrangIn, fakeClient({ seal: sealInfo({ seal_state: 'REVOKED', public_fields: PUBLIC }) }), { id: 'r1' })
    expect(revoked.text()).toContain('đã bị thu hồi')
    expect(revoked.text()).not.toContain('Nguyễn A')
    expect(revoked.findComponent(SealQr).exists()).toBe(false)
    const pending = await mountWith(TrangIn, fakeClient({ seal: sealInfo({ seal_state: 'SEAL_PENDING', public_fields: PUBLIC }) }), { id: 'r1' })
    expect(pending.text()).toContain('đang chờ niêm phong')
    expect(pending.text()).not.toContain('Nguyễn A')
  })

  test('shows the seal time in Vietnam time and "In" calls window.print()', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const w = await mountWith(TrangIn, fakeClient({ seal: sealInfo({ public_fields: PUBLIC, issued_at: '2026-11-02T03:00:00Z' }) }), { id: 'r1' })
    expect(w.text()).toContain('10:00 02/11/2026')
    expect(w.text()).toContain(sealInfo().verify_url)
    await click(w, 'In chứng nhận')
    expect(print).toHaveBeenCalledTimes(1)
    expect(w.findAll('button').find((b) => b.text() === 'In chứng nhận')!.classes()).toContain('dx-no-print')
  })

  test('print CSS is A4 landscape and hides the controls', () => {
    const css = readFileSync(resolve(import.meta.dirname, '../src/style.css'), 'utf8')
    expect(css).toMatch(/@page\s*\{[^}]*size:\s*A4 landscape/)
    expect(css).toMatch(/@media print/)
  })

  test('a seal that cannot be read shows the server problem', async () => {
    const w = await mountWith(TrangIn, fakeClient({ seal: problem('not-sealed') }), { id: 'r1' })
    expect(w.find('[role=alert]').text()).toBe('Hồ sơ chưa được niêm phong')
    expect(w.findComponent(SealQr).exists()).toBe(false)
  })
})
