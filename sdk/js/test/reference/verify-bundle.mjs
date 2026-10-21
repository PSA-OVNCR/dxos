// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Bản tham chiếu viết lúc lập Plan 03 (22/10), đã chạy với 3 gói mẫu từ builder test của witness. Task 4 viết lại
// thành sdk/js/src/proof/*.ts có test; tệp này chỉ để đối chiếu, không được import từ mã sản phẩm.
// Reference browser-style verifier for dxos-seal-bundle/1 using ONLY WebCrypto (crypto.subtle) + pure JS.
// Mirrors witness/src/dxos_witness/bundle.py (unpinned mode: keys/statement taken from the bundle).
import { readFileSync } from "node:fs";
const subtle = globalThis.crypto.subtle;
const te = new TextEncoder();

// ---- canonical JSON (dxos_proof.canonical.canonical_bytes) ----
function cmpCodePoint(a, b) { // Python str ordering = code point order
  const A = Array.from(a), B = Array.from(b);
  for (let i = 0; i < Math.min(A.length, B.length); i++) {
    const d = A[i].codePointAt(0) - B[i].codePointAt(0);
    if (d) return d;
  }
  return A.length - B.length;
}
function canon(v) {
  if (v === null || typeof v === "boolean") return JSON.stringify(v);
  if (typeof v === "number") { if (!Number.isInteger(v)) throw new Error("float not allowed"); return String(v); }
  if (typeof v === "bigint") return v.toString();
  if (typeof v === "string") return JSON.stringify(v.normalize("NFC"));
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  if (typeof v === "object") {
    const seen = new Map();
    for (const k of Object.keys(v)) { const n = k.normalize("NFC"); if (seen.has(n)) throw new Error("NFC key collision"); seen.set(n, v[k]); }
    return "{" + [...seen.keys()].sort(cmpCodePoint).map(k => JSON.stringify(k) + ":" + canon(seen.get(k))).join(",") + "}";
  }
  throw new Error("bad type");
}
const cb = (v) => te.encode(canon(v));

// ---- helpers ----
const hex = (u8) => Array.from(u8, b => b.toString(16).padStart(2, "0")).join("");
const unhex = (h) => { if (!/^[0-9a-f]{64}$/.test(h)) throw new Error("hex32"); return Uint8Array.from(h.match(/../g), x => parseInt(x, 16)); };
const b64 = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const sha = async (u8) => new Uint8Array(await subtle.digest("SHA-256", u8));
const cat = (...a) => { const o = new Uint8Array(a.reduce((n, x) => n + x.length, 0)); let p = 0; for (const x of a) { o.set(x, p); p += x.length; } return o; };
const eq = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const leafHash = (d) => sha(cat(Uint8Array.of(0), d));
const nodeHash = (l, r) => sha(cat(Uint8Array.of(1), l, r));
async function edVerify(pub32, sigB64, msg) {
  const key = await subtle.importKey("raw", pub32, { name: "Ed25519" }, false, ["verify"]);
  return subtle.verify({ name: "Ed25519" }, key, b64(sigB64), msg);
}

// ---- RFC 9162 verification (merkle.py verify_inclusion / verify_consistency) ----
async function verifyInclusion(leaf, index, size, proof, root) {
  if (index < 0 || index >= size) return false;
  let fn = BigInt(index), sn = BigInt(size - 1), r = leaf;
  for (const p of proof) {
    if (sn === 0n) return false;
    if ((fn & 1n) || fn === sn) {
      r = await nodeHash(p, r);
      if (!(fn & 1n)) { while (!(fn & 1n) && fn !== 0n) { fn >>= 1n; sn >>= 1n; } }
    } else r = await nodeHash(r, p);
    fn >>= 1n; sn >>= 1n;
  }
  return sn === 0n && eq(r, root);
}
async function verifyConsistency(m, n, rootM, rootN, proof) {
  if (m < 1 || m > n) return false;
  if (m === n) return proof.length === 0 && eq(rootM, rootN);
  if (!proof.length) return false;
  const path = [...proof];
  if ((m & (m - 1)) === 0) path.unshift(rootM);
  let fn = BigInt(m - 1), sn = BigInt(n - 1);
  while (fn & 1n) { fn >>= 1n; sn >>= 1n; }
  let fr = path[0], sr = path[0];
  for (const c of path.slice(1)) {
    if (sn === 0n) return false;
    if ((fn & 1n) || fn === sn) {
      fr = await nodeHash(c, fr); sr = await nodeHash(c, sr);
      if (!(fn & 1n)) { while (!(fn & 1n) && fn !== 0n) { fn >>= 1n; sn >>= 1n; } }
    } else sr = await nodeHash(sr, c);
    fn >>= 1n; sn >>= 1n;
  }
  return sn === 0n && eq(fr, rootM) && eq(sr, rootN);
}
const sthOk = (th, pub) => edVerify(pub, th.signature,
  cb({ tree_size: th.tree_size, root_hash: th.root_hash, ts: th.ts, key_version: th.key_version }));

