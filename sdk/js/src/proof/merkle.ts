// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Cây Merkle RFC 6962 và thuật toán kiểm RFC 9162 (§2.1.3.2 inclusion, §2.1.4.2 consistency), dịch từng
// dòng từ `dxos_proof.merkle`. Chỉ số/cỡ cây tính bằng bigint để không giới hạn ở 2^53 như Python.
import { canonicalBytes, type Json } from './canonical'
import { bytesEqual, concat, sha256With } from './hash'

const sub = () => globalThis.crypto.subtle

export function leafHashWith(subtle: SubtleCrypto, data: Uint8Array): Promise<Uint8Array> {
  return sha256With(subtle, concat(Uint8Array.of(0), data))
}

function nodeHash(subtle: SubtleCrypto, left: Uint8Array, right: Uint8Array): Promise<Uint8Array> {
  return sha256With(subtle, concat(Uint8Array.of(1), left, right))
}

/** Hash lá của một mục ledger: SHA-256(0x00 || canonical_bytes(entry)). */
export function leafHash(entry: Json): Promise<Uint8Array> {
  return leafHashWith(sub(), canonicalBytes(entry))
}

export async function inclusionOk(subtle: SubtleCrypto, leaf: Uint8Array, index: bigint, size: bigint,
  proof: Uint8Array[], root: Uint8Array): Promise<boolean> {
  if (index < 0n || index >= size) return false
  let fn = index
  let sn = size - 1n
  let r = leaf
  for (const p of proof) {
    if (sn === 0n) return false
    if ((fn & 1n) === 1n || fn === sn) {
      r = await nodeHash(subtle, p, r)
      if ((fn & 1n) === 0n) {
        while ((fn & 1n) === 0n && fn !== 0n) { fn >>= 1n; sn >>= 1n }
      }
    } else {
      r = await nodeHash(subtle, r, p)
    }
    fn >>= 1n
    sn >>= 1n
  }
  return sn === 0n && bytesEqual(r, root)
}

export async function consistencyOk(subtle: SubtleCrypto, m: bigint, n: bigint, rootM: Uint8Array,
  rootN: Uint8Array, proof: Uint8Array[]): Promise<boolean> {
  if (m < 1n || m > n) return false
  if (m === n) return proof.length === 0 && bytesEqual(rootM, rootN)
  if (proof.length === 0) return false
  const path = [...proof]
  if ((m & (m - 1n)) === 0n) path.unshift(rootM) // m là lũy thừa của 2
  let fn = m - 1n
  let sn = n - 1n
  while ((fn & 1n) === 1n) { fn >>= 1n; sn >>= 1n }
  let fr = path[0]!
  let sr = path[0]!
  for (const c of path.slice(1)) {
    if (sn === 0n) return false
    if ((fn & 1n) === 1n || fn === sn) {
      fr = await nodeHash(subtle, c, fr)
      sr = await nodeHash(subtle, c, sr)
      if ((fn & 1n) === 0n) {
        while ((fn & 1n) === 0n && fn !== 0n) { fn >>= 1n; sn >>= 1n }
      }
    } else {
      sr = await nodeHash(subtle, sr, c)
    }
    fn >>= 1n
    sn >>= 1n
  }
  return sn === 0n && bytesEqual(fr, rootM) && bytesEqual(sr, rootN)
}

const big = (v: number): bigint | null => (Number.isSafeInteger(v) ? BigInt(v) : null)

/** Kiểm inclusion proof (RFC 9162 §2.1.3.2); `leaf` là leaf hash. */
export async function verifyInclusion(leaf: Uint8Array, index: number, size: number, proof: Uint8Array[],
  root: Uint8Array): Promise<boolean> {
  const i = big(index)
  const s = big(size)
  return i !== null && s !== null && inclusionOk(sub(), leaf, i, s, proof, root)
}

/** Kiểm consistency proof giữa cây cỡ m và cây cỡ n (RFC 9162 §2.1.4.2). */
export async function verifyConsistency(m: number, n: number, rootM: Uint8Array, rootN: Uint8Array,
  proof: Uint8Array[]): Promise<boolean> {
  const a = big(m)
  const b = big(n)
  return a !== null && b !== null && consistencyOk(sub(), a, b, rootM, rootN, proof)
}
