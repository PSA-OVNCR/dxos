// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { rec } from 'dxos-sdk-js/testing'
import type { DxRecord } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import { formatVn, statusLabel } from '../src/status'

const STATUS_CASES: [DxRecord, string][] = [
  [rec({ seal_state: 'SEALED', wf_state: 'ended:approved' }), 'Đã ban hành'],
  [rec({ seal_state: 'REVOKED', wf_state: 'ended:approved' }), 'Đã thu hồi'],
  [rec({ seal_state: 'SEAL_PENDING', wf_state: 'ended:approved' }), 'Chờ niêm phong'],
  [rec({ wf_state: 'running' }), 'Đang duyệt'],
  [rec({ wf_state: 'ended:rejected' }), 'Bị trả lại'],
  [rec({ wf_state: 'ended:guard_failed' }), 'Dừng do vi phạm điều kiện duyệt'],
  [rec({ wf_state: null }), 'Nháp'],
  [rec({ wf_state: 'something-new' }), 'Nháp'],
]

describe('statusLabel', () => {
  test('covers every state', () => {
    for (const [r, l] of STATUS_CASES) expect(statusLabel(r)).toBe(l)
  })

  test('the seal state outranks the workflow state', () => {
    expect(statusLabel(rec({ seal_state: 'SEALED', wf_state: 'running' }))).toBe('Đã ban hành')
  })
})

describe('formatVn', () => {
  test('renders Asia/Ho_Chi_Minh time whatever the machine zone', () => {
    expect(formatVn('2026-10-22T00:00:00Z')).toBe('07:00 22/10/2026')
    expect(formatVn('2026-10-21T17:30:00Z')).toBe('00:30 22/10/2026')
    expect(formatVn('2026-10-22T00:00:00+07:00')).toBe('00:00 22/10/2026')
  })

  test('keeps an unreadable value as is', () => {
    expect(formatVn('không phải ngày')).toBe('không phải ngày')
  })
})
