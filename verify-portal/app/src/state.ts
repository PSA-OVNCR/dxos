// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Trạng thái hiển thị của cổng đối soát (hàm thuần). Bảng ánh xạ của máy chủ lấy từ
// verify-portal/minimal/README.md mục "Trạng thái hiển thị"; nhãn cuối cùng do kết quả tự kiểm trên
// trình duyệt quyết định (S8.4, Review Focus 4): máy chủ chỉ được phép hạ nhãn, không được nâng nhãn.
import type { BundleResult, Json } from 'dxos-sdk-js'

/** Mã niêm phong hợp lệ (spec 25.1): chỉ nhận từ fragment, kiểm trước khi đưa vào URL. */
export const SEAL_ID = /^[A-Z2-7]{26}$/

export type PortalState =
  | 'NOT_FOUND' | 'KEYS_UNAVAILABLE' | 'RATE_LIMITED' | 'UNAVAILABLE' | 'PENDING'
  | 'SERVER_INVALID' | 'REVOKED' | 'WAIT_STH'
  | 'VALID_UNANCHORED' | 'VALID_ANCHORED'

export type Tone = 'ok' | 'warn' | 'bad' | 'wait' | 'unanchored'
export interface Verdict { label: string; tone: Tone; note: string }

type Obj = { [k: string]: Json }
export const isObj = (v: unknown): v is Obj =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
const field = (o: unknown, k: string): Json | undefined => (isObj(o) && Object.hasOwn(o, k) ? o[k] : undefined)

/**
 * Trạng thái theo phản hồi của `GET /verify/v1/seals/{id}`. Các kết quả kiểm của máy chủ phải đúng nghĩa đen
 * `true` mới được tin (chuỗi "true", 1, thiếu trường đều là không đạt). Mã HTTP lạ hay thân không đọc được là
 * UNAVAILABLE ("chưa kiểm được"), không bao giờ là "Không hợp lệ".
 */
export function viewState(serverStatus: number, view: Json | null): PortalState {
  if (serverStatus === 404) return 'NOT_FOUND'
  if (serverStatus === 503) return 'KEYS_UNAVAILABLE'
  if (serverStatus === 429) return 'RATE_LIMITED'
  if (serverStatus !== 200 || !isObj(view)) return 'UNAVAILABLE'
  if (view.status === 'SEAL_PENDING') return 'PENDING'

  const inc = field(view, 'inclusion')
  const hasInclusion = isObj(inc)
  const treeKnown = hasInclusion && inc.tree_size !== null && inc.tree_size !== undefined
  const verified = hasInclusion && inc.verified === true
  const sigOk = view.signature_valid === true
  if (!sigOk || !hasInclusion || (treeKnown && !verified)) return 'SERVER_INVALID'
  if (view.status === 'REVOKED') return 'REVOKED'
  if (view.status !== 'VALID') return 'SERVER_INVALID'
  if (!verified) return 'WAIT_STH'
  return isObj(inc.anchored) ? 'VALID_ANCHORED' : 'VALID_UNANCHORED'
}

const SERVER_VERDICT: Record<PortalState, Verdict> = {
  NOT_FOUND: { label: 'Không tìm thấy', tone: 'bad', note: 'Mã niêm phong không tồn tại hoặc không được công khai.' },
  KEYS_UNAVAILABLE: { label: 'Chưa kiểm được', tone: 'warn', note: 'Tạm thời chưa kiểm được chữ ký, thử lại sau' },
  RATE_LIMITED: { label: 'Chưa kiểm được', tone: 'warn', note: 'Quá nhiều lượt kiểm tra, thử lại sau ít phút.' },
  UNAVAILABLE: { label: 'Chưa kiểm được', tone: 'warn', note: 'Máy chủ chưa trả được kết quả, thử lại sau.' },
  PENDING: {
    label: 'Chờ niêm phong', tone: 'warn',
    note: 'Văn bản đã được duyệt, niêm phong đang được hoàn tất. Thử lại sau ít phút.',
  },
  SERVER_INVALID: {
    label: 'Không hợp lệ', tone: 'bad',
    note: 'Máy chủ báo chữ ký hoặc chứng minh thuộc sổ cái của niêm phong này không đạt.',
  },
  REVOKED: {
    label: 'Đã thu hồi', tone: 'bad',
    note: 'Niêm phong này đã bị thu hồi: không dùng làm căn cứ xác nhận văn bản.',
  },
  WAIT_STH: {
    label: 'Chữ ký hợp lệ — đang chờ công bố vào sổ cái', tone: 'wait',
    note: 'Niêm phong chưa nằm trong STH nào đã công bố. Thử lại sau lần công bố STH kế tiếp.',
  },
  VALID_UNANCHORED: {
    label: 'Hợp lệ — chưa neo công khai', tone: 'unanchored',
    note: 'STH phủ niêm phong này chưa được neo công khai. Thử lại sau lần neo kế tiếp.',
  },
  VALID_ANCHORED: { label: 'Hợp lệ', tone: 'ok', note: '' },
}

/** Nhãn mà máy chủ báo cho trạng thái này (dùng cho mục "Máy chủ báo" và cho các trạng thái không cần gói). */
export function serverVerdict(state: PortalState): Verdict {
  return SERVER_VERDICT[state]
}

/**
 * Lời mô tả điều máy chủ báo, cho mục "Máy chủ báo". Cố ý không dùng cụm "Hợp lệ"/"Không hợp lệ": hai cụm đó chỉ
 * thuộc nhãn cuối cùng (do trình duyệt tự kiểm quyết định) nên không bao giờ xuất hiện hai lần trên trang.
 */
