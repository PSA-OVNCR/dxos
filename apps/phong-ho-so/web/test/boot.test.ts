// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises } from '@vue/test-utils'
import { fakeClient } from 'dxos-sdk-js/testing'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { boot } from '../src/boot'
import { makeRouter } from '../src/router'
import { createLoginGuard, createSession } from '../src/session'
import { A_VIEW, fakeAuth, MemoryStorage } from './helpers'

beforeEach(() => { document.body.innerHTML = '<div id="app"></div>' })
afterEach(() => { document.body.innerHTML = '' })

function parts(authed: boolean, storage = new MemoryStorage()) {
  const log: string[] = []
  let release: (v: boolean) => void = () => {}
  const auth = fakeAuth({
    init: vi.fn(() => new Promise<boolean>((resolve) => { release = (v) => { log.push('init-done'); resolve(v) } })),
  })
  const client = fakeClient({ manifest: A_VIEW, listAll: [] })
  const connect = vi.fn(() => {
    log.push('connect')
    return createSession({ auth, client, guard: createLoginGuard(auth, { storage }) })
  })
  const makeIt = vi.fn(() => {
    log.push('router')
    return makeRouter(createMemoryHistory())
  })
  return { log, auth, connect, makeIt, finish: () => release(authed), storage }
}

describe('boot', () => {
  test('the router is only created after auth.init() has finished', async () => {
    const p = parts(true)
    const booted = boot({ auth: p.auth, mount: '#app', connect: p.connect, makeRouter: p.makeIt })
    await flushPromises()
    expect(p.makeIt).not.toHaveBeenCalled() // init() still pending (e.g. exchanging ?code=...)
    expect(document.querySelector('#app')?.innerHTML).toBe('')
    p.finish()
    const app = await booted
    expect(app).not.toBeNull()
    expect(p.log).toEqual(['init-done', 'connect', 'router'])
    await flushPromises()
    expect(document.querySelector('#app')?.textContent).toContain('Danh sách văn bản')
  })

  test('without a session it sends the user to log in and mounts nothing', async () => {
    const p = parts(false)
    location.hash = '#/van-ban/r1'
    const booted = boot({ auth: p.auth, mount: '#app', connect: p.connect, makeRouter: p.makeIt })
    p.finish()
    expect(await booted).toBeNull()
    expect(p.auth.login).toHaveBeenCalledWith('#/van-ban/r1')
    expect(p.makeIt).not.toHaveBeenCalled()
    expect(document.querySelector('#app')?.innerHTML).toBe('')
  })

  test('back from login but still without a session: shows the error screen, no second redirect', async () => {
    const storage = new MemoryStorage()
    const p1 = parts(false, storage)
    const first = boot({ auth: p1.auth, mount: '#app', connect: p1.connect, makeRouter: p1.makeIt })
    p1.finish()
    await first
    const p2 = parts(false, storage)
    const second = boot({ auth: p2.auth, mount: '#app', connect: p2.connect, makeRouter: p2.makeIt })
    p2.finish()
    expect(await second).not.toBeNull()
    await flushPromises()
    expect(p2.auth.login).not.toHaveBeenCalled()
    expect(document.querySelector('#app')?.textContent).toContain('Phiên đăng nhập không được máy chủ chấp nhận')
    expect(document.querySelector('#app button')?.textContent).toBe('Đăng nhập lại')
  })
})
