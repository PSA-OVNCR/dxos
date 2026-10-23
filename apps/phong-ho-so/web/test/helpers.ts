// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Helper test riêng của App A: dữ liệu mẫu và các thao tác giống người dùng (mountWith, fill, click, pickFile).
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { DxosAuth, DxosClient, FieldView, ManifestView } from 'dxos-sdk-js'
import { att, fakeClient, rec, sealInfo, task, type FakeClient, type FakeClientOptions } from 'dxos-sdk-js/testing'
import { vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import type { Component } from 'vue'
import { makeRouter } from '../src/router'
import { createLoginGuard, createSession, SESSION_KEY, type LoginGuard, type Session } from '../src/session'

function f(type: FieldView['type'], over: Partial<FieldView> = {}): FieldView {
  return { type, required: false, public: false, pii: null, format: null, label: null, ...over }
}

/** Dạng `GET /api/v1/apps/phong-ho-so/manifest` của manifest App A (apps/phong-ho-so/manifest.yaml). */
export const A_VIEW: ManifestView = {
  app: { id: 'phong-ho-so', version: '1.1.0', name: 'Phòng hồ sơ số' },
  roles: ['chuyen_vien', 'truong_phong', 'giam_doc', 'van_thu', 'nhan_vien'],
  collections: {
    van_ban: {
      fields: {
        so_hieu: f('sequence', { public: true, format: '{n:02}/QĐ-SM', label: 'Số, ký hiệu' }),
        loai_van_ban: f('string', { public: true, label: 'Tên loại văn bản' }),
        trich_yeu: f('string', { required: true, public: true, label: 'Trích yếu nội dung' }),
        chuc_vu_nguoi_ky: f('string', { public: true, label: 'Chức vụ người ký' }),
        noi_nhan: f('string', { label: 'Nơi nhận' }),
        nguoi_lien_he_cccd: f('string', { pii: 'CCCD', label: 'CCCD người liên hệ' }),
      },
      attachments: { kinds: ['pdf'], max_mb: 15, min: 1 },
      access: {
        read: ['owner', 'role:truong_phong', 'role:giam_doc', 'role:van_thu', 'role:nhan_vien'],
        create: ['role:chuyen_vien'], update: ['owner'],
      },
    },
  },
  workflow: {
    tasks: {
      duyet_noi_dung: { role: 'truong_phong', guards: ['attachments_clean', 'not_same_actor:creator'] },
      ban_hanh: { role: 'giam_doc', guards: ['attachments_clean', 'pii_reviewed', 'not_same_actor:creator', 'not_same_actor:duyet_noi_dung'] },
    },
    decisions: { duyet_noi_dung: ['approve', 'reject'], ban_hanh: ['approve', 'reject'] },
  },
  policies: {
    pii: { reveal_roles: ['giam_doc', 'van_thu'], erase_roles: ['van_thu'] },
    seal: { public_fields: ['so_hieu', 'loai_van_ban', 'trich_yeu', 'chuc_vu_nguoi_ky'], revoke_roles: ['giam_doc'] },
    verify: { public: true, require_file: true },
  },
}

export function fakeAuth(over: Partial<DxosAuth> & { roleStrings?: string[] } = {}): DxosAuth & {
  login: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn>
} {
  const { roleStrings = ['app:phong-ho-so:chuyen_vien'], ...rest } = over
  return {
    init: vi.fn(async () => true),
    login: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    token: async () => 'tok',
    profile: () => ({ username: 'a.nguyen', name: 'Nguyễn Văn A' }),
    roles: () => roleStrings,
    ...rest,
  } as DxosAuth & { login: ReturnType<typeof vi.fn>; logout: ReturnType<typeof vi.fn> }
}

/** Client giả cho màn chi tiết: mặc định có bản ghi của chủ và không có tệp; `over` ghi đè. */
export function detailClient(over: FakeClientOptions = {}): FakeClient {
  return fakeClient({ get: rec({ is_owner: true, data: {} }), attachments: [], ...over })
}

export interface MountOptions {
  /** Chuỗi vai trò thật của token, ví dụ 'app:phong-ho-so:chuyen_vien'. */
  roleStrings?: string[]
  view?: ManifestView | null
  route?: string
  guard?: LoginGuard
  auth?: DxosAuth
}

export type Mounted = VueWrapper & { session: Session }

/** Gắn một view với phiên giả (manifest đã nạp sẵn) và router bộ nhớ thật. Đợi mọi lời gọi ban đầu xong. */
export async function mountWith(
  component: Component, client: DxosClient, props: Record<string, unknown> = {}, o: MountOptions = {},
): Promise<Mounted> {
  const auth = o.auth ?? fakeAuth({ roleStrings: o.roleStrings ?? ['app:phong-ho-so:chuyen_vien'] })
  const guard = o.guard ?? createLoginGuard(auth, { storage: new MemoryStorage() })
  const session = createSession({ auth, client, guard })
  session.view.value = o.view === undefined ? A_VIEW : o.view
  const router = makeRouter(createMemoryHistory())
  await router.push(o.route ?? '/')
  await router.isReady()
  const w = mount(component, { props, global: { plugins: [router], provide: { [SESSION_KEY as symbol]: session } } })
  await flushPromises()
  return Object.assign(w, { session }) as Mounted
}

export class MemoryStorage {
  private readonly m = new Map<string, string>()
  getItem(k: string): string | null { return this.m.get(k) ?? null }
  setItem(k: string, v: string): void { this.m.set(k, v) }
  removeItem(k: string): void { this.m.delete(k) }
}

/** Điền các ô theo thuộc tính name; mặc định gửi biểu mẫu như người dùng bấm nút. */
export async function fill(w: VueWrapper, values: Record<string, string>, o: { submit?: boolean } = {}): Promise<void> {
  for (const [name, v] of Object.entries(values)) {
    const input = w.find(`input[name="${name}"]`)
    if (!input.exists()) throw new Error(`không có ô name="${name}"`)
    await input.setValue(v)
  }
  if (o.submit ?? true) await w.find('form').trigger('submit')
  await flushPromises()
}

/** Bấm nút theo chữ hiển thị (khớp chính xác sau khi cắt khoảng trắng). */
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

export { att, rec, sealInfo, task }
