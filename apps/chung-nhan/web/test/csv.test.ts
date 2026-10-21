// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Review Focus 1: CSV lưu từ Excel. Đọc đúng, hoặc báo lỗi rõ theo số dòng; không bao giờ gửi chữ vỡ lên máy chủ.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, test } from 'vitest'
import { CsvError, decodeCsv, mapRows, parseCsv, parseCsvWithLines } from '../src/csv'
import { B_VIEW } from './helpers'

const VIEW = B_VIEW.collections.chung_nhan!

function fixture(name: string): Uint8Array {
  return new Uint8Array(readFileSync(resolve(import.meta.dirname, 'fixtures', name)))
}

/** Ba dòng dữ liệu chung của mọi tệp mẫu (test/fixtures/README.md). */
const EXPECTED = [
  { ho_ten: 'Nguyễn Văn An', su_kien: 'Hội thảo Phần mềm nguồn mở', ngay_cap: '2026-11-10', email: 'an@example.vn' },
  { ho_ten: 'Lê, Thị "Bình"', su_kien: 'Ngày hội Git, GitHub', ngay_cap: '2026-11-10' },
  { ho_ten: 'Phạm Đức Thịnh', su_kien: 'Tập huấn Ứng dụng Chứng nhận số', ngay_cap: '2026-11-12', email: 'thinh@example.vn' },
]

describe('decodeCsv', () => {
  test.each([
    ['utf8-bom.csv', 'utf-8'], ['cp1258.csv', 'windows-1258'], ['utf16le-bom.csv', 'utf-16le'], ['utf8.csv', 'utf-8'],
    ['utf8-nfd.csv', 'utf-8'],
  ])('decodeCsv %s', (f, enc) => {
    const d = decodeCsv(fixture(f))
    expect(d.encoding).toBe(enc)
    expect(d.text).toContain('Nguyễn')
    expect(d.text.startsWith('﻿')).toBe(false)
    expect(d.text).not.toContain('�')
    expect(d.text).toBe(d.text.normalize('NFC'))
  })

  test('UTF-16BE with BOM', () => {
    const units = [...'﻿Họ và tên;Sự kiện'].map((c) => c.charCodeAt(0))
    const bytes = new Uint8Array(units.flatMap((u) => [u >> 8, u & 0xff]))
    expect(decodeCsv(bytes)).toEqual({ text: 'Họ và tên;Sự kiện', encoding: 'utf-16be' })
  })

  test('bytes that are not valid UTF-8 and have no BOM are read as Windows-1258', () => {
    // "Hà Nội" trong cp1258: H, a + U+0300 (0xCC), ' ', N, ô (0xF4) + U+0323 (0xF2) ... không phải UTF-8 hợp lệ
    const bytes = new Uint8Array([0x48, 0xe0, 0x20, 0x4e, 0xf4, 0xf2, 0x69])
    const d = decodeCsv(bytes)
    expect(d.encoding).toBe('windows-1258')
    expect(d.text).toBe('Hà Nội')
  })

  test('plain ASCII is UTF-8', () => {
    expect(decodeCsv(new TextEncoder().encode('a,b\r\n1,2'))).toEqual({ text: 'a,b\r\n1,2', encoding: 'utf-8' })
  })

  test('empty input is empty UTF-8 text', () => {
    expect(decodeCsv(new Uint8Array())).toEqual({ text: '', encoding: 'utf-8' })
  })
})

