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

export type AppStatus = 'PENDING' | 'ACTIVE' | 'DISABLED'

/** Một phiên bản của một app (GET /admin/v1/apps). Người nộp/duyệt chỉ là HMAC của sub, không phải định danh thật. */
export interface AppVersionRow {
  app_id: string
  version: string
  status: AppStatus
  manifest_sha256: string
  submitted_by_ref: string | null
  approved_by_ref: string | null
  created_at: string
}

/** Cặp giá trị cũ/mới; `old` là null khi chưa có bản đang hoạt động để so. */
export interface Pair<T> { old: T | null; new: T | null }

/** Diff quyền của một phiên bản (installer.permission_diff). Mọi danh sách đã sắp xếp. */
export interface PermissionDiff {
  app_id: string
  version: string
  /** Bản mốc để so (ACTIVE, hoặc bản từng ACTIVE); null nếu app chưa từng được duyệt. */
  against: string | null
  roles_added: string[]
  collections_added: string[]
  fields_added: Record<string, string[]>
  access: Record<string, { read: string[]; create: string[]; update: string[] }>
  pii_reveal_roles: Pair<string[]>
  pii_erase_roles: Pair<string[]>
  seal: Pair<unknown>
  verify: Pair<unknown>
  tasks: Record<string, { role: string; guards: string[] }>
  labels: Record<string, Record<string, Pair<string>>>
  sequences: Record<string, Record<string, Pair<unknown>>>
  bpmn_sha256: string | null
}

/** Kết quả :approve (installer._installed_view). */
export interface InstalledView {
  app_id: string
  version: string
  status: AppStatus
  manifest_sha256: string
  /** true khi người duyệt chính là người nộp (chỉ xảy ra khi máy chủ bật DXOS_ALLOW_SELF_APPROVAL). */
  self_approved: boolean
  deployment_id: string | null
  rendered_sha256: string | null
}

export interface DisabledView { app_id: string; version: string; status: 'DISABLED' }

/** Upload bị cách ly (GET /admin/v1/quarantine): không có tên tệp, chỉ mã băm nội dung. */
export interface QuarantineItem {
  upload_id: string
  sha256: string
  status: 'INFECTED' | 'REJECTED'
  reason: string | null
  app_id: string
  created_at: string
}

export interface AdminApi {
  health(): Promise<HealthReport>
  ledgerStatus(): Promise<LedgerStatus>
  ledgerEntries(o?: { type?: string; limit?: number }): Promise<{ items: LedgerEntry[] }>
  /** Lập STH ngay và xếp việc neo. Ghi: gọi đúng một lần mỗi lần bấm. */
  anchorRun(): Promise<AnchorRunResult>
  apps(): Promise<AppVersionRow[]>
  appDiff(appId: string, version: string): Promise<PermissionDiff>
  /** Ghi: đúng một lần mỗi lần bấm. Máy chủ quyết định bốn mắt (403 self_approval); SPA không tự chặn. */
  approveApp(appId: string, version: string): Promise<InstalledView>
  /** Ghi: đúng một lần mỗi lần bấm. */
  disableApp(appId: string): Promise<DisabledView>
  quarantine(limit?: number): Promise<QuarantineItem[]>
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

/** `reason` của 403 `forbidden` khi người duyệt cũng là người nộp (core/registry/installer.py, bốn mắt). */
const SELF_APPROVAL_REASON = 'self_approval'
export const SELF_APPROVAL_TITLE = 'Người duyệt phải khác người nộp (nguyên tắc bốn mắt / four eyes): hãy nhờ quản trị viên khác duyệt'

/**
 * Câu tiếng Việt cho các lỗi vòng đời app mà SDK chưa biết (ProblemMessage dùng `title` cho slug lạ).
 * `{detail}` được thay bằng `detail` của máy chủ (lý do cụ thể, ví dụ vì sao manifest sai).
 */
const ADMIN_TITLES: Record<string, string> = {
  'app-version-not-found': 'Không tìm thấy phiên bản này của ứng dụng',
  'app-version-not-pending': 'Phiên bản này không còn ở trạng thái chờ duyệt, hãy tải lại danh sách',
  'app-version-conflict': 'Phiên bản này đã được nộp hoặc xử lý, hãy tải lại danh sách',
  'install-in-progress': 'Đang có thao tác cài đặt khác cho ứng dụng này, hãy thử lại sau ít phút',
  'version-not-newer': 'Phiên bản phải mới hơn phiên bản đang hoạt động',
  'deployment-mismatch': 'Quy trình đã triển khai của phiên bản này khác bản dựng lại, hãy tăng số phiên bản',
  'idp-admin-unavailable': 'Dịch vụ đăng nhập (Keycloak) tạm thời không sẵn sàng để tạo vai trò, hãy thử lại sau ít phút',
  'manifest-invalid': 'Bản khai báo (manifest) không hợp lệ: {detail}',
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
    const detail = typeof problem?.detail === 'string' ? problem.detail : undefined
    if (resp.status === 403) {
      // Người duyệt trùng người nộp: câu trả lời của máy chủ cho bốn mắt, không phải thiếu vai trò.
      if (problem?.reason === SELF_APPROVAL_REASON) {
        throw new ApiError(403, 'self-approval', SELF_APPROVAL_TITLE, detail, problem)
      }
      // Mọi 403 khác (cổng hay lõi) chỉ có một nghĩa ở đây: tài khoản thiếu vai trò quản trị.
      throw new ApiError(403, 'not-admin', NOT_ADMIN_TITLE, undefined, null)
    }
    const type = typeof problem?.type === 'string' ? problem.type : null
    const slug = type ? slugOf(type) : `http-${resp.status}`
    const given = typeof problem?.title === 'string' ? problem.title : resp.statusText || `HTTP ${resp.status}`
    const template = Object.hasOwn(ADMIN_TITLES, slug) ? ADMIN_TITLES[slug] : undefined
    const title = template === undefined ? given : template.replace('{detail}', detail ?? given)
    throw new ApiError(resp.status, slug, title, detail, problem)
  }

  private async json<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers = new Headers()
    const token = await this.o.getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const init: RequestInit = { method, headers }
    if (body !== undefined) {
      headers.set('Content-Type', 'application/json')
      init.body = JSON.stringify(body)
    }
    const f = this.o.fetch ?? ((input, init2) => fetch(input, init2))
    const resp = await f(this.baseUrl + path, init)
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

  apps(): Promise<AppVersionRow[]> {
    return this.json('GET', '/admin/v1/apps')
  }

  appDiff(appId: string, version: string): Promise<PermissionDiff> {
    return this.json('GET', `/admin/v1/apps/${encodeURIComponent(appId)}/versions/${encodeURIComponent(version)}/diff`)
  }

  approveApp(appId: string, version: string): Promise<InstalledView> {
    return this.json('POST', `/admin/v1/apps/${encodeURIComponent(appId)}:approve`, { version })
  }

  disableApp(appId: string): Promise<DisabledView> {
    return this.json('POST', `/admin/v1/apps/${encodeURIComponent(appId)}:disable`)
  }

  quarantine(limit = 100): Promise<QuarantineItem[]> {
    return this.json('GET', `/admin/v1/quarantine?limit=${String(limit)}`)
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
