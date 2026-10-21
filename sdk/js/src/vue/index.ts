// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Điểm vào "dxos-sdk-js/vue": thành phần Vue dùng chung cho ứng dụng Tầng 2.
export { default as AppShell } from './AppShell.vue'
export { default as ConfirmDialog } from './ConfirmDialog.vue'
export { CORE_SLUGS, messageFor } from './messages'
export { default as PiiPanel } from './PiiPanel.vue'
export { default as ProblemMessage } from './ProblemMessage.vue'
export { default as QuarantineStatus } from './QuarantineStatus.vue'
export { default as RecordForm } from './RecordForm.vue'
export { default as SealPanel } from './SealPanel.vue'
export { default as SealQr } from './SealQr.vue'
export { default as VerifyLink } from './VerifyLink.vue'
export { ERASE_REASONS, REVOKE_REASONS } from './reasons'
export type { Reason } from './reasons'
export { boot } from './boot'
export type { BootDeps } from './boot'
export { connect, createClient, createLoginGuard, createSession, SESSION_KEY, useSession } from './session'
export type { LoginGuard, LoginGuardOptions, MarkerStorage, Session } from './session'
