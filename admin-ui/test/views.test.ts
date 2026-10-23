// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { flushPromises, type DOMWrapper } from '@vue/test-utils'
import { ApiError } from 'dxos-sdk-js'
import { describe, expect, test } from 'vitest'
import HealthView from '../src/views/HealthView.vue'
import LedgerView from '../src/views/LedgerView.vue'
import { click, fakeApi, HEALTH_OK, mountView, STATUS_OK } from './helpers'

// Đúng như AdminApi dựng cho mọi 403 (test/api.test.ts kiểm phần đó).
const NOT_ADMIN = new ApiError(403, 'not-admin', 'Tài khoản này không có quyền quản trị', undefined, null)

describe('HealthView', () => {
  test('HealthView shows each dependency with status text, not colour only', async () => {
    const api = fakeApi({
      health: async () => ({ ...HEALTH_OK, clamav: 'down: timeout', seal_key: 'expired', org: 'down: not configured' }),
    })
    const w = await mountView(HealthView, api)
    const rows: Record<string, DOMWrapper<Element>> = Object.fromEntries(
      w.findAll('[data-dep]').map((r) => [r.attributes('data-dep') ?? '', r]))
    expect(Object.keys(rows)).toEqual(['db', 'clamav', 'openbao', 'flowable', 'keycloak', 'seal_key', 'org'])
    // Mỗi thành phần có CHỮ trạng thái; màu (class) chỉ là phần thêm.
    expect(rows.db?.find('.dx-state').text()).toContain('Hoạt động')
    expect(rows.db?.find('.dx-state').classes()).toContain('dx-state-ok')
    expect(rows.clamav?.find('.dx-state').text()).toContain('Lỗi')
    expect(rows.clamav?.find('.dx-state').text()).toContain('timeout')
    expect(rows.clamav?.find('.dx-state').classes()).toContain('dx-state-bad')
    expect(rows.seal_key?.find('.dx-state').text()).toContain('Đã hết hạn')
    expect(rows.org?.find('.dx-state').text()).toContain('not configured')
    for (const r of Object.values(rows)) expect(r.find('.dx-state').text().trim().length).toBeGreaterThan(3)
    expect(api.health).toHaveBeenCalledTimes(1)
  })

  test('shows counters, the last anchor age and reloads on demand', async () => {
    const api = fakeApi({
      health: async () => ({ ...HEALTH_OK, seal_pending: 3, task_intents_stuck: 2, anchor: { last_tree_size: 12, last_anchor_age_s: 7200 } }),
    })
    const w = await mountView(HealthView, api)
    expect(w.text()).toContain('Hồ sơ chờ niêm phong')
    expect(w.find('[data-counter="seal_pending"]').text()).toContain('3')
    expect(w.find('[data-counter="task_intents_stuck"]').text()).toContain('2')
    expect(w.find('[data-counter="task_intents_stuck"] .dx-state').classes()).toContain('dx-state-warn')
    expect(w.find('[data-counter="anchor"]').text()).toContain('12')
    expect(w.find('[data-counter="anchor"]').text()).toContain('2 giờ')
    await click(w, 'Tải lại')
    expect(api.health).toHaveBeenCalledTimes(2)
  })

  test('seal_key values other than ok are spelled out in Vietnamese', async () => {
    const texts: Record<string, string> = {
      none: 'Chưa có', invalid: 'Không hợp lệ', unknown: 'Chưa rõ', 'down: db unavailable': 'Lỗi',
    }
    for (const [value, expected] of Object.entries(texts)) {
      const w = await mountView(HealthView, fakeApi({ health: async () => ({ ...HEALTH_OK, seal_key: value }) }))
      expect(w.find('[data-dep="seal_key"] .dx-state').text()).toContain(expected)
    }
  })

  test('403 from admin API shows "Tài khoản này không có quyền quản trị" via ProblemMessage', async () => {
    const w = await mountView(HealthView, fakeApi({ health: async () => { throw NOT_ADMIN } }))
    expect(w.find('.dx-problem').text()).toBe('Tài khoản này không có quyền quản trị')
    expect(w.find('[data-dep]').exists()).toBe(false)
  })

  test('another error is shown through ProblemMessage with a retry button', async () => {
    let n = 0
    const w = await mountView(HealthView, fakeApi({
      health: async () => { if (n++ === 0) throw new ApiError(502, 'http-502', 'Bad Gateway', undefined, null); return HEALTH_OK },
    }))
    expect(w.find('.dx-problem').text()).toContain('Dịch vụ tạm thời không sẵn sàng')
    await click(w, 'Tải lại')
    expect(w.find('.dx-problem').exists()).toBe(false)
    expect(w.findAll('[data-dep]')).toHaveLength(7)
  })
})

