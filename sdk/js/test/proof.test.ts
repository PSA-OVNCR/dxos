// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Kiểm gói bằng chứng trên trình duyệt: phải ra CÙNG mã với dxos-witness trên các vector do
// witness/tests/test_web_vectors.py sinh (ghim và chưa ghim), cộng các test đơn vị cho canonical/merkle/neo.
import { describe, expect, test } from 'vitest'
import {
  canonicalBytes, leafHash, parseJsonLossless, rawAnchor, sha256Hex, verifyBundle, verifyConsistency,
  verifyInclusion, type AnchorSource, type FailCode,
} from '../src/index'
import { parseRfc3339Micros, verifyBundleWith } from '../src/proof/bundle'
import { b64decodePy } from '../src/proof/hash'
import merkleVectors from './vectors/merkle/rfc9162.json'

interface Vector {
  bundle_text: string; anchor_files: Record<string, string>; file_sha256?: string
  expected: FailCode | null; expected_unpinned: FailCode | null
}
const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
const hexb = (h: string) => Uint8Array.from(h.match(/../g) ?? [], (x) => parseInt(x, 16))
// Vector JSON đọc qua Vite (không cần @types/node); bundle_text là chuỗi nên không qua số thực.
const VECTORS = import.meta.glob<Vector>('./vectors/*.json', { eager: true, import: 'default' })
const loadVec = (f: string): Vector => VECTORS[`./vectors/${f}`]!
const anchorOf = (v: Vector): AnchorSource => ({
  file: async (p) => (v.anchor_files[p] !== undefined ? b64(v.anchor_files[p]!) : null),
})
const files = Object.keys(VECTORS).map((p) => p.slice('./vectors/'.length)).sort()

test('vector directory is populated', () => {
  expect(files.length).toBeGreaterThanOrEqual(43)
  expect(files).toContain('ok-anchored.json')
})

for (const f of files) {
  test(`vector ${f} (pinned)`, async () => {
    const v = loadVec(f)
    const r = await verifyBundle(v.bundle_text, { anchor: anchorOf(v), fileSha256: v.file_sha256 })
    expect(r.ok ? null : r.code).toBe(v.expected)
    expect(r.pinned).toBe(true)
    expect(r.ok).toBe(r.code === null)
    if (!r.ok) expect(r.message.startsWith(`${r.code}: `)).toBe(true)
  })
  test(`vector ${f} (unpinned)`, async () => {
    const v = loadVec(f)
    const r = await verifyBundle(v.bundle_text, { fileSha256: v.file_sha256 })
    expect(r.ok ? null : r.code).toBe(v.expected_unpinned)
    expect(r.pinned).toBe(false)
  })
}

