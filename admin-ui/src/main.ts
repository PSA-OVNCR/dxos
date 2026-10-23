// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { createAuth } from 'dxos-sdk-js'
import 'dxos-sdk-js/style.css'
import { boot } from './boot'
import { BASE, CLIENT_ID } from './session'
import './style.css'

// Client công khai riêng của trang (PKCE S256, redirect `${origin}/ui/`); token chỉ nằm trong sessionStorage.
boot({ auth: createAuth({ appBase: BASE, clientId: CLIENT_ID }), mount: '#app' }).catch(() => {
  // Lưới an toàn cuối cùng: không bao giờ để trang trắng (textContent, không phải HTML).
  const el = document.querySelector('#app')
  if (el) el.textContent = 'Không khởi động được trang quản trị. Hãy tải lại trang hoặc báo quản trị viên.'
})
