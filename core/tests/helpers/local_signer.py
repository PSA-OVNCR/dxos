# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Signer ed25519 trong bộ nhớ — **chỉ dùng trong test** (sản phẩm luôn ký qua OpenBao transit)."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dxos_core.kms.base import KeyName, KmsUnavailable, SignResult


class LocalSigner:
    def __init__(self) -> None:
        self._keys: dict[str, dict[int, Ed25519PrivateKey]] = {
            "seal-key": {1: Ed25519PrivateKey.generate()}, "sth-key": {1: Ed25519PrivateKey.generate()}}

    def rotate(self, key: KeyName) -> int:
        v = max(self._keys[key]) + 1
        self._keys[key][v] = Ed25519PrivateKey.generate()
        return v

    async def sign(self, key: KeyName, data: bytes, *, key_version: int | None = None) -> SignResult:
        v = key_version or max(self._keys[key])
        return SignResult(signature=self._keys[key][v].sign(data), key_version=v)

    async def public_keys(self) -> dict[KeyName, dict[int, bytes]]:
        raw = (Encoding.Raw, PublicFormat.Raw)
        return {name: {v: k.public_key().public_bytes(*raw) for v, k in vers.items()}
                for name, vers in self._keys.items()}


class FailingSigner(LocalSigner):
    """OpenBao bị khóa hoặc mất kết nối."""

    async def sign(self, key: KeyName, data: bytes, *, key_version: int | None = None) -> SignResult:
        raise KmsUnavailable("OpenBao sealed (giả lập)")
