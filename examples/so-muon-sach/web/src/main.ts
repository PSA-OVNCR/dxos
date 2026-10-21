// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { createAuth } from 'dxos-sdk-js'
import 'dxos-sdk-js/style.css'
import { boot, connect } from 'dxos-sdk-js/vue'
import App from './App.vue'
import { makeRouter } from './router'
import { APP, BASE } from './session'

// boot() của SDK: auth.init() xong rồi mới tạo router, chuyển sang Keycloak khi chưa đăng nhập.
boot({
  auth: createAuth({ appBase: BASE }), mount: '#app', root: App, makeRouter,
  connect: (auth) => connect(auth, { app: APP, marker: `dxos:${APP}:login-attempt` }),
}).catch(() => {
  document.querySelector('#app')!.textContent = 'Không khởi động được ứng dụng. Hãy tải lại trang hoặc báo quản trị viên.'
})
