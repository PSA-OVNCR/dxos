// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { createAuth } from 'dxos-sdk-js'
import { boot } from './boot'
import { BASE } from './session'
import './style.css'

boot({ auth: createAuth({ appBase: BASE }), mount: '#app' }).catch(() => {
  // Lưới an toàn cuối cùng: không bao giờ để trang trắng (textContent, không phải HTML).
  const el = document.querySelector('#app')
  if (el) el.textContent = 'Không khởi động được ứng dụng. Hãy tải lại trang hoặc báo quản trị viên.'
})
