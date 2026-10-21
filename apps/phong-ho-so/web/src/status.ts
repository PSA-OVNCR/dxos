// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Nhãn trạng thái và định dạng giờ Việt Nam. Chỉ để HIỂN THỊ: quyết định thật luôn do lõi.
import type { DxRecord } from 'dxos-sdk-js'

/** Trạng thái người dùng thấy của một văn bản, suy từ seal_state (ưu tiên) rồi wf_state. */
export function statusLabel(r: DxRecord): string {
  if (r.seal_state === 'SEALED') return 'Đã ban hành'
  if (r.seal_state === 'REVOKED') return 'Đã thu hồi'
  if (r.seal_state === 'SEAL_PENDING') return 'Chờ niêm phong'
  switch (r.wf_state) {
    case 'running': return 'Đang duyệt'
    case 'ended:rejected': return 'Bị trả lại'
    case 'ended:guard_failed': return 'Dừng do vi phạm điều kiện duyệt'
    default: return 'Nháp'
  }
}

const VN_TIME = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  hourCycle: 'h23',
})

/** Thời điểm ISO-8601 -> giờ Việt Nam (UTC+7); chuỗi không đọc được thì giữ nguyên. */
export function formatVn(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : VN_TIME.format(d)
}

const VN_DATE = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric' })

/** Ngày theo giờ Việt Nam (dd/mm/yyyy); không đọc được thì null. */
export function formatVnDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : VN_DATE.format(d)
}

/** Năm theo giờ Việt Nam; không đọc được thì null. */
export function yearVn(iso: string | null): number | null {
  const s = formatVnDate(iso)
  return s ? Number(s.slice(-4)) : null
}

/** Nhãn trạng thái niêm phong (SealInfo.seal_state). */
export function sealLabel(state: string): string {
  switch (state) {
    case 'SEALED': return 'Đã niêm phong'
    case 'REVOKED': return 'Đã thu hồi'
    case 'SEAL_PENDING': return 'Chờ niêm phong'
    default: return state
  }
}

/** Người dùng có ít nhất một vai trò trong danh sách (chỉ để ẩn/hiện nút, lõi mới quyết định). */
export function hasRole(mine: readonly string[], allowed: readonly string[] | undefined): boolean {
  return !!allowed && allowed.some((r) => mine.includes(r))
}
