// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Mã lý do cố định của lõi (docs/api/contract-tier2.md mục 2.8 và 5.2) kèm nhãn tiếng Việt. Lõi kiểm lại mọi mã.
export interface Reason { code: string; label: string }

/** Thu hồi niêm phong. */
export const REVOKE_REASONS: readonly Reason[] = [
  { code: 'superseded', label: 'Đã có văn bản thay thế' },
  { code: 'issued_in_error', label: 'Ban hành nhầm' },
  { code: 'content_error', label: 'Nội dung có sai sót' },
  { code: 'legal_order', label: 'Theo yêu cầu hợp pháp của cơ quan có thẩm quyền' },
  { code: 'other', label: 'Lý do khác' },
]

/** Xóa dữ liệu cá nhân: các trường hợp xóa của Điều 14 khoản 1 Luật 91/2025 (nhãn là diễn giải [ĐX] của đội). */
export const ERASE_REASONS: readonly Reason[] = [
  { code: 'data_subject_request', label: 'Chủ thể dữ liệu yêu cầu xóa' },
  { code: 'purpose_completed', label: 'Đã hoàn thành mục đích xử lý' },
  { code: 'retention_expired', label: 'Hết thời hạn lưu trữ' },
  { code: 'authority_decision', label: 'Theo quyết định của cơ quan có thẩm quyền' },
  { code: 'agreement', label: 'Theo thỏa thuận với chủ thể dữ liệu' },
]
