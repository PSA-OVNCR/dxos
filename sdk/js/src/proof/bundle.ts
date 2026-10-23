// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Kiểm gói bằng chứng niêm phong `dxos-seal-bundle/1` trên trình duyệt, dịch từng bước từ
// `witness/src/dxos_witness/bundle.py` (CÙNG thứ tự, CÙNG mã lỗi; docs/api/contract-tier2.md mục 6.5–6.6).
// Đọc gói như CLI `dxos-witness verify-bundle` (khóa JSON trùng → MALFORMED). Có `anchor` thì đối chiếu
// từng byte với repo neo như `--anchor-dir`. Trường `status` của gói không được ký nên bị bỏ qua.
// Mặc định chặt như `--anchor-dir`; cổng đối soát bật `allowPendingAnchor` để "chưa neo kịp" là `pendingAnchor`, không phải lỗi.
// Mọi lỗi bất ngờ → MALFORMED, không bao giờ ok. Không có Ed25519 trong WebCrypto → UNSUPPORTED_CRYPTO.
import type { AnchorSource } from './anchor'
import { canonicalBytes, JsonFloat, nfcEntries, parseJson, type Json } from './canonical'
import { b64decodePy, b64encode, bytesEqual, hex32, sha256With, toHex } from './hash'
import { consistencyOk, inclusionOk, leafHashWith } from './merkle'

export type FailCode = 'FORMAT' | 'KEY_VERSION' | 'KEY_MISSING' | 'KEY_NOT_ANCHORED' | 'KEY_MISMATCH' | 'KEY_STATEMENT'
  | 'KEY_STATEMENT_MISSING' | 'KEY_STATEMENT_NOT_ANCHORED' | 'KEY_NOT_VALID_AT_ISSUE' | 'SIGNATURE' | 'LEAF_LINK'
  | 'NO_STH' | 'INCLUSION' | 'STH_SIGNATURE' | 'NOT_ANCHORED' | 'ANCHORED_SIGNATURE' | 'CONSISTENCY'
  | 'FILE_NOT_IN_SEAL' | 'MALFORMED' | 'UNSUPPORTED_CRYPTO'

export interface BundleResult {
  ok: boolean
  /** true khi có repo neo (khóa, tuyên bố khóa và STH đã neo lấy từ đó), kể cả khi không hợp lệ. */
  pinned: boolean
  code: FailCode | null
  /** Hỏng: `"<MÃ>: <chi tiết>"` như `detail` của witness; hợp lệ: các ghi chú bắt đầu bằng "OK". */
  message: string
  /**
   * true chỉ khi `ok` và đã ghim, `allowPendingAnchor` được bật và STH đã neo CHƯA có/chưa phủ lá/chưa được công bố ở
   * repo neo (mọi bước khác đều đạt, khóa đã khớp repo neo). Nơi gọi phải hiển thị như "chưa neo", không như "đã neo".
   */
  pendingAnchor?: boolean
  /** Payload đã ký (chỉ khi ok). */
  payload: Json | null
  /** Bên niêm phong theo tuyên bố khóa (chỉ khi ok). */
  issuer: { name: string; id: string | null } | null
}

export interface VerifyOptions {
  anchor?: AnchorSource
  /** SHA-256 (hex) của tệp gốc người dùng chọn, như `--file`. */
  fileSha256?: string
  /**
   * Chỉ có nghĩa khi có `anchor`. Mặc định (false) giữ nguyên kiểm chặt của `dxos-witness verify-bundle --anchor-dir`
   * (ruling C8): gói không có `anchored`, STH đã neo chưa phủ lá, hoặc repo neo chưa có `sth/<n>.json` đều là
   * NOT_ANCHORED. Bật lên (cổng đối soát, Plan 04 R11) thì ba trường hợp "chưa neo kịp" đó cho `ok: true,
   * pendingAnchor: true`; mọi bước khác vẫn chặt (khóa phải khớp repo neo, chữ ký, inclusion, consistency, và
   * `sth/<n>.json` CÓ trong repo mà khác `anchored.sth` vẫn là NOT_ANCHORED).
   */
  allowPendingAnchor?: boolean
}