describe('LedgerView', () => {
  test("LedgerView shows tree size, last STH time in Asia/Ho_Chi_Minh, last anchor commit; 'Neo ngay' posts anchor:run once and disables while pending", async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    const api = fakeApi({
      anchorRun: async () => { await gate; return { ...STATUS_OK.latest_sth!, anchor_job_id: 'job-9' } },
    })
    const w = await mountView(LedgerView, api)
    expect(w.find('[data-field="tree_size"]').text()).toContain('42')
    // 10:00 UTC = 17:00 giờ Việt Nam (UTC+7)
    const sth = w.find('[data-field="sth_time"]').text()
    expect(sth).toContain('17:00')
    expect(sth).toContain('22/10/2026')
    expect(w.find('[data-field="sth_time"]').text()).not.toContain('10:00')
    const anchor = w.find('[data-field="anchor"]').text()
    expect(anchor).toContain('0123456789ab')
    expect(anchor).toContain('PSA-OVNCR/dxos-anchors')
    expect(anchor).toContain('10:30') // 03:30 UTC -> 10:30 giờ Việt Nam
    expect(w.find('[data-field="verify"]').text()).toContain('toàn vẹn')

    const btn = () => w.findAll('button').find((b) => b.text().trim() === 'Neo ngay')!
    expect(btn().attributes('disabled')).toBeUndefined()
    await btn().trigger('click')
    await btn().trigger('click') // bấm lần hai trong lúc chờ: không gửi thêm
    expect(btn().attributes('disabled')).toBeDefined()
    expect(api.anchorRun).toHaveBeenCalledTimes(1)

    release()
    await flushPromises()
    expect(api.anchorRun).toHaveBeenCalledTimes(1)
    expect(btn().attributes('disabled')).toBeUndefined()
    expect(w.find('[role="status"]').text()).toContain('42')
    expect(api.ledgerStatus).toHaveBeenCalledTimes(2) // làm mới trạng thái sau khi neo
  })

  test('Neo ngay is disabled while anchor jobs are already queued', async () => {
    const w = await mountView(LedgerView, fakeApi({ ledgerStatus: async () => ({ ...STATUS_OK, pending_anchor_jobs: 2 }) }))
    expect(w.findAll('button').find((b) => b.text().trim() === 'Neo ngay')!.attributes('disabled')).toBeDefined()
    expect(w.find('[data-field="pending"]').text()).toContain('2')
  })

  test('a failed ledger verification is spelled out, not colour only', async () => {
    const w = await mountView(LedgerView, fakeApi({
      ledgerStatus: async () => ({ ...STATUS_OK, verify: { ok: false, first_bad_idx: 17 } }),
    }))
    const v = w.find('[data-field="verify"]')
    expect(v.text()).toContain('Phát hiện lệch')
    expect(v.text()).toContain('17')
    expect(v.find('.dx-state').classes()).toContain('dx-state-bad')
  })

  test('no STH and no anchor yet: says so', async () => {
    const w = await mountView(LedgerView, fakeApi({
      ledgerStatus: async () => ({ ...STATUS_OK, tree_size: 0, latest_sth: null, last_anchor: null }),
    }))
    expect(w.find('[data-field="sth_time"]').text()).toContain('Chưa có')
    expect(w.find('[data-field="anchor"]').text()).toContain('Chưa có')
  })

  test('entries table shows Vietnam time, and the type filter reloads with that type', async () => {
    const api = fakeApi()
    const w = await mountView(LedgerView, api)
    expect(api.ledgerEntries).toHaveBeenLastCalledWith({ type: undefined, limit: 20 })
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.text()).toContain('record.created')
    expect(rows[0]?.text()).toContain('16:59') // 09:59 UTC
    expect(rows[1]?.text()).toContain('sth.published')
    await w.find('select[name="type"]').setValue('sth.published')
    await flushPromises()
    expect(api.ledgerEntries).toHaveBeenLastCalledWith({ type: 'sth.published', limit: 20 })
  })

  test('403 from admin API shows "Tài khoản này không có quyền quản trị"', async () => {
    const w = await mountView(LedgerView, fakeApi({
      ledgerStatus: async () => { throw NOT_ADMIN },
      ledgerEntries: async () => { throw NOT_ADMIN },
    }))
    expect(w.find('.dx-problem').text()).toBe('Tài khoản này không có quyền quản trị')
    expect(w.findAll('button').find((b) => b.text().trim() === 'Neo ngay')).toBeUndefined()
  })

  test('an anchor error is shown through ProblemMessage and the button works again', async () => {
    const api = fakeApi({
      anchorRun: async () => { throw new ApiError(503, 'kms-unavailable', 'Key service unavailable', undefined, null) },
    })
    const w = await mountView(LedgerView, api)
    await click(w, 'Neo ngay')
    expect(w.find('.dx-problem').text()).toContain('Dịch vụ ký tạm thời không sẵn sàng')
    expect(w.findAll('button').find((b) => b.text().trim() === 'Neo ngay')!.attributes('disabled')).toBeUndefined()
  })
})