describe('canonical JSON', () => {
  test('canonical: code-point key order, NFC, no spaces, bigint digits', () => {
    expect(new TextDecoder().decode(canonicalBytes(parseJsonLossless('{"b":1,"a":"é","\u{1D538}":9007199254740993}'))))
      .toBe('{"a":"é","b":1,"\u{1D538}":9007199254740993}')
  })
  test('canonical rejects floats and NFC-colliding keys', () => {
    expect(() => parseJsonLossless('{"x":1.5}')).toThrow()
    expect(() => canonicalBytes({ 'é': 1, 'é': 2 })).toThrow()
  })
  test('astral keys sort after U+FFFF (code point, not UTF-16 unit)', () => {
    const out = new TextDecoder().decode(canonicalBytes({ '\u{1D538}': 1, '￿': 2, '': 3, z: 4 }))
    expect(out).toBe('{"z":4,"":3,"￿":2,"\u{1D538}":1}')
  })
  test('string escaping matches Python json.dumps(ensure_ascii=False)', () => {
    // Python: canonical_bytes("a\x00\x1f\x7f\u2028\"\\/\b\f\n\r\t") -> đúng chuỗi dưới đây
    const s = 'a\u0000\u001f\u007f\u2028"\\/\b\f\n\r\t'
    expect(new TextDecoder().decode(canonicalBytes(s))).toBe('"a\\u0000\\u001f\u007f\u2028\\"\\\\/\\b\\f\\n\\r\\t"')
  })
  test('lossless integers: safe range stays number, beyond becomes bigint, -0 is 0', () => {
    expect(parseJsonLossless('9007199254740991')).toBe(9007199254740991)
    expect(parseJsonLossless('-9007199254740991')).toBe(-9007199254740991)
    expect(parseJsonLossless('9007199254740992')).toBe(9007199254740992n)
    expect(parseJsonLossless('-18446744073709551617')).toBe(-18446744073709551617n)
    expect(Object.is(parseJsonLossless('-0'), 0)).toBe(true)
    expect(new TextDecoder().decode(canonicalBytes([2n ** 64n, -1, 0]))).toBe('[18446744073709551616,-1,0]')
  })
  test('parser rejects what the witness CLI rejects', () => {
    for (const bad of ['{"a":1,"a":2}', '[1,]', '01', '1e3', '-Infinity', 'NaN', '"\u0001"', '"\\x"', '{"a":1} x',
      '"\uD800"', '﻿{}', "{'a':1}", '']) {
      expect(() => parseJsonLossless(bad), bad).toThrow()
    }
    expect(parseJsonLossless(' \t\n\r[true,false,null,"\\ud835\\udd38\\u00E9"] ')).toEqual([true, false, null, '\u{1D538}é'])
  })
  test('__proto__ is an ordinary own key', () => {
    const v = parseJsonLossless('{"__proto__":{"x":1}}') as Record<string, unknown>
    expect(Object.keys(v)).toEqual(['__proto__'])
    expect(Object.getPrototypeOf(v)).toBe(Object.prototype)
    expect(new TextDecoder().decode(canonicalBytes(v as never))).toBe('{"__proto__":{"x":1}}')
  })
  test('canonicalBytes rejects unsafe numbers, lone surrogates and non-plain objects', () => {
    expect(() => canonicalBytes(2 ** 60)).toThrow()
    expect(() => canonicalBytes(1.5)).toThrow()
    expect(() => canonicalBytes('\uD800')).toThrow()
    expect(() => canonicalBytes(new Date() as never)).toThrow()
    expect(() => canonicalBytes(undefined as never)).toThrow()
  })
})

describe('merkle (RFC 9162) on dxos-proof vectors', () => {
  const mv = merkleVectors as {
    inclusion: { leaf: string; index: number; size: number; proof: string[]; root: string; ok: boolean }[]
    consistency: { m: number; n: number; root_m: string; root_n: string; proof: string[]; ok: boolean }[]
  }
  test('inclusion verdicts equal Python', async () => {
    for (const c of mv.inclusion) {
      expect(await verifyInclusion(hexb(c.leaf), c.index, c.size, c.proof.map(hexb), hexb(c.root)), JSON.stringify(c)).toBe(c.ok)
    }
  })
  test('consistency verdicts equal Python', async () => {
    for (const c of mv.consistency) {
      expect(await verifyConsistency(c.m, c.n, hexb(c.root_m), hexb(c.root_n), c.proof.map(hexb)), JSON.stringify(c)).toBe(c.ok)
    }
  })
  test('leafHash = SHA-256(0x00 || canonical(entry))', async () => {
    // Python: leaf_hash(canonical_bytes({"i": 0})).hex()
    const first = mv.inclusion.find((c) => c.size === 1)!
    expect(Array.from(await leafHash({ i: 0 }), (b) => b.toString(16).padStart(2, '0')).join('')).toBe(first.leaf)
  })
})

