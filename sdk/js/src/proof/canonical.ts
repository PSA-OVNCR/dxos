// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// JSON chuẩn hóa giống từng byte `dxos_proof.canonical.canonical_bytes` (Python) và bộ đọc JSON không mất số.
//
// canonical: UTF-8, không khoảng trắng, khóa sắp theo CODE POINT (thứ tự chuỗi của Python, khác thứ tự
// UTF-16 khi có ký tự ngoài BMP), NFC trên mọi chuỗi và mọi khóa, hai khóa trùng sau NFC → lỗi, chỉ số
// nguyên (số thực → lỗi), thoát chuỗi như `json.dumps(ensure_ascii=False)` (= JSON.stringify với chuỗi
// hợp lệ). Surrogate lẻ → lỗi (Python lỗi khi mã hóa UTF-8).
//
// parse: số nguyên trong ±(2^53−1) → number, ngoài khoảng → bigint (không bao giờ làm tròn).

export type Json = null | boolean | number | bigint | string | Json[] | { [k: string]: Json }

/** Số thực đọc ở chế độ "như json.loads của Python" (chỉ dùng nội bộ bộ kiểm gói): giữ chỗ để
 *  `canonicalBytes` từ chối đúng lúc Python từ chối, thay vì từ chối ngay khi đọc. */
export class JsonFloat {
  constructor(readonly text: string) {}
}

export interface ParseOptions {
  /** 'reject': số thực → lỗi; 'keep': trả JsonFloat (Python json.loads nhận cả NaN/Infinity). */
  floats: 'reject' | 'keep'
  /** 'reject' như CLI dxos-witness (`_no_duplicate_keys`); 'last' như `json.loads` mặc định. */
  duplicates: 'reject' | 'last'
}

/** Đọc JSON không mất số: số nguyên ngoài ±(2^53−1) → bigint; số thực, khóa trùng → lỗi. */
export function parseJsonLossless(text: string): Json {
  return parseJson(text, { floats: 'reject', duplicates: 'reject' }) as Json
}

const LONE_SURROGATE = /[\uD800-\uDFFF]/u
const NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y
const SAFE_MAX = BigInt(Number.MAX_SAFE_INTEGER)
/** Giới hạn mặc định của Python 3.11+ (`sys.get_int_max_str_digits()`): `json.loads` từ chối số nguyên dài hơn thế. */
const MAX_INT_DIGITS = 4300
const ESCAPES: Record<string, string> = { '"': '"', '\\': '\\', '/': '/', b: '\b', f: '\f', n: '\n', r: '\r', t: '\t' }

/** Bộ đọc JSON theo ngữ pháp `json.loads` của Python (chặt: không ký tự điều khiển thô trong chuỗi). */
export function parseJson(text: string, o: ParseOptions): unknown {
  let i = 0
  const fail = (what: string): never => { throw new SyntaxError(`JSON không hợp lệ tại vị trí ${i}: ${what}`) }
  const ws = () => {
    for (;;) {
      const c = text.charCodeAt(i)
      if (c === 0x20 || c === 0x09 || c === 0x0a || c === 0x0d) i++
      else return
    }
  }
  const float = (t: string): JsonFloat => (o.floats === 'keep' ? new JsonFloat(t) : fail(`số thực ${t}`))
  const literal = (word: string, v: unknown): unknown => {
    if (!text.startsWith(word, i)) fail('ký tự lạ')
    i += word.length
    return v
  }
  const str = (): string => {
    i++ // "
    let out = ''
    let start = i
    for (;;) {
      if (i >= text.length) fail('chuỗi chưa đóng')
      const c = text.charCodeAt(i)
      if (c === 0x22) { out += text.slice(start, i); i++; return out }
      if (c < 0x20) fail('ký tự điều khiển trong chuỗi')
      if (c >= 0xd800 && c <= 0xdbff) {
        const d = text.charCodeAt(i + 1)
        if (!(d >= 0xdc00 && d <= 0xdfff)) fail('surrogate lẻ')
        i += 2
        continue
      }
      if (c >= 0xdc00 && c <= 0xdfff) fail('surrogate lẻ')
      if (c !== 0x5c) { i++; continue }
      out += text.slice(start, i)
      const e = text[i + 1]
      if (e !== undefined && Object.hasOwn(ESCAPES, e)) { out += ESCAPES[e]; i += 2 } else if (e === 'u') {
        const h = text.slice(i + 2, i + 6)
        if (!/^[0-9a-fA-F]{4}$/.test(h)) fail('\\u sai')
        out += String.fromCharCode(parseInt(h, 16)) // cặp surrogate thoát liền nhau tự ghép như Python
        i += 6
      } else fail('chuỗi thoát sai')
      start = i
    }
  }
  const value = (): unknown => {
    ws()
    const c = text[i]
    if (c === '{') {
      i++
      const obj: Record<string, unknown> = {}
      ws()
      if (text[i] === '}') { i++; return obj }
      for (;;) {
        ws()
        if (text[i] !== '"') fail('cần khóa chuỗi')
        const k = str()
        ws()
        if (text[i] !== ':') fail("cần ':'")
        i++
        const v = value()
        if (Object.hasOwn(obj, k) && o.duplicates === 'reject') fail(`khóa trùng ${JSON.stringify(k)}`)
        // defineProperty: "__proto__" là khóa thường, không đổi prototype.
        Object.defineProperty(obj, k, { value: v, enumerable: true, writable: true, configurable: true })
        ws()
        if (text[i] === ',') { i++; continue }
        if (text[i] === '}') { i++; return obj }
        fail("cần ',' hoặc '}'")
      }
    }
    if (c === '[') {
      i++
      const arr: unknown[] = []
      ws()
      if (text[i] === ']') { i++; return arr }
      for (;;) {
        arr.push(value())
        ws()
        if (text[i] === ',') { i++; continue }
        if (text[i] === ']') { i++; return arr }
        fail("cần ',' hoặc ']'")
      }
    }
    if (c === '"') return str()
    if (c === 't') return literal('true', true)
    if (c === 'f') return literal('false', false)
    if (c === 'n') return literal('null', null)
    if (c === 'N') { literal('NaN', 0); return float('NaN') }
    if (c === 'I') { literal('Infinity', 0); return float('Infinity') }
    if (c === '-' && text.startsWith('-Infinity', i)) { i += 9; return float('-Infinity') }
    NUMBER.lastIndex = i
    const m = NUMBER.exec(text)
    if (!m) return fail('cần giá trị')
    i += m[0].length
    if (m[1] !== undefined || m[2] !== undefined) return float(m[0])
    // Như Python: dấu trừ không tính vào số chữ số; quá giới hạn thì cả gói không đọc được (CLI báo MALFORMED).
    if (m[0].length - (m[0].startsWith('-') ? 1 : 0) > MAX_INT_DIGITS) fail(`số nguyên dài hơn ${MAX_INT_DIGITS} chữ số`)
    const n = BigInt(m[0])
    if (n > SAFE_MAX || n < -SAFE_MAX) return n
    return Number(n) // BigInt("-0") === 0n nên không có -0
  }
  const v = value()
  ws()
  if (i !== text.length) fail('dữ liệu thừa sau giá trị JSON')
  return v
}

