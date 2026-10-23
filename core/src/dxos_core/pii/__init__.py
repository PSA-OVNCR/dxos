# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dò PII (CCCD, số điện thoại, số tài khoản) trên lớp văn bản của tài liệu, kèm toạ độ để che (S1)."""

from dxos_core.pii.detect import DETECTABLE, Box, Finding, PiiType, detect_text

__all__ = ["DETECTABLE", "Box", "Finding", "PiiType", "detect_text"]
