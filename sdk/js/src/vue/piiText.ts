// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Câu tiếng Việt cho trạng thái dò dữ liệu cá nhân của một tệp (contract-tier2.md 3.4). Chỉ là chữ hiển thị:
// máy chủ quyết định ai mở được bản gốc và khi nào bước duyệt được qua.
import type { AttachmentPii } from '../types'

/** Nhãn ngắn của loại dữ liệu cá nhân mà bộ dò của lõi nhận ra; loại lạ thì hiện nguyên mã. */
const TYPE_LABEL: Record<string, string> = { CCCD: 'CCCD', PHONE: 'SĐT', BANK_ACCOUNT: 'STK' }
const TYPE_ORDER = Object.keys(TYPE_LABEL)

/** "CCCD 1, SĐT 1, STK 1": thứ tự cố định, loại lạ xếp sau theo mã; rỗng khi không có số đếm. */
export function countsText(counts: Record<string, number> | undefined): string {
  const entries = Object.entries(counts ?? {}).filter(([, n]) => n > 0)
  const rank = (t: string): number => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? TYPE_ORDER.length : i }
  entries.sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
  return entries.map(([t, n]) => `${TYPE_LABEL[t] ?? t} ${n}`).join(', ')
}

/**
 * Bản gốc của tệp có đang bị khóa sau `reveal_pii` không (contract-tier2.md 3.4, P4-D4): chỉ tệp đã dò xong và không
 * có phát hiện nào mới mở cho mọi người có quyền đọc; chưa dò xong, hỏng, quá lớn hay có phát hiện đều khóa. `null` (collection
 * không dò PII) thì không khóa. Chỉ để ẩn nút cho tiện, máy chủ mới quyết định.
 */
export function originalLocked(p: AttachmentPii | null | undefined): boolean {
  return !!p && (p.status !== 'DONE' || p.findings > 0)
}

export function piiLabel(p: AttachmentPii): string {
  switch (p.status) {
    case 'PENDING': return 'Đang dò dữ liệu cá nhân…'
    case 'TOO_LARGE': return 'Tệp quá 200 trang nên chưa được dò dữ liệu cá nhân; cần rà thủ công'
    case 'FAILED': return 'Dò dữ liệu cá nhân bị lỗi; cần rà thủ công'
    default: {
      if (p.findings <= 0) return 'Không phát hiện dữ liệu cá nhân'
      const by = countsText(p.counts)
      return `Phát hiện ${p.findings} dữ liệu cá nhân${by ? ` (${by})` : ''}`
    }
  }
}
