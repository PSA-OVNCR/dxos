// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router'
import Duyet from './views/Duyet.vue'
import Phieu from './views/Phieu.vue'

// Router băm (#/...). Chỉ gọi sau auth.init(): xem boot() trong SDK.
export const makeRouter = (history: RouterHistory = createWebHashHistory()) => createRouter({
  history,
  routes: [{ path: '/', component: Phieu }, { path: '/duyet', component: Duyet }, { path: '/:rest(.*)*', redirect: '/' }],
})
