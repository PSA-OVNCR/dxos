// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Trình tự khởi động dùng chung. Tách khỏi main.ts để test được thứ tự: auth.init() XONG rồi mới tạo router.
import { createApp, type App as VueApp, type Component, type Plugin } from 'vue'
import type { DxosAuth } from '../auth'
import { SESSION_KEY, type Session } from './session'

export interface BootDeps {
  auth: DxosAuth
  mount: string | Element
  /** Thành phần gốc của ứng dụng. */
  root: Component
  connect: (auth: DxosAuth) => Session
  /** Router (vue-router) tạo SAU auth.init(); nhận vào như một plugin Vue để SDK không phụ thuộc vue-router. */
  makeRouter: () => Plugin
}

/**
 * Luôn gắn ứng dụng: không bao giờ để trang trắng. Đang chuyển sang đăng nhập thì thành phần gốc hiện "Đang chuyển sang
 * trang đăng nhập…"; nếu việc đó hỏng (máy chủ danh tính không tới được, auth.init() ném lỗi) thì hiện màn hình lỗi.
 */
export async function boot(deps: BootDeps): Promise<VueApp> {
  // 1) init() xử lý ?code&state và đổi URL bằng history.replaceState (không bắn hashchange): nó PHẢI xong trước
  //    khi router đọc fragment. Vì vậy không tạo router (và không app.use) ở bất kỳ chỗ nào phía trên dòng này.
  let authed = false
  let initFailed = false
  try {
    authed = await deps.auth.init()
  } catch {
    initFailed = true // ví dụ kho phiên hỏng
  }
  const session = deps.connect(deps.auth)

  // 2) Chưa đăng nhập: chuyển sang Keycloak, trừ khi vừa đăng nhập xong mà vẫn chưa có phiên (chốt chặn vòng lặp).
  if (initFailed) session.guard.fail()
  else if (!authed) session.guard.attempt(location.hash)

  // 3) Giờ mới tạo router; app.use(router) chạy điều hướng đầu tiên theo fragment đã khôi phục.
  const router = deps.makeRouter()
  const app = createApp(deps.root)
  app.provide(SESSION_KEY, session)
  app.use(router)
  app.mount(deps.mount)
  return app
}
