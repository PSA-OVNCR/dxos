// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Router băm (#/...). `#/apps` và `#/quarantine` là chỗ của hai màn hình duyệt app và cách ly (Task 10).
import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router'
import HealthView from './views/HealthView.vue'
import LedgerView from './views/LedgerView.vue'
import SoonView from './views/SoonView.vue'

export const routes = [
  { path: '/', redirect: '/health' },
  { path: '/health', name: 'health', component: HealthView },
  { path: '/ledger', name: 'ledger', component: LedgerView },
  { path: '/apps', name: 'apps', component: SoonView },
  { path: '/quarantine', name: 'quarantine', component: SoonView },
  { path: '/:rest(.*)*', redirect: '/health' },
]

/**
 * Chỉ gọi SAU `await auth.init()`: init() đổi URL bằng history.replaceState (không bắn hashchange), nên router
 * tạo trước đó sẽ đọc fragment cũ. `history` truyền vào để test dùng lịch sử trong bộ nhớ.
 */
export function makeRouter(history: RouterHistory = createWebHashHistory()) {
  return createRouter({ history, routes })
}
