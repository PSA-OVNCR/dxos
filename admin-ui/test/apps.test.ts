// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ApiError } from 'dxos-sdk-js'
import { fakeFetch } from 'dxos-sdk-js/testing'
import { describe, expect, test } from 'vitest'
import { ADMIN_API_KEY, createAdminApi, type PermissionDiff } from '../src/api'
import AppDiffView from '../src/views/AppDiffView.vue'
import AppsView from '../src/views/AppsView.vue'
import { APPS_OK, appRow, click, DIFF_OK, fakeApi, mountView } from './helpers'

const rowOf = (w: VueWrapper, id: string, version: string) => w.find(`tr[data-app="${id}"][data-version="${version}"]`)

describe('AppsView', () => {
  test('AppsView lists active and pending versions', async () => {
    const api = fakeApi()
    const w = await mountView(AppsView, api)
    expect(api.apps).toHaveBeenCalledTimes(1)
    const rows = w.findAll('tbody tr[data-app]')
    expect(rows.map((r) => [r.attributes('data-app'), r.attributes('data-version')])).toEqual([
      ['so-muon-sach', '1.0.0'], ['so-muon-sach', '1.1.0'],
    ])
    const active = rowOf(w, 'so-muon-sach', '1.0.0')
    expect(active.find('.dx-state').text()).toContain('Đang hoạt động')
    expect(active.find('.dx-state').classes()).toContain('dx-state-ok')
    const pending = rowOf(w, 'so-muon-sach', '1.1.0')
    expect(pending.find('.dx-state').text()).toContain('Chờ duyệt')
    expect(pending.find('.dx-state').classes()).toContain('dx-state-warn')
    // 02:30 UTC = 09:30 giờ Việt Nam; người nộp/duyệt chỉ là mã ẩn.
    expect(pending.text()).toContain('22/10/2026')
    expect(pending.text()).toContain('09:30')
    expect(pending.text()).toContain('1111aaaa2222')
    expect(pending.text()).toContain('—') // chưa có người duyệt
    expect(w.text()).not.toContain('0.9.0') // bản đã vô hiệu hóa ẩn theo mặc định
    // Lọc "Tất cả" hiện cả bản đã vô hiệu hóa.
    await w.find('select[name="status"]').setValue('all')
    expect(rowOf(w, 'test-app', '0.9.0').find('.dx-state').text()).toContain('Đã vô hiệu hóa')
    // Mỗi dòng có liên kết băm tới màn hình diff.
    expect(rowOf(w, 'so-muon-sach', '1.1.0').find('a').attributes('href')).toBe('#/apps/so-muon-sach/versions/1.1.0')
  })

  test('only the active version has a disable button; an empty list says so', async () => {
    const w = await mountView(AppsView, fakeApi())
    expect(rowOf(w, 'so-muon-sach', '1.0.0').findAll('button').map((b) => b.text())).toEqual(['Vô hiệu hóa'])
    expect(rowOf(w, 'so-muon-sach', '1.1.0').find('button').exists()).toBe(false)
    const empty = await mountView(AppsView, fakeApi({ apps: async () => [] }))
    expect(empty.text()).toContain('Chưa có ứng dụng nào')
  })

  test('disable asks for confirmation with the app id typed', async () => {
    const api = fakeApi()
    const w = await mountView(AppsView, api)
    expect(w.find('[role="alertdialog"]').exists()).toBe(false)
    await click(w, 'Vô hiệu hóa')
    const dialog = w.find('[role="alertdialog"]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.text()).toContain('so-muon-sach')
    const confirm = () => w.findAll('[role="alertdialog"] button').find((b) => b.text().trim() === 'Vô hiệu hóa ứng dụng')!
    expect(confirm().attributes('disabled')).toBeDefined()
    const input = w.find('[role="alertdialog"] input')
    await input.setValue('so-muon') // gõ thiếu
    expect(confirm().attributes('disabled')).toBeDefined()
    await input.setValue('so-muon-sach ') // thừa khoảng trắng vẫn khớp sau khi cắt
    expect(confirm().attributes('disabled')).toBeUndefined()
    await input.setValue('SO-MUON-SACH') // phân biệt hoa thường
    expect(confirm().attributes('disabled')).toBeDefined()
    expect(api.disableApp).not.toHaveBeenCalled()
    await input.setValue('so-muon-sach')
    await confirm().trigger('click')
    await flushPromises()
    expect(api.disableApp).toHaveBeenCalledTimes(1)
    expect(api.disableApp).toHaveBeenCalledWith('so-muon-sach')
    expect(w.find('[role="alertdialog"]').exists()).toBe(false)
    expect(w.find('[role="status"]').text()).toContain('so-muon-sach')
    expect(api.apps).toHaveBeenCalledTimes(2) // làm mới danh sách
  })

  test('cancelling the disable dialog calls nothing; a failure is shown through ProblemMessage', async () => {
    const api = fakeApi({
      disableApp: async () => { throw new ApiError(404, 'app-not-active', 'Application not active', undefined, null) },
    })
    const w = await mountView(AppsView, api)
    await click(w, 'Vô hiệu hóa')
    await click(w, 'Hủy')
    expect(w.find('[role="alertdialog"]').exists()).toBe(false)
    expect(api.disableApp).not.toHaveBeenCalled()
    await click(w, 'Vô hiệu hóa')
    await w.find('[role="alertdialog"] input').setValue('so-muon-sach')
    await click(w, 'Vô hiệu hóa ứng dụng')
    expect(api.disableApp).toHaveBeenCalledTimes(1)
    expect(w.find('.dx-problem').text()).toContain('chưa được kích hoạt')
  })

  test('a list error is shown through ProblemMessage with a reload button', async () => {
    let n = 0
    const w = await mountView(AppsView, fakeApi({
      apps: async () => { if (n++ === 0) throw new ApiError(502, 'http-502', 'Bad Gateway', undefined, null); return APPS_OK },
    }))
    expect(w.find('.dx-problem').text()).toContain('Dịch vụ tạm thời không sẵn sàng')
    await click(w, 'Tải lại')
    expect(w.find('.dx-problem').exists()).toBe(false)
    expect(w.findAll('tbody tr[data-app]')).toHaveLength(2)
  })
})

const PROPS = { id: 'so-muon-sach', version: '1.1.0' }

describe('AppDiffView', () => {
  test('AppDiffView renders diff lines as text (no v-html) and highlights floor changes', async () => {
    const evil = '<img src=x onerror=alert(1)>'
    const api = fakeApi({
      appDiff: async () => ({ ...DIFF_OK, roles_added: [evil], pii_reveal_roles: { old: ['quan-ly'], new: ['quan-ly', evil] } }),
    })
    const w = await mountView(AppDiffView, api, PROPS)
    expect(api.appDiff).toHaveBeenCalledWith('so-muon-sach', '1.1.0')
    // Văn bản, không phải HTML: không có phần tử <img>, chuỗi hiện nguyên văn.
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain(evil)
    expect(w.html()).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(w.find('h1').text()).toContain('so-muon-sach')
    expect(w.find('h1').text()).toContain('1.1.0')
    expect(w.text()).toContain('1.0.0') // so với bản đang hoạt động

    const floor = w.findAll('[data-floor="changed"]')
    expect(floor.map((l) => l.attributes('data-key'))).toEqual(['pii_reveal_roles', 'pii_erase_roles', 'verify'])
    for (const l of floor) {
      expect(l.classes()).toContain('dx-diff-floor')
      expect(l.text()).toContain('Đổi') // chữ, không chỉ màu
    }
    expect(floor[0]?.text()).toContain(evil)
    // Chính sách không đổi vẫn hiện nhưng không bị làm nổi.
    const seal = w.find('[data-key="seal"]')
    expect(seal.exists()).toBe(true)
    expect(seal.attributes('data-floor')).toBe('same')
    expect(seal.classes()).not.toContain('dx-diff-floor')
    // Phần thêm có chữ "Thêm".
    expect(w.find('[data-key="roles_added"]').text()).toContain('Thêm')
    expect(w.find('[data-key="collections_added"]').text()).toContain('phieu-muon')
    expect(w.find('[data-key="fields_added"]').text()).toContain('isbn')
    expect(w.find('[data-key="tasks"]').text()).toContain('duyet')
    expect(w.find('[data-key="bpmn_sha256"]').text()).toContain('cdcdcdcdcdcd')
  })

  test('the first version of an app is compared with nothing and says so', async () => {
    const w = await mountView(AppDiffView, fakeApi({
      appDiff: async () => ({
        ...DIFF_OK, against: null, pii_reveal_roles: { old: null, new: ['quan-ly'] }, seal: { old: null, new: null },
        verify: { old: null, new: null }, pii_erase_roles: { old: null, new: [] },
      }),
    }), PROPS)
    expect(w.text()).toContain('Chưa có bản đang hoạt động để so sánh')
    expect(w.find('[data-key="pii_reveal_roles"]').attributes('data-floor')).toBe('changed')
    expect(w.find('[data-key="pii_reveal_roles"]').text()).toContain('Mới') // chưa có bản cũ: "Mới", không phải "Đổi"
    expect(w.find('[data-key="pii_reveal_roles"]').text()).not.toContain('Đổi')
    expect(w.find('[data-key="pii_erase_roles"]').attributes('data-floor')).toBe('changed') // [] khác "chưa có"
    expect(w.find('[data-key="seal"]').attributes('data-floor')).toBe('same')
  })

  test('approve posts the version once and refreshes; the button only exists for pending versions', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const api = fakeApi({
      approveApp: async (id, version) => {
        await gate
        return { app_id: id, version, status: 'ACTIVE', manifest_sha256: 'ab', self_approved: false, deployment_id: null, rendered_sha256: null }
      },
    })
    const w = await mountView(AppDiffView, api, PROPS)
    const btn = () => w.findAll('button').find((b) => b.text().trim() === 'Duyệt phiên bản này')!
    expect(w.find('[data-field="status"]').text()).toContain('Chờ duyệt')
    await btn().trigger('click')
    await btn().trigger('click')
    expect(btn().attributes('disabled')).toBeDefined()
    expect(api.approveApp).toHaveBeenCalledTimes(1)
    expect(api.approveApp).toHaveBeenCalledWith('so-muon-sach', '1.1.0')
    release()
    await flushPromises()
    expect(api.approveApp).toHaveBeenCalledTimes(1)
    expect(w.find('[role="status"]').text()).toContain('1.1.0')
    expect(api.apps).toHaveBeenCalledTimes(2)

    const active = await mountView(AppDiffView, fakeApi(), { id: 'so-muon-sach', version: '1.0.0' })
    expect(active.findAll('button').some((b) => b.text().includes('Duyệt'))).toBe(false)
    expect(active.find('[data-field="status"]').text()).toContain('Đang hoạt động')
  })

  test('approve warns when the server reports a self-approval (self-approval mode)', async () => {
    const w = await mountView(AppDiffView, fakeApi({
      approveApp: async (id, version) => ({
        app_id: id, version, status: 'ACTIVE', manifest_sha256: 'ab', self_approved: true, deployment_id: null, rendered_sha256: null,
      }),
    }), PROPS)
    await click(w, 'Duyệt phiên bản này')
    expect(w.find('[role="status"]').text()).toContain('chính người nộp')
  })

  test("approve by the submitter shows the server's four-eyes problem message", async () => {
    // Đi qua AdminApi thật: SPA không tự chặn, máy chủ trả 403 `forbidden` + reason self_approval.
    const f = fakeFetch([
      { json: APPS_OK },
      { json: DIFF_OK },
      {
        status: 403,
        problem: {
          type: 'https://dxos.dev/problems/forbidden', title: 'Forbidden', status: 403,
          detail: 'approver must differ from submitter (four eyes)', reason: 'self_approval',
        },
      },
    ])
    const api = createAdminApi({ getToken: async () => 'tok', fetch: f })
    const w = mount(AppDiffView, { props: PROPS, global: { provide: { [ADMIN_API_KEY as symbol]: api } } })
    await flushPromises()
    await click(w, 'Duyệt phiên bản này')
    const post = f.calls.find((c) => c.method === 'POST')!
    expect(post.url).toBe('/admin/v1/apps/so-muon-sach:approve')
    expect(post.body).toBe('{"version":"1.1.0"}')
    const text = w.find('.dx-problem').text()
    expect(text).toContain('bốn mắt')
    expect(text).not.toContain('không có quyền quản trị')
    expect(text).not.toBe('Bạn không có quyền thực hiện thao tác này')
    // Lỗi xong thì có thể bấm lại (không khóa vĩnh viễn).
    expect(w.findAll('button').find((b) => b.text().trim() === 'Duyệt phiên bản này')!.attributes('disabled')).toBeUndefined()
  })

  test('an approve failure from the server (not pending any more) is shown through ProblemMessage', async () => {
    const w = await mountView(AppDiffView, fakeApi({
      approveApp: async () => { throw new ApiError(409, 'app-version-not-pending', 'Phiên bản này không còn chờ duyệt', undefined, null) },
    }), PROPS)
    await click(w, 'Duyệt phiên bản này')
    expect(w.find('.dx-problem').text()).toContain('không còn chờ duyệt')
  })

  test('a diff error is shown through ProblemMessage (no diff lines)', async () => {
    const w = await mountView(AppDiffView, fakeApi({
      appDiff: async () => { throw new ApiError(404, 'not-found', 'x', undefined, null) },
    }), PROPS)
    expect(w.find('.dx-problem').text()).toContain('Không tìm thấy')
    expect(w.find('[data-key]').exists()).toBe(false)
  })

  test('a version that is not in the list still shows its diff but offers no approval', async () => {
    const w = await mountView(AppDiffView, fakeApi({ apps: async () => [appRow({ version: '9.9.9' })] }), PROPS)
    expect(w.find('[data-key="roles_added"]').exists()).toBe(true)
    expect(w.findAll('button').some((b) => b.text().includes('Duyệt'))).toBe(false)
  })

  test('changing the route params reloads the diff and approve posts the version that is displayed', async () => {
    const diffs: Record<string, PermissionDiff> = {
      '1.1.0': { ...DIFF_OK, version: '1.1.0', roles_added: ['vai-tro-cua-1-1-0'] },
      '1.2.0': { ...DIFF_OK, version: '1.2.0', roles_added: ['vai-tro-cua-1-2-0'] },
    }
    const rows = [
      appRow({ version: '1.1.0', status: 'PENDING' }), appRow({ version: '1.2.0', status: 'PENDING' }),
      appRow({ version: '1.0.0', status: 'ACTIVE' }),
    ]
    let releaseSecond!: () => void
    const gate = new Promise<void>((r) => { releaseSecond = r })
    const api = fakeApi({
      apps: async () => rows,
      appDiff: async (_id, v) => {
        if (v === '1.2.0') await gate // phản hồi của phiên bản mới về chậm
        return diffs[v]!
      },
    })
    const w = await mountView(AppDiffView, api, { id: 'so-muon-sach', version: '1.1.0' })
    expect(w.text()).toContain('vai-tro-cua-1-1-0')

    await w.setProps({ version: '1.2.0' })
    await flushPromises()
    // Đang chờ diff mới: không còn diff cũ dưới tiêu đề mới, và không thể duyệt cái chưa thấy.
    expect(w.find('h1').text()).toContain('1.2.0')
    expect(w.text()).not.toContain('vai-tro-cua-1-1-0')
    expect(w.findAll('button').some((b) => b.text().includes('Duyệt'))).toBe(false)
    await w.vm.$nextTick()
    releaseSecond()
    await flushPromises()
    expect(api.appDiff).toHaveBeenLastCalledWith('so-muon-sach', '1.2.0')
    expect(w.text()).toContain('vai-tro-cua-1-2-0')
    expect(w.text()).not.toContain('vai-tro-cua-1-1-0')

    await click(w, 'Duyệt phiên bản này')
    expect(api.approveApp).toHaveBeenCalledTimes(1)
    expect(api.approveApp).toHaveBeenCalledWith('so-muon-sach', '1.2.0')
  })

  test('a slow response for the previous version is dropped after the params change', async () => {
    let releaseFirst!: () => void
    const gate = new Promise<void>((r) => { releaseFirst = r })
    const api = fakeApi({
      appDiff: async (_id, v) => {
        if (v === '1.1.0') await gate
        return { ...DIFF_OK, version: v, roles_added: [`vai-tro-${v}`] }
      },
      apps: async () => [appRow({ version: '1.1.0', status: 'PENDING' }), appRow({ version: '1.2.0', status: 'PENDING' })],
    })
    const w = await mountView(AppDiffView, api, { id: 'so-muon-sach', version: '1.1.0' })
    await w.setProps({ version: '1.2.0' })
    await flushPromises()
    expect(w.text()).toContain('vai-tro-1.2.0')
    releaseFirst() // diff của 1.1.0 về muộn
    await flushPromises()
    expect(w.text()).toContain('vai-tro-1.2.0')
    expect(w.text()).not.toContain('vai-tro-1.1.0')
    await click(w, 'Duyệt phiên bản này')
    expect(api.approveApp).toHaveBeenCalledWith('so-muon-sach', '1.2.0')
  })
})