const BUNDLE_FORMAT = 'dxos-seal-bundle/1'
const STATEMENT_FORMAT = 'dxos-key-statement/1'
const STH_FIELDS = ['tree_size', 'root_hash', 'ts', 'key_version', 'signature']
// RFC 3339 có múi giờ, chữ số ASCII (Python: regex + datetime.fromisoformat chỉ nhận chữ số ASCII).
const RFC3339 = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?(?:Z|([+-])([0-9]{2}):([0-9]{2}))$/
// Khóa công khai mẫu RFC 8032 §7.1 (test 1): import được thì WebCrypto có Ed25519.
const PROBE_KEY = Uint8Array.from([0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9,
  0x64, 0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68, 0xf7, 0x07, 0x51, 0x1a])

type Obj = Record<string, unknown>

class Fail extends Error {
  constructor(readonly code: FailCode, detail: string) { super(`${code}: ${detail}`) }
}
class Unsupported extends Error {}
class AnchorFileError extends Error {}

const fail = (code: FailCode, detail: string): never => { throw new Fail(code, detail) }

// ---------------------------------------------------------------- đọc trường (Python dict.get / isinstance)
const isObj = (v: unknown): v is Obj =>
  v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof JsonFloat)
const isInt = (v: unknown): v is number | bigint => typeof v === 'number' || typeof v === 'bigint'
const get = (o: unknown, k: string): unknown => (isObj(o) && Object.hasOwn(o, k) ? o[k] : undefined)
const none = (v: unknown): v is null | undefined => v === null || v === undefined
const repr = (v: unknown): string => (typeof v === 'bigint' ? v.toString() : JSON.stringify(v) ?? 'None')
const pad12 = (v: number | bigint): string => String(v).padStart(12, '0')

function obj(v: unknown, name: string): Obj {
  return isObj(v) ? v : fail('MALFORMED', `${name} phải là object`)
}
function int(v: unknown, name: string): number | bigint {
  return isInt(v) ? v : fail('MALFORMED', `${name} phải là số nguyên`)
}
function str(v: unknown, name: string): string {
  return typeof v === 'string' ? v : fail('MALFORMED', `${name} phải là chuỗi`)
}
function hex(v: unknown, name: string): Uint8Array {
  return hex32(v) ?? fail('MALFORMED', `${name} phải là 64 ký tự hex thường`)
}
function hexList(v: unknown, name: string): Uint8Array[] {
  if (!Array.isArray(v)) fail('MALFORMED', `${name} phải là mảng`)
  return (v as unknown[]).map((x, i) => hex(x, `${name}[${i}]`))
}

interface Sth { tree_size: number | bigint; root_hash: string; ts: string; key_version: number | bigint; signature: string }

function sth(v: unknown, name: string): Sth {
  const th = obj(v, name)
  const keys = Object.keys(th)
  if (keys.length !== STH_FIELDS.length || !STH_FIELDS.every((k) => Object.hasOwn(th, k))) {
    fail('MALFORMED', `${name} phải có đúng các trường ${STH_FIELDS.join(', ')}`)
  }
  int(th.tree_size, `${name}.tree_size`)
  int(th.key_version, `${name}.key_version`)
  hex(th.root_hash, `${name}.root_hash`)
  str(th.ts, `${name}.ts`)
  str(th.signature, `${name}.signature`)
  if ((th.tree_size as number | bigint) < 1) fail('MALFORMED', `${name}.tree_size phải ≥ 1`)
  return th as unknown as Sth
}

/** Như `_no_nfc_collisions`: không object lồng nào có hai khóa trùng sau NFC. */
function noNfcCollisions(v: unknown, name: string): void {
  if (isObj(v)) {
    let m: Map<string, unknown>
    try { m = nfcEntries(v) } catch (e) { return fail('MALFORMED', `${name}: ${(e as Error).message}`) }
    for (const [k, item] of m) noNfcCollisions(item, `${name}.${k}`)
  } else if (Array.isArray(v)) {
    v.forEach((item, i) => noNfcCollisions(item, `${name}[${i}]`))
  }
}

