// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Helper test của trang admin: API giả và các thao tác giống người dùng.
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { DxosAuth } from 'dxos-sdk-js'
import { vi, type Mock } from 'vitest'
import type { Component } from 'vue'
import {
  ADMIN_API_KEY, type AdminApi, type AppVersionRow, type HealthReport, type LedgerEntry, type LedgerStatus,
  type PermissionDiff, type QuarantineItem,
} from '../src/api'

export const HEALTH_OK: HealthReport = {
  db: 'ok', clamav: 'ok', openbao: 'ok', flowable: 'ok', keycloak_default_roles: 'ok',
  anchor: { last_tree_size: 12, last_anchor_age_s: 3600 },
  seal_pending: 0, task_intents_stuck: 0, seal_key: 'ok', org: 'ok',
}

export const STATUS_OK: LedgerStatus = {
  tree_size: 42,
  latest_sth: { tree_size: 42, root_hash: 'ab'.repeat(32), ts: '2026-10-22T10:00:00Z', key_version: 1, signature: 'c2ln' },
  last_anchor: {
    tree_size: 40, repo: 'PSA-OVNCR/dxos-anchors', commit_sha: '0123456789abcdef0123456789abcdef01234567',
    anchored_at: '2026-10-22T03:30:00+00:00',
  },
  pending_anchor_jobs: 0,
  verify: { ok: true, first_bad_idx: null },
}

export function entry(over: Partial<LedgerEntry> = {}): LedgerEntry {
  return { idx: 41, ts: '2026-10-22T09:59:00Z', type: 'record.created', app_id: 'test-app', subject: 'rec-1', actor_ref: 'f'.repeat(16), ...over }
}

export function appRow(over: Partial<AppVersionRow> = {}): AppVersionRow {
  return {
    app_id: 'so-muon-sach', version: '1.0.0', status: 'ACTIVE', manifest_sha256: 'ab'.repeat(32),
    submitted_by_ref: '1111aaaa2222bbbb', approved_by_ref: '3333cccc4444dddd', created_at: '2026-10-20T01:00:00Z', ...over,
  }
}

export const APPS_OK: AppVersionRow[] = [
  appRow(),
  appRow({ version: '1.1.0', status: 'PENDING', approved_by_ref: null, created_at: '2026-10-22T02:30:00Z' }),
  appRow({ app_id: 'test-app', version: '0.9.0', status: 'DISABLED', created_at: '2026-10-01T00:00:00Z' }),
]

export const DIFF_OK: PermissionDiff = {
  app_id: 'so-muon-sach', version: '1.1.0', against: '1.0.0',
  roles_added: ['thu-thu'], collections_added: ['phieu-muon'], fields_added: { sach: ['isbn'] },
  access: { 'phieu-muon': { read: ['thu-thu'], create: ['thu-thu'], update: [] } },
  pii_reveal_roles: { old: ['quan-ly'], new: ['quan-ly'] },
  pii_erase_roles: { old: ['quan-ly'], new: ['quan-ly', 'thu-thu'] },
  seal: { old: null, new: null },
  verify: { old: { fields: ['so'] }, new: { fields: ['so', 'ten'] } },
  tasks: { duyet: { role: 'thu-thu', guards: ['not_same_actor'] } },
  labels: { sach: { isbn: { old: null, new: 'Mã ISBN' } } },
  sequences: {},
  bpmn_sha256: 'cd'.repeat(32),
}

export function quarantineItem(over: Partial<QuarantineItem> = {}): QuarantineItem {
  return {
    upload_id: 'u-1', sha256: 'ef'.repeat(32), status: 'INFECTED', reason: 'Eicar-Test-Signature',
    app_id: 'so-muon-sach', created_at: '2026-10-22T03:00:00Z', ...over,
  }
}

export type FakeAdminApi = { [K in keyof AdminApi]: Mock<AdminApi[K]> }

export function fakeApi(over: Partial<AdminApi> = {}): FakeAdminApi {
  const base: AdminApi = {
    health: async () => HEALTH_OK,
    ledgerStatus: async () => STATUS_OK,
    ledgerEntries: async () => ({ items: [entry(), entry({ idx: 40, type: 'sth.published', app_id: null, subject: null })] }),
    anchorRun: async () => ({ ...STATUS_OK.latest_sth!, anchor_job_id: 'job-1' }),
    apps: async () => APPS_OK,
    appDiff: async () => DIFF_OK,
    approveApp: async (id, version) => ({
      app_id: id, version, status: 'ACTIVE', manifest_sha256: 'ab'.repeat(32), self_approved: false,
      deployment_id: 'dep-1', rendered_sha256: null,
    }),
    disableApp: async (id) => ({ app_id: id, version: '1.0.0', status: 'DISABLED' }),
    quarantine: async () => [quarantineItem()],
  }
  const merged = { ...base, ...over }
  return {
    health: vi.fn(merged.health), ledgerStatus: vi.fn(merged.ledgerStatus),
    ledgerEntries: vi.fn(merged.ledgerEntries), anchorRun: vi.fn(merged.anchorRun),
    apps: vi.fn(merged.apps), appDiff: vi.fn(merged.appDiff), approveApp: vi.fn(merged.approveApp),
    disableApp: vi.fn(merged.disableApp), quarantine: vi.fn(merged.quarantine),
  }
}

export function fakeAuth(over: Partial<DxosAuth> = {}): DxosAuth & { login: Mock; logout: Mock } {
  return {
    init: vi.fn(async () => true),
    login: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    token: async () => 'tok',
    profile: () => ({ username: 'admin1', name: 'Quản trị viên 1' }),
    roles: () => ['dxos-admin'],
    ...over,
  } as DxosAuth & { login: Mock; logout: Mock }
}

export async function mountView(
  component: Component, api: FakeAdminApi, props: Record<string, unknown> = {},
): Promise<VueWrapper> {
  const w = mount(component, { props, global: { provide: { [ADMIN_API_KEY as symbol]: api } } })
  await flushPromises()
  return w
}

/** Bấm nút theo chữ hiển thị (khớp chính xác sau khi cắt khoảng trắng). */
export async function click(w: VueWrapper, label: string): Promise<void> {
  const b = w.findAll('button, a').find((x) => x.text().trim() === label)
  if (!b) throw new Error(`không có nút "${label}"; hiện có: ${w.findAll('button, a').map((x) => x.text().trim()).join(' | ')}`)
  await b.trigger('click')
  await flushPromises()
}

export class MemoryStorage {
  private readonly m = new Map<string, string>()
  getItem(k: string): string | null { return this.m.get(k) ?? null }
  setItem(k: string, v: string): void { this.m.set(k, v) }
  removeItem(k: string): void { this.m.delete(k) }
}
