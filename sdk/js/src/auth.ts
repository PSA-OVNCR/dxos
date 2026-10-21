// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Đăng nhập OIDC Authorization Code + PKCE (S256) với Keycloak, token chỉ nằm trong sessionStorage.
import { UserManager, WebStorageStateStore, type UserManagerSettings } from 'oidc-client-ts'

export interface AuthConfig {
  /** Đường dẫn gốc của ứng dụng, ví dụ '/apps/phong-ho-so/'. redirect_uri = origin + appBase. */
  appBase: string
  /** Mặc định `${location.origin}/auth/realms/dxos`. */
  issuer?: string
  /** Mặc định 'dxos-spa'. */
  clientId?: string
}

export interface DxosAuth {
  /** Xử lý ?code&state, xóa query khỏi URL, giữ fragment; true nếu đã đăng nhập. */
  init(): Promise<boolean>
  /** returnTo (mặc định location.hash) được khôi phục sau callback. */
  login(returnTo?: string): Promise<void>
  logout(): Promise<void>
  /** Làm mới single-flight khi còn ≤ 30 s; hỏng thì null (và xóa phiên, không lặp). */
  token(): Promise<string | null>
  profile(): { username: string; name: string } | null
  /** `realm_access.roles` của access token (chỉ để hiển thị; lõi tự kiểm quyền). */
  roles(): string[]
}

/** Phần của User (oidc-client-ts) mà SDK dùng; để test thay bằng đối tượng giả. */
export interface UserLike {
  access_token: string
  expires_in?: number
  profile: { sub?: string; preferred_username?: string; name?: string }
  state?: unknown
}

/** Phần của UserManager mà SDK dùng; test truyền bản giả qua `deps.manager`. */
export interface UserManagerLike {
  getUser(): Promise<UserLike | null>
  signinRedirect(args?: { state?: unknown }): Promise<void>
  signinCallback(url?: string): Promise<UserLike | undefined | void>
  signinSilent(): Promise<UserLike | null>
  signoutRedirect(): Promise<void>
  removeUser(): Promise<void>
}

export type AuthSettings = UserManagerSettings & {
  userStore: WebStorageStateStore
  stateStore: WebStorageStateStore
}

/** Làm mới khi access token còn không quá ngần này giây. */
const REFRESH_MARGIN_S = 30

/**
 * Cấu hình UserManager (hàm thuần). PKCE S256 là mặc định của oidc-client-ts với response_type=code.
 * Cả userStore lẫn stateStore (chứa code_verifier) đặt trong sessionStorage; mặc định của thư viện cho
 * stateStore là kho lưu bền theo origin (không phải của phiên) nên phải ghi đè.
 */
export function settingsFor(cfg: AuthConfig, origin: string): AuthSettings {
  const redirect = origin + cfg.appBase
  return {
    authority: cfg.issuer ?? `${origin}/auth/realms/dxos`,
    client_id: cfg.clientId ?? 'dxos-spa',
    redirect_uri: redirect,
    post_logout_redirect_uri: redirect,
    response_type: 'code',
    scope: 'openid profile',
    automaticSilentRenew: false,
    userStore: new WebStorageStateStore({ store: sessionStorage }),
    stateStore: new WebStorageStateStore({ store: sessionStorage }),
  }
}

/** Vai trò 'app:<app>:<r>' của đúng ứng dụng, trả về 'r'. */
export function appRoles(roles: string[], app: string): string[] {
  const prefix = `app:${app}:`
  return roles.filter((r) => r.startsWith(prefix)).map((r) => r.slice(prefix.length))
}

function decodeRoles(accessToken: string): string[] {
  try {
    const payload = accessToken.split('.')[1]
    if (!payload) return []
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as { realm_access?: { roles?: unknown } }
    const roles = claims.realm_access?.roles
    return Array.isArray(roles) ? roles.filter((r): r is string => typeof r === 'string') : []
  } catch {
    return []
  }
}

function fresh(u: UserLike): boolean {
  return u.expires_in === undefined || u.expires_in > REFRESH_MARGIN_S
}

export function createAuth(cfg: AuthConfig, deps: { manager?: UserManagerLike } = {}): DxosAuth {
  // Tạo UserManager thật khi cần để import module này không đụng tới sessionStorage/location.
  let real: UserManagerLike | undefined = deps.manager
  const manager = (): UserManagerLike => (real ??= new UserManager(settingsFor(cfg, location.origin)))

  let current: UserLike | null = null
  let inflight: Promise<void> | undefined
  let initialised: Promise<boolean> | undefined

  async function forget(): Promise<void> {
    current = null
    try {
      await manager().removeUser()
    } catch {
      // Kho phiên không xóa được thì vẫn coi như chưa đăng nhập.
    }
  }

  // Tải user đã lưu (nếu chưa có) rồi làm mới nếu sắp hết hạn. Refresh token dùng một lần
  // (refreshTokenMaxReuse: 0) nên mọi lời gọi chung một chuyến bay.
  async function renew(): Promise<void> {
    current ??= await manager().getUser()
    if (!current || fresh(current)) return
    try {
      const next = await manager().signinSilent()
      if (!next) throw new Error('signinSilent returned no user')
      current = next
    } catch {
      await forget()
    }
  }

  async function token(): Promise<string | null> {
    if (!current || !fresh(current)) {
      inflight ??= renew().finally(() => {
        inflight = undefined
      })
      await inflight
    }
    return current?.access_token ?? null
  }

  function cleanUrl(returnTo: unknown): void {
    // returnTo chỉ được là fragment, để không dẫn đi nơi khác.
    const hash = typeof returnTo === 'string' && returnTo.startsWith('#') ? returnTo : location.hash
    history.replaceState(history.state, '', location.pathname + hash)
  }

  async function doInit(): Promise<boolean> {
    const q = new URLSearchParams(location.search)
    if ((q.has('code') || q.has('error')) && q.has('state')) {
      try {
        const user = await manager().signinCallback(location.href)
        current = user ?? null
        cleanUrl(current?.state && (current.state as { returnTo?: unknown }).returnTo)
      } catch {
        cleanUrl(undefined)
        await forget()
        return false
      }
    }
    return (await token()) !== null
  }

  return {
    init: () => (initialised ??= doInit()),
    login: (returnTo = location.hash) => manager().signinRedirect({ state: { returnTo } }),
    async logout() {
      current = null
      await manager().signoutRedirect()
    },
    token,
    profile() {
      if (!current) return null
      const p = current.profile
      const username = p.preferred_username ?? p.sub ?? ''
      return { username, name: p.name ?? username }
    },
    roles: () => (current ? decodeRoles(current.access_token) : []),
  }
}