// ---- main (unpinned) ----
export async function verifyBundle(b, fileSha256 = null) {
  const fail = (code, msg) => ({ ok: false, code, msg });
  if (b.format !== "dxos-seal-bundle/1") return fail("FORMAT");
  const p = b.payload, kv = p.key_version;
  if (b.seal_key.version !== kv) return fail("KEY_VERSION");
  const sealPub = b64(b.seal_key.public_key);
  const st = b.seal_key.statement;
  if (!st) return fail("KEY_STATEMENT_MISSING");
  if (st.format !== "dxos-key-statement/1" || st.key !== "seal-key" || st.version !== kv || st.algorithm !== "ed25519"
      || !eq(b64(st.public_key), sealPub)) return fail("KEY_STATEMENT");
  const at = Date.parse(p.issued_at);
  if (!(Date.parse(st.valid_from) <= at && at <= Date.parse(st.valid_until))) return fail("KEY_NOT_VALID_AT_ISSUE");
  if (!(await edVerify(sealPub, b.signature, cb(p)))) return fail("SIGNATURE");
  const { entry, body } = b.ledger, leafIndex = b.inclusion.leaf_index;
  const payloadSha = hex(await sha(cb(p)));
  if (body.payload_sha256 !== payloadSha || body.seal_id !== p.seal_id
      || entry.body_sha256 !== hex(await sha(cb(body))) || entry.type !== "record.sealed"
      || entry.subject !== p.seal_id || entry.idx !== leafIndex) return fail("LEAF_LINK");
  if (b.sth == null) return fail("NO_STH");
  const sth = b.sth, proof = b.inclusion.proof.map(unhex);
  if (b.inclusion.tree_size !== sth.tree_size ||
      !(await verifyInclusion(await leafHash(cb(entry)), leafIndex, sth.tree_size, proof, unhex(sth.root_hash)))) return fail("INCLUSION");
  if (!(await sthOk(sth, b64(b.sth_keys[String(sth.key_version)])))) return fail("STH_SIGNATURE");
  let anchoredCovers = false;
  if (b.anchored) {
    const a = b.anchored.sth;
    anchoredCovers = a.tree_size > leafIndex;
    if (!(await sthOk(a, b64(b.sth_keys[String(a.key_version)])))) return fail("ANCHORED_SIGNATURE");
    const cons = b.anchored.consistency.map(unhex);
    const ok = a.tree_size === sth.tree_size ? (cons.length === 0 && a.root_hash === sth.root_hash)
      : (a.tree_size < sth.tree_size && await verifyConsistency(a.tree_size, sth.tree_size, unhex(a.root_hash), unhex(sth.root_hash), cons));
    if (!ok) return fail("CONSISTENCY");
  }
  if (fileSha256 && !p.attachments.includes(fileSha256.toLowerCase())) return fail("FILE_NOT_IN_SEAL");
  return { ok: true, pinned: false, anchoredCovers, issuer: st.issuer };
}

if (process.argv[2]) {
  const b = JSON.parse(readFileSync(process.argv[2], "utf8"));
  console.log(process.argv[2].split("/").pop(), JSON.stringify(await verifyBundle(b)));
  // tamper tests
  const t = (name, fn) => { const c = structuredClone(b); fn(c); return verifyBundle(c).then(r => console.log("  tamper", name, "->", r.ok ? "VALID(!)" : r.code)); };
  await t("payload.public_fields", c => { c.payload.public_fields.title = "x"; });
  await t("signature", c => { const s = b64(c.signature); s[0] ^= 1; c.signature = btoa(String.fromCharCode(...s)); });
  await t("proof", c => { if (c.inclusion.proof.length) c.inclusion.proof[0] = (c.inclusion.proof[0][0] === "0" ? "1" : "0") + c.inclusion.proof[0].slice(1); });
  await t("sth.root", c => { c.sth.root_hash = (c.sth.root_hash[0] === "0" ? "1" : "0") + c.sth.root_hash.slice(1); });
}