describe('verifyBundle behaviour', () => {
  test('unpinned when no anchor is given', async () => {
    const v = loadVec('ok-anchored.json'); const r = await verifyBundle(v.bundle_text)
    expect(r.ok).toBe(true); expect(r.pinned).toBe(false)
  })
  test('valid result carries payload (big integers intact) and issuer', async () => {
    const v = loadVec('bigint-public-field.json')
    const r = await verifyBundle(v.bundle_text, { anchor: anchorOf(v) })
    expect(r.ok).toBe(true)
    expect(r.issuer).toEqual({ name: 'Trường Đại học Thử', id: 'TDHT-01' })
    expect((r.payload as { public_fields: { diem: bigint } }).public_fields.diem).toBe(2n ** 60n)
    expect(r.message).toContain('sth/000000000008.json')
  })
  test('missing Ed25519 support → UNSUPPORTED_CRYPTO, never ok', async () => {
    const real = globalThis.crypto.subtle
    const noEd25519Subtle = new Proxy(real, {
      get(t, k) {
        if (k === 'importKey') return async () => { throw new DOMException('Ed25519 unsupported', 'NotSupportedError') }
        const val = Reflect.get(t, k) as unknown
        return typeof val === 'function' ? val.bind(t) : val
      },
    })
    const v = loadVec('ok-anchored.json')
    for (const anchor of [undefined, anchorOf(v)]) {
      const r = await verifyBundleWith(noEd25519Subtle, v.bundle_text, { anchor })
      expect(r.ok).toBe(false); expect(r.code).toBe('UNSUPPORTED_CRYPTO')
    }
    const missing = await verifyBundleWith(undefined as unknown as SubtleCrypto, v.bundle_text, {})
    expect(missing.code).toBe('UNSUPPORTED_CRYPTO')
  })
  test('garbage never throws and is MALFORMED', async () => {
    for (const t of ['', 'null', '[]', '{"format":"dxos-seal-bundle/1"}', '{"a":1,"a":1}', '\uD800']) {
      const r = await verifyBundle(t)
      expect(r.ok).toBe(false)
      expect(r.code, t).toBe('MALFORMED')
    }
  })
  test('an anchor source that fails is MALFORMED, never ok', async () => {
    const v = loadVec('ok-anchored.json')
    const r = await verifyBundle(v.bundle_text, { anchor: { file: async () => { throw new Error('mạng hỏng') } } })
    expect(r.ok).toBe(false); expect(r.code).toBe('MALFORMED'); expect(r.message).toContain('mạng hỏng')
  })
  test('anchor paths requested are exactly the witness layout', async () => {
    const v = loadVec('ok-newer-sth.json'); const asked: string[] = []
    const a = anchorOf(v)
    await verifyBundle(v.bundle_text, { anchor: { file: (p) => { asked.push(p); return a.file(p) } } })
    expect(asked).toEqual(['keys/seal-key/v1.pub', 'keys/sth-key/v1.pub', 'keys/seal-key/v1.json', 'sth/000000000007.json'])
  })
})

describe('RFC 3339 instants (as Python datetime.fromisoformat + astimezone(UTC))', () => {
  test('microsecond precision, offsets, truncation', () => {
    const z = parseRfc3339Micros('2026-10-21T09:00:00Z')
    expect(parseRfc3339Micros('2026-10-21T16:00:00+07:00')).toBe(z)
    expect(parseRfc3339Micros('2026-10-21T09:00:00.0000019Z')).toBe(z + 1n)
    expect(parseRfc3339Micros('2026-01-01T00:00:00+05:99')).toBe(parseRfc3339Micros('2025-12-31T17:21:00Z'))
    expect(parseRfc3339Micros('1970-01-01T00:00:00Z')).toBe(0n)
    expect(parseRfc3339Micros('2000-02-29T00:00:00Z')).toBe(951782400000000n)
  })
  test('ValueError cases', () => {
    for (const s of ['2026-01-01T00:00:00+24:00', '2026-01-01T00:00:00-23:60', '2023-02-29T00:00:00Z',
      '1900-02-29T00:00:00Z', '2026-01-01T24:00:00Z', '2026-01-01T00:60:00Z', '2026-01-01T00:00:60Z',
      '0000-01-01T00:00:00Z', '2026-13-01T00:00:00Z', '2026-01-01T00:00:00', '2026-01-01 00:00:00Z',
      '2026-01-01T00:00:00.1234567890Z', '2026-01-01t00:00:00Z', '２０２６-01-01T00:00:00Z']) {
      expect(() => parseRfc3339Micros(s), s).toThrow(RangeError)
    }
  })
  test('OverflowError cases are not RangeError (witness reports MALFORMED)', () => {
    for (const s of ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00']) {
      let err: unknown
      try { parseRfc3339Micros(s) } catch (e) { err = e }
      expect(err).toBeInstanceOf(Error); expect(err).not.toBeInstanceOf(RangeError)
    }
  })
})

