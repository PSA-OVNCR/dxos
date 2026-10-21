// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Trình tự khởi động. Tách khỏi main.ts để test được thứ tự: auth.init() XONG rồi mới tạo router.
import type { DxosAuth } from 'dxos-sdk-js'
import { createApp, type App as VueApp } from 'vue'
import type { Router } from 'vue-router'
import App from './App.vue'
import { makeRouter } from './router'
import { connect, SESSION_KEY, type Session } from './session'

export interface BootDeps {
  auth: DxosAuth
  mount: string | Element
  connect?: (auth: DxosAuth) => Session
  makeRouter?: () => Router
}

/**
 * Luôn gắn ứng dụng: không bao giờ để trang trắng. Đang chuyển sang đăng nhập thì App hiện "Đang chuyển sang trang
 * đăng nhập…"; nếu việc đó hỏng (máy chủ danh tính không tới được, auth.init() ném lỗi) thì App hiện màn hình lỗi.
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
  const session = (deps.connect ?? connect)(deps.auth)

  // 2) Chưa đăng nhập: chuyển sang Keycloak, trừ khi vừa đăng nhập xong mà vẫn chưa có phiên (chốt chặn vòng lặp).
  if (initFailed) session.guard.fail()
  else if (!authed) session.guard.attempt(location.hash)

  // 3) Giờ mới tạo router; app.use(router) chạy điều hướng đầu tiên theo fragment đã khôi phục.
  const router = (deps.makeRouter ?? makeRouter)()
  const app = createApp(App)
  app.provide(SESSION_KEY, session)
  app.use(router)
  app.mount(deps.mount)
  return app
}
