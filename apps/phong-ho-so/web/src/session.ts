// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Phiên làm việc của App A: phần dùng chung (chốt chặn vòng lặp đăng nhập, client, manifest, vai trò) nằm trong SDK;
// ở đây chỉ còn định danh của ứng dụng.
import type { DxosAuth, DxosClient } from 'dxos-sdk-js'
import {
  connect as sdkConnect, createClient, createLoginGuard as sdkCreateLoginGuard, createSession as sdkCreateSession, SESSION_KEY, useSession,
  type LoginGuard, type LoginGuardOptions, type Session,
} from 'dxos-sdk-js/vue'

export const APP = 'phong-ho-so'
export const COL = 'van_ban'
/** Phải trùng `base` trong vite.config.ts. */
export const BASE = '/apps/phong-ho-so/'

/** Khoá sessionStorage đánh dấu "vừa chuyển sang trang đăng nhập". */
export const LOGIN_MARKER = 'dxos:phong-ho-so:login-attempt'

export function createLoginGuard(auth: Pick<DxosAuth, 'login'>, o: Omit<LoginGuardOptions, 'marker'> = {}): LoginGuard {
  return sdkCreateLoginGuard(auth, { marker: LOGIN_MARKER, ...o })
}

export function createSession(parts: { auth: DxosAuth; client: DxosClient; guard: LoginGuard }): Session {
  return sdkCreateSession({ app: APP, ...parts })
}

/** Phiên thật cho `main.ts`. Gọi SAU `auth.init()` để `roles` đọc từ token đã có. */
export function connect(auth: DxosAuth): Session {
  return sdkConnect(auth, { app: APP, marker: LOGIN_MARKER })
}

export { createClient, SESSION_KEY, useSession }
export type { LoginGuard, Session }
