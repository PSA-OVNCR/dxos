// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { fakeClient, fakeFetch, problem } from 'dxos-sdk-js/testing'
import { describe, expect, test, vi } from 'vitest'
import { A_VIEW, fakeAuth, MemoryStorage } from './helpers'
import { APP, createClient, createLoginGuard, createSession, LOGIN_MARKER } from '../src/session'

describe('App A login guard wrapper', () => {
  test('uses the App A marker key and the real client routes a 401 through it', async () => {
    const storage = new MemoryStorage()
    const auth = fakeAuth()
    const guard = createLoginGuard(auth, { storage, now: () => 1_000_000 })
    const f = fakeFetch([{ status: 401, text: '<html>401</html>' }])
    await expect(createClient(auth, guard, f).manifest(APP)).rejects.toMatchObject({ status: 401 })
    expect(f.calls[0]?.headers.get('Authorization')).toBe('Bearer tok')
    expect(auth.login).toHaveBeenCalledTimes(1)
    expect(storage.getItem(LOGIN_MARKER)).toBe('1000000')
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