/** Khóa ed25519 thô từ base64 (chặt như Python); sai dạng → null. */
function b64Key(v: unknown): Uint8Array | null {
  if (typeof v !== 'string') return null
  const raw = b64decodePy(v)
  return raw !== null && raw.length === 32 ? raw : null
}

const cb = (v: unknown): Uint8Array => canonicalBytes(v as Json)

// ---------------------------------------------------------------- Ed25519 (WebCrypto)
async function hasEd25519(subtle: SubtleCrypto): Promise<boolean> {
  try {
    await subtle.importKey('raw', PROBE_KEY, { name: 'Ed25519' }, false, ['verify'])
    return true
  } catch {
    return false
  }
}

async function ed25519Ok(subtle: SubtleCrypto, pub: Uint8Array, signature: unknown, message: Uint8Array): Promise<boolean> {
  if (typeof signature !== 'string') return false
  let key: CryptoKey
  try {
    key = await subtle.importKey('raw', new Uint8Array(pub), { name: 'Ed25519' }, false, ['verify'])
  } catch {
    if (!(await hasEd25519(subtle))) throw new Unsupported()
    return false // khóa này bị từ chối nhưng Ed25519 có hỗ trợ
  }
  const sig = b64decodePy(signature)
  if (sig === null || sig.length !== 64) return false
  return subtle.verify({ name: 'Ed25519' }, key, new Uint8Array(sig), new Uint8Array(message))
}

function sthSignatureOk(subtle: SubtleCrypto, th: Sth, pub: Uint8Array): Promise<boolean> {
  const msg = cb({ tree_size: th.tree_size, root_hash: th.root_hash, ts: th.ts, key_version: th.key_version })
  return ed25519Ok(subtle, pub, th.signature, msg)
}

// ---------------------------------------------------------------- RFC 3339 (như datetime.fromisoformat)
const daysFromCivil = (y: number, m: number, d: number): number => {
  const yy = m <= 2 ? y - 1 : y
  const era = Math.floor(yy / 400)
  const yoe = yy - era * 400
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy
  return era * 146097 + doe - 719468
}
const MICROS_PER_DAY = 86_400_000_000n
const MIN_US = BigInt(daysFromCivil(1, 1, 1)) * MICROS_PER_DAY
const MAX_US = BigInt(daysFromCivil(9999, 12, 31)) * MICROS_PER_DAY + MICROS_PER_DAY - 1n

/**
 * Thời điểm RFC 3339 có múi giờ → micro giây kể từ 1970 (UTC), đúng như `parse_rfc3339` của witness:
 * sai dạng/ngoài miền (Python ValueError) → RangeError; ra ngoài năm 1…9999 sau khi đổi về UTC
 * (Python OverflowError, witness báo MALFORMED) → Error thường. Phần lẻ quá 6 chữ số bị cắt.
 */
export function parseRfc3339Micros(v: unknown): bigint {
  const m = typeof v === 'string' ? RFC3339.exec(v) : null
  if (!m) throw new RangeError(`không phải thời điểm RFC 3339 có múi giờ: ${repr(v)}`)
  const [y, mo, d, h, mi, s] = m.slice(1, 7).map(Number) as [number, number, number, number, number, number]
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0
  const dim = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
  if (y < 1 || dim === undefined || d < 1 || d > dim || h > 23 || mi > 59 || s > 59) {
    throw new RangeError(`thời điểm ngoài miền: ${repr(v)}`)
  }
  const offset = m[8] === undefined ? 0 : (m[8] === '-' ? -1 : 1) * (Number(m[9]) * 3600 + Number(m[10]) * 60)
  if (Math.abs(offset) >= 86400) throw new RangeError(`múi giờ phải trong (−24h, 24h): ${repr(v)}`)
  const micros = BigInt((m[7] ?? '').slice(0, 6).padEnd(6, '0'))
  const us = BigInt(daysFromCivil(y, mo, d)) * MICROS_PER_DAY + BigInt(h * 3600 + mi * 60 + s - offset) * 1_000_000n + micros
  if (us < MIN_US || us > MAX_US) throw new Error(`OverflowError: date value out of range: ${repr(v)}`)
  return us
}

