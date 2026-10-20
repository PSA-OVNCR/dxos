# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Giao diện ký số dùng chung cho STH (``sth-key``) và niêm phong (``seal-key``)."""

from dataclasses import dataclass
from typing import Literal, Protocol

KeyName = Literal["seal-key", "sth-key"]
KEY_NAMES: tuple[KeyName, ...] = ("seal-key", "sth-key")


@dataclass
class SignResult:
    signature: bytes
    key_version: int


class KmsUnavailable(Exception):
    """KMS bị khóa (sealed), từ chối hoặc không liên lạc được → mọi việc ký đều dừng (fail-closed, F8)."""


class Signer(Protocol):
    async def sign(self, key: KeyName, data: bytes, *, key_version: int | None = None) -> SignResult: ...

    async def public_keys(self) -> dict[KeyName, dict[int, bytes]]: ...
