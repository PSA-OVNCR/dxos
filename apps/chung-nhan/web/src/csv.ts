// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Đọc tệp CSV lưu từ Excel (Review Focus 1): bảng mã (UTF-8 có/không BOM, Windows-1258, UTF-16), dấu phân cách
// (`,` `;` TAB), RFC 4180, ngày DD/MM/YYYY, họ tên NFD. Đọc đúng, hoặc báo lỗi rõ theo số dòng; không bao giờ để chữ vỡ
// (U+FFFD, ký tự điều khiển) đi lên máy chủ. Chỉ chuẩn bị dữ liệu: mọi quy tắc quyết định vẫn do lõi kiểm lại.
import type { CollectionView, FieldView } from 'dxos-sdk-js'

export type CsvEncoding = 'utf-8' | 'utf-16le' | 'utf-16be' | 'windows-1258'

/** Lỗi cú pháp CSV kèm số dòng (tính từ 1) nơi lỗi bắt đầu. */
export class CsvError extends Error {
  readonly line: number

  constructor(line: number, message: string) {
    super(message)
    this.name = 'CsvError'
    this.line = line
  }
}

/**
 * Nhận diện bảng mã và đọc thành chuỗi NFC. BOM quyết định trước (EF BB BF, FF FE, FE FF); không BOM thì UTF-8 nếu
 * đọc được nghiêm ngặt, ngược lại Windows-1258 (Excel tiếng Việt cũ). Windows-1258 viết "ễ" bằng "ê" + dấu ngã kết hợp,
 * nên chuẩn hóa NFC sau khi đọc.
 */
export function decodeCsv(bytes: Uint8Array): { text: string; encoding: CsvEncoding } {
  const done = (text: string, encoding: CsvEncoding) => ({ text: text.normalize('NFC'), encoding })
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return done(new TextDecoder('utf-8').decode(bytes.subarray(3)), 'utf-8')
  }
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return done(new TextDecoder('utf-16le').decode(bytes.subarray(2)), 'utf-16le')
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return done(new TextDecoder('utf-16be').decode(bytes.subarray(2)), 'utf-16be')
  try {
    return done(new TextDecoder('utf-8', { fatal: true }).decode(bytes), 'utf-8')
  } catch {
    return done(new TextDecoder('windows-1258').decode(bytes), 'windows-1258')
  }
}

const DELIMITERS = [',', ';', '\t'] as const

/** Dấu phân cách theo dòng tiêu đề (dòng đầu không trống): dấu nào xuất hiện nhiều nhất ngoài dấu nháy kép; hòa hay không có thì ','. */
function detectDelimiter(text: string): string {
  const counts = new Map<string, number>(DELIMITERS.map((d) => [d, 0]))
  let quoted = false
  let seen = false
  for (const c of text) {
    if (c === '"') quoted = !quoted
    else if (!quoted && (c === '\n' || c === '\r')) {
      if (seen) break
    } else if (!quoted) {
      if (c !== ' ' && c !== '\t') seen = true
      if (counts.has(c)) counts.set(c, (counts.get(c) ?? 0) + 1)
    } else seen = true
  }
  let best = ','
  for (const d of DELIMITERS) if ((counts.get(d) ?? 0) > (counts.get(best) ?? 0)) best = d
  return best
}

export interface ParsedCsv {
  rows: string[][]
  /** Dòng thật trong tệp (từ 1) nơi mỗi hàng bắt đầu; khác chỉ số hàng khi có ô nhiều dòng. */
  lines: number[]
}

/**
 * RFC 4180 (ô trong dấu nháy kép, `""`, xuống dòng trong ô, CRLF/LF/CR). Dòng trống ở giữa được giữ (thành `['']`) để số
 * dòng không lệch; dòng trống ở cuối tệp bị bỏ. Ném `CsvError` nếu có dấu nháy kép mở mà không đóng.
 */
