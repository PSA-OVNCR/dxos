// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Công cụ test dùng chung cho SDK và các ứng dụng Tầng 2 (import từ "dxos-sdk-js/testing").
// Chỉ dùng trong test: import `vitest`, không bao giờ được nhập từ `src/index.ts` hay `src/vue/index.ts`.
import { vi, type Mock } from 'vitest'
import { DxosClient, type ClientOptions } from './client'
import { ApiError } from './errors'
import type { AttachmentItem, DxRecord, SealInfo, TaskItem } from './types'

// ---- fetch giả -----------------------------------------------------------------------------

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

/** DxosClient thật chạy trên fetch giả. */
export function client(f: typeof fetch, over: Partial<ClientOptions> = {}): DxosClient {
  return new DxosClient({ getToken: async () => 'tok', fetch: f, ...over })
}

// ---- dữ liệu mẫu ---------------------------------------------------------------------------

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

export function att(over: Partial<AttachmentItem> = {}): AttachmentItem {
  return {
    upload_id: 'u1', status: 'CLEAN', sha256: 'a'.repeat(64), reason: null,
    created_at: '2026-10-22T00:00:00Z', pii: null, ...over,
  }
}

const SEAL_ID = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' // 26 ký tự thuộc [A-Z2-7]

export function sealInfo(over: Partial<SealInfo> = {}): SealInfo {
  const origin = (globalThis as { location?: { origin: string } }).location?.origin ?? 'https://dxos.test'
  return {
    seal_id: SEAL_ID, seal_state: 'SEALED', issued_at: '2026-10-22T00:00:00Z', key_version: 1,
    public_fields: {}, verify_url: `${origin}/apps/verify/#${SEAL_ID}`, ...over,
  }
}

// ---- lỗi problem+json ----------------------------------------------------------------------

const STATUS: Record<string, number> = {
  'guard-failed': 403, 'not-found': 404, 'app-not-active': 404, forbidden: 403, unauthenticated: 401,
  'bad-request': 400, 'invalid-request': 422, schema: 422, 'invalid-decision': 422, 'invalid-comment': 422,
  'invalid-reason-code': 422, 'invalid-note': 422, 'payload-too-large': 413, 'precondition-required': 428,
  'length-required': 411, 'unsupported-media-type': 415, 'integrity-error': 500, internal: 500,
  'workflow-finalize-failed': 500, 'workflow-model-mismatch': 500,
  'storage-unavailable': 503, 'kms-unavailable': 503, 'workflow-unavailable': 503, 'workflow-pending': 503,
  'idp-unavailable': 503, 'key-statement-invalid': 503, 'seal-key-expired': 503, 'org-not-configured': 503,
  'keys-unavailable': 503, 'not-ready': 503,
}

/**
 * ApiError như client thật dựng từ một phản hồi problem+json. `ext` là các trường mở rộng (`reason`, `guard`,
 * `errors`...) và có thể ghi đè `title`, `detail`, `status`. Mặc định: 409 cho slug không có trong bảng.
 */
export function problem(slug: string, ext: Record<string, unknown> = {}): ApiError {
  const { title: t, detail: d, status: s, ...rest } = ext
  const status = typeof s === 'number' ? s : STATUS[slug] ?? 409
  const title = typeof t === 'string' ? t : slug
  const detail = typeof d === 'string' ? d : undefined
  const body: Record<string, unknown> = {
    type: `https://dxos.dev/problems/${slug}`, title, status, ...(detail ? { detail } : {}), ...rest,
  }
  return new ApiError(status, slug, title, detail, body)
}

/** Tên khác của `problem`, đọc tự nhiên hơn trong `expect(messageFor(apiErr(...)))`. */
export const apiErr = problem

// ---- DxosClient giả ------------------------------------------------------------------------

export const CLIENT_METHODS = [
  'whoami', 'manifest', 'list', 'listAll', 'get', 'create', 'bulk', 'patch', 'upload', 'uploadStatus',
  'attachments', 'downloadObject', 'start', 'tasks', 'complete', 'piiReview', 'revoke', 'erasePii', 'seal',
  'publicSeal', 'checkHash', 'bundle',
] as const satisfies readonly (keyof DxosClient)[]

type Method = (typeof CLIENT_METHODS)[number]
type Ret<K extends Method> = Awaited<ReturnType<DxosClient[K]>>
type Args<K extends Method> = Parameters<DxosClient[K]>
type Entry<K extends Method> = Ret<K> | Error | ((...args: Args<K>) => Ret<K> | Promise<Ret<K>>)

export type FakeClientOptions = { [K in Method]?: Entry<K> | Entry<K>[] } & { whoamiRoles?: string[] }
export type FakeClient = DxosClient & { [K in Method]: Mock<DxosClient[K]> }

/** Phương thức có kết quả là mảng: một mảng phẳng là GIÁ TRỊ, không phải chuỗi kết quả lần lượt. */
const ARRAY_RESULT = new Set<Method>(['listAll', 'attachments', 'tasks', 'bulk'])

function successive(name: Method, v: unknown): v is unknown[] {
  if (!Array.isArray(v)) return false
  if (!ARRAY_RESULT.has(name)) return true
  return v.some((x) => Array.isArray(x) || x instanceof Error || typeof x === 'function')
}

/**
 * Client giả: mọi phương thức của `DxosClient` là `vi.fn`. Tuỳ chọn `opts[tên]`:
 * giá trị (trả cho mọi lần gọi), mảng (lần lượt từng lần gọi, lần cuối lặp lại), hàm (nhận đối số),
 * hoặc `Error`/`ApiError` (bị ném, tức Promise bị từ chối). Phương thức không cấu hình thì từ chối với lỗi rõ ràng.
 */
export function fakeClient(opts: FakeClientOptions = {}): FakeClient {
  const out: Record<string, Mock> = {}
  for (const name of CLIENT_METHODS) {
    const configured = Object.hasOwn(opts, name)
    const cfg: unknown = name === 'whoami' && !configured
      ? { sub: 'u', roles: opts.whoamiRoles ?? [], is_admin: false }
      : (opts as Record<string, unknown>)[name]
    const known = configured || name === 'whoami'
    let calls = 0
    out[name] = vi.fn(async (...args: unknown[]) => {
      if (!known || (Array.isArray(cfg) && successive(name, cfg) && cfg.length === 0)) {
        throw new Error(`fakeClient: ${name}() chưa được cấu hình`)
      }
      let entry = cfg
      if (successive(name, cfg)) entry = cfg[Math.min(calls, cfg.length - 1)]
      calls += 1
      if (entry instanceof Error) throw entry
      if (typeof entry === 'function') return (entry as (...a: unknown[]) => unknown)(...args)
      return entry
    })
  }
  return out as unknown as FakeClient
}
