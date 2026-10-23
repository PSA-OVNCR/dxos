// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { ApiError } from 'dxos-sdk-js'
import { messageFor } from 'dxos-sdk-js/vue'
import { fakeFetch } from 'dxos-sdk-js/testing'
import { describe, expect, test, vi } from 'vitest'
import { createAdminApi } from '../src/api'
import { APPS_OK, DIFF_OK, HEALTH_OK, quarantineItem, STATUS_OK } from './helpers'

function api(replies: Parameters<typeof fakeFetch>[0], over: { onUnauthorized?: () => void } = {}) {
  const f = fakeFetch(replies)
  return { f, api: createAdminApi({ getToken: async () => 'tok', fetch: f, ...over }) }
}

describe('AdminApi', () => {
  test('GET calls go to the same-origin /admin/v1 with the bearer token', async () => {
    const { f, api: a } = api([{ json: HEALTH_OK }, { json: STATUS_OK }, { json: { items: [] } }])
    expect(await a.health()).toEqual(HEALTH_OK)
    expect(await a.ledgerStatus()).toEqual(STATUS_OK)
    await a.ledgerEntries({ type: 'record.created', limit: 50 })
    expect(f.calls.map((c) => [c.method, c.url])).toEqual([
      ['GET', '/admin/v1/health'],
      ['GET', '/admin/v1/ledger/status'],
      ['GET', '/admin/v1/ledger/entries?type=record.created&limit=50'],
    ])
    expect(f.calls.every((c) => c.headers.get('Authorization') === 'Bearer tok')).toBe(true)
  })

  test('entries without options use the default limit and no type filter', async () => {
    const { f, api: a } = api([{ json: { items: [] } }])
    await a.ledgerEntries()
    expect(f.calls[0]?.url).toBe('/admin/v1/ledger/entries?limit=20')
  })

  test('anchorRun is a single POST to anchor:run without a body', async () => {
    const { f, api: a } = api([{ json: { tree_size: 42, anchor_job_id: 'j' } }])
    expect((await a.anchorRun()).anchor_job_id).toBe('j')
    expect(f.calls).toHaveLength(1)
    expect(f.calls[0]?.method).toBe('POST')
    expect(f.calls[0]?.url).toBe('/admin/v1/anchor:run')
    expect(f.calls[0]?.body).toBeUndefined()
  })

  test('403 becomes the "no admin rights" message, whatever the body', async () => {
    const { api: a } = api([
      { status: 403, problem: { type: 'https://dxos.dev/problems/forbidden', title: 'Forbidden', status: 403 } },
      { status: 403, text: '<html>denied</html>' },
    ])
    for (const call of [() => a.health(), () => a.ledgerStatus()]) {
      const err = await call().catch((e: unknown) => e)
      expect(err).toBeInstanceOf(ApiError)
      expect((err as ApiError).status).toBe(403)
      expect(messageFor(err)).toBe('Tài khoản này không có quyền quản trị')
    }
  })

  test('401 calls onUnauthorized and still throws', async () => {
    const onUnauthorized = vi.fn()
    const { api: a } = api([{ status: 401, text: 'no' }], { onUnauthorized })
    await expect(a.health()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  test('problem+json errors keep their slug; non-JSON gateway errors get http-<status>', async () => {
    const { api: a } = api([
      { status: 503, problem: { type: 'https://dxos.dev/problems/kms-unavailable', title: 'Key service unavailable', status: 503 } },
      { status: 502, text: 'bad gateway' },
    ])
    expect(await a.anchorRun().catch((e: unknown) => (e as ApiError).slug)).toBe('kms-unavailable')
    expect(await a.health().catch((e: unknown) => (e as ApiError).slug)).toBe('http-502')
  })

  test('app review calls: list, diff, approve with {"version"}, disable without a body, quarantine with a limit', async () => {
    const view = { app_id: 'so-muon-sach', version: '1.1.0', status: 'ACTIVE', self_approved: false }
    const { f, api: a } = api([
      { json: APPS_OK }, { json: DIFF_OK }, { json: view }, { json: { app_id: 'so-muon-sach', version: '1.1.0', status: 'DISABLED' } },
      { json: [quarantineItem()] },
    ])
    expect(await a.apps()).toEqual(APPS_OK)
    expect(await a.appDiff('so-muon-sach', '1.1.0')).toEqual(DIFF_OK)
    expect((await a.approveApp('so-muon-sach', '1.1.0')).status).toBe('ACTIVE')
    expect((await a.disableApp('so-muon-sach')).status).toBe('DISABLED')
    expect(await a.quarantine(500)).toEqual([quarantineItem()])
    expect(f.calls.map((c) => [c.method, c.url])).toEqual([
      ['GET', '/admin/v1/apps'],
      ['GET', '/admin/v1/apps/so-muon-sach/versions/1.1.0/diff'],
      ['POST', '/admin/v1/apps/so-muon-sach:approve'],
      ['POST', '/admin/v1/apps/so-muon-sach:disable'],
      ['GET', '/admin/v1/quarantine?limit=500'],
    ])
    expect(f.calls[2]?.body).toBe('{"version":"1.1.0"}')
    expect(f.calls[2]?.headers.get('Content-Type')).toBe('application/json')
    expect(f.calls[3]?.body).toBeUndefined()
    expect(f.calls.every((c) => c.headers.get('Authorization') === 'Bearer tok')).toBe(true)
  })

  test('write calls are never retried, even after a 5xx or a 401', async () => {
    const onUnauthorized = vi.fn()
    const { f, api: a } = api([{ status: 503, text: 'down' }, { status: 401, text: 'no' }], { onUnauthorized })
    await expect(a.approveApp('so-muon-sach', '1.1.0')).rejects.toBeInstanceOf(ApiError)
    await expect(a.disableApp('so-muon-sach')).rejects.toBeInstanceOf(ApiError)
    expect(f.calls).toHaveLength(2)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  test('a 403 with reason self_approval is the four-eyes message, not "no admin rights"', async () => {
    const { api: a } = api([
      {
        status: 403,
        problem: {
          type: 'https://dxos.dev/problems/forbidden', title: 'Forbidden', status: 403,
          detail: 'approver must differ from submitter (four eyes)', reason: 'self_approval',
        },
      },
      { status: 403, problem: { type: 'https://dxos.dev/problems/forbidden', title: 'Forbidden', status: 403, reason: 'other' } },
    ])
    const four = await a.approveApp('x', '1.0.0').catch((e: unknown) => e)
    expect((four as ApiError).slug).toBe('self-approval')
    expect(messageFor(four)).toContain('bốn mắt')
    expect(messageFor(four)).toContain('khác người nộp')
    const other = await a.approveApp('x', '1.0.0').catch((e: unknown) => e)
    expect(messageFor(other)).toBe('Tài khoản này không có quyền quản trị')
  })

  test('app lifecycle problems get a Vietnamese message; a manifest problem keeps the server detail', async () => {
    const t = 'https://dxos.dev/problems/'
    const { api: a } = api([
      { status: 409, problem: { type: `${t}app-version-not-pending`, title: 'Conflict', status: 409, detail: 'x 1.0.0 đang DISABLED' } },
      { status: 409, problem: { type: `${t}install-in-progress`, title: 'Conflict', status: 409 } },
      { status: 404, problem: { type: `${t}app-version-not-found`, title: 'Application version not found', status: 404 } },
      { status: 503, problem: { type: `${t}idp-admin-unavailable`, title: 'Identity provider admin unavailable', status: 503 } },
      { status: 422, problem: { type: `${t}manifest-invalid`, title: 'Manifest invalid', status: 422, detail: 'thiếu tệp BPMN đã nộp' } },
      { status: 404, problem: { type: `${t}app-not-active`, title: 'Application not active', status: 404 } },
    ])
    const msgs: string[] = []
    for (let i = 0; i < 6; i++) msgs.push(messageFor(await a.approveApp('x', '1.0.0').catch((e: unknown) => e)))
    expect(msgs[0]).toContain('không còn ở trạng thái chờ duyệt')
    expect(msgs[1]).toContain('thao tác cài đặt khác')
    expect(msgs[2]).toContain('Không tìm thấy phiên bản')
    expect(msgs[3]).toContain('đăng nhập')
    expect(msgs[4]).toContain('Bản khai báo')
    expect(msgs[4]).toContain('thiếu tệp BPMN đã nộp')
    expect(msgs[5]).toBe('Ứng dụng chưa được kích hoạt hoặc không tồn tại')
  })
})
