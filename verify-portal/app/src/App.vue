<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
// Cổng đối soát công khai (spec 8.4, 13.3, 25.1, 25.4; R-2, AT-25).
// - Mã niêm phong chỉ từ fragment (#<seal_id>), khớp ^[A-Z2-7]{26}$ trước khi gọi API.
// - Tệp người dùng được băm bằng WebCrypto TẠI TRÌNH DUYỆT; chỉ {"sha256": hex} (JSON) được gửi đi.
// - Gói bằng chứng được trình duyệt TỰ KIỂM (chữ ký, sổ cái, STH, repo neo). Kết quả tự kiểm thắng `status` của máy chủ.
// - Repo neo chỉ lấy từ cấu hình build (VITE_ANCHOR_RAW_BASE), không bao giờ từ chuỗi `repo` máy chủ trả.
import { DxosClient, parseJsonLossless, rawAnchor, sha256Hex, type AnchorSource, type Json } from 'dxos-sdk-js'
import { ProblemMessage } from 'dxos-sdk-js/vue'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  field, finalVerdict, formatVn, isObj, publicRows, SEAL_ID, serverSays, valueText, viewState,
  type PortalState, type Tone,
} from './state'
import { explainFailure, verifyInBrowser, type LocalCheck } from './verify'

const client = new DxosClient({ getToken: async () => null })
const ANCHOR_BASE = String(import.meta.env.VITE_ANCHOR_RAW_BASE ?? '').trim()
const anchor: AnchorSource | undefined = ANCHOR_BASE === '' ? undefined : rawAnchor(ANCHOR_BASE)

const WITH_DATA: ReadonlySet<PortalState> = new Set(['VALID_ANCHORED', 'VALID_UNANCHORED', 'WAIT_STH', 'REVOKED'])
const HAS_BUNDLE: ReadonlySet<PortalState> = new Set(['VALID_ANCHORED', 'VALID_UNANCHORED', 'REVOKED'])

const sealInput = ref('')
const inputError = ref('')
const sealId = ref<string | null>(null)
const loading = ref(false)
const view = shallowRef<Json | null>(null)
const state = ref<PortalState | null>(null)

const verifying = ref(false)
const local = shallowRef<LocalCheck | null>(null)
const bundleText = ref<string | null>(null)
const bundleError = ref<unknown>(null)

const fileHash = ref('')
const fileMsg = ref<{ text: string; tone: Tone } | null>(null)
const fileError = ref<unknown>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// Mỗi lần tải lại hoặc chọn tệp mới tăng token; phản hồi của lần cũ bị bỏ.
let run = 0

const requireFile = computed(() => field(view.value, 'require_file') === true)

function reset(): void {
  inputError.value = ''
  sealId.value = null
  loading.value = false
  view.value = null
  state.value = null
  resetFile()
}

function resetFile(clearInput = true): void {
  verifying.value = false
  local.value = null
  bundleText.value = null
  bundleError.value = null
  fileHash.value = ''
  fileMsg.value = null
  fileError.value = null
  if (clearInput && fileInput.value) fileInput.value.value = ''
}