test('base64 decoding follows Python b64decode(validate=True)', () => {
  // (dữ liệu, số '=') -> độ dài kết quả hoặc null, đo trên Python 3.12
  const py: [number, number, number | null][] = [[0, 0, 0], [0, 1, null], [1, 0, null], [2, 0, null], [2, 1, null],
    [2, 2, 1], [3, 0, null], [3, 1, 2], [3, 2, null], [4, 0, 3], [4, 1, 3], [4, 2, 3], [5, 1, null], [6, 2, 4], [7, 1, 5]]
  for (const [d, p, len] of py) expect(b64decodePy('A'.repeat(d) + '='.repeat(p))?.length ?? null, `${d},${p}`).toBe(len)
  expect(Array.from(b64decodePy('A/==')!)).toEqual([3])
  expect(b64decodePy('AA AA')).toBeNull()
  expect(b64decodePy('AA=A')).toBeNull()
})

// ---------------------------------------------------------------- Plan 04 R11: "chưa neo kịp" là chờ, không phải lỗi
describe('verifyBundle allowPendingAnchor (cổng đối soát)', () => {
  const pad = (n: number) => String(n).padStart(12, '0')
  const strip = (v: Vector, files: Record<string, string | null>): Vector => ({
    ...v, anchor_files: Object.fromEntries(Object.entries({ ...v.anchor_files, ...files }).filter(([, x]) => x !== null)) as Record<string, string>,
  })
  const edit = (v: Vector, fn: (b: Record<string, any>) => void): string => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const b = JSON.parse(v.bundle_text) as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
    fn(b)
    return JSON.stringify(b)
  }
  const b64Of = (u: Uint8Array) => btoa(String.fromCharCode(...u))
  const flipHex = (h: string) => (h[0] === '0' ? '1' : '0') + h.slice(1)
  const pending = (v: Vector, text = v.bundle_text) => verifyBundle(text, { anchor: anchorOf(v), allowPendingAnchor: true })
  const strict = (v: Vector, text = v.bundle_text) => verifyBundle(text, { anchor: anchorOf(v) })

  test('STH đã neo chưa phủ lá: strict → NOT_ANCHORED; allowPendingAnchor → ok, pendingAnchor, vẫn pinned', async () => {
    const v = loadVec('leaf-after-last-anchor.json')
    expect((await strict(v)).code).toBe('NOT_ANCHORED')
    const r = await pending(v)
    expect(r.ok).toBe(true)
    expect(r.code).toBeNull()
    expect(r.pinned).toBe(true)
    expect(r.pendingAnchor).toBe(true)
    expect(r.payload).not.toBeNull()
    expect(r.issuer).not.toBeNull()
    expect(r.message).toMatch(/^OK; /)
    expect(r.message).toContain('chưa phủ lá')
  })

  test('gói không có anchored: strict → NOT_ANCHORED; allowPendingAnchor → pendingAnchor', async () => {
    const v = loadVec('ok-anchored.json')
    const text = edit(v, (b) => { delete b.anchored })
    const s = await strict(v, text)
    expect([s.ok, s.code]).toEqual([false, 'NOT_ANCHORED'])
    const r = await pending(v, text)
    expect([r.ok, r.pinned, r.pendingAnchor]).toEqual([true, true, true])
    const nul = await pending(v, edit(v, (b) => { b.anchored = null }))
    expect([nul.ok, nul.pendingAnchor]).toEqual([true, true])
  })

  test('repo neo chưa có sth/<n>.json của STH đã neo (đẩy chưa kịp): chờ; strict vẫn NOT_ANCHORED', async () => {
    const v = loadVec('ok-anchored.json')
    const size = (JSON.parse(v.bundle_text) as { anchored: { sth: { tree_size: number } } }).anchored.sth.tree_size
    const missing = strip(v, { [`sth/${pad(size)}.json`]: null })
    expect((await strict(missing)).code).toBe('NOT_ANCHORED')
    const r = await pending(missing)
    expect([r.ok, r.pendingAnchor]).toEqual([true, true])
    expect(r.message).toContain('chưa có trong repo neo')
  })

  test('đã neo và khớp repo: không pending (allowPendingAnchor không đổi kết quả của gói đã neo)', async () => {
    for (const f of ['ok-anchored.json', 'ok-newer-sth.json']) {
      const v = loadVec(f)
      const r = await pending(v)
      expect([r.ok, r.pinned, r.pendingAnchor], f).toEqual([true, true, false])
      expect(r.message).toContain('đã neo: sth/')
    }
  })

  test('sth/<n>.json CÓ trong repo nhưng khác anchored.sth → hỏng thật, kể cả khi STH chưa phủ lá', async () => {
    const v = loadVec('anchor-sth-mismatch.json')
    expect((await pending(v)).code).toBe('NOT_ANCHORED')
    const lv = loadVec('leaf-after-last-anchor.json')
    const size = (JSON.parse(lv.bundle_text) as { anchored: { sth: { tree_size: number } } }).anchored.sth.tree_size
    const other = Object.values(lv.anchor_files).find((x) => x !== undefined)!
    const differs = strip(lv, { [`sth/${pad(size)}.json`]: other })
    const r = await pending(differs)
    expect([r.ok, r.code, r.pendingAnchor]).toEqual([false, 'NOT_ANCHORED', false])
  })

  test('khóa chưa neo / khóa khác khóa đã neo → hỏng thật, không bao giờ pending', async () => {
    const cases: [string, string][] = [['seal-key-not-anchored.json', 'KEY_NOT_ANCHORED'],
      ['sth-key-not-anchored.json', 'KEY_NOT_ANCHORED'], ['key-mismatch.json', 'KEY_MISMATCH'],
      ['statement-not-anchored.json', 'KEY_STATEMENT_NOT_ANCHORED'], ['statement-differs.json', 'KEY_STATEMENT']]
    for (const [f, code] of cases) {
      const r = await pending(loadVec(f))
      expect([r.ok, r.code, r.pendingAnchor], f).toEqual([false, code, false])
    }
    // Cùng gói "chưa neo kịp" nhưng khóa sth không có trong repo neo: máy chủ không thể dùng chờ để né việc ghim khóa.
    const lv = loadVec('leaf-after-last-anchor.json')
    const noKey = await pending(strip(lv, { 'keys/sth-key/v1.pub': null }))
    expect([noKey.ok, noKey.code]).toEqual([false, 'KEY_NOT_ANCHORED'])
    const noSeal = await pending(strip(lv, { 'keys/seal-key/v1.pub': null }))
    expect([noSeal.ok, noSeal.code]).toEqual([false, 'KEY_NOT_ANCHORED'])
    // Và với gói không có anchored.
    const ok = loadVec('ok-anchored.json')
    const text = edit(ok, (b) => { delete b.anchored })
    expect((await pending(strip(ok, { 'keys/sth-key/v1.pub': null }), text)).code).toBe('KEY_NOT_ANCHORED')
    expect((await pending(strip(ok, { 'keys/seal-key/v1.json': null }), text)).code).toBe('KEY_STATEMENT_NOT_ANCHORED')
  })

  test('chữ ký niêm phong, inclusion, chữ ký STH, STH đã neo và consistency vẫn kiểm đủ khi chờ neo', async () => {
    const lv = loadVec('leaf-after-last-anchor.json')
    expect((await pending(loadVec('tampered-payload.json'))).code).toBe('SIGNATURE')
    expect((await pending(loadVec('tampered-proof.json'))).code).toBe('INCLUSION')
    expect((await pending(loadVec('sth-signature.json'))).code).toBe('STH_SIGNATURE')
    // consistency của STH đã neo cũ bị sửa
    const bad = edit(lv, (b) => { b.anchored.consistency[0] = flipHex(b.anchored.consistency[0] as string) })
    const c = await pending(lv, bad)
    expect([c.ok, c.code]).toEqual([false, 'CONSISTENCY'])
    // chữ ký của STH đã neo cũ bị sửa (và tệp trong repo sửa theo để qua bước đối chiếu tệp)
    let sig = ''
    const text = edit(lv, (b) => {
      const raw = Uint8Array.from(atob(b.anchored.sth.signature as string), (ch) => ch.charCodeAt(0))
      raw[0] = raw[0]! ^ 1
      sig = b64Of(raw)
      b.anchored.sth.signature = sig
    })
    const size = (JSON.parse(text) as { anchored: { sth: { tree_size: number } } }).anchored.sth.tree_size
    const file = b64Of(canonicalBytes(parseJsonLossless(JSON.stringify((JSON.parse(text) as { anchored: { sth: unknown } }).anchored.sth))))
    const a = await pending(strip(lv, { [`sth/${pad(size)}.json`]: file }), text)
    expect([a.ok, a.code]).toEqual([false, 'ANCHORED_SIGNATURE'])
    expect(sig).not.toBe('')
    // gói không có STH nào phủ lá vẫn là NO_STH
    expect((await pending(loadVec('no-sth.json'))).code).toBe('NO_STH')
    // tệp không thuộc niêm phong vẫn hỏng
    const fv = loadVec('file-not-in-seal.json')
    expect((await verifyBundle(fv.bundle_text, { anchor: anchorOf(fv), fileSha256: fv.file_sha256, allowPendingAnchor: true })).code)
      .toBe('FILE_NOT_IN_SEAL')
  })

  test('không có repo neo thì allowPendingAnchor vô nghĩa: pendingAnchor luôn false', async () => {
    const r = await verifyBundle(loadVec('ok-anchored.json').bundle_text, { allowPendingAnchor: true })
    expect([r.ok, r.pinned, r.pendingAnchor]).toEqual([true, false, false])
  })
})

