// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Router băm (#/...).
import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router'
import ChungNhanDetail from './views/ChungNhanDetail.vue'
import ChungNhanList from './views/ChungNhanList.vue'
import DuyetLo from './views/DuyetLo.vue'
import NhapCsv from './views/NhapCsv.vue'
import TrangIn from './views/TrangIn.vue'

export const routes = [
  { path: '/', name: 'list', component: ChungNhanList },
  { path: '/nhap-csv', name: 'import', component: NhapCsv },
  { path: '/duyet-lo', name: 'batch', component: DuyetLo },
  { path: '/chung-nhan/:id', name: 'detail', component: ChungNhanDetail, props: true },
  { path: '/chung-nhan/:id/in', name: 'print', component: TrangIn, props: true },
  { path: '/:rest(.*)*', redirect: '/' },
]

/**
 * Chỉ gọi SAU `await auth.init()`: init() đổi URL bằng history.replaceState (không bắn hashchange), nên router
 * tạo trước đó sẽ đọc fragment cũ. `history` truyền vào để test dùng lịch sử trong bộ nhớ.
 */
export function makeRouter(history: RouterHistory = createWebHashHistory()) {
  return createRouter({ history, routes })
}
