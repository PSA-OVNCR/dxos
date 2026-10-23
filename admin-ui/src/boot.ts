// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Khởi động trang quản trị: trình tự (auth.init() xong rồi mới tạo router; không bao giờ để trang trắng) nằm trong SDK.
import type { DxosAuth } from 'dxos-sdk-js'
import { boot as sdkBoot, type Session } from 'dxos-sdk-js/vue'
import type { App as VueApp } from 'vue'
import type { Router } from 'vue-router'
import App from './App.vue'
import { makeRouter } from './router'
import { connect } from './session'

export interface BootDeps {
  auth: DxosAuth
  mount: string | Element
  connect?: (auth: DxosAuth) => Session
  makeRouter?: () => Router
}

export function boot(deps: BootDeps): Promise<VueApp> {
  return sdkBoot({
    auth: deps.auth, mount: deps.mount, root: App, connect: deps.connect ?? connect, makeRouter: deps.makeRouter ?? makeRouter,
  })
}