// ---------------------------------------------------------------- repo neo
async function anchoredPublicKey(src: AnchorSource, name: string, version: number | bigint): Promise<Uint8Array | null> {
  const path = `keys/${name}/v${version}.pub`
  const data = await src.file(path)
  if (data === null) return null
  let raw: Uint8Array | null = null
  if (data.length > 0 && data[data.length - 1] === 0x0a && data.subarray(0, -1).every((b) => b < 0x80)) {
    raw = b64Key(new TextDecoder().decode(data.subarray(0, -1)))
  }
  if (raw === null || !bytesEqual(new TextEncoder().encode(`${b64encode(raw)}\n`), data)) {
    throw new AnchorFileError(`${path} sai định dạng (base64 khóa ed25519 + \\n)`)
  }
  return raw
}

async function pinnedKey(src: AnchorSource, name: string, version: number | bigint, hint: unknown): Promise<Uint8Array> {
  let pub: Uint8Array | null
  try {
    pub = await anchoredPublicKey(src, name, version)
  } catch (e) {
    if (e instanceof AnchorFileError) return fail('KEY_NOT_ANCHORED', e.message)
    throw e
  }
  if (pub === null) return fail('KEY_NOT_ANCHORED', `repo neo không có keys/${name}/v${version}.pub`)
  if (!none(hint)) {
    const h = b64Key(hint)
    if (h === null || !bytesEqual(h, pub)) fail('KEY_MISMATCH', `khóa ${name} v${version} trong gói khác khóa đã neo`)
  }
  return pub
}

const withNewline = (b: Uint8Array): Uint8Array => {
  const out = new Uint8Array(b.length + 1)
  out.set(b)
  out[b.length] = 0x0a
  return out
}

async function anchoredStatement(src: AnchorSource, version: number | bigint, statement: unknown): Promise<Obj> {
  const path = `keys/seal-key/v${version}.json`
  const data = await src.file(path)
  if (data === null) return fail('KEY_STATEMENT_NOT_ANCHORED', `repo neo không có ${path}`)
  if (!none(statement) && (!isObj(statement) || !bytesEqual(withNewline(cb(statement)), data))) {
    fail('KEY_STATEMENT', `tuyên bố khóa trong gói khác ${path} đã neo`)
  }
  // Luôn dùng bản ĐÃ NEO: issuer hiển thị đúng chuỗi trong repo neo.
  let st: unknown
  try {
    st = parseJson(new TextDecoder('utf-8', { fatal: true }).decode(data), { floats: 'keep', duplicates: 'last' })
  } catch (e) {
    if (e instanceof SyntaxError || e instanceof TypeError) return fail('KEY_STATEMENT', `${path} không phải JSON`)
    throw e
  }
  if (!isObj(st) || !bytesEqual(withNewline(cb(st)), data)) fail('KEY_STATEMENT', `${path} không ở dạng chuẩn hóa`)
  return st as Obj
}

function checkStatement(st: Obj, version: number | bigint, sealPub: Uint8Array, issuedAt: unknown): { name: string; id: string | null } {
  if (get(st, 'format') !== STATEMENT_FORMAT || get(st, 'key') !== 'seal-key' || !isInt(get(st, 'version'))
    || get(st, 'version') !== version || get(st, 'algorithm') !== 'ed25519') {
    fail('KEY_STATEMENT', `tuyên bố không phải ${STATEMENT_FORMAT} của seal-key v${version} (ed25519)`)
  }
  const pk = b64Key(get(st, 'public_key'))
  if (pk === null || !bytesEqual(pk, sealPub)) fail('KEY_STATEMENT', 'public_key của tuyên bố khác khóa seal-key đang dùng')
  const issuer = get(st, 'issuer')
  const name = get(issuer, 'name')
  const id = get(issuer, 'id')
  if (!isObj(issuer) || typeof name !== 'string' || !name || !(none(id) || typeof id === 'string')) {
    fail('KEY_STATEMENT', 'issuer của tuyên bố sai dạng')
  }
  let start: bigint, end: bigint, at: bigint
  try {
    start = parseRfc3339Micros(get(st, 'valid_from'))
    end = parseRfc3339Micros(get(st, 'valid_until'))
    at = parseRfc3339Micros(issuedAt)
  } catch (e) {
    if (e instanceof RangeError) return fail('KEY_NOT_VALID_AT_ISSUE', e.message)
    throw e
  }
  if (!(start <= at && at <= end)) {
    fail('KEY_NOT_VALID_AT_ISSUE', `issued_at ${String(issuedAt)} nằm ngoài ${String(get(st, 'valid_from'))} … `
      + `${String(get(st, 'valid_until'))} của seal-key v${version}`)
  }
  return { name: name as string, id: none(id) ? null : (id as string) }
}

