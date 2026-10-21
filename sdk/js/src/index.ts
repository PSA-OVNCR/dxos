// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
// Điểm vào công khai của dxos-sdk-js.
export { DxosClient } from './client'
export type { ClientOptions } from './client'
export { ApiError, slugOf } from './errors'
export type * from './types'
export { appRoles, createAuth, settingsFor } from './auth'
export type { AuthConfig, DxosAuth } from './auth'
export { canonicalBytes, parseJsonLossless } from './proof/canonical'
export type { Json } from './proof/canonical'
export { leafHash, verifyConsistency, verifyInclusion } from './proof/merkle'
export { verifyBundle } from './proof/bundle'
export type { BundleResult, FailCode, VerifyOptions } from './proof/bundle'
export { rawAnchor } from './proof/anchor'
export type { AnchorSource } from './proof/anchor'
export { sha256Hex } from './proof/hash'
export { formatVn, formatVnDate, hasRole, sealLabel } from './format'