export function parseCsvWithLines(input: string): ParsedCsv {
  const text = input.startsWith('﻿') ? input.slice(1) : input
  const delim = detectDelimiter(text)
  const rows: string[][] = []
  const lines: number[] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  let quoteLine = 1
  let line = 1
  let rowLine = 1
  let fieldStart = true // đang ở đầu ô: dấu nháy kép ở đây mới mở ô có dấu nháy

  const endField = () => { row.push(field); field = ''; fieldStart = true }
  const endRow = () => { endField(); rows.push(row); lines.push(rowLine); row = [] }

  for (let i = 0; i < text.length; i++) {
    const c = text.charAt(i)
    if (inQuotes) {
      if (c === '"') {
        if (text.charAt(i + 1) === '"') { field += '"'; i++ } else inQuotes = false
      } else {
        if (c === '\r' && text.charAt(i + 1) === '\n') { field += '\r\n'; i++; line++ } else {
          field += c
          if (c === '\n' || c === '\r') line++
        }
      }
    } else if (c === '"' && fieldStart) {
      inQuotes = true
      fieldStart = false
      quoteLine = line
    } else if (c === delim) {
      endField()
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text.charAt(i + 1) === '\n') i++
      endRow()
      line++
      rowLine = line
    } else {
      field += c
      fieldStart = false
    }
  }
  if (inQuotes) throw new CsvError(quoteLine, `Dấu nháy kép mở ở dòng ${quoteLine} không được đóng`)
  if (field !== '' || row.length > 0) endRow()

  while (rows.length > 0 && rows[rows.length - 1]?.every((c) => c === '')) {
    rows.pop()
    lines.pop()
  }
  return { rows, lines }
}

export function parseCsv(text: string): string[][] {
  return parseCsvWithLines(text).rows
}

export interface MappedRows {
  ok: Record<string, unknown>[]
  errors: { line: number; message: string }[]
  /** Dòng thật trong tệp của từng hàng trong `ok` (cùng thứ tự). */
  lines: number[]
}

// Dấu hiệu đọc sai bảng mã: ký tự thay thế U+FFFD, ký tự điều khiển C0 (trừ TAB, LF, CR; gồm NUL của UTF-16 không BOM,
// mà PostgreSQL jsonb không biểu diễn được), DEL và C1 (review cuối Plan 03, I3).
const BROKEN = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F�]/
const DMY = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/

const key = (s: string): string => s.normalize('NFC').trim().toLowerCase()

function validDate(y: number, m: number, d: number): boolean {
  if (y < 1 || m < 1 || m > 12 || d < 1) return false
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] ?? 0
  return d <= days
}