// ---------------------------------------------------------------- kiểm
async function verify(
  subtle: SubtleCrypto, b: unknown, anchor: AnchorSource | null, fileSha256: string | null, allowPending: boolean,
): Promise<BundleResult> {
  // 1. định dạng
  b = obj(b, 'gói')
  if (get(b, 'format') !== BUNDLE_FORMAT) fail('FORMAT', `format phải là ${BUNDLE_FORMAT}`)
  const payload = obj(get(b, 'payload'), 'payload')
  const [skRaw, ledgerRaw, anchoredRaw] = ['seal_key', 'ledger', 'anchored'].map((k) => (isObj(get(b, k)) ? get(b, k) : {}))
  for (const [v, name] of [[payload, 'payload'], [get(skRaw, 'statement'), 'seal_key.statement'],
    [get(ledgerRaw, 'entry'), 'ledger.entry'], [get(ledgerRaw, 'body'), 'ledger.body'], [get(b, 'sth'), 'sth'],
    [get(anchoredRaw, 'sth'), 'anchored.sth']] as [unknown, string][]) {
    noNfcCollisions(v, name)
  }
  const kv = int(get(payload, 'key_version'), 'payload.key_version')
  const sealId = str(get(payload, 'seal_id'), 'payload.seal_id')

  // 2. khóa
  const sk = obj(get(b, 'seal_key'), 'seal_key')
  if (!isInt(get(sk, 'version')) || get(sk, 'version') !== kv) {
    fail('KEY_VERSION', `seal_key.version ${repr(get(sk, 'version'))} khác payload.key_version ${kv}`)
  }
  const th = none(get(b, 'sth')) ? null : sth(get(b, 'sth'), 'sth')
  const anchored = none(get(b, 'anchored')) ? null : obj(get(b, 'anchored'), 'anchored')
  const anchoredSth = anchored === null ? null : sth(get(anchored, 'sth'), 'anchored.sth')
  const hintsRaw = get(b, 'sth_keys')
  const hints = none(hintsRaw) ? {} : obj(hintsRaw, 'sth_keys')
  const versions = [...new Map([th, anchoredSth].filter((x): x is Sth => x !== null)
    .map((x) => [String(x.key_version), x.key_version])).values()].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0))
  const statement = get(sk, 'statement')
  const sthPubs = new Map<string, Uint8Array>()
  let sealPub: Uint8Array
  let st: Obj
  if (anchor !== null) {
    sealPub = await pinnedKey(anchor, 'seal-key', kv, get(sk, 'public_key'))
    for (const v of versions) sthPubs.set(String(v), await pinnedKey(anchor, 'sth-key', v, get(hints, String(v))))
    st = await anchoredStatement(anchor, kv, statement)
  } else {
    sealPub = b64Key(get(sk, 'public_key')) ?? fail('KEY_MISSING', 'gói không kèm khóa seal-key và không có repo neo')
    for (const v of versions) {
      sthPubs.set(String(v), b64Key(get(hints, String(v)))
        ?? fail('KEY_MISSING', `gói không kèm khóa sth-key v${v} và không có repo neo`))
    }
    if (none(statement)) fail('KEY_STATEMENT_MISSING', 'gói không kèm tuyên bố khóa và không có repo neo')
    if (!isObj(statement)) fail('KEY_STATEMENT', 'seal_key.statement phải là object')
    st = statement as Obj
  }
  const issuer = checkStatement(st, kv, sealPub, get(payload, 'issued_at'))

  // 3. chữ ký niêm phong
  const payloadBytes = cb(payload)
  if (!(await ed25519Ok(subtle, sealPub, get(b, 'signature'), payloadBytes))) {
    fail('SIGNATURE', 'chữ ký niêm phong không hợp lệ với khóa seal-key')
  }

  // 4. payload ↔ lá ledger (Python tính cả danh sách trước khi xét: canonical(body) lỗi → MALFORMED)
  const ledger = obj(get(b, 'ledger'), 'ledger')
  const body = obj(get(ledger, 'body'), 'ledger.body')
  const entry = obj(get(ledger, 'entry'), 'ledger.entry')
  const inclusion = obj(get(b, 'inclusion'), 'inclusion')
  const leafIndex = int(get(inclusion, 'leaf_index'), 'inclusion.leaf_index')
  const payloadSha = toHex(await sha256With(subtle, payloadBytes))
  const bodySha = toHex(await sha256With(subtle, cb(body)))
  const links: [boolean, string][] = [
    [get(body, 'payload_sha256') === payloadSha, 'body.payload_sha256'],
    [get(body, 'seal_id') === sealId, 'body.seal_id'],
    [get(entry, 'body_sha256') === bodySha, 'entry.body_sha256'],
    [get(entry, 'type') === 'record.sealed', 'entry.type'],
    [get(entry, 'subject') === sealId, 'entry.subject'],
    [isInt(get(entry, 'idx')) && get(entry, 'idx') === leafIndex, 'entry.idx'],
  ]
  for (const [ok, what] of links) if (!ok) fail('LEAF_LINK', `${what} không khớp niêm phong`)

  // 5. inclusion
  if (th === null) return fail('NO_STH', 'chưa có STH nào phủ lá của niêm phong; tải lại gói sau')
  const proof = hexList(get(inclusion, 'proof'), 'inclusion.proof')
  const size = th.tree_size
  const incSize = get(inclusion, 'tree_size')
  if (!isInt(incSize) || incSize !== size
    || !(await inclusionOk(subtle, await leafHashWith(subtle, cb(entry)), BigInt(leafIndex), BigInt(size), proof,
      hex32(th.root_hash)!))) {
    fail('INCLUSION', `inclusion proof của lá ${leafIndex} trong cây ${size} không hợp lệ`)
  }

  // 6. chữ ký STH
  if (!(await sthSignatureOk(subtle, th, sthPubs.get(String(th.key_version))!))) {
    fail('STH_SIGNATURE', `chữ ký STH cỡ ${size} không hợp lệ với khóa sth-key v${th.key_version}`)
  }

  // 7. neo
  const covered = anchoredSth !== null && anchoredSth.tree_size > leafIndex
  let pendingWhy: string | null = null // chỉ khi allowPendingAnchor: lý do "chưa neo kịp"
  if (anchor !== null) {
    if (anchoredSth === null) {
      if (!allowPending) fail('NOT_ANCHORED', 'gói không có STH đã neo')
      pendingWhy = 'gói chưa kèm STH đã neo'
    } else {
      const aSize = anchoredSth.tree_size
      const path = `sth/${pad12(aSize)}.json`
      if (!allowPending) {
        if (!covered) fail('NOT_ANCHORED', `STH đã neo (cỡ ${aSize}) chưa phủ lá ${leafIndex}`)
        const data = await anchor.file(path)
        if (data === null || !bytesEqual(data, cb(anchoredSth))) {
          fail('NOT_ANCHORED', `${path} trong repo neo thiếu hoặc khác anchored.sth`)
        }
      } else {
        // Tệp CÓ trong repo neo mà khác anchored.sth là hỏng thật, kể cả khi STH chưa phủ lá; chỉ "chưa có" mới là chờ.
        const data = await anchor.file(path)
        if (data !== null && !bytesEqual(data, cb(anchoredSth))) {
          fail('NOT_ANCHORED', `${path} trong repo neo khác anchored.sth`)
        }
        if (!covered) pendingWhy = `STH đã neo (cỡ ${aSize}) chưa phủ lá ${leafIndex}`
        else if (data === null) pendingWhy = `${path} chưa có trong repo neo`
      }
    }
  }
  if (anchoredSth !== null) {
    const aSize = anchoredSth.tree_size
    if (!(await sthSignatureOk(subtle, anchoredSth, sthPubs.get(String(anchoredSth.key_version))!))) {
      fail('ANCHORED_SIGNATURE', `chữ ký STH đã neo cỡ ${aSize} không hợp lệ`)
    }
    const consistency = hexList(get(anchored, 'consistency'), 'anchored.consistency')
    const consistent = aSize === size
      ? consistency.length === 0 && anchoredSth.root_hash === th.root_hash
      : aSize < size && (await consistencyOk(subtle, BigInt(aSize), BigInt(size), hex32(anchoredSth.root_hash)!,
        hex32(th.root_hash)!, consistency))
    if (!consistent) fail('CONSISTENCY', `consistency proof ${aSize} → ${size} không hợp lệ`)
  }

  // 8. tệp
  const attachments = get(payload, 'attachments')
  if (!Array.isArray(attachments)) return fail('MALFORMED', 'payload.attachments phải là mảng')
  if (fileSha256 !== null && !attachments.includes(fileSha256.toLowerCase())) {
    fail('FILE_NOT_IN_SEAL', 'SHA-256 của tệp không thuộc niêm phong này')
  }

  // 9. kết quả; status của gói không được dùng
  const notes = ['OK']
  if (anchor !== null && pendingWhy !== null) {
    notes.push(`khóa đã ghim từ repo neo; chưa neo công khai: ${pendingWhy}`)
  } else if (anchor !== null) {
    notes.push(`khóa đã ghim từ repo neo; đã neo: sth/${pad12(anchoredSth!.tree_size)}.json`)
  } else {
    notes.push('chưa ghim khóa: khóa lấy từ chính gói (không có repo neo)')
    notes.push(covered ? 'STH đã neo theo gói, chưa đối chiếu repo neo' : 'chưa neo: chưa có STH đã neo phủ lá')
  }
  notes.push(`trạng thái thu hồi cần tra trực tuyến: GET /verify/v1/seals/${sealId}`)
  return {
    ok: true, pinned: anchor !== null, pendingAnchor: pendingWhy !== null, code: null, message: notes.join('; '),
    payload: payload as Json, issuer,
  }
}

