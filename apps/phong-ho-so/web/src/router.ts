// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Router băm (#/...).
import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router'
import HopViec from './views/HopViec.vue'
import SoDangKy from './views/SoDangKy.vue'
import VanBanDetail from './views/VanBanDetail.vue'
import VanBanList from './views/VanBanList.vue'
import VanBanNew from './views/VanBanNew.vue'

export const routes = [
  { path: '/', name: 'list', component: VanBanList },
  { path: '/hop-viec', name: 'inbox', component: HopViec },
  { path: '/so-dang-ky', name: 'register', component: SoDangKy },
  { path: '/van-ban/moi', name: 'new', component: VanBanNew },
  { path: '/van-ban/:id', name: 'detail', component: VanBanDetail, props: true },
  { path: '/:rest(.*)*', redirect: '/' },
]

/**
 * Chỉ gọi SAU `await auth.init()`: init() đổi URL bằng history.replaceState (không bắn hashchange), nên router
 * tạo trước đó sẽ đọc fragment cũ. `history` truyền vào để test dùng lịch sử trong bộ nhớ.
 */
export function makeRouter(history: RouterHistory = createWebHashHistory()) {
  return createRouter({ history, routes })
}