// ---------------------------------------------------------------- canonical
function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (v === null || typeof v !== 'object' || Array.isArray(v)) return false
  const p = Object.getPrototypeOf(v)
  return p === Object.prototype || p === null
}

/** So theo code point (thứ tự `str` của Python). */
function cmpCodePoint(a: string, b: string): number {
  const n = Math.min(a.length, b.length)
  for (let i = 0; i < n; i++) {
    const x = a.charCodeAt(i)
    const y = b.charCodeAt(i)
    if (x !== y) {
      // Khác nhau lần đầu: surrogate (ký tự ngoài BMP) phải đứng SAU U+E000–U+FFFF.
      const rank = (u: number) => (u >= 0xd800 && u <= 0xdfff ? u + 0x2000 : u >= 0xe000 ? u - 0x800 : u)
      return rank(x) - rank(y)
    }
  }
  return a.length - b.length
}

function quote(s: string): string {
  const n = s.normalize('NFC')
  if (LONE_SURROGATE.test(n)) throw new TypeError('chuỗi có surrogate lẻ, không mã hóa UTF-8 được')
  return JSON.stringify(n)
}

/** Khóa sau NFC của một object; hai khóa trùng sau NFC → lỗi. */
export function nfcEntries(v: Record<string, unknown>): Map<string, unknown> {
  const out = new Map<string, unknown>()
  for (const k of Object.keys(v)) {
    const n = k.normalize('NFC')
    if (out.has(n)) throw new TypeError(`hai khóa trùng nhau sau chuẩn hóa NFC: ${JSON.stringify(n)}`)
    out.set(n, v[k])
  }
  return out
}

function encode(v: unknown, out: string[]): void {
  if (v === null) out.push('null')
  else if (v === true) out.push('true')
  else if (v === false) out.push('false')
  else if (typeof v === 'number') {
    if (!Number.isSafeInteger(v)) throw new TypeError(`chỉ nhận số nguyên an toàn, nhận ${v}`)
    out.push(String(v))
  } else if (typeof v === 'bigint') out.push(v.toString())
  else if (typeof v === 'string') out.push(quote(v))
  else if (Array.isArray(v)) {
    out.push('[')
    v.forEach((x, i) => { if (i) out.push(','); encode(x, out) })
    out.push(']')
  } else if (isPlainObject(v)) {
    const m = nfcEntries(v)
    out.push('{')
    ;[...m.keys()].sort(cmpCodePoint).forEach((k, i) => {
      if (i) out.push(',')
      out.push(quote(k), ':')
      encode(m.get(k), out)
    })
    out.push('}')
  } else if (v instanceof JsonFloat) throw new TypeError(`kiểu không được phép: số thực ${v.text}`)
  else throw new TypeError(`kiểu không được phép: ${typeof v}`)
}

/** Biểu diễn JSON chuẩn hóa dạng UTF-8 (khớp từng byte với canonical_bytes của dxos-proof). */
export function canonicalBytes(v: Json): Uint8Array {
  const out: string[] = []
  encode(v, out)
  return new TextEncoder().encode(out.join(''))
}