/** Nội bộ (cho test): như `verifyBundle` nhưng dùng `subtle` được truyền vào. */
export async function verifyBundleWith(subtle: SubtleCrypto, text: string, o: VerifyOptions = {}): Promise<BundleResult> {
  const anchor = o.anchor ?? null
  const bad = (code: FailCode, message: string): BundleResult =>
    ({ ok: false, pinned: anchor !== null, pendingAnchor: false, code, message, payload: null, issuer: null })
  try {
    let b: unknown
    try {
      b = parseJson(text, { floats: 'keep', duplicates: 'reject' })
    } catch (e) {
      return bad('MALFORMED', `MALFORMED: không đọc được gói: ${(e as Error).name}: ${(e as Error).message}`)
    }
    return await verify(subtle, b, anchor, o.fileSha256 ?? null, o.allowPendingAnchor === true)
  } catch (e) {
    if (e instanceof Fail) return bad(e.code, e.message)
    if (e instanceof Unsupported) {
      return bad('UNSUPPORTED_CRYPTO', 'UNSUPPORTED_CRYPTO: trình duyệt này không hỗ trợ Ed25519 trong WebCrypto; '
        + 'dùng trình duyệt mới hơn hoặc dxos-witness verify-bundle')
    }
    const err = e instanceof Error ? e : new Error(String(e))
    return bad('MALFORMED', `MALFORMED: ${err.name}: ${err.message}`)
  }
}

/**
 * Kiểm gói `dxos-seal-bundle/1` (văn bản JSON nguyên vẹn, đọc bằng UTF-8 chặt) hoàn toàn trên máy người dùng.
 * Có `anchor` → khóa, tuyên bố khóa và STH đã neo lấy từ repo neo (`pinned: true`); không có → chỉ biết gói
 * tự nhất quán. Trạng thái thu hồi luôn cần tra trực tuyến.
 */
export function verifyBundle(text: string, o?: VerifyOptions): Promise<BundleResult> {
  return verifyBundleWith(globalThis.crypto?.subtle, text, o)
}
