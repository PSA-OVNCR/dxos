// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Phiên làm việc của App B: phần dùng chung (chốt chặn vòng lặp đăng nhập, client, manifest, vai trò) nằm trong SDK;
// ở đây chỉ còn định danh của ứng dụng.
import type { DxosAuth } from 'dxos-sdk-js'
import { connect as sdkConnect, SESSION_KEY, useSession, type Session } from 'dxos-sdk-js/vue'

export const APP = 'chung-nhan'
export const COL = 'chung_nhan'
/** Phải trùng `base` trong vite.config.ts. */
export const BASE = '/apps/chung-nhan/'

/** Khoá sessionStorage đánh dấu "vừa chuyển sang trang đăng nhập". */
export const LOGIN_MARKER = 'dxos:chung-nhan:login-attempt'

/** Phiên thật cho `main.ts`. Gọi SAU `auth.init()` để `roles` đọc từ token đã có. */
export function connect(auth: DxosAuth): Session {
  return sdkConnect(auth, { app: APP, marker: LOGIN_MARKER })
}

export { SESSION_KEY, useSession }
export type { Session }
