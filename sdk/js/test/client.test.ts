// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from 'vitest'
import { ApiError, slugOf } from '../src/errors'
import { client, fakeFetch, rec, task } from './helpers'

test('write sends quoted If-Match from a fresh GET', async () => {
  const f = fakeFetch([{ json: rec({ version: 7 }) }, { json: rec({ version: 8, wf_state: 'running' }) }])
  await client(f).start('a', 'c', 'r1')
  expect(f.calls[0]!.method).toBe('GET')
  expect(f.calls[1]!.headers.get('If-Match')).toBe('"7"')
})

test('problem+json becomes ApiError with slug and guard', async () => {
  const f = fakeFetch([{ json: rec() }, { status: 409, problem: { type: 'https://dxos.dev/problems/guard-failed',
    title: 'Guard failed', status: 409, guard: 'pii_reviewed', reason: 'pii_not_reviewed' } }])
  const e = await client(f).complete('a', task(), 'approve').catch((x) => x)
  expect(e).toBeInstanceOf(ApiError)
  expect(e.slug).toBe('guard-failed')
  expect(e.status).toBe(409)
  expect(e.problem.guard).toBe('pii_reviewed')
})

test('non-JSON error body falls back to http-<status>', async () => {
  const e = await client(fakeFetch([{ status: 429, text: '<html>' }])).tasks('a').catch((x) => x)
  expect(e).toBeInstanceOf(ApiError)
  expect(e.slug).toBe('http-429')
  expect(e.problem).toBeNull()
})

test('401 calls onUnauthorized once and does not retry', async () => {
  const onU = vi.fn()
  const f = fakeFetch([{ status: 401, text: '' }])
  await client(f, { onUnauthorized: onU }).tasks('a').catch(() => {})
  expect(onU).toHaveBeenCalledTimes(1)
  expect(f.calls).toHaveLength(1)
})

test('writes are never retried on 5xx', async () => {
  const f = fakeFetch([{ json: rec() }, { status: 503, problem: { type: 'x/workflow-pending', title: 't', status: 503 } }])
  await client(f).start('a', 'c', 'r').catch(() => {})
  expect(f.calls).toHaveLength(2)
})

test('bulk rejects more than 500 rows before any request', async () => {
  const f = fakeFetch([])
  await expect(client(f).bulk('a', 'c', Array(501).fill({}))).rejects.toThrow(/500/)
  expect(f.calls).toHaveLength(0)
})

test('upload uses multipart field "file"', async () => {
  const f = fakeFetch([{ status: 202, json: { upload_id: 'u', status: 'STAGING' } }])
  await client(f).upload('a', 'c', 'r', new Blob(['%PDF']), 'x.pdf')
  expect((f.calls[0]!.body as FormData).get('file')).toBeInstanceOf(Blob)
  // để trình duyệt tự đặt Content-Type kèm boundary
  expect(f.calls[0]!.headers.has('Content-Type')).toBe(false)
})

test('checkHash sends exactly {"sha256": ...} as application/json', async () => {
  const f = fakeFetch([{ json: { match: true } }])
  await client(f).checkHash('A'.repeat(26), 'ab'.repeat(32))
  expect(f.calls[0]!.headers.get('Content-Type')).toBe('application/json')
  expect(f.calls[0]!.body).toBe(JSON.stringify({ sha256: 'ab'.repeat(32) }))
})

test('path segments are encoded', async () => {
  const f = fakeFetch([{ json: rec() }])
  await client(f).get('a', 'c', '../x')
  expect(f.calls[0]!.url).toContain('%2E%2E%2Fx')
})

describe('request basics', () => {
  test('adds Bearer token and baseUrl', async () => {
    const f = fakeFetch([{ json: { sub: 's', roles: [], is_admin: false } }])
    await client(f, { baseUrl: 'https://h.example' }).whoami()
    expect(f.calls[0]!.url).toBe('https://h.example/api/v1/whoami')
    expect(f.calls[0]!.headers.get('Authorization')).toBe('Bearer tok')
  })

  test('no Authorization header when there is no token', async () => {
    const f = fakeFetch([{ json: { items: [] } }])
    await client(f, { getToken: async () => null }).tasks('a')
    expect(f.calls[0]!.headers.has('Authorization')).toBe(false)
  })

  test('slugOf takes the last path segment', () => {
    expect(slugOf('https://dxos.dev/problems/x')).toBe('x')
    expect(slugOf('plain')).toBe('plain')
  })

  test('manifest hits the Task 1 endpoint', async () => {
    const f = fakeFetch([{ json: { app: { id: 'a', version: '1', name: 'A' } } }])
    await client(f).manifest('a')
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/manifest')
  })
})

