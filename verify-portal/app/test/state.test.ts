// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Bảng trạng thái của verify-portal/minimal/README.md ("Trạng thái hiển thị"), thêm 429, và nhãn cuối cùng.
import type { BundleResult, Json } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import { finalVerdict, formatVn, SEAL_ID, serverSays, serverVerdict, viewState, type PortalState } from '../src/state'

const anchored = { tree_size: 8, repo: 'r', commit_sha: 'c' }
function view(over: Record<string, unknown> = {}): Json {
  return {
    seal_id: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', status: 'VALID', signature_valid: true,
    inclusion: { leaf_index: 5, tree_size: 8, verified: true, anchored },
    ...over,
  } as Json
}
const inc = (over: Record<string, unknown>) => view({ inclusion: { leaf_index: 5, tree_size: 8, verified: true, anchored, ...over } })

describe('viewState (mỗi dòng của bảng)', () => {
  test.each<[string, number, Json | null, PortalState]>([
    ['404 → không tìm thấy', 404, null, 'NOT_FOUND'],
    ['503 keys-unavailable', 503, null, 'KEYS_UNAVAILABLE'],
    ['429 gateway', 429, null, 'RATE_LIMITED'],
    ['SEAL_PENDING (không lộ trường nào)', 200, { seal_id: 'X', status: 'SEAL_PENDING' }, 'PENDING'],
    ['signature_valid false', 200, view({ signature_valid: false }), 'SERVER_INVALID'],
    ['signature_valid thiếu', 200, view({ signature_valid: undefined }), 'SERVER_INVALID'],
    ['signature_valid là chuỗi "true"', 200, view({ signature_valid: 'true' }), 'SERVER_INVALID'],
    ['inclusion.verified false khi đã có STH phủ lá', 200, inc({ verified: false, anchored: null }), 'SERVER_INVALID'],
    ['thiếu inclusion', 200, view({ inclusion: undefined }), 'SERVER_INVALID'],
    ['REVOKED', 200, view({ status: 'REVOKED' }), 'REVOKED'],
    ['VALID, đã kiểm, anchored khác null', 200, view(), 'VALID_ANCHORED'],
    ['VALID, đã kiểm, anchored null', 200, inc({ anchored: null }), 'VALID_UNANCHORED'],
    ['VALID, chữ ký đúng, chưa có STH phủ lá', 200,
      inc({ tree_size: null, verified: false, anchored: null }), 'WAIT_STH'],
    ['trạng thái lạ', 200, view({ status: 'WEIRD' }), 'SERVER_INVALID'],
  ])('%s', (_name, status, body, expected) => {
    expect(viewState(status, body)).toBe(expected)
  })

  test('REVOKED mà chữ ký sai vẫn là không hợp lệ (như trang tối giản)', () => {
    expect(viewState(200, view({ status: 'REVOKED', signature_valid: false }))).toBe('SERVER_INVALID')
  })
  test('mã HTTP khác hoặc thân không đọc được → UNAVAILABLE, không bao giờ là không hợp lệ', () => {
    expect(viewState(500, null)).toBe('UNAVAILABLE')
    expect(viewState(200, null)).toBe('UNAVAILABLE')
    expect(viewState(200, [] as Json)).toBe('UNAVAILABLE')
  })
})

const ok = (pinned: boolean): BundleResult => ({
  ok: true, pinned, code: null, message: 'OK', payload: {}, issuer: { name: 'Trường', id: null },
})
const bad = (code: BundleResult['code']): BundleResult => ({
  ok: false, pinned: true, code, message: `${code}: x`, payload: null, issuer: null,
})

const pendingOk = (): BundleResult => ({ ...ok(true), pendingAnchor: true })

