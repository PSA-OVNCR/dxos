// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Client của API quản trị `/admin/v1` (cùng origin). Hình dạng phản hồi theo core/src/dxos_core/admin/{router,ops}.py.
// Quy tắc như client Tầng 2: không bao giờ tự thử lại yêu cầu ghi (POST anchor:run); 401 đi qua chốt chặn đăng nhập.
import { ApiError, slugOf } from 'dxos-sdk-js'
import { useSession } from 'dxos-sdk-js/vue'
import { inject, type InjectionKey } from 'vue'

/** Mỗi thành phần là "ok" hoặc "down: <lý do ngắn>". */
export interface HealthReport {
  db: string
  clamav: string
  openbao: string
  flowable: string
  keycloak_default_roles: string
  anchor: { last_tree_size: number | null; last_anchor_age_s: number | null }
  seal_pending: number | null
  task_intents_stuck: number | null
  /** ok | none | expired | invalid | unknown | down: ... */
  seal_key: string
  org: string
}

export interface TreeHead {
  tree_size: number
  root_hash: string
  /** RFC 3339 UTC. */
  ts: string
  key_version: number
  signature: string
}

export interface LedgerStatus {
  tree_size: number
  latest_sth: TreeHead | null
  last_anchor: { tree_size: number; repo: string; commit_sha: string; anchored_at: string } | null
  pending_anchor_jobs: number
  verify: { ok: boolean; first_bad_idx: number | null }
}

export interface LedgerEntry {
  idx: number
  ts: string
  type: string
  app_id: string | null
  subject: string | null
  /** HMAC của sub, không phải định danh thật. */
  actor_ref: string | null
}

export type AnchorRunResult = TreeHead & { anchor_job_id: string | number }

export interface AdminApi {
  health(): Promise<HealthReport>
  ledgerStatus(): Promise<LedgerStatus>
  ledgerEntries(o?: { type?: string; limit?: number }): Promise<{ items: LedgerEntry[] }>
  /** Lập STH ngay và xếp việc neo. Ghi: gọi đúng một lần mỗi lần bấm. */
  anchorRun(): Promise<AnchorRunResult>
}

export interface AdminApiOptions {
  /** Mặc định '' = cùng origin. */
  baseUrl?: string
  getToken: () => Promise<string | null>
  onUnauthorized?: () => void
  /** Gọi khi một lời gọi thành công (để chốt chặn đăng nhập xóa dấu). */
  onSuccess?: () => void
  fetch?: typeof fetch
}

/** Câu hiện cho mọi 403: token hợp lệ nhưng không có vai trò dxos-admin (lõi trả 403 `forbidden`). */
export const NOT_ADMIN_TITLE = 'Tài khoản này không có quyền quản trị'

class HttpAdminApi implements AdminApi {
  private readonly baseUrl: string
  private readonly o: AdminApiOptions

  constructor(o: AdminApiOptions) {
    this.o = o
    this.baseUrl = o.baseUrl ?? ''
  }

  private async fail(resp: Response): Promise<never> {
    if (resp.status === 403) {
      // Cổng hay lõi đều chỉ có một nghĩa ở đây: tài khoản thiếu vai trò quản trị.
      throw new ApiError(403, 'not-admin', NOT_ADMIN_TITLE, undefined, null)
    }
    const ct = resp.headers.get('Content-Type') ?? ''
    let problem: Record<string, unknown> | null = null
    if (ct.startsWith('application/problem+json') || ct.startsWith('application/json')) {
      try {
        const body: unknown = await resp.json()
        if (body && typeof body === 'object' && !Array.isArray(body)) problem = body as Record<string, unknown>
      } catch {
        problem = null
      }
    }
    const type = typeof problem?.type === 'string' ? problem.type : null
    const title = typeof problem?.title === 'string' ? problem.title : resp.statusText || `HTTP ${resp.status}`
    const detail = typeof problem?.detail === 'string' ? problem.detail : undefined
    throw new ApiError(resp.status, type ? slugOf(type) : `http-${resp.status}`, title, detail, problem)
  }

  private async json<T>(method: string, path: string): Promise<T> {
    const headers = new Headers()
    const token = await this.o.getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const f = this.o.fetch ?? ((input, init) => fetch(input, init))
    const resp = await f(this.baseUrl + path, { method, headers })
    if (resp.status === 401) this.o.onUnauthorized?.()
    if (!resp.ok) await this.fail(resp)
    this.o.onSuccess?.()
    return (await resp.json()) as T
  }

  health(): Promise<HealthReport> {
    return this.json('GET', '/admin/v1/health')
  }

  ledgerStatus(): Promise<LedgerStatus> {
    return this.json('GET', '/admin/v1/ledger/status')
  }

  ledgerEntries(o: { type?: string; limit?: number } = {}): Promise<{ items: LedgerEntry[] }> {
    const q = new URLSearchParams()
    if (o.type) q.set('type', o.type)
    q.set('limit', String(o.limit ?? 20))
    return this.json('GET', `/admin/v1/ledger/entries?${q.toString()}`)
  }

  anchorRun(): Promise<AnchorRunResult> {
    return this.json('POST', '/admin/v1/anchor:run')
  }
}

export function createAdminApi(o: AdminApiOptions): AdminApi {
  return new HttpAdminApi(o)
}

export const ADMIN_API_KEY: InjectionKey<AdminApi> = Symbol('dxos-admin-api')

const bySession = new WeakMap<object, AdminApi>()

/** API cho view: bản được cấp (test) hoặc bản thật dựng từ phiên (token, chốt chặn đăng nhập). */
export function useAdminApi(): AdminApi {
  const given = inject(ADMIN_API_KEY, null)
  if (given) return given
  const session = useSession()
  let api = bySession.get(session)
  if (!api) {
    api = createAdminApi({
      getToken: () => session.auth.token(),
      onUnauthorized: () => { session.guard.onUnauthorized() },
      onSuccess: () => { session.guard.succeeded() },
    })
    bySession.set(session, api)
  }
  return api
}