describe('parseCsv', () => {
  test('semicolon separator, quotes, commas inside cells, trailing blank lines', () => {
    expect(parseCsv('Họ và tên;Sự kiện\r\n"Lê, Văn ""A""";Hội thảo\r\n\r\n')).toEqual([['Họ và tên', 'Sự kiện'], ['Lê, Văn "A"', 'Hội thảo']])
  })

  test.each([
    ['comma', 'a,b,c\n1,2,3'], ['semicolon', 'a;b;c\n1;2;3'], ['tab', 'a\tb\tc\n1\t2\t3'],
  ])('the separator is detected from the header line: %s', (_n, text) => {
    expect(parseCsv(text)).toEqual([['a', 'b', 'c'], ['1', '2', '3']])
  })

  test('a separator inside a quoted header cell does not decide the separator', () => {
    expect(parseCsv('"a;b;c",d\n1,2')).toEqual([['a;b;c', 'd'], ['1', '2']])
  })

  test('commas inside cells of a semicolon file stay in the cell', () => {
    expect(parseCsv('Tên;Sự kiện\nNguyễn A;Hội thảo, tập huấn')).toEqual([['Tên', 'Sự kiện'], ['Nguyễn A', 'Hội thảo, tập huấn']])
  })

  test('line breaks inside quotes are kept; CRLF, LF and CR all end rows', () => {
    expect(parseCsv('a;b\r"x\ny";z\n1;2\r\n')).toEqual([['a', 'b'], ['x\ny', 'z'], ['1', '2']])
  })

  test('blank lines in the middle are kept (line numbers must stay true), blank lines at the end go', () => {
    expect(parseCsv('a;b\n\n1;2\n;\n\n')).toEqual([['a', 'b'], [''], ['1', '2']])
  })

  test('a stray BOM character at the start is dropped', () => {
    expect(parseCsv('﻿a;b\n1;2')).toEqual([['a', 'b'], ['1', '2']])
  })

  test('an unterminated quote is an error that names the line where it opened', () => {
    expect(() => parseCsv('a;b\n1;"2\n3;4\n')).toThrowError(CsvError)
    try {
      parseCsv('a;b\n1;"2\n3;4\n')
    } catch (e) {
      expect((e as CsvError).line).toBe(2)
      expect((e as CsvError).message).toMatch(/dòng 2/)
    }
  })

  test('parseCsvWithLines gives the real line of every row, also after a multi-line cell', () => {
    const r = parseCsvWithLines('a;b\n\n"x\ny";z\n1;2\n')
    expect(r.rows).toEqual([['a', 'b'], [''], ['x\ny', 'z'], ['1', '2']])
    expect(r.lines).toEqual([1, 2, 3, 5])
  })

  test('empty text has no rows', () => {
    expect(parseCsv('')).toEqual([])
    expect(parseCsv('\r\n\r\n')).toEqual([])
  })
})

