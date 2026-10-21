// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Nguồn đọc repo neo (dxos-transparency-log) cho chế độ ghim của bộ kiểm gói, tương đương `--anchor-dir`.

/** Đọc một tệp theo đường dẫn tương đối trong repo neo; chưa có tệp → null. Lỗi khác thì ném. */
export interface AnchorSource {
  file(path: string): Promise<Uint8Array | null>
}

// Chỉ các đường dẫn bộ kiểm cần (`keys/<khóa>/v<n>.pub|json`, `sth/<12 chữ số>.json`): không `..`, không
// tuyệt đối, không scheme/host/query, nên `${base}/${path}` không thể rời khỏi `base`.
const SAFE_PATH = /^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_.-]+)*$/

/**
 * Repo neo đọc qua HTTP thô, ví dụ `rawAnchor('https://raw.githubusercontent.com/<org>/dxos-transparency-log/main')`.
 * Mỗi tệp lấy tại `${base}/${path}` (không theo chuyển hướng, không gửi cookie, không dùng cache);
 * 404 → null, mã khác 2xx → ném lỗi để nơi gọi quyết định. Không bao giờ gọi host nào khác `base`.
 */
export function rawAnchor(base: string, fetchFn?: typeof fetch): AnchorSource {
  const root = base.replace(/\/+$/, '')
  return {
    async file(path: string): Promise<Uint8Array | null> {
      if (!SAFE_PATH.test(path) || path.split('/').some((seg) => seg === '.' || seg === '..')) {
        throw new Error(`đường dẫn repo neo không hợp lệ: ${JSON.stringify(path)}`)
      }
      const f = fetchFn ?? globalThis.fetch.bind(globalThis)
      const res = await f(`${root}/${path}`, { redirect: 'error', credentials: 'omit', cache: 'no-store' })
      if (res.status === 404) return null
      if (!res.ok) throw new Error(`repo neo trả HTTP ${res.status} cho ${path}`)
      return new Uint8Array(await res.arrayBuffer())
    },
  }
}
