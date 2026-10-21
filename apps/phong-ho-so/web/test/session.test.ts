// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { fakeClient, fakeFetch, problem } from 'dxos-sdk-js/testing'
import { describe, expect, test, vi } from 'vitest'
import { A_VIEW, fakeAuth, MemoryStorage } from './helpers'
import { APP, createClient, createLoginGuard, createSession, LOGIN_MARKER } from '../src/session'

function setup(storage = new MemoryStorage(), t0 = 1_000_000) {
  let t = t0
  const auth = fakeAuth()
  const guard = createLoginGuard(auth, { storage, now: () => t })
  return { auth, guard, storage, advance: (ms: number) => { t += ms } }
}

describe('login loop guard', () => {
  test('the first 401 sends the user to log in and leaves a marker', () => {
    const { auth, guard, storage } = setup()
    location.hash = '#/van-ban/r1'
    guard.onUnauthorized()
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(auth.login).toHaveBeenCalledWith('#/van-ban/r1')
    expect(storage.getItem(LOGIN_MARKER)).not.toBeNull()
    expect(guard.rejected.value).toBe(false)
  })

  test('a 401 right after returning from login shows the error instead of looping', () => {
    const { auth, storage } = setup()
    const first = createLoginGuard(auth, { storage, now: () => 1_000_000 })
    first.onUnauthorized() // ... đi đăng nhập, trang tải lại: bộ nhớ trang mất, sessionStorage còn
    expect(auth.login).toHaveBeenCalledTimes(1)
    const afterReturn = createLoginGuard(auth, { storage, now: () => 1_005_000 })
    afterReturn.onUnauthorized()
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(afterReturn.rejected.value).toBe(true)
  })

  test('parallel 401s redirect once and are not mistaken for a loop', () => {
    const { auth, guard } = setup()
    guard.onUnauthorized()
    guard.onUnauthorized()
    guard.onUnauthorized()
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(guard.rejected.value).toBe(false)
  })

  test('startup without a session: first time redirects, second time (marker present) does not', () => {
    const { auth, guard, storage } = setup()
    expect(guard.attempt('#/')).toBe(true)
    expect(auth.login).toHaveBeenCalledTimes(1)
    const again = createLoginGuard(auth, { storage, now: () => 1_000_100 })
    expect(again.attempt('#/')).toBe(false)
    expect(again.rejected.value).toBe(true)
    expect(auth.login).toHaveBeenCalledTimes(1)
  })

  test('the marker is cleared by the first successful API call, so a later expiry logs in again', async () => {
    const { auth, guard, storage } = setup()
    guard.onUnauthorized()
    const afterReturn = createLoginGuard(auth, { storage, now: () => 1_001_000 })
    const f = fakeFetch([{ json: { sub: 'u', roles: [], is_admin: false } }, { status: 401, problem: { type: 'https://dxos.dev/problems/unauthenticated', title: 'x', status: 401 } }])
    const client = createClient(auth, afterReturn, f)
    await client.whoami()
    expect(storage.getItem(LOGIN_MARKER)).toBeNull()
    await expect(client.whoami()).rejects.toMatchObject({ status: 401 })
    expect(afterReturn.rejected.value).toBe(false)
    expect(auth.login).toHaveBeenCalledTimes(2)
  })

  test('a failed call keeps the marker (the server has not accepted the session yet)', async () => {
    const { auth, guard, storage } = setup()
    guard.onUnauthorized()
    const afterReturn = createLoginGuard(auth, { storage, now: () => 1_001_000 })
    const f = fakeFetch([{ status: 401, problem: { type: 'https://dxos.dev/problems/unauthenticated', title: 'x', status: 401 } }])
    await expect(createClient(auth, afterReturn, f).whoami()).rejects.toMatchObject({ status: 401 })
    expect(afterReturn.rejected.value).toBe(true)
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(storage.getItem(LOGIN_MARKER)).not.toBeNull()
  })

  test('an abandoned login does not block the user forever (marker expires)', () => {
    const { auth, guard, storage, advance } = setup()
    guard.onUnauthorized()
    advance(10 * 60_000)
    const later = createLoginGuard(auth, { storage, now: () => 1_000_000 + 10 * 60_000 })
    later.onUnauthorized()
    expect(auth.login).toHaveBeenCalledTimes(2)
    expect(later.rejected.value).toBe(false)
  })

  test('retry() clears the error and logs in again', () => {
    const { auth, storage } = setup()
    const g1 = createLoginGuard(auth, { storage, now: () => 1_000_000 })
    g1.onUnauthorized()
    const g2 = createLoginGuard(auth, { storage, now: () => 1_000_500 })
    g2.onUnauthorized()
    expect(g2.rejected.value).toBe(true)
    g2.retry()
    expect(g2.rejected.value).toBe(false)
    expect(auth.login).toHaveBeenCalledTimes(2)
  })

  test('a login page that cannot be opened ends in the error screen, not a silent hang', async () => {
    const auth = fakeAuth()
    auth.login.mockRejectedValueOnce(new TypeError('network'))
    const guard = createLoginGuard(auth, { storage: new MemoryStorage() })
    guard.onUnauthorized()
    await Promise.resolve()
    await Promise.resolve()
    expect(guard.rejected.value).toBe(true)
  })

  test('the real client sends the token and routes a 401 through the guard', async () => {
    const { auth, guard } = setup()
    const f = fakeFetch([{ status: 401, text: '<html>401</html>' }])
    await expect(createClient(auth, guard, f).manifest(APP)).rejects.toMatchObject({ status: 401 })
    expect(f.calls[0]?.headers.get('Authorization')).toBe('Bearer tok')
    expect(auth.login).toHaveBeenCalledTimes(1)
  })
})

describe('session', () => {
  test('roles are the app-specific part of the token roles', () => {
    const auth = fakeAuth({ roleStrings: ['app:phong-ho-so:chuyen_vien', 'app:chung-nhan:truong_clb', 'dxos-admin'] })
    const s = createSession({ auth, client: fakeClient(), guard: createLoginGuard(auth, { storage: new MemoryStorage() }) })
    expect(s.roles.value).toEqual(['chuyen_vien'])
  })

  test('the manifest is loaded once and a failure can be retried', async () => {
    const auth = fakeAuth()
    const client = fakeClient({ manifest: [problem('unavailable', { status: 503 }), A_VIEW] })
    const s = createSession({ auth, client, guard: createLoginGuard(auth, { storage: new MemoryStorage() }) })
    await s.load()
    expect(s.view.value).toBeNull()
    expect(s.viewError.value).not.toBeNull()
    await s.load()
    expect(s.view.value).toEqual(A_VIEW)
    expect(s.viewError.value).toBeNull()
    await s.load()
    await s.load()
    expect(client.manifest).toHaveBeenCalledTimes(2)
    expect(client.manifest).toHaveBeenCalledWith(APP)
  })

  test('concurrent loads share one request', async () => {
    const auth = fakeAuth()
    const client = fakeClient({ manifest: A_VIEW })
    const s = createSession({ auth, client, guard: createLoginGuard(auth, { storage: new MemoryStorage() }) })
    await Promise.all([s.load(), s.load(), s.load()])
    expect(client.manifest).toHaveBeenCalledTimes(1)
    expect(vi.isMockFunction(client.manifest)).toBe(true)
  })
})
