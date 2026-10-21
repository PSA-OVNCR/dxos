// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Thông điệp lỗi tiếng Việt cho mọi problem+json mà lõi trả cho client Tầng 2 (contract-tier2.md mục 8).
import { ApiError } from '../errors'

/**
 * Mọi slug không dành riêng cho quản trị mà lõi có thể trả. `tests/repo/test_web_hygiene.py` đối chiếu
 * mảng này với các `ProblemError(...)` thật trong `core/src` để danh sách không lệch khi lõi thêm lỗi mới.
 */
export const CORE_SLUGS = [
  // chung, HTTP_SLUGS mặc định của lõi
  'bad-request', 'conflict', 'forbidden', 'http-error', 'internal', 'invalid-request', 'method-not-allowed',
  'not-acceptable', 'not-found', 'payload-too-large', 'precondition-failed', 'precondition-required',
  'rate-limited', 'unauthorized', 'unavailable', 'unsupported-media-type',
  // định danh, tình trạng hệ thống
  'app-not-active', 'idp-unavailable', 'length-required', 'not-ready', 'unauthenticated',
  // bản ghi, tệp
  'integrity-error', 'record-in-workflow', 'record-not-open', 'record-sealed', 'schema', 'seal-pending',
  'storage-unavailable', 'version-conflict',
  // quy trình
  'already-running', 'app-not-deployed', 'attachments-not-clean', 'attachments-pending', 'guard-failed',
  'invalid-comment', 'invalid-decision', 'no-workflow', 'task-gone', 'task-unknown',
  'workflow-finalize-failed', 'workflow-inconsistent', 'workflow-model-mismatch', 'workflow-pending',
  'workflow-unavailable',
  // khoá ký, niêm phong, xác minh
  'invalid-note', 'invalid-reason-code', 'key-statement-invalid', 'keys-unavailable', 'kms-unavailable',
  'not-sealed', 'org-not-configured', 'seal-key-expired',
] as const

const RELOAD = 'Dữ liệu đã thay đổi, hãy tải lại'
const TRY_LATER = 'hãy thử lại sau ít phút'

const BY_SLUG: Record<(typeof CORE_SLUGS)[number], string> = {
  'bad-request': 'Yêu cầu không hợp lệ',
  conflict: RELOAD,
  forbidden: 'Bạn không có quyền thực hiện thao tác này',
  'http-error': 'Máy chủ trả về lỗi không xác định',
  internal: `Máy chủ gặp sự cố, ${TRY_LATER}`,
  'invalid-request': 'Dữ liệu gửi lên không hợp lệ',
  'method-not-allowed': 'Thao tác này không được hỗ trợ',
  'not-acceptable': 'Máy chủ không trả được định dạng dữ liệu yêu cầu',
  'not-found': 'Không tìm thấy dữ liệu hoặc bạn không có quyền xem',
  'payload-too-large': 'Dữ liệu hoặc tệp quá lớn',
  'precondition-failed': RELOAD,
  'precondition-required': 'Thiếu thông tin phiên bản của dữ liệu, hãy tải lại trang rồi thử lại',
  'rate-limited': 'Thao tác quá nhanh, hãy đợi một lát rồi thử lại',
  unauthorized: 'Phiên đăng nhập không hợp lệ, hãy đăng nhập lại',
  unavailable: `Dịch vụ tạm thời không sẵn sàng, ${TRY_LATER}`,
  'unsupported-media-type': 'Định dạng dữ liệu gửi lên không được hỗ trợ',

  'app-not-active': 'Ứng dụng chưa được kích hoạt hoặc không tồn tại',
  'idp-unavailable': `Dịch vụ đăng nhập tạm thời không sẵn sàng, ${TRY_LATER}`,
  'length-required': 'Yêu cầu thiếu độ dài nội dung, hãy thử lại',
  'not-ready': `Hệ thống chưa sẵn sàng, ${TRY_LATER}`,
  unauthenticated: 'Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn',

  'integrity-error': 'Tệp lưu trữ không qua được kiểm tra toàn vẹn, hãy báo quản trị viên',
  'record-in-workflow': 'Hồ sơ đang trong quy trình xử lý, không thể sửa hoặc xoá dữ liệu lúc này',
  'record-not-open': 'Hồ sơ không còn ở trạng thái cho phép đính kèm tệp',
  'record-sealed': 'Hồ sơ đã được niêm phong, không thể thay đổi',
  schema: 'Dữ liệu chưa hợp lệ',
  'seal-pending': 'Hồ sơ đang chờ niêm phong, hãy thử lại sau',
  'storage-unavailable': `Kho lưu trữ tệp tạm thời không sẵn sàng, ${TRY_LATER}`,
  'version-conflict': RELOAD,

  'already-running': 'Hồ sơ này đã được đưa vào quy trình',
  'app-not-deployed': 'Quy trình của ứng dụng chưa được triển khai, hãy báo quản trị viên',
  'attachments-not-clean': 'Chưa đủ tệp đính kèm đã kiểm dịch sạch',
  'attachments-pending': 'Còn tệp đính kèm đang được kiểm dịch, hãy đợi rồi thử lại',
  'guard-failed': 'Chưa đạt điều kiện kiểm soát của bước này',
  'invalid-comment': 'Ý kiến không hợp lệ (tối đa 1000 ký tự)',
  'invalid-decision': 'Quyết định không hợp lệ cho bước này',
  'no-workflow': 'Ứng dụng này không có quy trình xử lý',
  'task-gone': RELOAD,
  'task-unknown': 'Bước này không còn được ứng dụng khai báo, hãy báo quản trị viên',
  'workflow-finalize-failed': 'Bước đã hoàn thành nhưng chưa ghi nhận được, hệ thống sẽ tự đối chiếu; hãy tải lại sau ít phút',
  'workflow-inconsistent': 'Trạng thái quy trình không nhất quán, hãy tải lại hoặc báo quản trị viên',
  'workflow-model-mismatch': 'Quy trình đã triển khai không khớp với bản khai báo, hãy báo quản trị viên',
  'workflow-pending': 'Kết quả của bước trước chưa rõ, hãy đợi ít giây rồi thử lại',
  'workflow-unavailable': `Máy chủ quy trình tạm thời không sẵn sàng, ${TRY_LATER}`,

  'invalid-note': 'Ghi chú không hợp lệ',
  'invalid-reason-code': 'Lý do không hợp lệ',
  'key-statement-invalid': 'Khoá niêm phong chưa qua kiểm tra, không thể niêm phong; hãy báo quản trị viên',
  'keys-unavailable': `Chưa lấy được khoá công khai để đối soát, ${TRY_LATER}`,
  'kms-unavailable': `Dịch vụ ký tạm thời không sẵn sàng, ${TRY_LATER}`,
  'not-sealed': 'Hồ sơ chưa được niêm phong',
  'org-not-configured': 'Chưa cấu hình tên tổ chức để niêm phong, hãy báo quản trị viên',
  'seal-key-expired': 'Khoá niêm phong đã hết hạn, hãy báo quản trị viên',
}

