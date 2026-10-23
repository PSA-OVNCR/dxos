// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// SHA-256 (WebCrypto), hex, base64 cho bộ kiểm gói bằng chứng. Giải mã base64 CHUẨN TẮC (RFC 4648 mục 4), cùng quy tắc
// với `dxos_witness.b64.b64decode_canonical` (ruling R29), để hai bên nhận/từ chối cùng chuỗi mà không phụ thuộc bản vá CPython.

/** Bản sao trên ArrayBuffer thường (WebCrypto không nhận SharedArrayBuffer). */
export function own(u8: Uint8Array): Uint8Array<ArrayBuffer> {
  return new Uint8Array(u8)
}

export async function sha256With(subtle: SubtleCrypto, data: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await subtle.digest('SHA-256', own(data)))
}

/** SHA-256 dạng hex thường của tệp (Blob/File) hoặc dãy byte; tính ngay trên máy người dùng. */
export async function sha256Hex(data: Blob | Uint8Array): Promise<string> {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(await data.arrayBuffer())
  return toHex(await sha256With(globalThis.crypto.subtle, bytes))
}

export function toHex(u8: Uint8Array): string {
  let s = ''
  for (const b of u8) s += b.toString(16).padStart(2, '0')
  return s
}

/** 64 ký tự hex thường → 32 byte; chuỗi khác → null (như `_HEX64.fullmatch` của witness). */
export function hex32(v: unknown): Uint8Array | null {
  if (typeof v !== 'string' || !/^[0-9a-f]{64}$/.test(v)) return null
  const out = new Uint8Array(32)
  for (let i = 0; i < 32; i++) out[i] = parseInt(v.slice(2 * i, 2 * i + 2), 16)
  return out
}

export function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0))
  let at = 0
  for (const p of parts) { out.set(p, at); at += p.length }
  return out
}

export function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

export function b64encode(u8: Uint8Array): string {
  let s = ''
  for (const b of u8) s += String.fromCharCode(b)
  return btoa(s)
}

/**
 * Giải mã base64 CHUẨN TẮC (RFC 4648 mục 4), cùng quy tắc với `dxos_witness.b64.b64decode_canonical` (ruling R29):
 * bảng chữ chuẩn, độ dài chia hết cho 4, `=` chỉ là phần đệm cuối (0 đến 2 dấu, đúng số byte còn thiếu), không khoảng
 * trắng. Kiểm tường minh trước khi giải mã nên không phụ thuộc phiên bản CPython (bản vá CVE-2026-3446 đổi cách
 * `b64decode(validate=True)` xử lý thừa `=`). Bit thừa cuối không bị bắt buộc bằng 0. Sai → null. Vector dùng chung:
 * sdk/js/test/vectors/b64/validate.json.
 */
export function b64decodePy(s: string): Uint8Array | null {
  const m = /^([A-Za-z0-9+/]*)(={0,2})$/.exec(s)
  if (!m) return null
  const data = m[1]!
  const pads = m[2]!.length
  const r = data.length % 4
  if (r === 1 || (r === 0 && pads !== 0) || (r === 2 && pads !== 2) || (r === 3 && pads !== 1)) return null
  const out = new Uint8Array(Math.floor((data.length * 6) / 8))
  let acc = 0
  let bits = 0
  let at = 0
  for (const ch of data) {
    acc = ((acc << 6) | ALPHABET.indexOf(ch)) & 0xffff
    bits += 6
    if (bits >= 8) {
      bits -= 8
      out[at++] = (acc >> bits) & 0xff
    }
  }
  return out
}
