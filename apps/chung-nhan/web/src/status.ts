// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Nhãn trạng thái và ngày hiển thị. Chỉ để HIỂN THỊ: quyết định thật luôn do lõi.
import type { DxRecord } from 'dxos-sdk-js'

/** Trạng thái người dùng thấy của một chứng nhận, suy từ seal_state (ưu tiên) rồi wf_state. */
export function statusLabel(r: DxRecord): string {
  if (r.seal_state === 'SEALED') return 'Đã cấp'
  if (r.seal_state === 'REVOKED') return 'Đã thu hồi'
  if (r.seal_state === 'SEAL_PENDING') return 'Chờ niêm phong'
  switch (r.wf_state) {
    case 'running': return 'Chờ duyệt'
    case 'ended:rejected': return 'Bị từ chối'
    case 'ended:guard_failed': return 'Dừng do vi phạm điều kiện duyệt'
    default: return 'Chưa gửi duyệt'
  }
}

/** Giá trị trường để hiện: trống thì "—". */
export function show(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  return String(v)
}

/** Ngày lịch `YYYY-MM-DD` -> `DD/MM/YYYY` (ngày lịch không có múi giờ nên không đổi gì ngoài thứ tự); dạng khác giữ nguyên. */
export function dateVn(v: unknown): string {
  const s = show(v)
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s
}
