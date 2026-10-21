// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Helper test riêng của App B: manifest mẫu và các thao tác giống người dùng (mountWith, click, pickFile).
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { DxosAuth, FieldView, ManifestView } from 'dxos-sdk-js'
import { createLoginGuard, createSession, SESSION_KEY, type LoginGuard, type Session } from 'dxos-sdk-js/vue'
import { fakeClient, rec, sealInfo, task, type FakeClient, type FakeClientOptions } from 'dxos-sdk-js/testing'
import { vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { makeRouter } from '../src/router'
import { APP, LOGIN_MARKER } from '../src/session'

function f(type: FieldView['type'], over: Partial<FieldView> = {}): FieldView {
  return { type, required: false, public: false, pii: null, format: null, label: null, ...over }
}

/** Dạng `GET /api/v1/apps/chung-nhan/manifest` của manifest App B (apps/chung-nhan/manifest.yaml). */
export const B_VIEW: ManifestView = {
  app: { id: 'chung-nhan', version: '1.1.0', name: 'Chứng nhận số' },
  roles: ['can_bo_clb', 'truong_clb'],
  collections: {
    chung_nhan: {
      fields: {
        so_chung_nhan: f('sequence', { public: true, format: '{n}/CN-CLB', label: 'Số chứng nhận' }),
        ho_ten: f('string', { required: true, public: true, label: 'Họ và tên' }),
        su_kien: f('string', { required: true, public: true, label: 'Sự kiện' }),
        ngay_cap: f('date', { required: true, public: true, label: 'Ngày cấp' }),
        email: f('string', { pii: 'EMAIL', label: 'Email' }),
      },
      attachments: null,
      access: { read: ['role:can_bo_clb', 'role:truong_clb'], create: ['role:can_bo_clb'], update: ['owner'] },
    },
  },
  workflow: {
    tasks: { phe_duyet: { role: 'truong_clb', guards: ['not_same_actor:creator'] } },
    decisions: { phe_duyet: ['approve', 'reject'] },
  },
  policies: {
    pii: { reveal_roles: ['truong_clb'], erase_roles: ['truong_clb'] },
    seal: { public_fields: ['so_chung_nhan', 'ho_ten', 'su_kien', 'ngay_cap'], revoke_roles: ['truong_clb'] },
    verify: { public: true, require_file: false },
  },
}

export function fakeAuth(over: Partial<DxosAuth> & { roleStrings?: string[] } = {}): DxosAuth & {
  login: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn>
} {
  const { roleStrings = ['app:chung-nhan:can_bo_clb'], ...rest } = over
  return {
    init: vi.fn(async () => true),
    login: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    token: async () => 'tok',
    profile: () => ({ username: 'b.tran', name: 'Trần Thị B' }),
    roles: () => roleStrings,
    ...rest,
  } as DxosAuth & { login: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn> }
}

export class MemoryStorage {
  private readonly m = new Map<string, string>()
  getItem(k: string): string | null { return this.m.get(k) ?? null }
  setItem(k: string, v: string): void { this.m.set(k, v) }
  removeItem(k: string): void { this.m.delete(k) }
}

export interface MountOptions {
  /** Chuỗi vai trò thật của token, ví dụ 'app:chung-nhan:can_bo_clb'. */
  roleStrings?: string[]
  view?: ManifestView | null
  route?: string
  guard?: LoginGuard
  auth?: DxosAuth
}

export type Mounted = VueWrapper & { session: Session }

/** Gắn một view với phiên giả (manifest đã nạp sẵn) và router bộ nhớ thật. Đợi mọi lời gọi ban đầu xong. */
export async function mountWith(
  component: Component, client: FakeClient, props: Record<string, unknown> = {}, o: MountOptions = {},
): Promise<Mounted> {
  const auth = o.auth ?? fakeAuth({ roleStrings: o.roleStrings ?? ['app:chung-nhan:can_bo_clb'] })
  const guard = o.guard ?? createLoginGuard(auth, { marker: LOGIN_MARKER, storage: new MemoryStorage() })
  const session = createSession({ app: APP, auth, client, guard })
  session.view.value = o.view === undefined ? B_VIEW : o.view
  const router = makeRouter(createMemoryHistory())
  await router.push(o.route ?? '/')
  await router.isReady()
  const w = mount(component, { props, global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
  await flushPromises()
  return Object.assign(w, { session }) as Mounted
}

/** Bấm nút hoặc liên kết theo chữ hiển thị (khớp chính xác sau khi cắt khoảng trắng). */
export async function click(w: VueWrapper, label: string): Promise<void> {
  const b = w.findAll('button, a').find((x) => x.text().trim() === label)
  if (!b) throw new Error(`không có nút "${label}"; hiện có: ${w.findAll('button, a').map((x) => x.text().trim()).join(' | ')}`)
  await b.trigger('click')
  await flushPromises()
}

/** Chọn tệp ở ô input[type=file] như người dùng. */
export async function pickFile(w: VueWrapper, file: File): Promise<void> {
  const input = w.find('input[type="file"]')
  if (!input.exists()) throw new Error('không có ô chọn tệp')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

export { rec, sealInfo, task, fakeClient }
export type { FakeClientOptions }
