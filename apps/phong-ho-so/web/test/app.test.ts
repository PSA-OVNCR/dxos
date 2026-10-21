// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { fakeClient, fakeFetch, problem } from 'dxos-sdk-js/testing'
import { describe, expect, test } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../src/App.vue'
import { makeRouter } from '../src/router'
import { createClient, createLoginGuard, createSession, SESSION_KEY } from '../src/session'
import { A_VIEW, click, fakeAuth, MemoryStorage } from './helpers'

async function mountApp(client = fakeClient({ manifest: A_VIEW, listAll: [] }), roleStrings = ['app:phong-ho-so:chuyen_vien', 'app:phong-ho-so:van_thu']) {
  const auth = fakeAuth({ roleStrings })
  const guard = createLoginGuard(auth, { storage: new MemoryStorage() })
  const session = createSession({ auth, client, guard })
  const router = makeRouter(createMemoryHistory())
  await router.push('/')
  const w = mount(App, { global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
  await flushPromises()
  return { w, auth, guard, client, session }
}

describe('App shell', () => {
  test('header shows the user, roles and a logout button; the manifest is fetched once', async () => {
    const { w, auth, client } = await mountApp()
    expect(w.find('header').text()).toContain('Nguyễn Văn A')
    expect(w.find('header').text()).toContain('Chuyên viên, Văn thư')
    expect(w.find('header').text()).toContain('Phòng hồ sơ số')
    await click(w, 'Đăng xuất')
    expect(auth.logout).toHaveBeenCalledTimes(1)
    expect(client.manifest).toHaveBeenCalledTimes(1)
    expect(client.manifest).toHaveBeenCalledWith('phong-ho-so')
  })

  test('a manifest failure is shown with the server problem and can be retried', async () => {
    const client = fakeClient({ manifest: [problem('unavailable', { status: 503 }), A_VIEW], listAll: [] })
    const { w } = await mountApp(client)
    expect(w.find('[role=alert]').text()).toBe('Dịch vụ tạm thời không sẵn sàng, hãy thử lại sau ít phút')
    expect(w.find('main h1').exists()).toBe(false)
    await click(w, 'Tải lại')
    expect(w.find('[role=alert]').exists()).toBe(false)
    expect(w.find('main h1').text()).toBe('Văn bản')
  })

  test('when the server rejects the fresh session it shows the error screen with a re-login button', async () => {
    const { w, auth, guard } = await mountApp()
    // Lần 401 thứ nhất đi đăng nhập; sau khi quay về, lần 401 kế tiếp là vòng lặp.
    guard.rejected.value = true
    await flushPromises()
    expect(w.find('[role=alert] h1').text()).toBe('Phiên đăng nhập không được máy chủ chấp nhận')
    expect(w.find('header').exists()).toBe(false)
    expect(auth.login).not.toHaveBeenCalled()
    await click(w, 'Đăng nhập lại')
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(w.find('[role=alert] h1').exists()).toBe(false)
  })

  test('end to end: a 401 after returning from login ends in the error screen, not a redirect loop', async () => {
    const auth = fakeAuth()
    const storage = new MemoryStorage()
    createLoginGuard(auth, { storage }).onUnauthorized() // lượt đăng nhập diễn ra trước khi trang tải lại
    expect(auth.login).toHaveBeenCalledTimes(1)
    const guard = createLoginGuard(auth, { storage }) // trang mới: bộ nhớ trang mất, sessionStorage còn
    const f = fakeFetch([{ status: 401, text: 'Unauthorized' }])
    const session = createSession({ auth, client: createClient(auth, guard, f), guard })
    const router = makeRouter(createMemoryHistory())
    await router.push('/')
    const w = mount(App, { global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
    await flushPromises()
    expect(w.text()).toContain('Phiên đăng nhập không được máy chủ chấp nhận')
    expect(auth.login).toHaveBeenCalledTimes(1) // không chuyển hướng lần hai
    expect(f.calls).toHaveLength(1)
  })
})
