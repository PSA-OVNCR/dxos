// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Tự kiểm gói trên trình duyệt có repo neo: repo không truy cập được ≠ gói không hợp lệ (quyết định điều phối 1).
import { rawAnchor, type AnchorSource } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import { ANCHOR_PROBE_PATH, explainFailure, verifyInBrowser } from '../src/verify'

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

  test('máy chủ chọn đường dẫn làm fetch hỏng nhưng repo neo vẫn trả lời → không hợp lệ, không rơi về không ghim', async () => {
    const v = vec('ok-anchored')
    const real = fromVector(v)
    // Đường dẫn do gói chọn (keys/seal-key/v<key_version>.pub) bị hỏng; đường dẫn cố định vẫn trả lời.
    const poisoned: AnchorSource = {
      file: async (p) => {
        if (p.startsWith('keys/seal-key/')) throw new Error('414 URI Too Long')
        return real.file(p)
      },
    }
    const r = await verifyInBrowser(v.bundle_text, { anchor: poisoned })
    expect(r.result.ok).toBe(false)
    expect(r.result.pinned).toBe(true)
    expect(r.anchorNote).toBe('')
    // Repo neo trả 404 cho đường dẫn thăm dò cũng là "đã với tới repo".
    const notFound: AnchorSource = {
      file: async (p) => {
        if (p === ANCHOR_PROBE_PATH) return null
        throw new Error('boom')
      },
    }
    const r2 = await verifyInBrowser(v.bundle_text, { anchor: notFound })
    expect(r2.result.ok).toBe(false)
    expect(r2.anchorNote).toBe('')
  })

  test('đường dẫn thăm dò cũng ném lỗi → repo neo thật sự không truy cập được → không ghim kèm ghi chú', async () => {
    const v = vec('ok-anchored')
    const probed: string[] = []
    const down: AnchorSource = { file: async (p) => { probed.push(p); throw new Error('mạng đứt') } }
    const r = await verifyInBrowser(v.bundle_text, { anchor: down })
    expect(r.result.ok).toBe(true)
    expect(r.result.pinned).toBe(false)
    expect(r.anchorNote).toBe('Không truy cập được repo neo — chưa đối chiếu')
    expect(probed).toContain(ANCHOR_PROBE_PATH)
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

// Plan 04 R11: niêm phong vừa ban hành, STH phủ nó chưa kịp lên repo neo → chờ, không phải "Không hợp lệ". Mọi bước khác chặt.
describe('verifyInBrowser: STH chưa neo kịp', () => {
  const edit = (v: Vector, fn: (b: Record<string, any>) => void): string => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const b = JSON.parse(v.bundle_text) as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
    fn(b)
    return JSON.stringify(b)
  }
  const without = (v: Vector, path: string): Vector => {
    const { [path]: _drop, ...rest } = v.anchor_files
    return { ...v, anchor_files: rest }
  }

  test('STH đã neo chưa phủ lá (khóa đã ghim) → ok, pendingAnchor, pinned, không ghi chú "chưa đối chiếu"', async () => {
    const v = vec('leaf-after-last-anchor')
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })
    expect(r.result.ok).toBe(true)
    expect(r.result.pinned).toBe(true)
    expect(r.result.pendingAnchor).toBe(true)
    expect(r.anchorNote).toBe('')
  })

  test('gói không có anchored → pendingAnchor', async () => {
    const v = vec('ok-anchored')
    const r = await verifyInBrowser(edit(v, (b) => { delete b.anchored }), { anchor: fromVector(v) })
    expect([r.result.ok, r.result.pinned, r.result.pendingAnchor]).toEqual([true, true, true])
  })

  test('sth/<n>.json trong repo neo khác anchored.sth → hỏng thật (NOT_ANCHORED), kể cả khi chưa phủ lá', async () => {
    const v = vec('anchor-sth-mismatch')
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })
    expect([r.result.ok, r.result.code, r.result.pendingAnchor]).toEqual([false, 'NOT_ANCHORED', false])
    const lv = vec('leaf-after-last-anchor')
    const size = (JSON.parse(lv.bundle_text) as { anchored: { sth: { tree_size: number } } }).anchored.sth.tree_size
    const path = `sth/${String(size).padStart(12, '0')}.json`
    const differs = { ...lv, anchor_files: { ...lv.anchor_files, [path]: lv.anchor_files['keys/sth-key/v1.pub']! } }
    const r2 = await verifyInBrowser(lv.bundle_text, { anchor: fromVector(differs) })
    expect([r2.result.ok, r2.result.code]).toEqual([false, 'NOT_ANCHORED'])
  })

  test('khóa chưa neo trong repo → hỏng thật dù STH chưa neo kịp; máy chủ không dùng "chờ" để né việc ghim khóa', async () => {
    const lv = vec('leaf-after-last-anchor')
    for (const path of ['keys/seal-key/v1.pub', 'keys/sth-key/v1.pub']) {
      const r = await verifyInBrowser(lv.bundle_text, { anchor: fromVector(without(lv, path)) })
      expect([r.result.ok, r.result.code, r.result.pendingAnchor], path).toEqual([false, 'KEY_NOT_ANCHORED', false])
      expect(r.anchorNote).toBe('')
    }
    const km = vec('key-mismatch')
    const r = await verifyInBrowser(km.bundle_text, { anchor: fromVector(km) })
    expect([r.result.ok, r.result.code]).toEqual([false, 'KEY_MISMATCH'])
  })

  test('chữ ký, inclusion, consistency vẫn hỏng thật khi chờ neo', async () => {
    for (const [name, code] of [['tampered-payload', 'SIGNATURE'], ['tampered-proof', 'INCLUSION'],
      ['sth-signature', 'STH_SIGNATURE'], ['consistency', 'CONSISTENCY']] as const) {
      const v = vec(name)
      const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })
      expect([r.result.ok, r.result.code], name).toEqual([false, code])
    }
  })

  test('đã neo thật: không pending', async () => {
    const v = vec('ok-anchored')
    expect((await verifyInBrowser(v.bundle_text, { anchor: fromVector(v) })).result.pendingAnchor).toBe(false)
  })

  test('chưa cấu hình repo neo: không bao giờ pending', async () => {
    const v = vec('leaf-after-last-anchor')
    const r = await verifyInBrowser(v.bundle_text, {})
    expect([r.result.ok, r.result.pinned, r.result.pendingAnchor]).toEqual([true, false, false])
  })

  test('niêm phong khác mã đang kiểm vẫn bị loại khi đang chờ neo', async () => {
    const v = vec('leaf-after-last-anchor')
    const r = await verifyInBrowser(v.bundle_text, { anchor: fromVector(v), sealId: 'ZZZZZZZZZZZZZZZZZZZZZZZZZZ' })
    expect([r.result.ok, r.result.code, r.result.pendingAnchor]).toEqual([false, 'MALFORMED', false])
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