async function load(): Promise<void> {
  const mine = ++run
  reset()
  const raw = location.hash.replace(/^#/, '').trim().toUpperCase()
  sealInput.value = raw
  if (raw === '') return
  if (!SEAL_ID.test(raw)) {
    inputError.value = 'Mã niêm phong không đúng dạng (26 ký tự gồm chữ A–Z và số 2–7).'
    return
  }
  sealId.value = raw
  loading.value = true
  let status = 0
  let parsed: Json | null = null
  try {
    const r = await client.publicSeal(raw)
    status = r.status
    if (status === 200) {
      try {
        parsed = parseJsonLossless(r.text)
      } catch {
        parsed = null
      }
    }
  } catch {
    status = 0
  }
  if (mine !== run) return
  loading.value = false
  view.value = parsed
  state.value = viewState(status, parsed)
  // Niêm phong không bắt buộc tệp: lấy gói ngay. Bắt buộc tệp: chờ người dùng chọn tệp.
  if (HAS_BUNDLE.has(state.value) && !requireFile.value) await fetchAndVerify(mine, raw, undefined)
}

async function fetchAndVerify(mine: number, id: string, sha: string | undefined): Promise<void> {
  verifying.value = true
  try {
    const text = await client.bundle(id, sha)
    if (mine !== run) return
    bundleText.value = text
    // `text` đưa thẳng cho bộ kiểm, không qua JSON.parse.
    const check = await verifyInBrowser(text, { anchor, fileSha256: sha, sealId: id })
    if (mine !== run) return
    local.value = check
  } catch (err) {
    if (mine !== run) return
    bundleError.value = err
  } finally {
    if (mine === run) verifying.value = false
  }
}

async function onFile(ev: Event): Promise<void> {
  const mine = ++run
  const id = sealId.value
  const picked = (ev.target as HTMLInputElement).files?.[0] // đọc TRƯỚC khi dọn trạng thái
  resetFile(false)
  if (!picked || id === null) return
  fileMsg.value = { text: 'Đang tính mã băm…', tone: 'warn' }
  let hex: string
  try {
    hex = await sha256Hex(picked)
  } catch {
    if (mine !== run) return
    fileMsg.value = { text: 'Không đọc được tệp này để tính mã băm.', tone: 'bad' }
    return
  }
  if (mine !== run) return
  fileHash.value = hex
  try {
    const r = await client.checkHash(id, hex)
    if (mine !== run) return
    if ('status' in r) {
      fileMsg.value = { text: 'Niêm phong đang chờ hoàn tất: chưa đối chiếu được, thử lại sau.', tone: 'warn' }
    } else if (r.match === true) {
      fileMsg.value = { text: 'Khớp: tệp này đúng là tệp đã được niêm phong.', tone: 'ok' }
      if (state.value !== null && HAS_BUNDLE.has(state.value)) await fetchAndVerify(mine, id, hex)
    } else {
      fileMsg.value = { text: 'Không khớp: tệp này khác tệp đã được niêm phong (đã bị sửa hoặc là tệp khác).', tone: 'bad' }
    }
  } catch (err) {
    if (mine !== run) return
    fileMsg.value = null
    fileError.value = err
  }
}

// ---------------------------------------------------------------- hiển thị
const verdict = computed(() => {
  if (state.value === null) return null
  if (verifying.value && local.value === null) {
    return { label: 'Đang tự kiểm trên trình duyệt…', tone: 'wait' as Tone, note: '' }
  }
  const v = finalVerdict(state.value, local.value?.result ?? null)
  if (local.value === null && requireFile.value && HAS_BUNDLE.has(state.value) && state.value !== 'REVOKED') {
    return { ...v, note: 'Chọn đúng tệp ở mục "Đối chiếu tệp": gói bằng chứng chỉ được cấp cho tệp khớp với niêm phong.' }
  }
  return v
})

const localInvalid = computed(() => local.value !== null && !local.value.result.ok && local.value.result.code !== 'UNSUPPORTED_CRYPTO')
const showDetails = computed(() => state.value !== null && WITH_DATA.has(state.value) && !localInvalid.value)
// WAIT_STH: vẫn cho chọn tệp để chạy `:check` (như trang tối giản), nhưng chưa có gói nên không có kết quả tự kiểm.
const showFileCheck = computed(() => showDetails.value && requireFile.value
  && (HAS_BUNDLE.has(state.value as PortalState) || state.value === 'WAIT_STH'))

/** Payload đã ký (chỉ khi tự kiểm đạt): nguồn đáng tin cho giá trị hiển thị. */
const signed = computed(() => (local.value?.result.ok ? local.value.result.payload : null))
const rows = computed(() => publicRows(
  signed.value !== null ? field(signed.value, 'public_fields') : field(view.value, 'public_fields'),
  field(view.value, 'public_labels'), // nhãn (tiếng Việt) từ manifest; chỉ là chữ hiển thị
))
const issuedAt = computed(() => formatVn(valueText(signed.value !== null ? field(signed.value, 'issued_at') : field(view.value, 'issued_at'))))
const attachments = computed(() => {
  const list = signed.value !== null ? field(signed.value, 'attachments') : undefined
  return Array.isArray(list) ? String(list.length) : valueText(field(view.value, 'attachments_count'))
})
const issuer = computed(() => {
  const i = local.value?.result.ok ? local.value.result.issuer : field(view.value, 'issuer')
  const name = isObj(i) ? i.name : null
  if (typeof name !== 'string' || name === '') return '(không xác định)'
  const id = isObj(i) ? i.id : null
  return id === null || id === undefined || id === '' ? name : `${name} (mã định danh: ${valueText(id)})`
})
const ledger = computed(() => {
  const inc = field(view.value, 'inclusion')
  if (!isObj(inc) || inc.tree_size === null || inc.tree_size === undefined) return 'chưa có STH phủ niêm phong này'
  return `vị trí ${valueText(inc.leaf_index)} của cây có ${valueText(inc.tree_size)} mục`
})

const localText = computed(() => {
  const l = local.value
  if (verifying.value && l === null) return 'đang kiểm…'
  if (l === null) {
    if (bundleError.value !== null) return 'không lấy được gói bằng chứng'
    return requireFile.value ? 'chờ bạn chọn tệp để lấy gói bằng chứng' : 'chưa có gói bằng chứng'
  }
  if (l.result.ok) return `đạt, ${l.result.pinned ? 'đã đối chiếu repo neo' : 'chưa đối chiếu repo neo'}`
  if (l.result.code === 'UNSUPPORTED_CRYPTO') return 'trình duyệt này không có Ed25519, không tự kiểm được chữ ký'
  return 'không đạt'
})

function download(): void {
  if (bundleText.value === null || sealId.value === null) return
  // Blob dựng từ VĂN BẢN máy chủ trả, không bao giờ từ tệp người dùng.
  const href = URL.createObjectURL(new Blob([bundleText.value], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = href
  link.download = `dxos-seal-${sealId.value}.json`
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(href), 10000)
}

function go(): void {
  const wanted = sealInput.value.trim().toUpperCase()
  const next = wanted === '' ? '' : `#${wanted}`
  if (location.hash === next || (location.hash === '' && next === '')) void load()
  else location.hash = next // kích hoạt hashchange → load()
}

onMounted(() => {
  window.addEventListener('hashchange', load)
  void load()
})
onBeforeUnmount(() => window.removeEventListener('hashchange', load))
</script>

<template>
  <main>
    <header>
      <h1>Kiểm tra tính xác thực và toàn vẹn văn bản điện tử</h1>
      <p class="lede">Gợi ý cho văn thư khi tiếp nhận văn bản điện tử đến (việc kiểm tra tính xác thực và toàn vẹn nêu ở Điều 21 khoản 2 điểm a Nghị định 30/2020/NĐ-CP): nhập mã niêm phong ghi trên văn bản hoặc quét mã QR, rồi chọn đúng tệp đã nhận để đối chiếu.</p>
    </header>

    <section class="card" aria-labelledby="lookup-title">
      <h2 id="lookup-title">Mã niêm phong</h2>
      <label for="seal-input">Nhập mã niêm phong (26 ký tự)</label>
      <div class="row">
        <input id="seal-input" v-model="sealInput" type="text" inputmode="text" autocomplete="off"
               autocapitalize="characters" spellcheck="false" maxlength="40"
               placeholder="ví dụ: ABCDEFGHIJKLMNOPQRSTUVWXYZ" @keydown.enter="go">
        <button type="button" @click="go">Kiểm tra</button>
      </div>
      <p v-if="inputError" class="msg bad" role="alert">{{ inputError }}</p>
    </section>

    <section v-if="loading || verdict" class="card" aria-live="polite" aria-labelledby="result-title">
      <h2 id="result-title">Kết quả</h2>
      <p v-if="loading" class="msg">Đang kiểm tra…</p>
      <template v-if="verdict">
        <p class="badge" :class="verdict.tone" data-testid="verdict">{{ verdict.label }}</p>
        <p v-if="verdict.note" class="msg">{{ verdict.note }}</p>
        <p v-if="local && local.anchorNote" class="msg warn">{{ local.anchorNote }}</p>

        <div v-if="state !== 'NOT_FOUND'" class="parallel">
          <section aria-labelledby="server-title">
            <h3 id="server-title">Máy chủ báo</h3>
            <p class="msg">{{ serverSays(state as PortalState) }}</p>
            <p v-if="showDetails" class="msg">Sổ cái: {{ ledger }}.</p>
          </section>
          <section aria-labelledby="local-title">
            <h3 id="local-title">Trình duyệt tự kiểm</h3>
            <p class="msg">{{ localText }}</p>
            <p v-if="local && !local.result.ok" class="msg bad" :title="local.result.message">
              <span class="mono">{{ local.result.code }}</span>: {{ explainFailure(local.result) }}
            </p>
            <p v-if="ANCHOR_BASE" class="msg mono">Repo neo dùng để đối chiếu: {{ ANCHOR_BASE }}</p>
          </section>
        </div>

        <template v-if="showDetails">
          <p class="issuer">Đơn vị niêm phong: {{ issuer }}</p>
          <p class="msg">{{ signed !== null ? 'Nội dung dưới đây lấy từ gói đã ký mà trình duyệt vừa kiểm.' : 'Nội dung dưới đây do máy chủ báo, trình duyệt chưa tự kiểm.' }}</p>
          <dl>
            <template v-for="row in rows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </template>
            <dt>Thời điểm niêm phong</dt>
            <dd>{{ issuedAt }}</dd>
            <dt>Mã niêm phong</dt>
            <dd class="mono">{{ sealId }}</dd>
            <dt>Số tệp đính kèm</dt>
            <dd>{{ attachments }}</dd>
          </dl>
        </template>
      </template>
    </section>

    <section v-if="showFileCheck" class="card" aria-labelledby="file-title">
      <h2 id="file-title">Đối chiếu tệp</h2>
      <p>Chọn tệp văn bản bạn đã nhận. Mã băm SHA-256 được tính ngay trong trình duyệt này; tệp không được gửi đi đâu cả, chỉ mã băm được gửi để so khớp.</p>
      <label for="file-input">Chọn tệp để đối chiếu</label>
      <input id="file-input" ref="fileInput" type="file" @change="onFile">
      <p v-if="fileHash" class="msg mono">SHA-256: {{ fileHash }}</p>
      <p v-if="fileMsg" class="msg" :class="fileMsg.tone" role="status">{{ fileMsg.text }}</p>
      <ProblemMessage :error="fileError" />
    </section>

    <section v-if="showDetails && (bundleText !== null || bundleError !== null)" class="card" aria-labelledby="bundle-title">
      <h2 id="bundle-title">Gói bằng chứng</h2>
      <template v-if="bundleText !== null">
        <p class="msg">Gói chứa chữ ký, chứng minh thuộc sổ cái và STH, để kiểm lại ngoại tuyến bằng <code>dxos-witness</code>.</p>
        <button type="button" @click="download">Tải gói bằng chứng (.json)</button>
      </template>
      <ProblemMessage :error="bundleError" />
    </section>

    <section class="card" aria-labelledby="limits-title">
      <h2 id="limits-title">Giới hạn tin cậy</h2>
      <p>Cổng này tự kiểm gói bằng chứng ngay trên trình duyệt của bạn: chữ ký niêm phong, chứng minh thuộc sổ cái, chữ ký STH và, khi được cấu hình, so STH với bản lưu ở repo neo công khai. Khi kết quả tự kiểm khác với điều máy chủ báo thì kết quả tự kiểm được dùng. Việc thu hồi niêm phong không nằm trong gói đã ký nên chỉ máy chủ biết; máy chủ chỉ có thể hạ nhãn, không thể nâng nhãn.</p>
      <p>Khi chưa với tới repo neo, cổng nói rõ là chưa đối chiếu và không kết luận văn bản bị giả mạo. Chỉ mã băm SHA-256 của tệp được gửi đi; chính tệp được băm tại trình duyệt và không rời khỏi máy bạn.</p>
      <p>Muốn kiểm độc lập, không cần tin cổng này: tải gói bằng chứng, rồi chạy <code>dxos-witness verify-bundle --anchor-dir &lt;thư mục clone repo neo&gt; &lt;tệp gói&gt;.json</code>.</p>
    </section>

    <section class="card" aria-labelledby="legal-title">
      <h2 id="legal-title">Bản chất pháp lý của niêm phong</h2>
      <p>Niêm phong số là chữ ký điện tử chuyên dùng do tổ chức vận hành tạo lập (Điều 22 khoản 1 điểm a Luật Giao dịch điện tử 2023). Trong nội bộ tổ chức, niêm phong dùng để xác nhận văn bản đã được duyệt và chưa bị sửa. Niêm phong chưa được chứng nhận "bảo đảm an toàn", nên không tương đương chữ ký tay (Điều 23 khoản 2) và không phải chữ ký số. Muốn dùng niêm phong để giao dịch với tổ chức, cá nhân bên ngoài với giá trị pháp lý, tổ chức phải đăng ký chứng nhận (Điều 25 khoản 3). Với người ngoài, cổng đối soát là công cụ kiểm tra toàn vẹn về kỹ thuật.</p>
      <p>Chi tiết căn cứ pháp lý: <a href="https://github.com/PSA-OVNCR/dxos/blob/main/docs/legal-mapping.md" rel="noopener noreferrer">docs/legal-mapping.md</a>.</p>
    </section>
  </main>
</template>
