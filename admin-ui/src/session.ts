// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Phiên của trang quản trị: chốt chặn vòng lặp đăng nhập, token và hồ sơ người dùng nằm trong SDK. Trang này không có
// manifest ứng dụng (API quản trị không thuộc app nào) nên khung SDK nhận một "manifest" cố định chỉ mang tên trang.
import type { DxosAuth, ManifestView } from 'dxos-sdk-js'
import { connect as sdkConnect, type Session } from 'dxos-sdk-js/vue'

export const APP = 'dxos-admin'
/** Phải trùng `base` trong vite.config.ts. */
export const BASE = '/ui/'
/** Client Keycloak công khai riêng của trang (deploy/keycloak/realm-dxos.json). */
export const CLIENT_ID = 'dxos-admin-ui'
export const ADMIN_ROLE = 'dxos-admin'

/** Khoá sessionStorage đánh dấu "vừa chuyển sang trang đăng nhập". */
export const LOGIN_MARKER = 'dxos:admin-ui:login-attempt'

export const ADMIN_VIEW: ManifestView = {
  app: { id: APP, version: '0.9.0', name: 'Quản trị DX-OS' },
  roles: [ADMIN_ROLE],
  collections: {},
  workflow: null,
  policies: { pii: { reveal_roles: [], erase_roles: [] }, seal: null, verify: null },
}

export const ROLE_LABELS: Record<string, string> = { [ADMIN_ROLE]: 'Quản trị viên' }

/** Phiên thật cho `main.ts`. Gọi SAU `auth.init()` để `roles` đọc từ token đã có. */
export function connect(auth: DxosAuth): Session {
  const session = sdkConnect(auth, { app: APP, marker: LOGIN_MARKER })
  session.view.value = ADMIN_VIEW
  // Chỉ để hiện tên vai trò ở đầu trang; quyền thật do lõi kiểm từng lời gọi (403 nếu thiếu).
  session.roles.value = auth.roles().includes(ADMIN_ROLE) ? [ADMIN_ROLE] : []
  return session
}
