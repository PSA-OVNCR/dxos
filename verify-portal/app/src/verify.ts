// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Tự kiểm gói bằng chứng ngay trên trình duyệt, có đối chiếu repo neo khi cổng được build với repo neo.
import { verifyBundle, type AnchorSource, type BundleResult, type FailCode } from 'dxos-sdk-js'
import { isObj } from './state'

export const NOTE_ANCHOR_UNREACHABLE = 'Không truy cập được repo neo — chưa đối chiếu'
export const NOTE_ANCHOR_NOT_CONFIGURED = 'Cổng này chưa cấu hình repo neo — chưa đối chiếu'

export const NOTE_SEAL_ID_MISMATCH = 'seal_id trong gói khác mã niêm phong đang kiểm'

export interface LocalCheck {
  result: BundleResult
  /** Ghi chú về repo neo; rỗng khi đã đối chiếu xong (đạt hoặc hỏng thật). */
  anchorNote: string
}

/**
 * `text` là văn bản gói đúng như máy chủ trả (không qua JSON.parse). Có `anchor` thì kiểm ghim. Nếu kiểm ghim
 * hỏng VÌ nguồn neo ném lỗi (mạng, CORS, 5xx), thì đó là "chưa đối chiếu được" chứ không phải "không hợp lệ":
 * kiểm lại không ghim và báo kèm ghi chú. Repo neo trả 404 (→ *_NOT_ANCHORED) hay tệp khác gói là hỏng thật.
 */
export async function verifyInBrowser(
  text: string, o: { anchor?: AnchorSource; fileSha256?: string; sealId?: string },
): Promise<LocalCheck> {
  const check = await verifyPinnedOrNot(text, o)
  // Gói thật của MỘT niêm phong khác không được thay cho niêm phong đang xem: seal_id đã ký phải đúng mã người dùng
  // nhập/quét (payload.seal_id nằm trong phần được ký).
  const r = check.result
  if (o.sealId !== undefined && r.ok && !(isObj(r.payload) && r.payload.seal_id === o.sealId)) {
    return {
      ...check,
      result: { ...r, ok: false, code: 'MALFORMED', message: `MALFORMED: ${NOTE_SEAL_ID_MISMATCH}`,
        payload: null, issuer: null },
    }
  }
  return check
}

async function verifyPinnedOrNot(
  text: string, o: { anchor?: AnchorSource; fileSha256?: string },
): Promise<LocalCheck> {
  const { anchor, fileSha256 } = o
  if (!anchor) {
    return { result: await verifyBundle(text, { fileSha256 }), anchorNote: NOTE_ANCHOR_NOT_CONFIGURED }
  }
  let threw = false
  const watched: AnchorSource = {
    async file(path) {
      try {
        return await anchor.file(path)
      } catch (err) {
        threw = true
        throw err
      }
    },
  }
  const pinned = await verifyBundle(text, { anchor: watched, fileSha256 })
  if (!pinned.ok && threw && !(await anchorReachable(anchor))) {
    return { result: await verifyBundle(text, { fileSha256 }), anchorNote: NOTE_ANCHOR_UNREACHABLE }
  }
  return { result: pinned, anchorNote: '' }
}

/** Đường dẫn cố định, không phụ thuộc gói/máy chủ, để thăm dò repo neo (404 cũng là "đã với tới repo"). */
export const ANCHOR_PROBE_PATH = 'keys/sth-key/v1.pub'

/**
 * Nguồn neo ném lỗi ở đường dẫn do GÓI chọn (`keys/seal-key/v<key_version>.pub`, key_version không bị chặn) chưa
 * chứng tỏ repo neo hỏng: máy chủ bị chiếm có thể chọn đường dẫn làm fetch thất bại (URL quá dài...) để ép về kiểu
 * kiểm không ghim. Chỉ khi chính đường dẫn cố định cũng thất bại thì mới coi repo neo là không truy cập được.
 */
async function anchorReachable(anchor: AnchorSource): Promise<boolean> {
  try {
    await anchor.file(ANCHOR_PROBE_PATH)
    return true
  } catch {
    return false
  }
}

/**
 * Lời giải thích tiếng Việt cho mã hỏng. Cố ý không dùng cụm "hợp lệ": cụm đó chỉ thuộc nhãn cuối cùng, nên
 * không lặp lại ở dòng chi tiết. Chi tiết gốc của bộ kiểm (`result.message`) đặt ở thuộc tính `title`.
 */
const EXPLAIN: Record<FailCode, string> = {
  FORMAT: 'gói không đúng định dạng dxos-seal-bundle/1',
  KEY_VERSION: 'phiên bản khóa trong gói không khớp',
  KEY_MISSING: 'gói thiếu khóa công khai của niêm phong',
  KEY_NOT_ANCHORED: 'khóa niêm phong chưa có trong repo neo',
  KEY_MISMATCH: 'khóa trong gói khác khóa đã neo',
  KEY_STATEMENT: 'tuyên bố khóa sai nội dung hoặc sai dạng',
  KEY_STATEMENT_MISSING: 'gói thiếu tuyên bố khóa',
  KEY_STATEMENT_NOT_ANCHORED: 'tuyên bố khóa chưa có trong repo neo',
  KEY_NOT_VALID_AT_ISSUE: 'khóa đã hết hạn hoặc chưa có hiệu lực vào lúc niêm phong',
  SIGNATURE: 'chữ ký niêm phong không khớp nội dung đã niêm phong',
  LEAF_LINK: 'mục sổ cái không gắn với niêm phong này',
  NO_STH: 'gói chưa kèm STH phủ niêm phong',
  INCLUSION: 'chứng minh niêm phong thuộc sổ cái sai',
  STH_SIGNATURE: 'chữ ký của STH sai',
  NOT_ANCHORED: 'STH chưa có trong repo neo',
  ANCHORED_SIGNATURE: 'chữ ký của STH đã neo sai',
  CONSISTENCY: 'chứng minh nhất quán giữa hai STH sai',
  FILE_NOT_IN_SEAL: 'tệp bạn chọn không nằm trong niêm phong',
  MALFORMED: 'gói sai cấu trúc hoặc không đọc được',
  UNSUPPORTED_CRYPTO: 'trình duyệt này không có Ed25519',
}

export function explainFailure(r: BundleResult): string {
  if (r.code === null) return ''
  if (r.code === 'MALFORMED' && r.message.includes(NOTE_SEAL_ID_MISMATCH)) {
    return 'gói này thuộc niêm phong khác mã đang kiểm'
  }
  return EXPLAIN[r.code]
}
