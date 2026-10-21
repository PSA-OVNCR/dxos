// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { createLoginGuard, createSession, SESSION_KEY } from 'dxos-sdk-js/vue'
import { fakeClient } from 'dxos-sdk-js/testing'
import { describe, expect, test } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../src/App.vue'
import { boot } from '../src/boot'
import { makeRouter } from '../src/router'
import { APP, connect, LOGIN_MARKER } from '../src/session'
import { B_VIEW, click, fakeAuth, MemoryStorage } from './helpers'

async function mountApp(roleStrings: string[]) {
  const auth = fakeAuth({ roleStrings })
  const client = fakeClient({ manifest: B_VIEW, listAll: [] })
  const guard = createLoginGuard(auth, { marker: LOGIN_MARKER, storage: new MemoryStorage() })
  const session = createSession({ app: APP, auth, client, guard })
  const router = makeRouter(createMemoryHistory())
  await router.push('/')
  const w = mount(App, { global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
  await flushPromises()
  return { w, auth, client }
}

describe('App B shell', () => {
  test('header shows the user, the role names and a logout button; the manifest is fetched once', async () => {
    const { w, auth, client } = await mountApp(['app:chung-nhan:can_bo_clb', 'app:phong-ho-so:chuyen_vien'])
    expect(w.find('header').text()).toContain('Trần Thị B')
    expect(w.find('header').text()).toContain('Cán bộ CLB')
    expect(w.find('header').text()).toContain('Chứng nhận số')
    await click(w, 'Đăng xuất')
    expect(auth.logout).toHaveBeenCalledTimes(1)
    expect(client.manifest).toHaveBeenCalledTimes(1)
    expect(client.manifest).toHaveBeenCalledWith('chung-nhan')
  })

  test('navigation shows import and batch approval only to the roles that can use them (convenience)', async () => {
    const links = (w: { findAll: (s: string) => { text: () => string; attributes: (n: string) => string | undefined }[] }) =>
      w.findAll('nav a').map((a) => [a.text(), a.attributes('href')])
    const base = [['Danh sách chứng nhận', '/']]
    expect(links((await mountApp(['app:chung-nhan:can_bo_clb'])).w)).toEqual([...base, ['Nhập từ CSV', '/nhap-csv']])
    expect(links((await mountApp(['app:chung-nhan:truong_clb'])).w)).toEqual([...base, ['Duyệt theo lô', '/duyet-lo']])
  })
})

describe('boot', () => {
  test('mounts the app after init, using the App B session and routes', async () => {
    document.body.innerHTML = '<div id="app"></div>'
    const auth = fakeAuth()
    const client = fakeClient({ manifest: B_VIEW, listAll: [] })
    const guard = createLoginGuard(auth, { marker: LOGIN_MARKER, storage: new MemoryStorage() })
    await boot({
      auth, mount: '#app', connect: () => createSession({ app: APP, auth, client, guard }),
      makeRouter: () => makeRouter(createMemoryHistory()),
    })
    await flushPromises()
    expect(document.querySelector('#app')?.textContent).toContain('Danh sách chứng nhận')
    expect(typeof connect).toBe('function')
    document.body.innerHTML = ''
  })
})
