// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Router băm (#/...): sức khỏe, sổ cái, duyệt app (danh sách + diff của từng phiên bản) và cách ly.
import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router'
import AppDiffView from './views/AppDiffView.vue'
import AppsView from './views/AppsView.vue'
import HealthView from './views/HealthView.vue'
import LedgerView from './views/LedgerView.vue'
import QuarantineView from './views/QuarantineView.vue'

export const routes = [
  { path: '/', redirect: '/health' },
  { path: '/health', name: 'health', component: HealthView },
  { path: '/ledger', name: 'ledger', component: LedgerView },
  { path: '/apps', name: 'apps', component: AppsView },
  { path: '/apps/:id/versions/:version', name: 'app-diff', component: AppDiffView, props: true },
  { path: '/quarantine', name: 'quarantine', component: QuarantineView },
  { path: '/:rest(.*)*', redirect: '/health' },
]

/**
 * Chỉ gọi SAU `await auth.init()`: init() đổi URL bằng history.replaceState (không bắn hashchange), nên router
 * tạo trước đó sẽ đọc fragment cũ. `history` truyền vào để test dùng lịch sử trong bộ nhớ.
 */
export function makeRouter(history: RouterHistory = createWebHashHistory()) {
  return createRouter({ history, routes })
}
