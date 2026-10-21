// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Lưu một Blob thành tệp trên máy người dùng và đặt tên tệp PDF đã ban hành.

/** Tên tệp `<so_hieu>.pdf`, thay `/` bằng `-` (nhiều tệp thì thêm `-<số thứ tự>`); thiếu số hiệu thì dùng mã bản ghi. */
export function pdfFileName(soHieu: unknown, fallbackId: string, index?: number): string {
  const base = typeof soHieu === 'string' && soHieu.trim() !== '' ? soHieu.trim().replaceAll('/', '-') : fallbackId
  return `${base}${index === undefined ? '' : `-${index}`}.pdf`
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
