// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Client HTTP cho API Tầng 2 của lõi (docs/api/contract-tier2.md).
// Quy tắc: không bao giờ tự thử lại yêu cầu ghi; mọi ghi cần If-Match đều GET bản ghi ngay trước đó.
import { ApiError, slugOf } from './errors'
import type {
  AttachmentItem, BulkResult, DxRecord, ManifestView, ObjectVariant, SealInfo, SealState, TaskItem, UploadStatus,
} from './types'

export interface ClientOptions {
  /** Mặc định '' = cùng origin. */
  baseUrl?: string
  getToken: () => Promise<string | null>
  onUnauthorized?: () => void
  fetch?: typeof fetch
}

const BULK_MAX = 500
const PAGE_LIMIT = 200

/**
 * Mã hóa một đoạn đường dẫn. `encodeURIComponent` để nguyên dấu `.`, nên mã hóa thêm thành `%2E`:
 * đoạn `..` không bao giờ bị chuẩn hóa thành đi lên thư mục cha.
 */
function seg(s: string): string {
  return encodeURIComponent(s).replace(/\./g, '%2E')
}

interface Init {
  body?: BodyInit
  headers?: Record<string, string>
  /** false = gọi ẩn danh (xác minh công khai): không gửi token, 401 không kích hoạt onUnauthorized. */
  auth?: boolean
}

export class DxosClient {
  private readonly baseUrl: string
  private readonly getToken: ClientOptions['getToken']
  private readonly onUnauthorized?: () => void
  private readonly fetchImpl: typeof fetch

  constructor(o: ClientOptions) {
    this.baseUrl = o.baseUrl ?? ''
    this.getToken = o.getToken
    this.onUnauthorized = o.onUnauthorized
    this.fetchImpl = o.fetch ?? ((input, init) => fetch(input, init))
  }

  // ---- hạ tầng ----------------------------------------------------------------------------

  private async send(method: string, path: string, init: Init = {}): Promise<Response> {
    const headers = new Headers(init.headers)
    if (init.auth !== false) {
      const token = await this.getToken()
      if (token) headers.set('Authorization', `Bearer ${token}`)
    }
    const resp = await this.fetchImpl(this.baseUrl + path, { method, headers, body: init.body })
    if (resp.status === 401 && init.auth !== false) this.onUnauthorized?.()
    return resp
  }