describe('mapRows', () => {
  test('labels as headers, NFD → NFC, DD/MM/YYYY → ISO, line numbers in errors', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp', 'Email'], ['Nguyễn A', 'HT', '10/11/2026', 'a@x.vn'],
      ['', 'HT', '10/11/2026', '']], VIEW)
    expect(r.ok).toEqual([{ ho_ten: 'Nguyễn A', su_kien: 'HT', ngay_cap: '2026-11-10', email: 'a@x.vn' }])
    expect(r.errors).toEqual([{ line: 3, message: expect.stringMatching(/Họ và tên/) }])
  })

  test('NFD names (macOS) come out as NFC', () => {
    const nfd = 'Nguyễn'.normalize('NFD')
    expect(nfd).not.toBe('Nguyễn')
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], [nfd, 'HT'.normalize('NFD'), '1/2/2027']], VIEW)
    expect(r.ok[0]?.ho_ten).toBe('Nguyễn')
    expect(r.ok[0]?.ho_ten).toBe('Nguyễn'.normalize('NFC'))
  })

  test('unknown column is reported once by name', () => {
    const r = mapRows([['Họ và tên', 'Lớp'], ['A', '10A1'], ['B', '10A2']], VIEW)
    expect(r.errors[0]?.message).toMatch(/Lớp/)
    expect(r.errors.filter((e) => /Lớp/.test(e.message))).toHaveLength(1)
    expect(r.errors[0]?.line).toBe(1)
    expect(r.ok).toEqual([]) // tiêu đề sai thì không nhập gì
  })

  test('headers match the field name too, ignoring case and surrounding spaces', () => {
    const r = mapRows([[' HO_TEN ', 'su_kien', ' ngày CẤP', 'EMAIL'], ['A', 'HT', '5/6/2027', '']], VIEW)
    expect(r.errors).toEqual([])
    expect(r.ok).toEqual([{ ho_ten: 'A', su_kien: 'HT', ngay_cap: '2027-06-05' }])
  })

  test('a missing required column is reported on line 1 and nothing is imported', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện'], ['A', 'HT']], VIEW)
    expect(r.ok).toEqual([])
    expect(r.errors).toEqual([{ line: 1, message: expect.stringMatching(/Ngày cấp/) }])
  })

  test('a duplicated column is an error', () => {
    const r = mapRows([['Họ và tên', 'họ và tên', 'Sự kiện', 'Ngày cấp'], ['A', 'B', 'HT', '1/1/2027']], VIEW)
    expect(r.errors[0]?.message).toMatch(/trùng/)
    expect(r.ok).toEqual([])
  })

  test('the sequence column is issued by the core and cannot be imported', () => {
    const r = mapRows([['Số chứng nhận', 'Họ và tên', 'Sự kiện', 'Ngày cấp'], ['1/CN-CLB', 'A', 'HT', '1/1/2027']], VIEW)
    expect(r.errors[0]?.message).toMatch(/Số chứng nhận/)
    expect(r.ok).toEqual([])
  })

  test('blank rows are skipped but line numbers stay true', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], [''], ['A', 'HT', '1/1/2027'], ['', '', ''], ['', 'HT', '1/1/2027']], VIEW)
    expect(r.ok).toHaveLength(1)
    expect(r.lines).toEqual([3])
    expect(r.errors).toEqual([{ line: 5, message: expect.stringMatching(/Họ và tên/) }])
  })

  test('explicit lines (multi-line cells) replace the row index', () => {
    const rows = [['Họ và tên', 'Sự kiện', 'Ngày cấp'], ['A', 'HT\nđợt 2', '1/1/2027'], ['', 'HT', '1/1/2027']]
    const r = mapRows(rows, VIEW, [1, 2, 5])
    expect(r.lines).toEqual([2])
    expect(r.errors[0]?.line).toBe(5)
  })

  test.each([
    ['10/11/2026', '2026-11-10'], ['1/2/2027', '2027-02-01'], ['05-06-2027', '2027-06-05'], ['5.6.2027', '2027-06-05'],
    ['2026-11-10', '2026-11-10'], [' 29/02/2028 ', '2028-02-29'],
  ])('date %s', (raw, iso) => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], ['A', 'HT', raw]], VIEW)
    expect(r.errors).toEqual([])
    expect(r.ok[0]?.ngay_cap).toBe(iso)
  })

  test.each(['31/02/2026', '29/02/2027', '13/13/2026', '10/11/26', 'hôm qua', '46000', '10/11/2026 08:00'])('bad date %s is a line error', (raw) => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], ['A', 'HT', raw]], VIEW)
    expect(r.ok).toEqual([])
    expect(r.errors).toEqual([{ line: 2, message: expect.stringMatching(/Ngày cấp.*DD\/MM\/YYYY/) }])
  })

  test('a cell with a replacement character is refused: broken text never reaches the server', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], ['Nguy�n', 'HT', '1/1/2027'], ['B', 'H\u0085T', '1/1/2027']], VIEW)
    expect(r.ok).toEqual([])
    expect(r.errors.map((e) => e.line)).toEqual([2, 3])
    expect(r.errors[0]?.message).toMatch(/Họ và tên.*không đọc được/)
  })

  test('cells beyond the header are an error when they are not empty', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp'], ['A', 'HT', '1/1/2027', 'thừa'], ['B', 'HT', '1/1/2027', '']], VIEW)
    expect(r.errors).toEqual([{ line: 2, message: expect.stringMatching(/không có tiêu đề/) }])
    expect(r.ok).toHaveLength(1)
  })

  test('short rows are padded; empty optional cells are left out', () => {
    const r = mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp', 'Email'], ['A', 'HT', '1/1/2027']], VIEW)
    expect(r.ok).toEqual([{ ho_ten: 'A', su_kien: 'HT', ngay_cap: '2027-01-01' }])
  })

  test('an empty file and a header-only file', () => {
    expect(mapRows([], VIEW).errors).toEqual([{ line: 1, message: expect.stringMatching(/trống/) }])
    expect(mapRows([['Họ và tên', 'Sự kiện', 'Ngày cấp']], VIEW)).toEqual({ ok: [], errors: [], lines: [] })
  })
})

describe('whole pipeline on the Excel fixtures', () => {
  test.each(['utf8-bom.csv', 'cp1258.csv', 'utf16le-bom.csv', 'utf8.csv', 'utf8-nfd.csv'])('%s gives the same three rows', (f) => {
    const { text } = decodeCsv(fixture(f))
    const { rows, lines } = parseCsvWithLines(text)
    const r = mapRows(rows, VIEW, lines)
    expect(r.errors).toEqual([])
    expect(r.ok).toEqual(EXPECTED)
    expect(r.lines).toEqual([2, 3, 4])
  })
})
