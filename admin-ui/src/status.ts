// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Chuyển giá trị trạng thái của API quản trị thành CHỮ tiếng Việt kèm mức (màu chỉ là phần thêm: trạng thái luôn có chữ).

export type Level = 'ok' | 'warn' | 'bad'

export interface StateText {
  level: Level
  text: string
}

/** Dấu đi trước chữ, để mức vẫn đọc được khi không phân biệt màu (ẩn khỏi trình đọc màn hình: chữ đã đủ nghĩa). */
export const MARK: Record<Level, string> = { ok: '✔', warn: '!', bad: '✖' }

/** "ok" hoặc "down: <lý do>" (health). `okText` là chữ cho trạng thái tốt của từng thành phần. */
export function probeState(value: string, okText = 'Hoạt động tốt'): StateText {
  if (value === 'ok') return { level: 'ok', text: okText }
  if (value.startsWith('down:')) return { level: 'bad', text: `Lỗi: ${value.slice(5).trim() || 'không rõ lý do'}` }
  return { level: 'warn', text: `Không rõ (${value})` }
}

/** `seal_key` của health (xem seal_key_status trong core/admin/ops.py). */
export function sealKeyState(value: string): StateText {
  switch (value) {
    case 'ok': return { level: 'ok', text: 'Còn hạn' }
    case 'none': return { level: 'warn', text: 'Chưa có (sẽ tạo ở lần niêm phong đầu tiên)' }
    case 'expired': return { level: 'bad', text: 'Đã hết hạn, chưa niêm phong được' }
    case 'invalid': return { level: 'bad', text: 'Không hợp lệ, việc niêm phong đang bị chặn' }
    case 'unknown': return { level: 'warn', text: 'Chưa rõ (không hỏi được dịch vụ ký)' }
    default: return probeState(value)
  }
}

/** "3 giờ", "12 phút"... cho khoảng thời gian tính bằng giây. */
export function ageText(seconds: number): string {
  if (seconds < 60) return 'dưới 1 phút'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ`
  return `${Math.floor(seconds / 86400)} ngày`
}

/** Mã băm / commit rút gọn để đọc; giá trị đầy đủ để trong thuộc tính title. */
export function short(hex: string, n = 12): string {
  return hex.length > n ? hex.slice(0, n) : hex
}

/** Loại sự kiện ledger (core/src/dxos_core/ledger/events.py: EVENT_TYPES) dùng cho bộ lọc. */
export const EVENT_TYPES = [
  'app.submitted', 'app.installed', 'app.disabled', 'record.created', 'record.updated', 'upload.staged',
  'object.clean', 'object.infected', 'object.rejected', 'object.read', 'field.revealed', 'pii.detected',
  'pii.reviewed', 'task.completed', 'record.sealed', 'record.revoked', 'policy.denied', 'sth.published',
  'workflow.started', 'workflow.completed', 'pii.erased', 'key.published',
] as const

/** Trạng thái một phiên bản app (core.apps.status). Bản đã vô hiệu hóa không phải lỗi: mức "warn". */
export function appStatusState(status: string): StateText {
  switch (status) {
    case 'ACTIVE': return { level: 'ok', text: 'Đang hoạt động' }
    case 'PENDING': return { level: 'warn', text: 'Chờ duyệt' }
    case 'DISABLED': return { level: 'warn', text: 'Đã vô hiệu hóa' }
    default: return { level: 'warn', text: `Không rõ (${status})` }
  }
}

/** Trạng thái upload bị cách ly (core.uploads.status: INFECTED | REJECTED). */
export function uploadStatusState(status: string): StateText {
  switch (status) {
    case 'INFECTED': return { level: 'bad', text: 'Nhiễm mã độc' }
    case 'REJECTED': return { level: 'bad', text: 'Bị từ chối' }
    default: return { level: 'warn', text: `Không rõ (${status})` }
  }
}