const SERVER_SAYS: Record<PortalState, string> = {
  NOT_FOUND: 'mã này không có trong hệ thống',
  KEYS_UNAVAILABLE: 'tạm thời chưa kiểm được chữ ký',
  RATE_LIMITED: 'quá nhiều lượt kiểm tra',
  UNAVAILABLE: 'chưa trả được kết quả',
  PENDING: 'niêm phong đang chờ hoàn tất',
  SERVER_INVALID: 'chữ ký hoặc chứng minh thuộc sổ cái không đạt',
  REVOKED: 'niêm phong đã bị thu hồi',
  WAIT_STH: 'chữ ký đạt, đang chờ STH phủ niêm phong',
  VALID_UNANCHORED: 'chữ ký và sổ cái đạt, STH chưa neo công khai',
  VALID_ANCHORED: 'chữ ký và sổ cái đạt, STH đã neo công khai',
}

export function serverSays(state: PortalState): string {
  return SERVER_SAYS[state]
}

const NEEDS_LOCAL: ReadonlySet<PortalState> = new Set(['VALID_UNANCHORED', 'VALID_ANCHORED'])

/**
 * Nhãn cuối cùng. `local` là kết quả `verifyBundle` trên gói do máy chủ trả (null: chưa có gói).
 * - tự kiểm hỏng (trừ UNSUPPORTED_CRYPTO) → "Không hợp lệ", bất kể máy chủ báo gì;
 * - UNSUPPORTED_CRYPTO → nhãn của máy chủ kèm lời giải thích;
 * - đạt nhưng khóa đã ghim còn STH phủ niêm phong chưa được công bố ở repo neo (`pendingAnchor`, Plan 04 R11) →
 *   "Hợp lệ — chưa neo công khai" như trạng thái chưa neo, kèm lời nhắc kiểm lại sau vài phút;
 * - đạt → "Hợp lệ — đã/chưa đối chiếu repo neo", trừ khi máy chủ báo đã thu hồi (thu hồi không nằm trong
 *   gói đã ký nên chỉ máy chủ biết; máy chủ chỉ được phép hạ nhãn);
 * - chưa có kết quả tự kiểm mà máy chủ báo VALID → "Chưa tự kiểm", không bao giờ "Hợp lệ" trần.
 */
export function finalVerdict(state: PortalState, local: BundleResult | null): Verdict {
  const server = SERVER_VERDICT[state]
  if (local !== null && !local.ok) {
    if (local.code === 'UNSUPPORTED_CRYPTO') {
      return { ...server, note: `Trình duyệt này không tự kiểm được chữ ký. ${server.note}`.trim() }
    }
    return {
      label: 'Không hợp lệ', tone: 'bad',
      note: 'Trình duyệt tự kiểm gói bằng chứng và thấy không đạt, dù máy chủ báo gì.',
    }
  }
  if (local !== null && local.ok) {
    if (state === 'REVOKED') return { ...server, note: `${server.note} Chữ ký trong gói đã được trình duyệt kiểm đạt.` }
    if (!NEEDS_LOCAL.has(state)) return server
    if (local.pendingAnchor === true) {
      return {
        ...SERVER_VERDICT.VALID_UNANCHORED,
        note: 'Chữ ký, chứng minh thuộc sổ cái và khóa đã được đối chiếu với repo neo, nhưng STH phủ niêm phong này chưa được '
          + 'công bố ở repo neo. Hãy kiểm tra lại sau vài phút.',
      }
    }
    return local.pinned
      ? { label: 'Hợp lệ — đã đối chiếu repo neo', tone: 'ok',
          note: 'Trình duyệt tự kiểm chữ ký, chứng minh thuộc sổ cái và so STH với repo neo.' }
      : { label: 'Hợp lệ — chưa đối chiếu repo neo', tone: 'unanchored',
          note: 'Trình duyệt tự kiểm chữ ký và chứng minh thuộc sổ cái, nhưng chưa so STH với repo neo.' }
  }
  if (NEEDS_LOCAL.has(state)) {
    return {
      label: 'Chưa tự kiểm trên trình duyệt', tone: 'wait',
      note: 'Máy chủ báo đạt, nhưng chưa có gói bằng chứng để trình duyệt tự kiểm.',
    }
  }
  return server
}

/** Thời điểm theo giờ Việt Nam (Asia/Ho_Chi_Minh); chuỗi không phải thời điểm thì giữ nguyên. */
export function formatVn(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const text = new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(d)
  return `${text} (giờ Việt Nam)`
}

/** Giá trị công khai → chuỗi hiển thị (số nguyên lớn dạng bigint giữ đủ chữ số). */
export function valueText(v: unknown): string {
  if (typeof v === 'string') return v
  if (v === null || v === undefined) return ''
  if (typeof v === 'bigint' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  return JSON.stringify(v, (_k, x: unknown) => (typeof x === 'bigint' ? x.toString() : x)) ?? ''
}

export interface Row { label: string; value: string }

/**
 * Các dòng "trường công khai" theo `public_labels` (nhãn đến từ manifest, chỉ hiển thị bằng {{ }}). Giá trị lấy
 * từ `values` (payload đã ký khi tự kiểm đạt, hoặc phản hồi của máy chủ khi chưa có gói).
 */
export function publicRows(values: unknown, labels: unknown): Row[] {
  if (!isObj(values)) return []
  return Object.keys(values).map((k) => {
    const label = isObj(labels) && Object.hasOwn(labels, k) ? valueText(labels[k]) : k
    return { label, value: valueText(values[k]) }
  })
}

export { field }
