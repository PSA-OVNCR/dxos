<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script lang="ts">
import type { DxRecord, SealInfo } from 'dxos-sdk-js'
import { formatVnDate, statusLabel, yearVn } from '../status'

export interface RegisterRow {
  so_hieu: string
  /** Năm ban hành theo giờ Việt Nam; null khi không đọc được thông tin niêm phong của văn bản. */
  nam: number | null
  ngay_ban_hanh: string
  loai: string
  trich_yeu: string
  chuc_vu: string
  noi_nhan: string
  trang_thai: string
}

function field(r: DxRecord, name: string): string {
  const v = r.data[name]
  return v === undefined || v === null || v === '' ? '—' : String(v)
}

/** Phần số của số hiệu ("02/QĐ-SM" -> 2); không đọc được thì đứng cuối. */
function ordinal(soHieu: string): number {
  const n = Number.parseInt(soHieu.split('/')[0] ?? '', 10)
  return Number.isNaN(n) ? Number.POSITIVE_INFINITY : n
}

/**
 * Các dòng của sổ đăng ký văn bản đi: chỉ bản ghi SEALED hoặc REVOKED, năm giảm dần rồi số tăng dần.
 * Số do lõi cấp và đặt lại hằng năm (manifest `reset: yearly`), nên so sánh theo (năm, số) chứ không theo chuỗi.
 */
export function registerRows(records: DxRecord[], seals: Map<string, SealInfo>): RegisterRow[] {
  return records
    .filter((r) => r.seal_state === 'SEALED' || r.seal_state === 'REVOKED')
    .map((r): RegisterRow => {
      const issued = seals.get(r.id)?.issued_at ?? null
      return {
        so_hieu: field(r, 'so_hieu'),
        nam: yearVn(issued),
        ngay_ban_hanh: formatVnDate(issued) ?? '—',
        loai: field(r, 'loai_van_ban'),
        trich_yeu: field(r, 'trich_yeu'),
        chuc_vu: field(r, 'chuc_vu_nguoi_ky'),
        noi_nhan: field(r, 'noi_nhan'),
        trang_thai: statusLabel(r),
      }
    })
    .sort((a, b) => {
      if (a.nam !== b.nam) return a.nam === null ? 1 : b.nam === null ? -1 : b.nam - a.nam
      const d = ordinal(a.so_hieu) - ordinal(b.so_hieu)
      return d !== 0 && !Number.isNaN(d) ? d : a.so_hieu.localeCompare(b.so_hieu, 'vi')
    })
}
</script>

<script setup lang="ts">
// Sổ đăng ký văn bản đi: dựng từ danh sách bản ghi và thông tin niêm phong của từng bản ghi đã ban hành/thu hồi.
// Chỉ hiển thị (ngày ban hành lấy từ lõi); in bằng hộp thoại in của trình duyệt, CSS @media print ẩn thanh điều hướng.
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { APP, COL, useSession } from '../session'

const { client, view } = useSession()

const records = ref<DxRecord[]>([])
const seals = ref(new Map<string, SealInfo>())
const failed = ref(0)
const loading = ref(true)
const error = ref<unknown>(null)
const year = ref('')
const yearId = useId()

let run = 0
let alive = true
onBeforeUnmount(() => { alive = false })

const label = (name: string): string => view.value?.collections[COL]?.fields[name]?.label ?? name
const rows = computed(() => registerRows(records.value, seals.value))
const years = computed(() => [...new Set(rows.value.map((r) => r.nam).filter((n): n is number => n !== null))].sort((a, b) => b - a))
const shown = computed(() => (year.value === '' ? rows.value : rows.value.filter((r) => String(r.nam) === year.value)))

/** Gọi `fn` cho từng phần tử với tối đa `limit` lời gọi song song (tránh dồn hàng trăm yêu cầu vào cổng). */
async function pool<T>(items: T[], limit: number, fn: (x: T) => Promise<void>): Promise<void> {
  let next = 0
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    for (let i = next++; i < items.length; i = next++) await fn(items[i] as T)
  }))
}

async function load(): Promise<void> {
  const mine = ++run
  loading.value = true
  error.value = null
  failed.value = 0
  try {
    const all = await client.listAll(APP, COL)
    const issued = all.filter((r) => r.seal_state === 'SEALED' || r.seal_state === 'REVOKED')
    const got = new Map<string, SealInfo>()
    let bad = 0
    await pool(issued, 6, async (r) => {
      try {
        got.set(r.id, await client.seal(APP, COL, r.id))
      } catch {
        bad += 1
      }
    })
    if (mine !== run || !alive) return
    records.value = all
    seals.value = got
    failed.value = bad
  } catch (e) {
    if (mine !== run || !alive) return
    records.value = []
    error.value = e
  } finally {
    if (mine === run && alive) loading.value = false
  }
}

function print(): void {
  window.print()
}

onMounted(load)
</script>

<template>
  <div class="dx-toolbar">
    <h1>Sổ đăng ký văn bản đi</h1>
    <button type="button" class="dx-no-print" @click="print">In</button>
  </div>
  <p class="dx-meta">Ứng dụng vận dụng Nghị định 30/2020; Công ty TNHH Sao Mai không thuộc diện áp dụng</p>

  <ProblemMessage :error="error" />
  <p v-if="failed > 0" class="dx-problem" role="alert">
    Không đọc được thông tin niêm phong của {{ failed }} văn bản nên ngày ban hành bị thiếu; hãy tải lại trang.
  </p>
  <p v-if="loading" role="status">Đang tải…</p>
  <template v-else-if="!error">
    <p v-if="rows.length === 0">Chưa có văn bản nào được ban hành.</p>
    <template v-else>
      <div class="dx-field dx-no-print dx-register-filter">
        <label :for="yearId">Năm</label>
        <select :id="yearId" v-model="year" name="nam">
          <option value="">Tất cả các năm</option>
          <option v-for="y in years" :key="y" :value="String(y)">{{ y }}</option>
        </select>
      </div>
      <table class="dx-table dx-register">
        <thead>
          <tr>
            <th scope="col">{{ label('so_hieu') }}</th>
            <th scope="col">Ngày ban hành</th>
            <th scope="col">{{ label('loai_van_ban') }}</th>
            <th scope="col">{{ label('trich_yeu') }}</th>
            <th scope="col">{{ label('chuc_vu_nguoi_ky') }}</th>
            <th scope="col">{{ label('noi_nhan') }}</th>
            <th scope="col">Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in shown" :key="i">
            <td>{{ r.so_hieu }}</td>
            <td>{{ r.ngay_ban_hanh }}</td>
            <td>{{ r.loai }}</td>
            <td>{{ r.trich_yeu }}</td>
            <td>{{ r.chuc_vu }}</td>
            <td>{{ r.noi_nhan }}</td>
            <td>{{ r.trang_thai }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </template>
</template>
