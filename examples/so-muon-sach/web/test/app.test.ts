// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import type { DxosAuth, ManifestView } from 'dxos-sdk-js'
import { fakeClient, rec, task, type FakeClient } from 'dxos-sdk-js/testing'
import { createLoginGuard, createSession, SESSION_KEY } from 'dxos-sdk-js/vue'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../src/App.vue'
import { makeRouter } from '../src/router'
import { APP, BASE, COL } from '../src/session'
import manifestView from './fixtures/manifest-view.json'

// Thân `GET /api/v1/apps/so-muon-sach/manifest` do lõi trả; tests/apps/test_app_manifests.py so khớp tệp này với
// manifest.yaml nên đây không phải schema chép tay.
const VIEW = manifestView as unknown as ManifestView
const FIELDS = VIEW.collections[COL]!.fields

class Memory {
  private readonly m = new Map<string, string>()
  getItem(k: string): string | null { return this.m.get(k) ?? null }
  setItem(k: string, v: string): void { this.m.set(k, v) }
  removeItem(k: string): void { this.m.delete(k) }
}

async function mountApp(roles: string[], client: FakeClient, route = '/') {
  const auth = {
    init: vi.fn(async () => true), login: vi.fn(async () => {}), logout: vi.fn(async () => {}),
    token: async () => 'tok', profile: () => ({ username: 'u', name: 'Nguyễn Văn An' }),
    roles: () => roles.map((r) => `app:so-muon-sach:${r}`),
  } as unknown as DxosAuth
  const guard = createLoginGuard(auth, { marker: 'test', storage: new Memory() })
  const session = createSession({ app: APP, auth, client, guard })
  const router = makeRouter(createMemoryHistory())
  await router.push(route)
  const w = mount(App, { global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
  await flushPromises()
  return w
}

const clientWith = (over: Parameters<typeof fakeClient>[0] = {}) => fakeClient({ manifest: VIEW, listAll: [], ...over })

describe('so-muon-sach web', () => {
  test('the form is generated from the manifest: four inputs (no so_phieu), labels taken from the manifest', async () => {
    const w = await mountApp(['ban_doc'], clientWith())
    const inputs = w.findAll('form input')
    expect(inputs.map((i) => i.attributes('name'))).toEqual(['ten_sach', 'nguoi_muon', 'ngay_muon', 'email'])
    expect(w.find('input[name="so_phieu"]').exists()).toBe(false)
    for (const input of inputs) {
      const name = input.attributes('name')!
      const label = w.find(`label[for="${input.attributes('id')}"]`)
      expect(label.exists(), name).toBe(true)
      expect(label.text().replace(/\s*\*$/, '')).toBe(FIELDS[name]!.label)
    }
    expect(w.find('input[name="ngay_muon"]').attributes('type')).toBe('date')
    expect(w.find('input[name="ten_sach"]').attributes('required')).toBeDefined()
    expect(w.find('input[name="email"]').attributes('required')).toBeUndefined()
  })

  test('submitting creates the loan slip through the SDK client and reloads the list', async () => {
    const client = clientWith({ create: rec({ id: 'p1' }) })
    const w = await mountApp(['ban_doc'], client)
    await w.find('input[name="ten_sach"]').setValue('Dế Mèn phiêu lưu ký')
    await w.find('input[name="nguoi_muon"]').setValue('Nguyễn Văn An')
    await w.find('input[name="ngay_muon"]').setValue('2026-11-02')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(client.create).toHaveBeenCalledWith(APP, COL, {
      ten_sach: 'Dế Mèn phiêu lưu ký', nguoi_muon: 'Nguyễn Văn An', ngay_muon: '2026-11-02',
    })
    expect(client.listAll).toHaveBeenCalledTimes(2)
  })

  test('a refused create shows the core problem and keeps what the user typed', async () => {
    const client = clientWith({ create: new Error('boom') })
    const w = await mountApp(['ban_doc'], client)
    await w.find('input[name="ten_sach"]').setValue('Sách')
    await w.find('input[name="nguoi_muon"]').setValue('An')
    await w.find('input[name="ngay_muon"]').setValue('2026-11-02')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect((w.find('input[name="ten_sach"]').element as HTMLInputElement).value).toBe('Sách')
  })

  test('the list takes its columns and labels from the manifest and never shows personal data', async () => {
    const rows = [rec({ id: 'a', data: { so_phieu: '1/PM', ten_sach: 'Truyện Kiều', nguoi_muon: '•••', ngay_muon: '2026-11-02', email: '•••' } })]
    const w = await mountApp(['ban_doc'], clientWith({ listAll: rows }))
    const heads = w.findAll('th').map((t) => t.text())
    expect(heads.slice(0, 3)).toEqual(['Số phiếu', 'Tên sách', 'Ngày mượn'])
    expect(heads).not.toContain(FIELDS.nguoi_muon!.label)
    expect(heads).not.toContain(FIELDS.email!.label)
    const cells = w.findAll('tbody tr')[0]!.findAll('td').map((t) => t.text())
    expect(cells.slice(0, 3)).toEqual(['1/PM', 'Truyện Kiều', '02/11/2026'])
    expect(w.text()).not.toContain('•••')
  })

  test('only an unsent slip has a "Gửi duyệt" button, which starts the workflow', async () => {
    const before = [rec({ id: 'a', data: { ten_sach: 'A' } }), rec({ id: 'b', wf_state: 'running', data: { ten_sach: 'B' } })]
    const after = [rec({ id: 'a', wf_state: 'running', data: { ten_sach: 'A' } }), before[1]!]
    const client = clientWith({ listAll: [before, after], start: rec({ id: 'a', wf_state: 'running' }) })
    const w = await mountApp(['ban_doc'], client)
    const buttons = w.findAll('button').filter((b) => b.text() === 'Gửi duyệt')
    expect(buttons).toHaveLength(1)
    await buttons[0]!.trigger('click')
    await flushPromises()
    expect(client.start).toHaveBeenCalledWith(APP, COL, 'a')
    expect(w.findAll('button').filter((b) => b.text() === 'Gửi duyệt')).toHaveLength(0)
    expect(w.findAll('.dx-status').map((e) => e.text())).toEqual(['Chờ thủ thư duyệt', 'Chờ thủ thư duyệt'])
  })

  test('a sealed slip shows the SDK seal panel (QR and verify link)', async () => {
    const sealed = rec({ id: 's', seal_state: 'SEALED', data: { ten_sach: 'S' } })
    const client = clientWith({ listAll: [sealed], seal: { seal_id: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', seal_state: 'SEALED', issued_at: null, key_version: 1, public_fields: {}, verify_url: 'https://dxos.test/apps/verify/#ABCDEFGHIJKLMNOPQRSTUVWXYZ' } })
    const w = await mountApp(['ban_doc'], client)
    expect(client.seal).toHaveBeenCalledWith(APP, COL, 's')
    expect(w.text()).toContain('Đã niêm phong')
  })

  test('the inbox offers the decisions the manifest allows and completes the task through the client', async () => {
    const t = task({ task_id: 't1', task_key: 'duyet_muon', record_id: 'a', collection: COL })
    const client = clientWith({
      tasks: [t], get: rec({ id: 'a', data: { ten_sach: 'Truyện Kiều' } }),
      complete: { record: rec({ id: 'a' }), seal_state: 'SEALED', seal_id: 'x' },
    })
    const w = await mountApp(['thu_thu'], client, '/duyet')
    expect(w.text()).toContain('Truyện Kiều')
    const labels = w.findAll('li button').map((b) => b.text())
    expect(labels).toEqual(['Duyệt', 'Từ chối'])
    await w.findAll('li button')[0]!.trigger('click')
    await flushPromises()
    expect(client.complete).toHaveBeenCalledWith(APP, t, 'approve')
  })

  test('navigation shows the inbox only to the task role (convenience; the core decides)', async () => {
    const links = async (roles: string[]) => (await mountApp(roles, clientWith())).findAll('nav a').map((a) => a.text())
    expect(await links(['ban_doc'])).toEqual(['Phiếu mượn'])
    expect(await links(['thu_thu'])).toEqual(['Phiếu mượn', 'Hộp việc'])
  })
})

describe('so-muon-sach packaging and size', () => {
  test('is served under /apps/so-muon-sach/ with a hash router', () => {
    expect(BASE).toBe('/apps/so-muon-sach/')
    expect(readFileSync(resolve(import.meta.dirname, '../vite.config.ts'), 'utf8')).toContain(`base: '${BASE}'`)
    expect(readFileSync(resolve(import.meta.dirname, '../src/router.ts'), 'utf8')).toContain('createWebHashHistory')
  })

  test('team code stays under 150 lines (.ts/.vue under src, no blanks or comments)', () => {
    const src = resolve(import.meta.dirname, '../src')
    const files = (readdirSync(src, { recursive: true }) as string[]).filter((f) => /\.(ts|vue)$/.test(f))
    expect(files.length).toBeGreaterThan(3)
    const count = files.reduce((n, f) => {
      const text = readFileSync(resolve(src, f), 'utf8').replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
      return n + text.split('\n').filter((l) => l.trim() !== '' && !l.trim().startsWith('//')).length
    }, 0)
    expect(count).toBeLessThanOrEqual(150)
  })
})
