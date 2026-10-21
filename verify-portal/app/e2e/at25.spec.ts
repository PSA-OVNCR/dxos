// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// AT-25 (R-2): tệp không rời trình duyệt, chỉ {"sha256"} được gửi. Cộng các kịch bản "máy chủ nói dối" và repo neo.
import { randomBytes } from 'node:crypto'
import { expect, mockVerifyApi, ORIGINAL, SEAL_ID, sha256hex, test } from './mock'

const PAGE = `/apps/verify/#${SEAL_ID}`
const OK_PINNED = 'Hợp lệ — đã đối chiếu repo neo'
const OK_UNPINNED = 'Hợp lệ — chưa đối chiếu repo neo'

test('AT-25: file never leaves the browser, only {"sha256"} is sent', async ({ page }) => {
  // Tệp gốc của vector: sha256 của nó nằm trong gói, nên cả chuỗi (check → bundle → tự kiểm) đi đến cùng.
  const marker = ORIGINAL
  const sent: { url: string; ct: string | null; body: Buffer | null }[] = []
  page.on('request', (r) => sent.push({ url: r.url(), ct: r.headers()['content-type'] ?? null, body: r.postDataBuffer() }))
  await mockVerifyApi(page, { requireFile: true, sha256: sha256hex(marker) })
  await page.goto(PAGE)
  await page.setInputFiles('input[type=file]', { name: 'van-ban.pdf', mimeType: 'application/pdf', buffer: marker })
  await expect(page.getByText(OK_PINNED)).toBeVisible()
  for (const s of sent) {
    expect(s.ct ?? '').not.toMatch(/multipart|octet-stream|application\/pdf/)
    if (s.body) {
      expect(s.body.includes(marker.subarray(0, 64))).toBe(false)
      expect(s.body.includes(Buffer.from('van-ban.pdf'))).toBe(false)
      expect(JSON.parse(s.body.toString())).toEqual({ sha256: sha256hex(marker) })
    }
  }
  expect(sent.filter((s) => s.body).map((s) => new URL(s.url).pathname))
    .toEqual([`/verify/v1/seals/${SEAL_ID}:check`, `/verify/v1/seals/${SEAL_ID}:bundle`])
  expect(sent.filter((s) => s.body).map((s) => s.ct)).toEqual(['application/json', 'application/json'])
  // Chỉ cùng một nguồn (cổng + API + repo neo giả cùng origin), không nơi nào khác.
  expect(new Set(sent.map((s) => new URL(s.url).host))).toEqual(new Set(['127.0.0.1:4173']))
})

test('a 4 KiB random file that does not match is hashed locally and never sent; no bundle is requested', async ({ page }) => {
  const marker = randomBytes(4096)
  const sent: { url: string; body: Buffer | null }[] = []
  page.on('request', (r) => sent.push({ url: r.url(), body: r.postDataBuffer() }))
  const calls = await mockVerifyApi(page, { requireFile: true, sha256: sha256hex(ORIGINAL) })
  await page.goto(PAGE)
  await page.setInputFiles('input[type=file]', { name: 'khac.bin', mimeType: 'application/octet-stream', buffer: marker })
  await expect(page.getByText('Không khớp')).toBeVisible()
  await expect(page.getByText(`SHA-256: ${sha256hex(marker)}`)).toBeVisible()
  for (const s of sent) if (s.body) {
    expect(s.body.includes(marker.subarray(0, 64))).toBe(false)
    expect(JSON.parse(s.body.toString())).toEqual({ sha256: sha256hex(marker) })
  }
  expect(calls.urls.filter((u) => u.includes(':bundle'))).toEqual([])
  await expect(page.getByTestId('verdict')).not.toHaveText(/^Hợp lệ/)
})

