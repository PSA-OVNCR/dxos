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

/** Trả ứng dụng đã gắn, hoặc null nếu đang chuyển sang trang đăng nhập. */
export async function boot(deps: BootDeps): Promise<VueApp | null> {
  // 1) init() xử lý ?code&state và đổi URL bằng history.replaceState (không bắn hashchange): nó PHẢI xong trước
  //    khi router đọc fragment. Vì vậy không tạo router (và không app.use) ở bất kỳ chỗ nào phía trên dòng này.
  const authed = await deps.auth.init()
  const session = (deps.connect ?? connect)(deps.auth)

  // 2) Chưa đăng nhập: chuyển sang Keycloak, trừ khi vừa đăng nhập xong mà vẫn chưa có phiên (chốt chặn vòng lặp):
  //    khi đó vẫn gắn ứng dụng để App.vue hiện màn hình lỗi.
  if (!authed && session.guard.attempt(location.hash)) return null

  // 3) Giờ mới tạo router; app.use(router) chạy điều hướng đầu tiên theo fragment đã khôi phục.
  const router = (deps.makeRouter ?? makeRouter)()
  const app = createApp(App)
  app.provide(SESSION_KEY, session)
  app.use(router)
  app.mount(deps.mount)
  return app
}