describe('records', () => {
  test('list passes cursor and limit', async () => {
    const f = fakeFetch([{ json: { items: [], next_cursor: null } }])
    await client(f).list('a', 'c', { cursor: 'k', limit: 50 })
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/collections/c/records?cursor=k&limit=50')
  })

  test('listAll follows next_cursor and stops at maxItems', async () => {
    const f = fakeFetch([
      { json: { items: [rec({ id: '1' }), rec({ id: '2' })], next_cursor: 'k1' } },
      { json: { items: [rec({ id: '3' }), rec({ id: '4' })], next_cursor: 'k2' } },
    ])
    const all = await client(f).listAll('a', 'c', 3)
    expect(all.map((r) => r.id)).toEqual(['1', '2', '3'])
    expect(f.calls).toHaveLength(2)
    expect(f.calls[1]!.url).toContain('cursor=k1')
  })

  test('listAll ends when next_cursor is null', async () => {
    const f = fakeFetch([{ json: { items: [rec()], next_cursor: null } }])
    expect(await client(f).listAll('a', 'c')).toHaveLength(1)
    expect(f.calls).toHaveLength(1)
  })

  test('create posts the data object itself', async () => {
    const f = fakeFetch([{ status: 201, json: rec() }])
    await client(f).create('a', 'c', { x: 1 })
    expect(f.calls[0]!.method).toBe('POST')
    expect(f.calls[0]!.body).toBe('{"x":1}')
    expect(f.calls[0]!.headers.get('Content-Type')).toBe('application/json')
  })

  test('bulk returns results in order', async () => {
    const f = fakeFetch([{ json: { results: [{ ok: true, id: 'x' }] } }])
    expect(await client(f).bulk('a', 'c', [{}])).toEqual([{ ok: true, id: 'x' }])
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/collections/c/records:bulk')
  })

  test('patch GETs first then sends only the changes', async () => {
    const f = fakeFetch([{ json: rec({ version: 3 }) }, { json: rec({ version: 4 }) }])
    await client(f).patch('a', 'c', 'r1', { t: 'z' })
    expect(f.calls[1]!.method).toBe('PATCH')
    expect(f.calls[1]!.headers.get('If-Match')).toBe('"3"')
    expect(f.calls[1]!.body).toBe('{"t":"z"}')
  })
})

describe('attachments', () => {
  test('uploadStatus, attachments and download', async () => {
    const f = fakeFetch([
      { json: { status: 'CLEAN', sha256: 'ab'.repeat(32) } },
      { json: { items: [{ upload_id: 'u', status: 'STAGING', sha256: null, reason: null, created_at: 'z' }] } },
      { blob: new Blob(['%PDF-1.7']) },
    ])
    const c = client(f)
    expect((await c.uploadStatus('u')).status).toBe('CLEAN')
    expect(f.calls[0]!.url).toBe('/api/v1/uploads/u')
    expect(await c.attachments('a', 'c', 'r')).toHaveLength(1)
    expect(f.calls[1]!.url).toBe('/api/v1/apps/a/collections/c/records/r/attachments')
    const b = await c.download('ab'.repeat(32))
    expect(b).toBeInstanceOf(Blob)
    expect(await b.text()).toBe('%PDF-1.7')
    expect(f.calls[2]!.url).toBe(`/api/v1/objects/${'ab'.repeat(32)}?variant=original`)
  })
})

