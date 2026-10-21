// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Điểm vào công khai của dxos-sdk-js (các mô-đun auth/proof được Task 3–4 bổ sung).
export { DxosClient } from './client'
export type { ClientOptions } from './client'
export { ApiError, slugOf } from './errors'
export type * from './types'
export { appRoles, createAuth, settingsFor } from './auth'
export type { AuthConfig, DxosAuth } from './auth'
