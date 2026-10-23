// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { fakeClient } from 'dxos-sdk-js/testing'
import { createLoginGuard, createSession, SESSION_KEY } from 'dxos-sdk-js/vue'
import { describe, expect, test } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../src/App.vue'
import { ADMIN_API_KEY } from '../src/api'
import { boot } from '../src/boot'
import { makeRouter, routes } from '../src/router'
import { ADMIN_VIEW, APP, connect, LOGIN_MARKER } from '../src/session'
import { click, fakeApi, fakeAuth, MemoryStorage } from './helpers'

function sessionFor(auth = fakeAuth()) {
  const guard = createLoginGuard(auth, { marker: LOGIN_MARKER, storage: new MemoryStorage() })
  const session = createSession({ app: APP, auth, client: fakeClient({}), guard })
  session.view.value = ADMIN_VIEW
  session.roles.value = ['dxos-admin']
  return { session, auth }
}

describe('router', () => {
  test('hash routes health, ledger, apps (+ version diff) and quarantine exist; anything else goes to health', async () => {
    expect(routes.map((r) => r.path)).toEqual([
      '/', '/health', '/ledger', '/apps', '/apps/:id/versions/:version', '/quarantine', '/:rest(.*)*',
    ])
    const router = makeRouter(createMemoryHistory())
    await router.push('/khong-co')
    expect(router.currentRoute.value.path).toBe('/health')
    await router.push('/ledger')
    expect(router.currentRoute.value.name).toBe('ledger')
    await router.push('/apps/so-muon-sach/versions/1.1.0')
    expect(router.currentRoute.value.name).toBe('app-diff')
    expect(router.currentRoute.value.params).toEqual({ id: 'so-muon-sach', version: '1.1.0' })
    await router.push('/apps/chi-co-id')                    // thiếu phần version: về health
    expect(router.currentRoute.value.path).toBe('/health')
  })
})

describe('admin shell', () => {
  test('header shows the user, the admin role and logout; navigation lists the four admin screens; no manifest call', async () => {
    const { session, auth } = sessionFor()
    const router = makeRouter(createMemoryHistory())
    await router.push('/health')
    const api = fakeApi()
    const w = mount(App, { global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session, [ADMIN_API_KEY as symbol]: api } } })
    await flushPromises()
    expect(w.find('header').text()).toContain('Quản trị viên 1')
    expect(w.find('header').text()).toContain('Quản trị viên')
    expect(w.find('header').text()).toContain('Quản trị DX-OS')
    expect(w.findAll('nav a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['Sức khỏe hệ thống', '/health'], ['Sổ cái', '/ledger'], ['Ứng dụng', '/apps'], ['Cách ly', '/quarantine'],
    ])
    expect(w.find('[data-dep="db"]').exists()).toBe(true)
    await click(w, 'Sổ cái')
    expect(w.find('[data-field="tree_size"]').exists()).toBe(true)
    await click(w, 'Ứng dụng')
    expect(w.find('tbody tr[data-app]').exists()).toBe(true)
    await click(w, 'Cách ly')
    expect(w.find('[data-quarantine]').exists()).toBe(true)
    expect(api.apps).toHaveBeenCalledTimes(1)
    expect(api.quarantine).toHaveBeenCalledTimes(1)
    await click(w, 'Đăng xuất')
    expect(auth.logout).toHaveBeenCalledTimes(1)
    expect(api.health).toHaveBeenCalledTimes(1)
  })
})

describe('connect / boot', () => {
  test('connect marks the session as the admin app and takes the admin role from the token', () => {
    const s = connect(fakeAuth())
    expect(s.view.value?.app.name).toBe('Quản trị DX-OS')
    expect(s.roles.value).toEqual(['dxos-admin'])
    expect(connect(fakeAuth({ roles: () => ['app:x:y'] })).roles.value).toEqual([])
  })

  test('boot mounts the app after init with the admin routes', async () => {
    document.body.innerHTML = '<div id="app"></div>'
    const { session, auth } = sessionFor()
    await boot({ auth, mount: '#app', connect: () => session, makeRouter: () => makeRouter(createMemoryHistory()) })
    await flushPromises()
    expect(document.querySelector('#app')?.textContent).toContain('Sức khỏe hệ thống')
    document.body.innerHTML = ''
  })
})
