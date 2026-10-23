// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Lưu một Blob thành tệp trên máy người dùng và đặt tên tệp PDF đã ban hành.
import type { ObjectVariant } from 'dxos-sdk-js'

/**
 * Tên tệp `<so_hieu>.pdf`, thay `/` bằng `-` (nhiều tệp thì thêm `-<số thứ tự>`); thiếu số hiệu thì dùng mã bản ghi.
 * Bản che thêm `-che` để không lẫn với bản gốc.
 */
export function pdfFileName(soHieu: unknown, fallbackId: string, index?: number, variant: ObjectVariant = 'original'): string {
  const base = typeof soHieu === 'string' && soHieu.trim() !== '' ? soHieu.trim().replaceAll('/', '-') : fallbackId
  return `${base}${variant === 'redacted' ? '-che' : ''}${index === undefined ? '' : `-${index}`}.pdf`
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  try {
    a.click()
  } finally {
    a.remove()
    URL.revokeObjectURL(url)
  }
}
