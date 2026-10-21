// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
import { createAuth } from 'dxos-sdk-js'
import { boot } from './boot'
import { BASE } from './session'
import './style.css'

void boot({ auth: createAuth({ appBase: BASE }), mount: '#app' })