describe('finalVerdict', () => {
  test('khóa đã ghim nhưng STH chưa neo kịp → "Hợp lệ — chưa neo công khai", không phải "Không hợp lệ" (Plan 04 R11)', () => {
    for (const s of ['VALID_UNANCHORED', 'VALID_ANCHORED'] as const) {
      const v = finalVerdict(s, pendingOk())
      expect(v.label).toBe('Hợp lệ — chưa neo công khai')
      expect(v.label).toBe(serverVerdict('VALID_UNANCHORED').label) // cùng nhãn và cùng huy hiệu với trạng thái chưa neo
      expect(v.tone).toBe(serverVerdict('VALID_UNANCHORED').tone)
      expect(v.tone).toBe('unanchored')
      expect(v.note).toContain('chưa được công bố')
      expect(v.note).toContain('vài phút')
    }
  })
  test('chờ neo không nâng nhãn: máy chủ báo thu hồi thì vẫn "Đã thu hồi"; tự kiểm hỏng vẫn "Không hợp lệ"', () => {
    expect(finalVerdict('REVOKED', pendingOk()).label).toBe('Đã thu hồi')
    expect(finalVerdict('VALID_UNANCHORED', bad('NOT_ANCHORED')).label).toBe('Không hợp lệ')
    expect(finalVerdict('VALID_UNANCHORED', bad('KEY_NOT_ANCHORED')).label).toBe('Không hợp lệ')
  })
  test('đã neo thật (pendingAnchor false/vắng) vẫn là "Hợp lệ — đã đối chiếu repo neo"', () => {
    expect(finalVerdict('VALID_ANCHORED', { ...ok(true), pendingAnchor: false }).label).toBe('Hợp lệ — đã đối chiếu repo neo')
    expect(finalVerdict('VALID_ANCHORED', ok(true)).label).toBe('Hợp lệ — đã đối chiếu repo neo')
  })
  test('server VALID nhưng gói SIGNATURE sai → Không hợp lệ', () => {
    const v = finalVerdict('VALID_ANCHORED', bad('SIGNATURE'))
    expect(v.label).toBe('Không hợp lệ')
    expect(v.tone).toBe('bad')
  })
  test('tự kiểm đạt và đã ghim repo neo', () => {
    expect(finalVerdict('VALID_UNANCHORED', ok(true)).label).toBe('Hợp lệ — đã đối chiếu repo neo')
  })
  test('tự kiểm đạt nhưng chưa ghim repo neo', () => {
    expect(finalVerdict('VALID_ANCHORED', ok(false)).label).toBe('Hợp lệ — chưa đối chiếu repo neo')
  })
  test('UNSUPPORTED_CRYPTO → nhãn của máy chủ kèm lời giải thích', () => {
    const v = finalVerdict('VALID_ANCHORED', bad('UNSUPPORTED_CRYPTO'))
    expect(v.label).toBe('Hợp lệ')
    expect(v.note).toContain('Trình duyệt này không tự kiểm được chữ ký')
  })
  test('máy chủ báo REVOKED thì tự kiểm đạt cũng không được thành "Hợp lệ"', () => {
    expect(finalVerdict('REVOKED', ok(true)).label).toBe('Đã thu hồi')
    expect(finalVerdict('REVOKED', bad('SIGNATURE')).label).toBe('Không hợp lệ')
  })
  test('chưa có kết quả tự kiểm: VALID không bao giờ là "Hợp lệ" trần', () => {
    for (const s of ['VALID_ANCHORED', 'VALID_UNANCHORED'] as const) {
      expect(finalVerdict(s, null).label).toBe('Chưa tự kiểm trên trình duyệt')
    }
  })
  test('các trạng thái không cần gói lấy nhãn của máy chủ', () => {
    expect(finalVerdict('NOT_FOUND', null).label).toBe('Không tìm thấy')
    expect(finalVerdict('PENDING', null).label).toBe('Chờ niêm phong')
    expect(finalVerdict('WAIT_STH', null).label).toBe('Chữ ký hợp lệ — đang chờ công bố vào sổ cái')
    expect(finalVerdict('SERVER_INVALID', null).label).toBe('Không hợp lệ')
    expect(finalVerdict('KEYS_UNAVAILABLE', null).note).toBe('Tạm thời chưa kiểm được chữ ký, thử lại sau')
    expect(finalVerdict('KEYS_UNAVAILABLE', null).label).not.toBe('Không hợp lệ')
    expect(finalVerdict('RATE_LIMITED', null).label).not.toBe('Không hợp lệ')
    expect(finalVerdict('UNAVAILABLE', null).label).not.toBe('Không hợp lệ')
  })
})

describe('helpers', () => {
  test('lời máy chủ báo không chứa cụm "hợp lệ" (chỉ nhãn cuối cùng được dùng)', () => {
    const all: PortalState[] = ['NOT_FOUND', 'KEYS_UNAVAILABLE', 'RATE_LIMITED', 'UNAVAILABLE', 'PENDING',
      'SERVER_INVALID', 'REVOKED', 'WAIT_STH', 'VALID_UNANCHORED', 'VALID_ANCHORED']
    for (const s of all) expect(serverSays(s).toLowerCase()).not.toContain('hợp lệ')
  })
  test('SEAL_ID là ^[A-Z2-7]{26}$', () => {
    expect(SEAL_ID.test('ABCDEFGHIJKLMNOPQRSTUVWXYZ')).toBe(true)
    expect(SEAL_ID.test('ABCDEFGHIJKLMNOPQRSTUVWXY1')).toBe(false)
    expect(SEAL_ID.test('abcdefghijklmnopqrstuvwxyz')).toBe(false)
    expect(SEAL_ID.test('ABCDEFGHIJKLMNOPQRSTUVWXYZ\n')).toBe(false)
  })
  test('formatVn: giờ Việt Nam (UTC+7)', () => {
    const s = formatVn('2026-10-21T09:00:00Z')
    expect(s).toContain('16:00:00')
    expect(s).toContain('21/10/2026')
    expect(s).toContain('giờ Việt Nam')
  })
  test('formatVn: chuỗi không phải thời điểm giữ nguyên, không ném lỗi', () => {
    expect(formatVn('không phải ngày')).toBe('không phải ngày')
  })
})
