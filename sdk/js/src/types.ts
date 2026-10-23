// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Kiểu dữ liệu theo hợp đồng HTTP của lõi (docs/api/contract-tier2.md).

export type SealState = 'NONE' | 'SEAL_PENDING' | 'SEALED' | 'REVOKED'

export interface DxRecord {
  id: string
  app_id: string
  collection: string
  data: Record<string, unknown>
  is_owner: boolean
  version: number
  seal_state: SealState
  wf_state: string | null
  created_at: string
  updated_at: string
}

export interface VersionRef {
  id: string
  version: number
}

export type UploadStatus =
  | { status: 'STAGING' }
  | { status: 'CLEAN'; sha256: string }
  | { status: 'INFECTED'; reason: string | null }
  | { status: 'REJECTED'; reason: string }

/**
 * Trạng thái dò dữ liệu cá nhân của một tệp CLEAN, chỉ có khi collection đòi dò PII tài liệu (contract-tier2.md 3.4).
 * `counts` chỉ gồm loại có n > 0 (tổng bằng `findings`); chỉ là số đếm, không bao giờ là giá trị.
 * `redacted` = có bản che (`variant=redacted`) để tải.
 */
export interface AttachmentPii {
  status: 'PENDING' | 'DONE' | 'TOO_LARGE' | 'FAILED'
  findings: number
  counts: Record<string, number>
  redacted: boolean
}

export interface AttachmentItem {
  upload_id: string
  status: UploadStatus['status']
  sha256: string | null
  reason: string | null
  created_at: string
  /** `null` khi collection không dò PII tài liệu hoặc tệp chưa CLEAN; máy chủ luôn gửi khoá này. */
  pii: AttachmentPii | null
}

/** Bản của một tệp để tải: `original` có thể bị khóa theo quyền xem PII, `redacted` chỉ có khi đã dựng. */
export type ObjectVariant = 'original' | 'redacted'

export interface TaskItem {
  task_id: string
  task_key: string
  name: string
  record_id: string
  collection: string
  created: string
}

export type BulkResult =
  | { ok: true; id: string }
  | { ok: false; row: number; error: { type: string; title: string; errors?: { path: string; msg: string }[] } }

export interface SealInfo {
  seal_id: string
  seal_state: Exclude<SealState, 'NONE'>
  issued_at: string | null
  key_version: number | null
  public_fields: Record<string, unknown>
  verify_url: string
}

export interface ManifestView {
  app: { id: string; version: string; name: string }
  roles: string[]
  collections: Record<string, CollectionView>
  // decisions[task] có thể là [] = không hạn chế (hợp đồng §2.9)
  workflow: {
    tasks: Record<string, { role: string; guards: string[] }>
    decisions: Record<string, string[]>
  } | null
  policies: {
    pii: { reveal_roles: string[]; erase_roles: string[] }
    seal: { public_fields: string[]; revoke_roles: string[] } | null
    verify: { public: boolean; require_file: boolean } | null
  }
}

export interface CollectionView {
  fields: Record<string, FieldView>
  attachments: { kinds: string[]; max_mb: number; min: number } | null
  access: { read: string[]; create: string[]; update: string[] }
}

export interface FieldView {
  type: 'string' | 'sequence' | 'integer' | 'boolean' | 'date'
  required: boolean
  public: boolean
  pii: string | null
  format: string | null
  label: string | null
}
