// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Giả lập fetch cho test client (Task 5 chuyển phần dùng chung sang src/testing.ts).
import { DxosClient, type ClientOptions } from '../src/client'
import type { DxRecord, TaskItem } from '../src/types'

export interface Call { url: string; method: string; headers: Headers; body: BodyInit | null | undefined }
export interface Reply { status?: number; json?: unknown; text?: string; problem?: Record<string, unknown>; blob?: Blob }
export type FakeFetch = typeof fetch & { calls: Call[] }

export function fakeFetch(replies: Reply[]): FakeFetch {
  const calls: Call[] = []
  const queue = [...replies]
  const f = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method ?? 'GET',
      headers: new Headers(init?.headers),
      body: init?.body,
    })
    const r = queue.shift()
    if (!r) throw new Error(`fakeFetch: không còn phản hồi cho ${String(input)}`)
    const status = r.status ?? 200
    if (r.problem) {
      return new Response(JSON.stringify(r.problem), { status, headers: { 'Content-Type': 'application/problem+json' } })
    }
    if (r.json !== undefined) {
      return new Response(JSON.stringify(r.json), { status, headers: { 'Content-Type': 'application/json' } })
    }
    if (r.blob) return new Response(r.blob, { status, headers: { 'Content-Type': 'application/pdf' } })
    return new Response(r.text ?? '', { status, headers: { 'Content-Type': 'text/html' } })
  }) as FakeFetch
  f.calls = calls
  return f
}

export function rec(over: Partial<DxRecord> = {}): DxRecord {
  return {
    id: 'r1', app_id: 'a', collection: 'c', data: {}, is_owner: true, version: 1, seal_state: 'NONE',
    wf_state: null, created_at: '2026-10-22T00:00:00Z', updated_at: '2026-10-22T00:00:00Z', ...over,
  }
}

export function task(over: Partial<TaskItem> = {}): TaskItem {
  return {
    task_id: 't1', task_key: 'duyet', name: 'Duyệt', record_id: 'r1', collection: 'c',
    created: '2026-10-22T00:00:00.000+07:00', ...over,
  }
}

export function client(f: typeof fetch, over: Partial<ClientOptions> = {}): DxosClient {
  return new DxosClient({ getToken: async () => 'tok', fetch: f, ...over })
}
