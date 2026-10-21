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

export interface AttachmentItem {
  upload_id: string
  status: UploadStatus['status']
  sha256: string | null
  reason: string | null
  created_at: string
}

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