test('server says the file matches but the signed bundle disagrees → Không hợp lệ', async ({ page }) => {
  const marker = randomBytes(4096)
  await mockVerifyApi(page, { requireFile: true, sha256: sha256hex(marker) })
  await page.goto(PAGE)
  await page.setInputFiles('input[type=file]', { name: 'gia.bin', mimeType: 'application/octet-stream', buffer: marker })
  await expect(page.getByText('Không hợp lệ')).toBeVisible()
  await expect(page.getByText(/FILE_NOT_IN_SEAL/)).toBeVisible()
  await expect(page.getByText('tệp bạn chọn không nằm trong niêm phong')).toBeVisible()
})

test('server says VALID but bundle signature is broken → Không hợp lệ', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false, bundleVector: 'status-lies' })
  await page.goto(PAGE)
  await expect(page.getByText('Không hợp lệ')).toBeVisible()
  await expect(page.getByText(/SIGNATURE/)).toBeVisible()
  // Không hiện đơn vị, trường công khai hay nút tải gói của một niêm phong không đáng tin.
  await expect(page.getByText('Đơn vị niêm phong')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Tải gói/ })).toHaveCount(0)
})

test('anchor repo from server is ignored; only configured base is fetched', async ({ page }) => {
  const hosts = new Set<string>(); page.on('request', (r) => hosts.add(new URL(r.url()).host))
  const calls = await mockVerifyApi(page, { requireFile: false, anchoredRepo: 'https://evil.example/repo' })
  await page.goto(PAGE); await expect(page.getByText(OK_PINNED)).toBeVisible()
  expect([...hosts].some((h) => h.includes('evil'))).toBe(false)
  expect(calls.urls.some((u) => u.startsWith('ANCHOR keys/seal-key/'))).toBe(true)
  await expect(page.getByText(/evil\.example/)).toHaveCount(0)
})

test('anchor repo unreachable → chưa đối chiếu, not Không hợp lệ', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false, anchor: 'down' })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText(OK_UNPINNED)
  await expect(page.getByText('Không truy cập được repo neo — chưa đối chiếu')).toBeVisible()
  await expect(page.getByText('Không hợp lệ')).toHaveCount(0)
})

test('anchor repo answers 404 for the key → Không hợp lệ (genuine pinned failure)', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false, anchor: 'empty' })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText('Không hợp lệ')
  await expect(page.getByText(/KEY_NOT_ANCHORED/)).toBeVisible()
  await expect(page.getByText('Không truy cập được repo neo')).toHaveCount(0)
})

test('valid seal shows issuer, labelled public fields and Vietnam time, and downloads the server bundle', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText(OK_PINNED)
  await expect(page.getByText('Đơn vị niêm phong: Trường Đại học Thử (mã định danh: TDHT-01)')).toBeVisible()
  await expect(page.getByText('Số văn bản', { exact: true })).toBeVisible()
  await expect(page.getByText('Quyết định thử')).toBeVisible()
  await expect(page.getByText('Thời điểm niêm phong', { exact: true })).toBeVisible()
  await expect(page.getByText(/16:00:00 21\/10\/2026 \(giờ Việt Nam\)/)).toBeVisible()
  await expect(page.getByText('Máy chủ báo', { exact: true })).toBeVisible()
  await expect(page.getByText('Trình duyệt tự kiểm', { exact: true })).toBeVisible()
  const [download] = await Promise.all([
    page.waitForEvent('download'), page.getByRole('button', { name: /Tải gói bằng chứng/ }).click(),
  ])
  expect(download.suggestedFilename()).toBe(`dxos-seal-${SEAL_ID}.json`)
})

test('server-side revocation can only lower the verdict: Đã thu hồi even though the bundle verifies', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false, view: { status: 'REVOKED' } })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText('Đã thu hồi')
})