/** `DD/MM/YYYY` (cũng `-`, `.`, ngày hoặc tháng một chữ số) hoặc `YYYY-MM-DD` -> `YYYY-MM-DD`; không hợp lệ thì null. */
function toIsoDate(raw: string): string | null {
  const dmy = DMY.exec(raw)
  const iso = dmy ? null : ISO.exec(raw)
  const parts = dmy ? [dmy[3], dmy[2], dmy[1]] : iso ? [iso[1], iso[2], iso[3]] : null
  if (!parts) return null
  const [y, m, d] = parts.map(Number) as [number, number, number]
  if (!validDate(y, m, d)) return null
  return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

const labelOf = (name: string, f: FieldView): string => f.label ?? name

/**
 * Dòng đầu tiên không trống là tiêu đề (nhãn trường hoặc tên trường, không phân biệt hoa thường, bỏ khoảng trắng hai đầu).
 * Tiêu đề sai (cột lạ, cột trùng, cột số thứ tự, thiếu cột bắt buộc) thì không nhập gì. Dòng dữ liệu lỗi bị loại và báo
 * kèm số dòng thật trong tệp (từ 1, gồm dòng tiêu đề); `lines` (từ `parseCsvWithLines`) cho số dòng đúng khi có ô nhiều dòng.
 * Chỉ ngày được đổi kiểu ở đây; các kiểu khác đi nguyên dạng chuỗi và lõi kiểm tra lại.
 */
export function mapRows(rows: string[][], view: CollectionView, lines?: number[]): MappedRows {
  const lineOf = (i: number): number => lines?.[i] ?? i + 1
  const blank = (r: string[]): boolean => r.every((c) => c.trim() === '')
  const h = rows.findIndex((r) => !blank(r))
  if (h < 0) return { ok: [], errors: [{ line: 1, message: 'Tệp trống, không có dòng tiêu đề' }], lines: [] }

  const names = new Map<string, string>() // khóa tiêu đề -> tên trường nhập được
  const sequences = new Set<string>()
  for (const [name, f] of Object.entries(view.fields)) {
    const target = f.type === 'sequence' ? sequences : null
    for (const k of [key(labelOf(name, f)), key(name)]) {
      if (target) target.add(k)
      else names.set(k, name)
    }
  }

  const headerLine = lineOf(h)
  if ((rows[h] ?? []).some((cell) => BROKEN.test(cell))) {
    const message = 'Dòng tiêu đề có ký tự không đọc được (tệp có thể lưu sai bảng mã, ví dụ UTF-16 không BOM; hãy lưu lại bằng "CSV UTF-8")'
    return { ok: [], errors: [{ line: headerLine, message }], lines: [] }
  }
  const errors: MappedRows['errors'] = []
  const columns: (string | null)[] = [] // tên trường theo vị trí cột; null = cột không dùng
  const seen = new Set<string>()
  for (const [i, cell] of (rows[h] ?? []).entries()) {
    const title = cell.normalize('NFC').trim()
    const k = key(title)
    const field = names.get(k)
    if (title === '') columns.push(null)
    else if (sequences.has(k)) {
      errors.push({ line: headerLine, message: `Cột "${title}" do hệ thống tự cấp, không nhập từ tệp` })
      columns.push(null)
    } else if (!field) {
      const valid = Object.entries(view.fields).filter(([, f]) => f.type !== 'sequence').map(([n, f]) => labelOf(n, f)).join(', ')
      errors.push({ line: headerLine, message: `Cột "${title}" không có trong mẫu (các cột hợp lệ: ${valid})` })
      columns.push(null)
    } else if (seen.has(field)) {
      errors.push({ line: headerLine, message: `Cột "${title}" bị trùng (cột ${i + 1})` })
      columns.push(null)
    } else {
      seen.add(field)
      columns.push(field)
    }
  }
  const missing = Object.entries(view.fields)
    .filter(([name, f]) => f.required && f.type !== 'sequence' && !seen.has(name))
    .map(([name, f]) => labelOf(name, f))
  if (missing.length > 0) errors.push({ line: headerLine, message: `Thiếu cột bắt buộc: ${missing.join(', ')}` })
  if (errors.length > 0) return { ok: [], errors, lines: [] }

  const ok: Record<string, unknown>[] = []
  const okLines: number[] = []
  for (let i = h + 1; i < rows.length; i++) {
    const cells = rows[i] ?? []
    if (blank(cells)) continue
    const problems: string[] = []
    const data: Record<string, unknown> = {}
    cells.forEach((cell, c) => {
      if (!columns[c] && cell.trim() !== '') problems.push(`Có ô ở cột ${c + 1} không có tiêu đề`)
    })
    columns.forEach((name, c) => {
      if (!name) return
      const f = view.fields[name]
      if (!f) return
      const raw = (cells[c] ?? '').normalize('NFC').trim()
      if (BROKEN.test(raw)) {
        problems.push(`${labelOf(name, f)}: có ký tự không đọc được (tệp có thể lưu sai bảng mã)`)
      } else if (raw === '') {
        if (f.required) problems.push(`Thiếu ${labelOf(name, f)} (bắt buộc)`)
      } else if (f.type === 'date') {
        const iso = toIsoDate(raw)
        if (iso) data[name] = iso
        else problems.push(`${labelOf(name, f)} "${raw}" không đúng định dạng DD/MM/YYYY`)
      } else {
        data[name] = raw
      }
    })
    if (problems.length > 0) errors.push({ line: lineOf(i), message: problems.join('; ') })
    else {
      ok.push(data)
      okLines.push(lineOf(i))
    }
  }
  return { ok, errors, lines: okLines }
}
