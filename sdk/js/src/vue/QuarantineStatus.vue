<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { DxosClient } from '../client'
import { ApiError } from '../errors'
import type { UploadStatus } from '../types'
import ProblemMessage from './ProblemMessage.vue'

const props = withDefaults(
  defineProps<{
    client: DxosClient
    uploadId: string
    intervalMs?: number
    timeoutMs?: number
    /** Trạng thái đã biết từ danh sách tệp của máy chủ: đã xong thì hiện luôn, không thăm dò; STAGING thì vẫn thăm dò. */
    initial?: UploadStatus
  }>(),
  { intervalMs: 2000, timeoutMs: 180000 },
)
const emit = defineEmits<{ settled: [status: UploadStatus] }>()

const REASONS: Record<string, string> = {
  EMPTY: 'tệp rỗng',
  TOO_LARGE: 'tệp quá lớn',
  BAD_MAGIC: 'không phải PDF',
  ENCRYPTED: 'PDF có mật khẩu',
  PARSE_ERROR: 'PDF hỏng',
  NO_TEXT_LAYER: 'PDF không có lớp chữ (bản scan)',
}

const status = ref<UploadStatus>({ status: 'STAGING' })
const timedOut = ref(false)
const failure = ref<ApiError | null>(null)

/** Lỗi tạm thời đáng thử lại: hết giờ yêu cầu, quá tải hoặc máy chủ/cổng hỏng. */
function isTransient(status: number): boolean {
  return status === 408 || status === 429 || status >= 500
}

let run = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
let deadline: ReturnType<typeof setTimeout> | undefined

function stop(): void {
  run += 1
  clearTimeout(pollTimer)
  clearTimeout(deadline)
}

function start(): void {
  stop()
  const mine = run
  timedOut.value = false
  failure.value = null
  if (props.initial && props.initial.status !== 'STAGING') {
    status.value = props.initial // máy chủ đã chốt, không cần hỏi lại
    return
  }
  status.value = { status: 'STAGING' }
  deadline = setTimeout(() => {
    if (mine !== run) return
    timedOut.value = true
    stop()
  }, props.timeoutMs)

  const poll = async (): Promise<void> => {
    try {
      const s = await props.client.uploadStatus(props.uploadId)
      if (mine !== run) return
      status.value = s
      if (s.status !== 'STAGING') {
        stop()
        emit('settled', s)
        return
      }
    } catch (e) {
      if (mine !== run) return
      if (e instanceof ApiError && !isTransient(e.status)) {
        failure.value = e // lỗi 4xx dứt khoát (404, 403...) thì thử lại cũng không khác
        stop()
        return
      }
      // lỗi mạng, 408, 429 hoặc 5xx là tạm thời: thử lại cho tới khi hết hạn (đây là GET, thử lại an toàn)
    }
    pollTimer = setTimeout(() => { void poll() }, props.intervalMs)
  }
  void poll()
}

watch(() => [props.uploadId, props.client] as const, start, { immediate: true })
onBeforeUnmount(stop)

const label = computed(() => {
  if (timedOut.value) return 'Kiểm dịch lâu bất thường — máy quét có thể đang dừng'
  const s = status.value
  switch (s.status) {
    case 'CLEAN': return 'Sạch'
    case 'INFECTED': return 'Nhiễm mã độc — đã cách ly'
    case 'REJECTED': return `Bị từ chối: ${REASONS[s.reason] ?? s.reason}`
    default: return 'Đang kiểm dịch…'
  }
})
</script>

<template>
  <ProblemMessage v-if="failure" :error="failure" />
  <p v-else class="dx-quarantine" role="status" :data-status="timedOut ? 'TIMEOUT' : status.status">{{ label }}</p>
</template>