  private async fail(resp: Response): Promise<never> {
    const ct = resp.headers.get('Content-Type') ?? ''
    let problem: Record<string, unknown> | null = null
    // 401/413/429 từ APISIX/nginx có thể không phải JSON: chỉ parse khi header cho biết là JSON.
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

  private async ok(method: string, path: string, init?: Init): Promise<Response> {
    const resp = await this.send(method, path, init)
    if (!resp.ok) await this.fail(resp)
    return resp
  }

  private async json<T>(method: string, path: string, init?: Init): Promise<T> {
    return (await (await this.ok(method, path, init)).json()) as T
  }

  private jsonBody(body: unknown, extra: Record<string, string> = {}): Init {
    return { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json', ...extra } }
  }

  private recordPath(app: string, col: string, id: string): string {
    return `/api/v1/apps/${seg(app)}/collections/${seg(col)}/records/${seg(id)}`
  }

  /** GET bản ghi để lấy version mới nhất, rồi gửi ghi với `If-Match: "<version>"` (có ngoặc kép). */
  private async withVersion<T>(
    app: string, col: string, id: string,
    write: (path: string, ifMatch: Record<string, string>) => Promise<T>,
  ): Promise<T> {
    const current = await this.get(app, col, id)
    return write(this.recordPath(app, col, id), { 'If-Match': `"${current.version}"` })
  }

  // ---- danh tính, manifest ---------------------------------------------------------------

  whoami(): Promise<{ sub: string; roles: string[]; is_admin: boolean }> {
    return this.json('GET', '/api/v1/whoami')
  }

  manifest(app: string): Promise<ManifestView> {
    return this.json('GET', `/api/v1/apps/${seg(app)}/manifest`)
  }

  // ---- bản ghi ---------------------------------------------------------------------------

  list(app: string, col: string, o: { cursor?: string; limit?: number } = {}):
    Promise<{ items: DxRecord[]; next_cursor: string | null }> {
    const q = new URLSearchParams()
    if (o.cursor) q.set('cursor', o.cursor)
    if (o.limit !== undefined) q.set('limit', String(o.limit))
    const qs = q.toString()
    return this.json('GET', `/api/v1/apps/${seg(app)}/collections/${seg(col)}/records${qs ? `?${qs}` : ''}`)
  }

  async listAll(app: string, col: string, maxItems = 2000): Promise<DxRecord[]> {
    const out: DxRecord[] = []
    let cursor: string | undefined
    while (out.length < maxItems) {
      const page = await this.list(app, col, { cursor, limit: Math.min(PAGE_LIMIT, maxItems - out.length) })
      out.push(...page.items)
      if (!page.next_cursor) break
      cursor = page.next_cursor
    }
    return out.slice(0, maxItems)
  }

  get(app: string, col: string, id: string): Promise<DxRecord> {
    return this.json('GET', this.recordPath(app, col, id))
  }

  create(app: string, col: string, data: Record<string, unknown>): Promise<DxRecord> {
    return this.json('POST', `/api/v1/apps/${seg(app)}/collections/${seg(col)}/records`, this.jsonBody(data))
  }

  async bulk(app: string, col: string, rows: Record<string, unknown>[]): Promise<BulkResult[]> {
    if (rows.length > BULK_MAX) throw new Error(`bulk: tối đa ${BULK_MAX} dòng mỗi lần, nhận ${rows.length}`)
    const r = await this.json<{ results: BulkResult[] }>(
      'POST', `/api/v1/apps/${seg(app)}/collections/${seg(col)}/records:bulk`, this.jsonBody(rows))
    return r.results
  }

  patch(app: string, col: string, id: string, changes: Record<string, unknown>): Promise<DxRecord> {
    return this.withVersion(app, col, id, (path, h) => this.json('PATCH', path, this.jsonBody(changes, h)))
  }

  // ---- tệp đính kèm ----------------------------------------------------------------------

  upload(app: string, col: string, id: string, file: Blob, filename: string): Promise<{ upload_id: string }> {
    const form = new FormData()
    form.append('file', file, filename) // Content-Type + boundary do trình duyệt đặt
    return this.json('POST', `${this.recordPath(app, col, id)}/attachments`, { body: form })
  }

  uploadStatus(uploadId: string): Promise<UploadStatus> {
    return this.json('GET', `/api/v1/uploads/${seg(uploadId)}`)
  }

  async attachments(app: string, col: string, id: string): Promise<AttachmentItem[]> {
    const r = await this.json<{ items: AttachmentItem[] }>('GET', `${this.recordPath(app, col, id)}/attachments`)
    return r.items
  }

  /**
   * Tải một tệp CLEAN theo sha256. `variant='original'` (mặc định) có thể bị khóa theo quyền xem dữ liệu cá nhân
   * (máy chủ trả 404), `variant='redacted'` là bản che (chỉ có khi đã dựng). GET một lần, không tự thử lại.
   */
  async downloadObject(sha256: string, variant: ObjectVariant = 'original'): Promise<Blob> {
    return (await this.ok('GET', `/api/v1/objects/${seg(sha256)}?variant=${variant}`)).blob()
  }

  // ---- xem trang (Viewer, Plan 04 Task 8) -------------------------------------------------

  /**
   * Viewer có bật và sống không: đúng khi `GET /view/v1/healthz` trả 200. Mọi trường hợp khác (route vắng ở p8, 502/503
   * của cổng, mất mạng) là `false`, không ném lỗi: Viewer là tính năng tùy chọn nên vắng mặt không phải lỗi. Một lần
   * gọi, không thử lại. Như mọi lời gọi có token, 401 kích hoạt `onUnauthorized`.
   */
  async viewerAvailable(): Promise<boolean> {
    try {
      return (await this.send('GET', '/view/v1/healthz')).status === 200
    } catch {
      return false
    }
  }

  /** Số trang của một tệp CLEAN. `variant` chuyển nguyên cho Viewer (rồi tới API): quyền xem bản gốc do máy chủ quyết định. */
  viewInfo(sha256: string, variant: ObjectVariant = 'original'): Promise<{ pages: number }> {
    return this.json('GET', `/view/v1/objects/${seg(sha256)}/info?variant=${variant}`)
  }

  /** Ảnh PNG (có watermark) của MỘT trang, đánh số từ 1. GET một lần, không tự thử lại; lỗi là `ApiError`. */
  async viewPage(sha256: string, page: number, variant: ObjectVariant = 'original'): Promise<Blob> {
    if (!Number.isInteger(page) || page < 1) throw new Error(`viewPage: số trang phải là số nguyên từ 1, nhận ${page}`)
    return (await this.ok('GET', `/view/v1/objects/${seg(sha256)}/pages/${page}.png?variant=${variant}`)).blob()
  }

  // ---- quy trình -------------------------------------------------------------------------

  start(app: string, col: string, id: string): Promise<DxRecord> {
    return this.withVersion(app, col, id, (path, h) => this.json('POST', `${path}/workflow:start`, { headers: h }))
  }

  async tasks(app: string): Promise<TaskItem[]> {
    const r = await this.json<{ items: TaskItem[] }>('GET', `/api/v1/apps/${seg(app)}/tasks?assigned=me`)
    return r.items
  }

  /** Mục hộp việc không có version bản ghi: GET bản ghi của task để lấy If-Match. */
  async complete(app: string, task: TaskItem, decision: string, comment?: string):
    Promise<{ record: DxRecord; seal_state: SealState; seal_id: string | null }> {
    const current = await this.get(app, task.collection, task.record_id)
    const body: Record<string, unknown> = { decision }
    if (comment !== undefined) body.comment = comment
    return this.json('POST', `/api/v1/apps/${seg(app)}/tasks/${seg(task.task_id)}:complete`,
      this.jsonBody(body, { 'If-Match': `"${current.version}"` }))
  }

  piiReview(app: string, col: string, id: string): Promise<DxRecord> {
    return this.withVersion(app, col, id, (path, h) => this.json('POST', `${path}:pii-review`, { headers: h }))
  }

  revoke(app: string, col: string, id: string, reason_code: string, note?: string): Promise<DxRecord> {
    const body: Record<string, unknown> = { reason_code }
    if (note !== undefined) body.note = note
    return this.withVersion(app, col, id, (path, h) => this.json('POST', `${path}:revoke`, this.jsonBody(body, h)))
  }

  erasePii(app: string, col: string, id: string, fields: string[], reason_code: string): Promise<DxRecord> {
    return this.withVersion(app, col, id, (path, h) =>
      this.json('POST', `${path}:erase-pii`, this.jsonBody({ fields, reason_code }, h)))
  }

  // ---- dấu chứng nhận --------------------------------------------------------------------

  seal(app: string, col: string, id: string): Promise<SealInfo> {
    return this.json('GET', `${this.recordPath(app, col, id)}/seal`)
  }

  // ---- xác minh công khai (ẩn danh, không gửi token) -------------------------------------

  /** Trả văn bản thô kèm mã trạng thái (kể cả 404): Task 4 tự parse. */
  async publicSeal(sealId: string): Promise<{ status: number; text: string }> {
    const resp = await this.send('GET', `/verify/v1/seals/${seg(sealId)}`, { auth: false })
    return { status: resp.status, text: await resp.text() }
  }

  checkHash(sealId: string, sha256: string):
    Promise<{ match: boolean } | { match: false; status: 'SEAL_PENDING' }> {
    return this.json('POST', `/verify/v1/seals/${seg(sealId)}:check`, { ...this.jsonBody({ sha256 }), auth: false })
  }

  /** Có sha256 thì POST `:bundle` (ứng dụng yêu cầu tệp), không thì GET `/bundle`. Trả văn bản JSON thô. */
  async bundle(sealId: string, sha256?: string): Promise<string> {
    const resp = sha256 === undefined
      ? await this.ok('GET', `/verify/v1/seals/${seg(sealId)}/bundle`, { auth: false })
      : await this.ok('POST', `/verify/v1/seals/${seg(sealId)}:bundle`, { ...this.jsonBody({ sha256 }), auth: false })
    return resp.text()
  }
}
