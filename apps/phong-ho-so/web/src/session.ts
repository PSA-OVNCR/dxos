// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Phiên làm việc dùng chung: đăng nhập, client HTTP, vai trò, manifest, và chốt chặn vòng lặp đăng nhập.
import { appRoles, DxosClient, type DxosAuth, type ManifestView } from 'dxos-sdk-js'
import { inject, ref, shallowRef, type InjectionKey, type Ref } from 'vue'

export const APP = 'phong-ho-so'
export const COL = 'van_ban'
/** Phải trùng `base` trong vite.config.ts. */
export const BASE = '/apps/phong-ho-so/'

/** Khoá sessionStorage đánh dấu "vừa chuyển sang trang đăng nhập" (giá trị: thời điểm, ms). */
export const LOGIN_MARKER = 'dxos:phong-ho-so:login-attempt'
/** Dấu cũ hơn ngưỡng này không còn tính (người dùng bỏ dở đăng nhập, quay lại sau): chỉ chặn vòng lặp nhanh. */
const MARKER_TTL_MS = 5 * 60_000

export type MarkerStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export interface LoginGuard {
  /** true = máy chủ không chấp nhận phiên vừa đăng nhập: hiện màn hình lỗi, không chuyển hướng nữa. */
  rejected: Ref<boolean>
  /** true = đã gọi auth.login và đang chờ trình duyệt rời trang: App hiện "Đang chuyển..." thay vì nội dung. */
  redirecting: Ref<boolean>
  /** Khởi động hỏng trước khi đăng nhập được (ví dụ auth.init() ném lỗi): hiện màn hình lỗi có nút "Đăng nhập lại". */
  fail(): void
  /** Chuyển sang đăng nhập nếu chưa thử gần đây. false = không chuyển (đã thử rồi nên `rejected` thành true). */
  attempt(returnTo?: string): boolean
  /** Dành cho `DxosClient.onUnauthorized`. */
  onUnauthorized(): void
  /** Một lời gọi API thành công chứng tỏ máy chủ nhận token: xóa dấu. */
  succeeded(): void
  /** Nút "Đăng nhập lại": người dùng chủ động bắt đầu lượt mới. */
  retry(): void
}

/**
 * Chốt chặn vòng lặp 401 -> đăng nhập -> callback -> 401 (lệch đồng hồ, lõi từ chối token...).
 * Dấu đặt NGAY TRƯỚC khi chuyển hướng và sống qua lần chuyển hướng (sessionStorage); lần 401 hoặc "chưa đăng
 * nhập" kế tiếp mà còn dấu thì hiện lỗi thay vì chuyển hướng. Dấu bị xóa khi một lời gọi API thành công.
 */
export function createLoginGuard(
  auth: Pick<DxosAuth, 'login'>,
  o: { storage?: MarkerStorage; now?: () => number } = {},
): LoginGuard {
  const now = o.now ?? Date.now
  const memory = new Map<string, string>()
  const store: MarkerStorage = o.storage ?? {
    getItem: (k) => {
      try { return sessionStorage.getItem(k) } catch { return memory.get(k) ?? null }
    },
    setItem: (k, v) => {
      try { sessionStorage.setItem(k, v) } catch { memory.set(k, v) }
    },
    removeItem: (k) => {
      try { sessionStorage.removeItem(k) } catch { memory.delete(k) }
    },
  }
  const rejected = ref(false)
  // Nhiều yêu cầu song song cùng nhận 401: chỉ yêu cầu đầu tiên chuyển hướng, các yêu cầu sau không phải là "lần lặp".
  const redirecting = ref(false)

  function marked(): boolean {
    const t = Number(store.getItem(LOGIN_MARKER))
    return Number.isFinite(t) && t > 0 && now() - t < MARKER_TTL_MS
  }

  function attempt(returnTo?: string): boolean {
    if (redirecting.value) return true
    if (marked()) {
      rejected.value = true
      return false
    }
    redirecting.value = true
    store.setItem(LOGIN_MARKER, String(now()))
    auth.login(returnTo ?? location.hash).catch(() => {
      // Không mở được trang đăng nhập (ví dụ không tới được máy chủ danh tính): để người dùng tự bấm lại.
      store.removeItem(LOGIN_MARKER)
      redirecting.value = false
      rejected.value = true
    })
    return true
  }

  return {
    rejected,
    redirecting,
    fail() {
      redirecting.value = false
      rejected.value = true
    },
    attempt,
    onUnauthorized: () => { attempt() },
    succeeded: () => { store.removeItem(LOGIN_MARKER) },
    retry() {
      store.removeItem(LOGIN_MARKER)
      rejected.value = false
      redirecting.value = false
      attempt()
    },
  }
}

/** DxosClient thật: 401 đi qua chốt chặn, phản hồi `ok` đầu tiên xóa dấu. Không bao giờ tự thử lại yêu cầu ghi. */
export function createClient(auth: DxosAuth, guard: LoginGuard, f: typeof fetch = (i, init) => fetch(i, init)): DxosClient {
  return new DxosClient({
    getToken: () => auth.token(),
    onUnauthorized: () => { guard.onUnauthorized() },
    fetch: async (input, init) => {
      const resp = await f(input, init)
      if (resp.ok) guard.succeeded()
      return resp
    },
  })
}

export interface Session {
  auth: DxosAuth
  client: DxosClient
  guard: LoginGuard
  /** Vai trò của ứng dụng này (phần sau `app:phong-ho-so:`); chỉ để ẩn/hiện nút cho tiện, lõi mới quyết định. */
  roles: Ref<string[]>
  /** Manifest đọc từ máy chủ lúc chạy (nhãn, trường, giới hạn tệp). null cho tới khi tải xong. */
  view: Ref<ManifestView | null>
  viewError: Ref<unknown>
  /** Tải manifest một lần; gọi lại sau khi lỗi thì thử lại. */
  load(): Promise<void>
}

export function createSession(parts: { auth: DxosAuth; client: DxosClient; guard: LoginGuard }): Session {
  const { auth, client, guard } = parts
  const roles = ref<string[]>(appRoles(auth.roles(), APP))
  const view = shallowRef<ManifestView | null>(null)
  const viewError = ref<unknown>(null)
  let inflight: Promise<void> | undefined
  return {
    auth, client, guard, roles, view, viewError,
    load() {
      if (view.value) return Promise.resolve()
      inflight ??= (async () => {
        viewError.value = null
        try {
          view.value = await client.manifest(APP)
        } catch (e) {
          viewError.value = e
        } finally {
          inflight = undefined
        }
      })()
      return inflight
    },
  }
}

/** Phiên thật cho `main.ts`. Gọi SAU `auth.init()` để `roles` đọc từ token đã có. */
export function connect(auth: DxosAuth): Session {
  const guard = createLoginGuard(auth)
  return createSession({ auth, client: createClient(auth, guard), guard })
}

export const SESSION_KEY: InjectionKey<Session> = Symbol('dxos-session')

export function useSession(): Session {
  const s = inject(SESSION_KEY)
  if (!s) throw new Error('useSession: chưa có phiên (app.provide(SESSION_KEY, session))')
  return s
}
