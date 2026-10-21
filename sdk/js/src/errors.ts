// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Lỗi HTTP của lõi (problem+json, RFC 9457) và lỗi không phải JSON từ cổng (401/413/429).

/** 'https://dxos.dev/problems/guard-failed' -> 'guard-failed'. */
export function slugOf(type: string): string {
  const i = type.lastIndexOf('/')
  return i >= 0 ? type.slice(i + 1) : type
}

export class ApiError extends Error {
  readonly status: number
  readonly slug: string
  readonly title: string
  readonly detail?: string
  /** Toàn bộ thân problem+json (guard, reason, errors...), null nếu thân không phải JSON. */
  readonly problem: Record<string, unknown> | null

  constructor(status: number, slug: string, title: string, detail: string | undefined, problem: Record<string, unknown> | null) {
    super(detail ? `${title}: ${detail}` : title)
    this.name = 'ApiError'
    this.status = status
    this.slug = slug
    this.title = title
    this.detail = detail
    this.problem = problem
  }
}
