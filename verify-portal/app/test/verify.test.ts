// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Tự kiểm gói trên trình duyệt có repo neo: repo không truy cập được ≠ gói không hợp lệ (quyết định điều phối 1).
import { rawAnchor, type AnchorSource } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import { explainFailure, verifyInBrowser } from '../src/verify'

interface Vector { bundle_text: string; anchor_files: Record<string, string>; file_sha256?: string }
const VECTORS = import.meta.glob<Vector>('../../../sdk/js/test/vectors/*.json', { eager: true, import: 'default' })
const vec = (name: string): Vector => VECTORS[`../../../sdk/js/test/vectors/${name}.json`]!
const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
const fromVector = (v: Vector): AnchorSource => ({
  file: async (p) => (v.anchor_files[p] !== undefined ? b64(v.anchor_files[p]!) : null),
})
const throwing: AnchorSource = { file: async () => { throw new Error('mạng đứt') } }

describe('verifyInBrowser', () => {
  test('repo neo đọc được → đã ghim, không ghi chú', async () => {
    const v = vec('ok-anchored')
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })
    expect(r.result.ok).toBe(true)
    expect(r.result.pinned).toBe(true)
    expect(r.anchorNote).toBe('')
  })

  test('chưa cấu hình repo neo → tự kiểm không ghim và nói rõ', async () => {
    const v = vec('ok-anchored')
    const r = await verifyInBrowser(v.bundle_text, {})
    expect(r.result.ok).toBe(true)
    expect(r.result.pinned).toBe(false)
    expect(r.anchorNote).toContain('chưa đối chiếu')
  })

  test('repo neo ném lỗi (mạng/CORS/5xx) → kết quả không ghim kèm ghi chú, KHÔNG phải không hợp lệ', async () => {
    const v = vec('ok-anchored')
    const r = await verifyInBrowser(v.bundle_text, { anchor: throwing })
    expect(r.result.ok).toBe(true)
    expect(r.result.pinned).toBe(false)
    expect(r.anchorNote).toBe('Không truy cập được repo neo — chưa đối chiếu')
  })

  test('repo neo trả HTTP 5xx qua rawAnchor → cũng là chưa đối chiếu', async () => {
    const v = vec('ok-anchored')
    const anchor = rawAnchor('https://anchor.test/log', async () => new Response('', { status: 503 }))
    const r = await verifyInBrowser(v.bundle_text, { anchor })
    expect(r.result.ok).toBe(true)
    expect(r.anchorNote).toContain('Không truy cập được repo neo')
  })

  test('repo neo lỗi nhưng gói hỏng thật → vẫn không hợp lệ', async () => {
    const v = vec('status-lies')
    const r = await verifyInBrowser(v.bundle_text, { anchor: throwing })
    expect(r.result.ok).toBe(false)
    expect(r.result.code).toBe('SIGNATURE')
  })

  test('repo neo trả 404 → KEY_NOT_ANCHORED là không hợp lệ thật (không rơi về không ghim)', async () => {
    const v = vec('ok-anchored')
    const empty: AnchorSource = { file: async () => null }
    const r = await verifyInBrowser(v.bundle_text, { anchor: empty })
    expect(r.result.ok).toBe(false)
    expect(r.result.code).toBe('KEY_NOT_ANCHORED')
    expect(r.result.pinned).toBe(true)
    expect(r.anchorNote).toBe('')
  })

  test('tệp có trong repo neo nhưng khác gói → không hợp lệ thật', async () => {
    const v = vec('key-mismatch')
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })
    expect(r.result.ok).toBe(false)
    expect(r.result.pinned).toBe(true)
    expect(r.anchorNote).toBe('')
  })

  test('mã băm tệp được chuyển cho bộ kiểm', async () => {
    const v = vec('file-in-seal')
    expect((await verifyInBrowser(v.bundle_text, { anchor: fromVector(v), fileSha256: v.file_sha256 })).result.ok)
      .toBe(true)
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v), fileSha256: 'a'.repeat(64) })
    expect(r.result.code).toBe('FILE_NOT_IN_SEAL')
  })

  test('gói thật của niêm phong khác mã đang kiểm → không hợp lệ (máy chủ bị chiếm không thể tráo gói)', async () => {
    const v = vec('ok-anchored')
    const ok = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v), sealId: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' })
    expect(ok.result.ok).toBe(true)
    const swapped = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v), sealId: 'ZZZZZZZZZZZZZZZZZZZZZZZZZZ' })
    expect(swapped.result.ok).toBe(false)
    expect(swapped.result.code).toBe('MALFORMED')
    expect(swapped.result.message).toContain('seal_id')
  })
})

describe('explainFailure', () => {
  const codes = ['FORMAT', 'KEY_VERSION', 'KEY_MISSING', 'KEY_NOT_ANCHORED', 'KEY_MISMATCH', 'KEY_STATEMENT',
    'KEY_STATEMENT_MISSING', 'KEY_STATEMENT_NOT_ANCHORED', 'KEY_NOT_VALID_AT_ISSUE', 'SIGNATURE', 'LEAF_LINK',
    'NO_STH', 'INCLUSION', 'STH_SIGNATURE', 'NOT_ANCHORED', 'ANCHORED_SIGNATURE', 'CONSISTENCY',
    'FILE_NOT_IN_SEAL', 'MALFORMED', 'UNSUPPORTED_CRYPTO'] as const
  test('mọi mã đều có lời giải thích tiếng Việt, không chứa cụm "hợp lệ"', () => {
    for (const code of codes) {
      const text = explainFailure({ ok: false, pinned: false, code, message: `${code}: x`, payload: null, issuer: null })
      expect(text.length).toBeGreaterThan(5)
      expect(text.toLowerCase()).not.toContain('hợp lệ')
    }
  })
})
