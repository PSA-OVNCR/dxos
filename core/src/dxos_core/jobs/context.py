# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Ngữ cảnh dùng chung cho các việc nền của worker."""

from dataclasses import dataclass
from typing import Any

import asyncpg

from dxos_core.settings import Settings


@dataclass
class WorkerContext:
    pool: asyncpg.Pool
    store: Any            # dxos_core.objects.storage.ObjectStore
    settings: Settings
    hmac_key: bytes
    signer: Any = None    # dxos_core.kms.base.Signer (Task 15)
