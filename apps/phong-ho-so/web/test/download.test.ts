// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest'
import { pdfFileName, saveBlob } from '../src/download'

afterEach(() => { vi.restoreAllMocks() })

test('saveBlob clicks a temporary download link and releases the object URL', () => {
  const created = vi.fn(() => 'blob:dxos-1')
  const revoked = vi.fn()
  Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked })
  const seen: { href: string; download: string; connected: boolean }[] = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    seen.push({ href: this.href, download: this.download, connected: this.isConnected })
  })
  const blob = new Blob(['%PDF'])
  saveBlob(blob, '02-QĐ-SM.pdf')
  expect(created).toHaveBeenCalledWith(blob)
  expect(seen).toEqual([{ href: 'blob:dxos-1', download: '02-QĐ-SM.pdf', connected: true }])
  expect(document.querySelector('a[download]')).toBeNull()
  expect(revoked).toHaveBeenCalledWith('blob:dxos-1')
})

test('pdfFileName replaces "/" with "-" and falls back to the record id', () => {
  expect(pdfFileName('02/QĐ-SM', 'r1')).toBe('02-QĐ-SM.pdf')
  expect(pdfFileName('02/QĐ-SM', 'r1', 2)).toBe('02-QĐ-SM-2.pdf')
  expect(pdfFileName(undefined, 'r1')).toBe('r1.pdf')
  expect(pdfFileName('', 'r1')).toBe('r1.pdf')
})

test('pdfFileName marks the redacted copy with -che, before the file number', () => {
  expect(pdfFileName('02/QĐ-SM', 'r1', undefined, 'redacted')).toBe('02-QĐ-SM-che.pdf')
  expect(pdfFileName('02/QĐ-SM', 'r1', 2, 'redacted')).toBe('02-QĐ-SM-che-2.pdf')
  expect(pdfFileName(undefined, 'r1', undefined, 'redacted')).toBe('r1-che.pdf')
  expect(pdfFileName('02/QĐ-SM', 'r1', 2, 'original')).toBe('02-QĐ-SM-2.pdf')
})