test('a bundle of a different seal cannot stand in for the one being checked', async ({ page }) => {
  // Người dùng quét mã ZZZ…, máy chủ (giả) trả gói thật của ABC….
  const other = 'ZZZZZZZZZZZZZZZZZZZZZZZZZZ'
  await mockVerifyApi(page, { requireFile: false, routeId: other })
  await page.goto(`/apps/verify/#${other}`)
  await expect(page.getByTestId('verdict')).toHaveText('Không hợp lệ')
  await expect(page.getByText('gói này thuộc niêm phong khác mã đang kiểm')).toBeVisible()
})

test('404 and 503 are never reported as Không hợp lệ', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false, viewStatus: 404 })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText('Không tìm thấy')
  await page.unrouteAll()
  await mockVerifyApi(page, { requireFile: false, viewStatus: 503 })
  await page.goto(PAGE)
  await page.reload()
  await expect(page.getByTestId('verdict')).toHaveText('Chưa kiểm được')
  await expect(page.getByText('Tạm thời chưa kiểm được chữ ký, thử lại sau')).toBeVisible()
})

test('a malformed fragment makes no API call', async ({ page }) => {
  const calls = await mockVerifyApi(page, { requireFile: false })
  await page.goto('/apps/verify/#../../etc/passwd')
  await expect(page.getByText('Mã niêm phong không đúng dạng')).toBeVisible()
  expect(calls.urls).toEqual([])
})

test('typing a code and pressing Enter loads it; the input has a label', async ({ page }) => {
  await mockVerifyApi(page, { requireFile: false })
  await page.goto('/apps/verify/')
  await page.getByLabel('Nhập mã niêm phong (26 ký tự)').fill(SEAL_ID.toLowerCase())
  await page.getByLabel('Nhập mã niêm phong (26 ký tự)').press('Enter')
  await expect(page.getByTestId('verdict')).toHaveText(OK_PINNED)
  await expect(page).toHaveURL(new RegExp(`#${SEAL_ID}$`))
})

test('server-chosen anchor path fails while the anchor repo answers → Không hợp lệ, not the unpinned fallback', async ({ page }) => {
  // Mô phỏng máy chủ bị chiếm chọn key_version khổng lồ: mọi đường dẫn do gói chọn bị hủy, còn
  // keys/sth-key/v1.pub (đường dẫn cố định dùng để thăm dò) vẫn trả lời.
  const calls = await mockVerifyApi(page, { requireFile: false, anchor: 'poisoned' })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText('Không hợp lệ')
  await expect(page.getByText('Không truy cập được repo neo')).toHaveCount(0)
  await expect(page.getByText('Đơn vị niêm phong')).toHaveCount(0)
  expect(calls.urls).toContain('ANCHOR keys/sth-key/v1.pub')
})

test('WAIT_STH with require_file: the file can be checked (:check only), no bundle and no local verdict', async ({ page }) => {
  const sent: string[] = []
  page.on('request', (r) => { if (r.postDataBuffer()) sent.push(new URL(r.url()).pathname) })
  const calls = await mockVerifyApi(page, {
    requireFile: true, sha256: sha256hex(ORIGINAL),
    view: { inclusion: { leaf_index: 5, tree_size: null, verified: false, anchored: null } },
  })
  await page.goto(PAGE)
  await expect(page.getByTestId('verdict')).toHaveText('Chữ ký hợp lệ — đang chờ công bố vào sổ cái')
  await page.setInputFiles('input[type=file]', { name: 'van-ban.pdf', mimeType: 'application/pdf', buffer: ORIGINAL })
  await expect(page.getByText('Khớp: tệp này đúng là tệp đã được niêm phong.')).toBeVisible()
  await expect(page.getByTestId('verdict')).toHaveText('Chữ ký hợp lệ — đang chờ công bố vào sổ cái')
  expect(sent).toEqual([`/verify/v1/seals/${SEAL_ID}:check`])
  expect(calls.urls.filter((u) => u.includes('bundle') || u.startsWith('ANCHOR'))).toEqual([])
  await expect(page.getByRole('button', { name: /Tải gói/ })).toHaveCount(0)
})
