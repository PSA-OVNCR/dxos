// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils'
import { fakeClient, problem } from 'dxos-sdk-js/testing'
import { describe, expect, test } from 'vitest'
import HopViec from '../src/views/HopViec.vue'
import { click, mountWith, rec, task } from './helpers'

const DONE = { record: rec(), seal_state: 'NONE' as const, seal_id: null }

describe('HopViec (hộp việc)', () => {
  test('inbox loads each task record and completes with a fresh version', async () => {
    const c = fakeClient({
      tasks: [task({ task_key: 'duyet_noi_dung', record_id: 'r1' })],
      get: rec({ id: 'r1', version: 4, data: { so_hieu: '02/QĐ-SM', trich_yeu: 'Bổ nhiệm trưởng phòng' } }),
      complete: DONE,
    })
    const w = await mountWith(HopViec, c)
    expect(c.get).toHaveBeenCalledWith('phong-ho-so', 'c', 'r1')
    expect(w.text()).toContain('02/QĐ-SM')
    expect(w.text()).toContain('Bổ nhiệm trưởng phòng')
    await click(w, 'Duyệt')
    expect(c.complete).toHaveBeenCalledTimes(1)
    expect(c.complete).toHaveBeenCalledWith('phong-ho-so', expect.objectContaining({ record_id: 'r1' }), 'approve', undefined)
  })

  test('shows the step name, the creation time in Vietnam time and a link to the record', async () => {
    const c = fakeClient({
      tasks: [task({ name: 'Duyệt nội dung', created: '2026-10-21T13:14:30.393+07:00', record_id: 'r7' })],
      get: rec({ id: 'r7' }),
    })
    const w = await mountWith(HopViec, c)
    expect(w.find('h1').text()).toBe('Hộp việc')
    expect(w.find('li h2').text()).toBe('Duyệt nội dung')
    expect(w.text()).toContain('13:14 21/10/2026')
    expect(w.find('li a').attributes('href')).toBe('/van-ban/r7')
  })

  test('after a completion the inbox is reloaded from the server and the outcome is stated', async () => {
    const c = fakeClient({
      tasks: [[task({ task_id: 't1' })], [task({ task_id: 't2', name: 'Ban hành' })]],
      get: rec(),
      complete: { record: rec(), seal_state: 'NONE', seal_id: null },
    })
    const w = await mountWith(HopViec, c)
    await click(w, 'Duyệt')
    expect(c.tasks).toHaveBeenCalledTimes(2)
    expect(w.findAll('li h2').map((h) => h.text())).toEqual(['Ban hành'])
    expect(w.text()).toContain('Đã duyệt văn bản.')
  })

  test.each([
    ['SEALED', 'Văn bản đã được niêm phong.'],
    ['SEAL_PENDING', 'Văn bản đang chờ niêm phong.'],
  ])('a completion that reaches %s says so', async (state, text) => {
    const c = fakeClient({
      tasks: [[task()], []], get: rec(), complete: { record: rec(), seal_state: state as 'SEALED', seal_id: 'X' },
    })
    const w = await mountWith(HopViec, c)
    await click(w, 'Duyệt')
    expect(w.text()).toContain(text)
    expect(w.text()).toContain('Không có việc nào đang chờ bạn.')
  })

  test('reject asks for confirmation first and states that the note is not stored', async () => {
    const c = fakeClient({ tasks: [[task()], []], get: rec(), complete: DONE })
    const w = await mountWith(HopViec, c)
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
    await click(w, 'Trả lại')
    expect(c.complete).not.toHaveBeenCalled()
    expect(w.find('[role=alertdialog]').exists()).toBe(true)
    expect(w.text()).toContain('Ghi chú không được lưu')
    await click(w, 'Xác nhận trả lại')
    expect(c.complete).toHaveBeenCalledTimes(1)
    expect(c.complete.mock.calls[0]?.[2]).toBe('reject')
    expect(w.text()).toContain('Đã trả lại văn bản.')
  })

  test('the reject note is a labelled field, trimmed, sent as the comment, and empty means no comment', async () => {
    const c = fakeClient({ tasks: [[task()], [task()], []], get: rec(), complete: DONE })
    const w = await mountWith(HopViec, c)
    await click(w, 'Trả lại')
    const area = w.find('textarea[name="comment"]')
    expect(area.attributes('maxlength')).toBe('1000')
    const label = w.find(`label[for="${area.attributes('id')}"]`)
    expect(label.text()).toBe('Ghi chú (không bắt buộc)')
    await area.setValue('  Thiếu căn cứ pháp lý  ')
    await click(w, 'Xác nhận trả lại')
    expect(c.complete.mock.calls[0]?.[3]).toBe('Thiếu căn cứ pháp lý')
    await click(w, 'Trả lại')
    await w.find('textarea[name="comment"]').setValue('   ')
    await click(w, 'Xác nhận trả lại')
    expect(c.complete.mock.calls[1]?.[3]).toBeUndefined()
  })

  test('cancelling the reject dialog does not call the API', async () => {
    const c = fakeClient({ tasks: [task()], get: rec(), complete: DONE })
    const w = await mountWith(HopViec, c)
    await click(w, 'Trả lại')
    await click(w, 'Hủy')
    expect(w.find('[role=alertdialog]').exists()).toBe(false)
    expect(c.complete).not.toHaveBeenCalled()
  })

  test('409 task-gone shows reload hint and does not retry', async () => {
    const c = fakeClient({ tasks: [task()], get: rec(), complete: problem('task-gone') })
    const w = await mountWith(HopViec, c)
    await click(w, 'Duyệt')
    expect(w.find('[role=alert]').text()).toBe('Dữ liệu đã thay đổi, hãy tải lại')
    expect(w.text()).toMatch(/tải lại/)
    expect(c.complete).toHaveBeenCalledTimes(1)
    expect(c.tasks).toHaveBeenCalledTimes(1) // không tự tải lại, người dùng chủ động
    await click(w, 'Tải lại')
    expect(c.tasks).toHaveBeenCalledTimes(2)
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(c.complete).toHaveBeenCalledTimes(1)
  })

  test('a 409 on reject closes the dialog and keeps the problem visible', async () => {
    const c = fakeClient({ tasks: [task()], get: rec(), complete: problem('version-conflict') })
    const w = await mountWith(HopViec, c)
    await click(w, 'Trả lại')
    await click(w, 'Xác nhận trả lại')
    expect(w.find('[role=alert]').text()).toBe('Dữ liệu đã thay đổi, hãy tải lại')
    expect(c.complete).toHaveBeenCalledTimes(1)
  })

  test('ban_hanh guard pii_reviewed explains who must act', async () => {
    const c = fakeClient({
      tasks: [task({ task_key: 'ban_hanh' })], get: rec(),
      complete: problem('guard-failed', { reason: 'pii_not_reviewed' }),
    })
    const w = await mountWith(HopViec, c)
    await click(w, 'Duyệt')
    expect(w.text()).toMatch(/chưa xác nhận đã rà dữ liệu cá nhân/)
    expect(c.complete).toHaveBeenCalledTimes(1)
  })

  test('a double click completes once', async () => {
    let release: (v: typeof DONE) => void = () => {}
    const pending = new Promise<typeof DONE>((res) => { release = res })
    const c = fakeClient({ tasks: [[task()], []], get: rec(), complete: () => pending })
    const w = await mountWith(HopViec, c)
    const btn = w.findAll('button').find((b) => b.text() === 'Duyệt')!
    await btn.trigger('click')
    await btn.trigger('click')
    expect(c.complete).toHaveBeenCalledTimes(1)
    release(DONE)
    await flushPromises()
    expect(c.complete).toHaveBeenCalledTimes(1)
  })

  test('empty inbox and a failing inbox', async () => {
    const empty = await mountWith(HopViec, fakeClient({ tasks: [] }))
    expect(empty.text()).toContain('Không có việc nào đang chờ bạn.')
    const bad = await mountWith(HopViec, fakeClient({ tasks: problem('forbidden') }))
    expect(bad.find('[role=alert]').text()).toBe('Bạn không có quyền thực hiện thao tác này')
    expect(bad.find('li').exists()).toBe(false)
  })

  test('a record that cannot be read does not hide the other tasks', async () => {
    const c = fakeClient({
      tasks: [task({ task_id: 'a', record_id: 'ra' }), task({ task_id: 'b', record_id: 'rb', name: 'Ban hành' })],
      get: (_a: string, _c: string, id: string) => (id === 'ra' ? Promise.reject(problem('not-found')) : Promise.resolve(rec({ id: 'rb', data: { trich_yeu: 'Còn đọc được' } }))),
    })
    const w = await mountWith(HopViec, c)
    expect(w.findAll('li')).toHaveLength(2)
    expect(w.text()).toContain('Không tìm thấy dữ liệu hoặc bạn không có quyền xem')
    expect(w.text()).toContain('Còn đọc được')
  })

  test('a slow older load cannot overwrite a newer one', async () => {
    let releaseOld: (v: ReturnType<typeof task>[]) => void = () => {}
    const old = new Promise<ReturnType<typeof task>[]>((res) => { releaseOld = res })
    let calls = 0
    const c = fakeClient({
      tasks: () => (++calls === 1 ? old : Promise.resolve([task({ task_id: 'new', name: 'Mới' })])),
      get: rec(),
    })
    const w = await mountWith(HopViec, c)
    await click(w, 'Tải lại')
    releaseOld([task({ task_id: 'old', name: 'Cũ' })])
    await flushPromises()
    expect(w.findAll('li h2').map((h) => h.text())).toEqual(['Mới'])
  })
})
