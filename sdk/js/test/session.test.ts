// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { describe, expect, test, vi } from 'vitest'
import type { DxosAuth } from '../src/auth'
import { fakeFetch } from '../src/testing'
import { createClient, createLoginGuard as make, type LoginGuardOptions } from '../src/vue/session'

const LOGIN_MARKER = 'dxos:test:login-attempt'
const createLoginGuard = (auth: Pick<DxosAuth, 'login'>, o: Omit<LoginGuardOptions, 'marker'> = {}) => make(auth, { marker: LOGIN_MARKER, ...o })

class MemoryStorage {
  private readonly m = new Map<string, string>()
  getItem(k: string): string | null { return this.m.get(k) ?? null }
  setItem(k: string, v: string): void { this.m.set(k, v) }
  removeItem(k: string): void { this.m.delete(k) }
}

function fakeAuth() {
  return {
    init: vi.fn(async () => true), login: vi.fn(async () => {}), logout: vi.fn(async () => {}),
    token: async () => 'tok', profile: () => null, roles: () => [],
  } as unknown as DxosAuth & { login: ReturnType<typeof vi.fn> }
}

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
    await expect(createClient(auth, guard, f).manifest('app')).rejects.toMatchObject({ status: 401 })
    expect(f.calls[0]?.headers.get('Authorization')).toBe('Bearer tok')
    expect(auth.login).toHaveBeenCalledTimes(1)
  })
})

describe('marker isolation', () => {
  test('two apps on one origin keep separate markers', () => {
    const storage = new MemoryStorage()
    const a = fakeAuth()
    const b = fakeAuth()
    make(a, { marker: 'dxos:a:login-attempt', storage, now: () => 1_000_000 }).onUnauthorized()
    const other = make(b, { marker: 'dxos:b:login-attempt', storage, now: () => 1_000_100 })
    other.onUnauthorized()
    expect(b.login).toHaveBeenCalledTimes(1)
    expect(other.rejected.value).toBe(false)
  })
})
