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
