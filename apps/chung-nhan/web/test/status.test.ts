// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { rec } from 'dxos-sdk-js/testing'
import type { DxRecord } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import { dateVn, show, statusLabel } from '../src/status'

const CASES: [DxRecord, string][] = [
  [rec({ seal_state: 'SEALED', wf_state: 'ended:approved' }), 'Đã cấp'],
  [rec({ seal_state: 'REVOKED', wf_state: 'ended:approved' }), 'Đã thu hồi'],
  [rec({ seal_state: 'SEAL_PENDING', wf_state: 'ended:approved' }), 'Chờ niêm phong'],
  [rec({ wf_state: 'running' }), 'Chờ duyệt'],
  [rec({ wf_state: 'ended:rejected' }), 'Bị từ chối'],
  [rec({ wf_state: 'ended:guard_failed' }), 'Dừng do vi phạm điều kiện duyệt'],
  [rec({ wf_state: null }), 'Chưa gửi duyệt'],
  [rec({ wf_state: 'something-new' }), 'Chưa gửi duyệt'],
]

describe('status helpers', () => {
  test.each(CASES)('statusLabel %#', (r, label) => { expect(statusLabel(r)).toBe(label) })

  test('calendar dates are shown DD/MM/YYYY without any time-zone shift; other values are kept', () => {
    expect(dateVn('2026-11-10')).toBe('10/11/2026')
    expect(dateVn('2026-01-01')).toBe('01/01/2026')
    expect(dateVn('hôm nay')).toBe('hôm nay')
    expect(dateVn(undefined)).toBe('—')
    expect(show('')).toBe('—')
    expect(show(0)).toBe('0')
  })
})
