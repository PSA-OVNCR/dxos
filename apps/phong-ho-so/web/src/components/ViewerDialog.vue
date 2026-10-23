<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Xem từng trang của một tệp đính kèm bằng Viewer (Plan 04 Task 8, S2). Mỗi trang là một ảnh PNG có watermark do Viewer dựng
// trong RAM; ở đây lấy bằng bearer token của người dùng (qua SDK, không tự thử lại), hiện qua blob: URL và thu hồi URL
// ngay khi đổi trang, đóng hộp thoại hoặc gỡ thành phần: mỗi lúc chỉ giữ ảnh của đúng một trang.
// Không chèn HTML thô, không style nội tuyến (CSP của /apps/* chỉ thêm `blob:` cho img-src). Mọi lỗi hiện bằng ProblemMessage;
// bấm "Trang trước/sau" là cách thử lại duy nhất. Watermark chỉ để răn đe, câu chữ bên dưới nói rõ điều đó.
import type { ObjectVariant } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { useSession } from '../session'

const props = defineProps<{ sha256: string; variant: ObjectVariant; label: string }>()
const emit = defineEmits<{ close: [] }>()

const { client } = useSession()

const titleId = useId()
const closeButton = ref<HTMLButtonElement | null>(null)
const pages = ref<number | null>(null)
const page = ref(1)
const url = ref<string | null>(null)
const loading = ref(true)
const error = ref<unknown>(null)

// Mỗi lần đổi trang tăng số này; phản hồi của lần cũ (hoặc đến sau khi đã đóng) bị bỏ, không tạo blob: URL.
let run = 0
let alive = true

/** Thu hồi blob: URL đang giữ (nếu có) và bỏ ảnh. Gọi nhiều lần vẫn chỉ thu hồi một lần. */
function release(): void {
  if (url.value !== null) URL.revokeObjectURL(url.value)
  url.value = null
}

async function show(n: number): Promise<void> {
  const mine = ++run
  page.value = n
  error.value = null
  loading.value = true
  release()
  try {
    const blob = await client.viewPage(props.sha256, n, props.variant)
    if (mine !== run || !alive) return
    url.value = URL.createObjectURL(blob)
  } catch (e) {
    if (mine === run && alive) error.value = e
  } finally {
    if (mine === run) loading.value = false
  }
}

async function init(): Promise<void> {
  const mine = ++run
  try {
    const { pages: n } = await client.viewInfo(props.sha256, props.variant)
    if (mine !== run || !alive) return
    if (!Number.isInteger(n) || n < 1) throw new Error('viewInfo: số trang không hợp lệ')
    pages.value = n
  } catch (e) {
    if (mine === run && alive) {
      error.value = e
      loading.value = false
    }
    return
  }
  await show(1)
}

function close(): void {
  alive = false
  run += 1
  release()
  emit('close')
}

onMounted(() => {
  closeButton.value?.focus()
  void init()
})
onBeforeUnmount(() => {
  alive = false
  run += 1
  release()
})
</script>

<template>
  <div class="dx-dialog dx-viewer" role="dialog" aria-modal="true" :aria-labelledby="titleId" @keydown.esc="close">
    <h3 :id="titleId">Xem {{ label }}</h3>
    <ProblemMessage :error="error" />
    <p v-if="loading" role="status">Đang tải trang…</p>
    <img v-if="url" class="dx-viewer-page" :src="url" :alt="`Trang ${page} của ${label}`">
    <div class="dx-viewer-nav">
      <button type="button" class="dx-secondary" :disabled="loading || pages === null || page <= 1" @click="show(page - 1)">Trang trước</button>
      <span v-if="pages !== null">Trang {{ page }} / {{ pages }}</span>
      <button type="button" class="dx-secondary" :disabled="loading || pages === null || page >= pages" @click="show(page + 1)">Trang sau</button>
      <button ref="closeButton" type="button" @click="close">Đóng</button>
    </div>
    <p class="dx-meta">
      Mỗi trang có dấu mờ ghi người xem và giờ xem. Dấu này chỉ để răn đe, không ngăn được việc chụp màn hình.
    </p>
  </div>
</template>
