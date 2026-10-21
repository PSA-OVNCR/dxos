// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Nhãn trạng thái và định dạng giờ Việt Nam. Chỉ để HIỂN THỊ: quyết định thật luôn do lõi.
import { formatVnDate, type DxRecord } from 'dxos-sdk-js'

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

/** Năm theo giờ Việt Nam; không đọc được thì null. */
export function yearVn(iso: string | null): number | null {
  const s = formatVnDate(iso)
  return s ? Number(s.slice(-4)) : null
}

export { formatVn, formatVnDate, hasRole, sealLabel } from 'dxos-sdk-js'
