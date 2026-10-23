// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { appRoles, createAuth, settingsFor, type UserLike, type UserManagerLike } from '../src/auth'

// Ghi lại cấu hình mà createAuth đưa cho UserManager thật (lớp con của bản thật, không đổi hành vi).
const built = vi.hoisted(() => [] as { client_id?: string; authority?: string; redirect_uri?: string; userStore?: unknown }[])
vi.mock('oidc-client-ts', async (orig) => {
  const real = await orig<typeof import('oidc-client-ts')>()
  class Spy extends real.UserManager {
    constructor(settings: ConstructorParameters<typeof real.UserManager>[0]) {
      super(settings)
      built.push(settings)
    }
  }
  return { ...real, UserManager: Spy }
})

function b64url(o: unknown): string {
  return btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function jwt(payload: Record<string, unknown>): string {
  return `${b64url({ alg: 'RS256' })}.${b64url(payload)}.sig`
}

interface FakeOpts {
  expiresIn?: number
  refreshFails?: boolean
  stored?: boolean
  roles?: string[]
  callbackReturnTo?: string
  callbackFails?: boolean
}

function user(expiresIn: number, token: string, roles: string[] = [], state?: unknown): UserLike {
  return {
    access_token: token,
    expires_in: expiresIn,
    profile: { sub: 's1', preferred_username: 'an', name: 'Nguyễn An' },
    state,
    // Chỉ để roles() đọc; token thật là JWT, nên gắn payload vào access_token ở nơi gọi.
    ...(roles.length ? { access_token: jwt({ realm_access: { roles } }) } : {}),
  }
}

function fakeManager(o: FakeOpts = {}) {
  let stored: UserLike | null = o.stored === false ? null : user(o.expiresIn ?? 300, 'old', o.roles)
  const m = {
    getUser: vi.fn(async () => stored),
    signinRedirect: vi.fn(async () => undefined),
    signinCallback: vi.fn(async () => {
      if (o.callbackFails) throw new Error('access_denied')
      stored = user(300, 'cb', o.roles, { returnTo: o.callbackReturnTo })
      return stored
    }),
    signinSilent: vi.fn(async () => {
      await Promise.resolve()
      if (o.refreshFails) throw new Error('invalid_grant')
      stored = user(300, 'fresh', o.roles)
      return stored
    }),
    signoutRedirect: vi.fn(async () => undefined),
    removeUser: vi.fn(async () => {
      stored = null
    }),
  }
  return m satisfies UserManagerLike
}

const cfg = { appBase: '/apps/x/' }

beforeEach(() => {
  history.replaceState(null, '', '/apps/x/')
  sessionStorage.clear()
  localStorage.clear()
})
afterEach(() => vi.restoreAllMocks())

describe('settingsFor', () => {
  test('code flow, PKCE S256 (library default), sessionStorage, redirect = origin + appBase', async () => {
    const s = settingsFor(cfg, 'https://h')
    expect(s.response_type).toBe('code')
    expect(s.redirect_uri).toBe('https://h/apps/x/')
    expect(s.post_logout_redirect_uri).toBe('https://h/apps/x/')
    expect(s.authority).toBe('https://h/auth/realms/dxos')
    expect(s.client_id).toBe('dxos-spa')
    expect(s.scope).toBe('openid profile')
    expect(s.automaticSilentRenew).toBe(false)
    expect(s.disablePKCE).toBeFalsy()
    // Cả kho user lẫn kho state (code_verifier) phải nằm trong sessionStorage.
    await s.userStore.set('u', '1')
    await s.stateStore.set('s', '2')
    expect(sessionStorage.getItem('oidc.u')).toBe('1')
    expect(sessionStorage.getItem('oidc.s')).toBe('2')
    expect(localStorage.length).toBe(0)
  })

  test('issuer and clientId can be overridden', () => {
    const s = settingsFor({ appBase: '/apps/y/', issuer: 'https://k/auth/realms/r', clientId: 'c' }, 'https://h')
    expect(s.authority).toBe('https://k/auth/realms/r')
    expect(s.client_id).toBe('c')
    expect(s.redirect_uri).toBe('https://h/apps/y/')
  })
})

describe('createAuth clientId', () => {
  test('createAuth uses given clientId and keeps sessionStorage', async () => {
    built.length = 0
    const admin = createAuth({ appBase: '/ui/', clientId: 'dxos-admin-ui' })
    await admin.login('#/health').catch(() => undefined) // chỉ cần UserManager được dựng; không có IdP để chuyển hướng
    const dflt = createAuth({ appBase: '/apps/x/' })
    await dflt.token()
    expect(built.map((s) => s.client_id)).toEqual(['dxos-admin-ui', 'dxos-spa'])
    expect(built[0]?.redirect_uri).toBe(`${location.origin}/ui/`)
    expect(built[0]?.authority).toBe(`${location.origin}/auth/realms/dxos`)
    // Kho user và kho state (code_verifier) là sessionStorage, không phải localStorage.
    await (built[0]?.userStore as { set(k: string, v: string): Promise<void> }).set('k', 'v')
    expect(sessionStorage.getItem('oidc.k')).toBe('v')
    expect(localStorage.length).toBe(0)
  })
})

describe('token', () => {
  test('fresh token is returned without refreshing', async () => {
    const m = fakeManager({ expiresIn: 300 })
    const a = createAuth(cfg, { manager: m })
    expect(await a.token()).toBe('old')
    expect(m.signinSilent).not.toHaveBeenCalled()
  })

  test('token within 30 s of expiry is refreshed and the new token returned', async () => {
    const m = fakeManager({ expiresIn: 30 })
    const a = createAuth(cfg, { manager: m })
    expect(await a.token()).toBe('fresh')
    expect(await a.token()).toBe('fresh')
    expect(m.signinSilent).toHaveBeenCalledTimes(1)
  })

  test('concurrent token() calls trigger exactly one refresh', async () => {
    const m = fakeManager({ expiresIn: 5 })
    const a = createAuth(cfg, { manager: m })
    const all = await Promise.all([a.token(), a.token(), a.token()])
    expect(m.signinSilent).toHaveBeenCalledTimes(1)
    expect(all).toEqual(['fresh', 'fresh', 'fresh'])
  })

  test('failed refresh returns null and clears the user (no loop)', async () => {
    const m = fakeManager({ expiresIn: 5, refreshFails: true })
    const a = createAuth(cfg, { manager: m })
    expect(await a.token()).toBeNull()
    expect(m.removeUser).toHaveBeenCalled()
    expect(await a.token()).toBeNull()
    expect(m.signinSilent).toHaveBeenCalledTimes(1)
  })

  test('no stored user gives null without refreshing', async () => {
    const m = fakeManager({ stored: false })
    const a = createAuth(cfg, { manager: m })
    expect(await a.token()).toBeNull()
    expect(m.signinSilent).not.toHaveBeenCalled()
  })
})

describe('login / logout', () => {
  test('login keeps the hash route and restores it after callback', async () => {
    const m = fakeManager({})
    const a = createAuth(cfg, { manager: m })
    await a.login('#/van-ban/1')
    expect(m.signinRedirect).toHaveBeenCalledWith({ state: { returnTo: '#/van-ban/1' } })
  })

  test('login without argument uses the current location.hash', async () => {
    history.replaceState(null, '', '/apps/x/#/hang-doi')
    const m = fakeManager({})
    await createAuth(cfg, { manager: m }).login()
    expect(m.signinRedirect).toHaveBeenCalledWith({ state: { returnTo: '#/hang-doi' } })
  })

  test('logout signs out at the IdP and forgets the user', async () => {
    const m = fakeManager({ roles: ['dxos-admin'] })
    const a = createAuth(cfg, { manager: m })
    await a.init()
    expect(a.profile()).not.toBeNull()
    await a.logout()
    expect(m.signoutRedirect).toHaveBeenCalledTimes(1)
    expect(a.profile()).toBeNull()
    expect(a.roles()).toEqual([])
  })
})

describe('init', () => {
  test('without callback and without stored user: false', async () => {
    const a = createAuth(cfg, { manager: fakeManager({ stored: false }) })
    expect(await a.init()).toBe(false)
  })

  test('with a stored fresh user: true, profile and roles available', async () => {
    const m = fakeManager({ roles: ['app:x:editor', 'dxos-admin'] })
    const a = createAuth(cfg, { manager: m })
    expect(await a.init()).toBe(true)
    expect(m.signinCallback).not.toHaveBeenCalled()
    expect(a.profile()).toEqual({ username: 'an', name: 'Nguyễn An' })
    expect(a.roles()).toEqual(['app:x:editor', 'dxos-admin'])
  })

  test('with an expired stored user it refreshes once; failure gives false', async () => {
    const m = fakeManager({ expiresIn: 0, refreshFails: true })
    const a = createAuth(cfg, { manager: m })
    expect(await a.init()).toBe(false)
    expect(m.signinSilent).toHaveBeenCalledTimes(1)
  })

  test('handles ?code&state, strips the query and restores the hash from state', async () => {
    history.replaceState(null, '', '/apps/x/?code=abc&state=xyz&session_state=q')
    const m = fakeManager({ stored: false, callbackReturnTo: '#/van-ban/1' })
    const a = createAuth(cfg, { manager: m })
    expect(await a.init()).toBe(true)
    expect(m.signinCallback).toHaveBeenCalledTimes(1)
    expect(location.search).toBe('')
    expect(location.pathname).toBe('/apps/x/')
    expect(location.hash).toBe('#/van-ban/1')
  })

  test('ignores a returnTo that is not a fragment', async () => {
    history.replaceState(null, '', '/apps/x/?code=abc&state=xyz')
    const m = fakeManager({ stored: false, callbackReturnTo: '//evil.example/x' })
    await createAuth(cfg, { manager: m }).init()
    expect(location.pathname).toBe('/apps/x/')
    expect(location.hash).toBe('')
  })

  test('a failed callback cleans the URL, clears state and returns false (no throw)', async () => {
    history.replaceState(null, '', '/apps/x/?error=access_denied&state=xyz#/x')
    const m = fakeManager({ stored: false, callbackFails: true })
    const a = createAuth(cfg, { manager: m })
    expect(await a.init()).toBe(false)
    expect(location.search).toBe('')
    expect(location.hash).toBe('#/x')
    expect(m.removeUser).toHaveBeenCalled()
  })

  test('calling init twice processes the callback only once', async () => {
    history.replaceState(null, '', '/apps/x/?code=abc&state=xyz')
    const m = fakeManager({ stored: false })
    const a = createAuth(cfg, { manager: m })
    await Promise.all([a.init(), a.init()])
    expect(m.signinCallback).toHaveBeenCalledTimes(1)
  })
})

describe('appRoles', () => {
  test('keeps only roles of that app', () => {
    expect(appRoles(['app:a:x', 'app:b:y', 'dxos-admin', 'app:a:z'], 'a')).toEqual(['x', 'z'])
  })

  test('does not confuse apps sharing a prefix', () => {
    expect(appRoles(['app:ab:x', 'app:a:y'], 'a')).toEqual(['y'])
  })
})

describe('roles', () => {
  test('is empty for a token that is not a decodable JWT', async () => {
    const m = fakeManager({})
    const a = createAuth(cfg, { manager: m })
    await a.init()
    expect(a.roles()).toEqual([])
  })
})