describe('rawAnchor', () => {
  const fake = (status: number, body = 'x') => {
    const calls: { url: string; init?: RequestInit }[] = []
    const f = (async (u: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(u), init }); return new Response(status === 200 ? body : null, { status })
    }) as typeof fetch
    return { f, calls }
  }
  test('fetches base/path from the same host only; 404 → null; other errors throw', async () => {
    const ok = fake(200, 'abc')
    const a = rawAnchor('https://raw.githubusercontent.com/o/log/main/', ok.f)
    expect(new TextDecoder().decode((await a.file('keys/seal-key/v1.pub'))!)).toBe('abc')
    expect(ok.calls[0]!.url).toBe('https://raw.githubusercontent.com/o/log/main/keys/seal-key/v1.pub')
    expect(ok.calls[0]!.init?.redirect).toBe('error')
    expect(ok.calls[0]!.init?.credentials).toBe('omit')
    expect(await rawAnchor('https://h/x', fake(404).f).file('sth/000000000001.json')).toBeNull()
    await expect(rawAnchor('https://h/x', fake(500).f).file('sth/000000000001.json')).rejects.toThrow()
  })
  test('refuses paths that could leave the base', async () => {
    const { f, calls } = fake(200)
    const a = rawAnchor('https://h/x', f)
    for (const p of ['../x', '/etc/passwd', 'https://evil.example/x', '//evil.example/x', 'a/../../b', 'a?b', 'a#b', 'a\\b', '']) {
      await expect(a.file(p), p).rejects.toThrow()
    }
    expect(calls).toHaveLength(0)
  })
})

test('sha256Hex of bytes and Blob', async () => {
  const abc = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  expect(await sha256Hex(new TextEncoder().encode('abc'))).toBe(abc)
  expect(await sha256Hex(new Blob(['abc']))).toBe(abc)
})