/** `reason` của `guard-failed` (contract-tier2.md mục 4.3). */
const BY_GUARD_REASON: Record<string, string> = {
  same_actor: 'Người tạo hoặc người đã duyệt bước trước không được duyệt bước này',
  role_not_allowed: 'Vai trò của bạn không được phép thực hiện bước này',
  not_assignee: 'Bước này không được giao cho bạn',
  field_missing: 'Hồ sơ còn thiếu trường bắt buộc',
  attachments_not_clean: 'Tệp đính kèm chưa được kiểm dịch xong hoặc không sạch',
  pii_not_reviewed: 'Văn thư hoặc giám đốc chưa xác nhận đã rà dữ liệu cá nhân',
  record_sealed: 'Hồ sơ đã được niêm phong, không thể thay đổi',
}

const GENERIC = 'Đã xảy ra lỗi, hãy thử lại'

/** Lỗi từ cổng (APISIX/nginx, không phải problem+json): client đặt slug `http-<mã>`. */
function byGatewayStatus(status: number): string | null {
  if (status === 401) return 'Phiên đăng nhập đã hết hạn, hãy đăng nhập lại'
  if (status === 403) return BY_SLUG.forbidden
  if (status === 413) return BY_SLUG['payload-too-large']
  if (status === 429) return BY_SLUG['rate-limited']
  if (status >= 500) return BY_SLUG.unavailable
  return null
}

function schemaMessage(e: ApiError): string {
  const errs = e.problem?.errors
  if (!Array.isArray(errs)) return BY_SLUG.schema
  const lines: string[] = []
  for (const x of errs.slice(0, 5)) {
    if (!x || typeof x !== 'object') continue
    const { path, msg } = x as { path?: unknown; msg?: unknown }
    if (typeof msg !== 'string' || !msg) continue
    const field = typeof path === 'string' ? path.replace(/^\//, '') : ''
    lines.push(field ? `${field}: ${msg}` : msg)
  }
  return lines.length ? `${BY_SLUG.schema}: ${lines.join('; ')}` : BY_SLUG.schema
}

/** Câu tiếng Việt cho mọi lỗi; không bao giờ trả chuỗi rỗng. Slug lạ thì dùng `title` của máy chủ. */
export function messageFor(e: unknown): string {
  if (!(e instanceof ApiError)) return GENERIC
  if (e.slug === 'guard-failed') {
    const reason = e.problem?.reason
    return (typeof reason === 'string' ? BY_GUARD_REASON[reason] : undefined) ?? BY_SLUG['guard-failed']
  }
  if (e.slug === 'schema') return schemaMessage(e)
  if (Object.hasOwn(BY_SLUG, e.slug)) return BY_SLUG[e.slug as (typeof CORE_SLUGS)[number]]
  const gateway = /^http-(\d{3})$/.exec(e.slug)
  const g = gateway ? byGatewayStatus(Number(gateway[1])) : null
  if (g) return g
  return e.title.trim() || `Lỗi máy chủ (${e.status})`
}