describe('workflow and seal', () => {
  test('tasks asks for assigned=me', async () => {
    const f = fakeFetch([{ json: { items: [task()] } }])
    expect(await client(f).tasks('a')).toHaveLength(1)
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/tasks?assigned=me')
  })

  test('complete GETs the task record, then posts decision with its version', async () => {
    const out = { record: rec({ version: 5 }), seal_state: 'NONE', seal_id: null }
    const f = fakeFetch([{ json: rec({ version: 4 }) }, { json: out }])
    const r = await client(f).complete('a', task({ task_id: 't9', record_id: 'r9', collection: 'van_ban' }), 'approve', 'ok')
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/collections/van_ban/records/r9')
    expect(f.calls[1]!.url).toBe('/api/v1/apps/a/tasks/t9:complete')
    expect(f.calls[1]!.headers.get('If-Match')).toBe('"4"')
    expect(f.calls[1]!.body).toBe('{"decision":"approve","comment":"ok"}')
    expect(r.record.version).toBe(5)
  })

  test('complete omits comment when absent', async () => {
    const f = fakeFetch([{ json: rec() }, { json: { record: rec(), seal_state: 'NONE', seal_id: null } }])
    await client(f).complete('a', task(), 'reject')
    expect(f.calls[1]!.body).toBe('{"decision":"reject"}')
  })

  test.each([
    ['piiReview', ':pii-review', undefined],
    ['revoke', ':revoke', '{"reason_code":"superseded"}'],
    ['erasePii', ':erase-pii', '{"fields":["cccd"],"reason_code":"data_subject_request"}'],
  ] as const)('%s GETs first and posts %s with If-Match', async (name, suffix, body) => {
    const f = fakeFetch([{ json: rec({ version: 2 }) }, { json: rec({ version: 3 }) }])
    const c = client(f)
    if (name === 'piiReview') await c.piiReview('a', 'c', 'r1')
    else if (name === 'revoke') await c.revoke('a', 'c', 'r1', 'superseded')
    else await c.erasePii('a', 'c', 'r1', ['cccd'], 'data_subject_request')
    expect(f.calls[1]!.url).toBe(`/api/v1/apps/a/collections/c/records/r1${suffix}`)
    expect(f.calls[1]!.headers.get('If-Match')).toBe('"2"')
    expect(f.calls[1]!.body).toBe(body)
  })

  test('revoke includes note when given', async () => {
    const f = fakeFetch([{ json: rec() }, { json: rec() }])
    await client(f).revoke('a', 'c', 'r1', 'other', 'ghi chú')
    expect(f.calls[1]!.body).toBe('{"reason_code":"other","note":"ghi chú"}')
  })

  test('seal reads /seal without If-Match', async () => {
    const f = fakeFetch([{ json: { seal_id: 'S' } }])
    await client(f).seal('a', 'c', 'r1')
    expect(f.calls[0]!.url).toBe('/api/v1/apps/a/collections/c/records/r1/seal')
  })
})

describe('public verification', () => {
  const SEAL = 'A'.repeat(26)

  test('publicSeal returns raw text and status without throwing on 404, and sends no token', async () => {
    const f = fakeFetch([{ status: 404, text: '{"title":"Not Found"}' }])
    const r = await client(f).publicSeal(SEAL)
    expect(r).toEqual({ status: 404, text: '{"title":"Not Found"}' })
    expect(f.calls[0]!.url).toBe(`/verify/v1/seals/${SEAL}`)
    expect(f.calls[0]!.headers.has('Authorization')).toBe(false)
  })

  test('checkHash posts to :check and passes the pending form through', async () => {
    const f = fakeFetch([{ json: { match: false, status: 'SEAL_PENDING' } }])
    const r = await client(f).checkHash(SEAL, 'ab'.repeat(32))
    expect(r).toEqual({ match: false, status: 'SEAL_PENDING' })
    expect(f.calls[0]!.url).toBe(`/verify/v1/seals/${SEAL}:check`)
    expect(f.calls[0]!.method).toBe('POST')
  })

  test('bundle without sha256 is a GET, with sha256 a POST :bundle', async () => {
    const f = fakeFetch([{ text: '{"format":"x"}' }, { text: '{"format":"y"}' }])
    const c = client(f)
    expect(await c.bundle(SEAL)).toBe('{"format":"x"}')
    expect(f.calls[0]!.url).toBe(`/verify/v1/seals/${SEAL}/bundle`)
    expect(f.calls[0]!.method).toBe('GET')
    expect(await c.bundle(SEAL, 'ab'.repeat(32))).toBe('{"format":"y"}')
    expect(f.calls[1]!.url).toBe(`/verify/v1/seals/${SEAL}:bundle`)
    expect(f.calls[1]!.method).toBe('POST')
    expect(f.calls[1]!.body).toBe(JSON.stringify({ sha256: 'ab'.repeat(32) }))
  })

  test('verify errors become ApiError', async () => {
    const f = fakeFetch([{ status: 415, problem: { type: 'https://dxos.dev/problems/unsupported-media-type', title: 'U', status: 415 } }])
    const e = await client(f).checkHash(SEAL, 'ab'.repeat(32)).catch((x) => x)
    expect(e.slug).toBe('unsupported-media-type')
  })
})
