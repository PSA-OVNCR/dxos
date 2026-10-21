// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Định dạng giờ Việt Nam và nhãn hiển thị dùng chung. Chỉ để HIỂN THỊ: quyết định thật luôn do lõi.

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
