// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Thăm dò định kỳ khi `active()` là true (ví dụ còn tệp đang được dò PII), cùng cách chịu lỗi tạm như QuarantineStatus.
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { ApiError } from '../errors'

/** Lỗi tạm thời đáng thử lại: hết giờ yêu cầu, quá tải hoặc máy chủ/cổng hỏng. */
export function isTransientStatus(status: number): boolean {
  return status === 408 || status === 429 || status >= 500
}

export interface PollOptions {
  /** Còn việc phải chờ không; false thì dừng, true (lại) thì bắt đầu một lượt mới. */
  active: () => boolean
  /** Một lần hỏi (GET, thử lại an toàn). Ném `ApiError` 4xx = dứt khoát, dừng; lỗi khác là tạm thời. */
  tick: () => Promise<void>
  intervalMs?: number
  /** Quá hạn này mà vẫn `active()` thì ngừng hỏi và báo `timedOut`. */
  timeoutMs?: number
}

export function usePoll(o: PollOptions) {
  const intervalMs = o.intervalMs ?? 3000
  const timeoutMs = o.timeoutMs ?? 300_000
  const failure = shallowRef<ApiError | null>(null)
  const timedOut = ref(false)
  let gen = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let deadline: ReturnType<typeof setTimeout> | undefined

  function stop(): void {
    gen += 1
    clearTimeout(timer)
    clearTimeout(deadline)
  }

  function begin(): void {
    stop()
    const mine = gen
    failure.value = null
    timedOut.value = false
    deadline = setTimeout(() => {
      if (mine !== gen) return
      timedOut.value = true
      stop()
    }, timeoutMs)
    const next = (): void => {
      timer = setTimeout(async () => {
        try {
          await o.tick()
        } catch (e) {
          if (mine !== gen) return
          if (e instanceof ApiError && !isTransientStatus(e.status)) {
            failure.value = e // 4xx dứt khoát: thử lại cũng không khác
            stop()
            return
          }
          // lỗi mạng, 408, 429 hoặc 5xx: tạm thời, hỏi tiếp cho tới hạn
        }
        if (mine !== gen) return
        next()
      }, intervalMs)
    }
    next()
  }

  watch(o.active, (a) => { if (a) begin(); else stop() }, { immediate: true })
  onBeforeUnmount(stop)

  /** Xóa `failure`/`timedOut` và hỏi lại từ đầu nếu vẫn còn việc phải chờ (nút "Tải lại"). */
  function restart(): void {
    stop()
    failure.value = null
    timedOut.value = false
    if (o.active()) begin()
  }

  return { failure, timedOut, restart }
}
