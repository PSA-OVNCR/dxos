// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Kiểm đường dẫn đối soát trước khi vẽ mã QR hoặc đặt vào thẻ <a>: chỉ trang đối soát của chính origin này.

const FRAGMENT = /^#[A-Z2-7]{26}$/
export const VERIFY_INVALID = 'Liên kết đối soát không hợp lệ'

/** Trả URL đã chuẩn hoá nếu hợp lệ, ngược lại null. */
export function checkedVerifyUrl(verifyUrl: string): string | null {
  let u: URL
  try {
    u = new URL(verifyUrl)
  } catch {
    return null
  }
  if (u.origin !== location.origin || u.origin === 'null') return null
  if (u.username || u.password || u.search) return null
  if (u.pathname !== '/apps/verify/') return null
  if (!FRAGMENT.test(u.hash)) return null
  return u.href
}
