// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { ApiError } from 'dxos-sdk-js'
import { messageFor } from 'dxos-sdk-js/vue'
import { fakeFetch } from 'dxos-sdk-js/testing'
import { describe, expect, test, vi } from 'vitest'
import { createAdminApi } from '../src/api'
import { HEALTH_OK, STATUS_OK } from './helpers'

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
})
