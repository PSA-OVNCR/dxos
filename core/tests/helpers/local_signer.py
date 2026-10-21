# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Signer ed25519 trong bộ nhớ — **chỉ dùng trong test** (sản phẩm luôn ký qua OpenBao transit)."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dxos_core.kms.base import KeyName, KmsUnavailable, SignResult

# Bytes của lần ký thăm dò R-1 (dxos_core.workflow.service.KMS_PROBE).
KMS_PROBE = b"dxos-kms-probe"


class LocalSigner:
    def __init__(self, share_keys_with: "LocalSigner | None" = None) -> None:
        """``share_keys_with``: dùng chung bộ khóa với signer khác (cùng khóa công khai, cùng tuyên bố
        khóa)."""
        if share_keys_with is not None:
            self._keys = share_keys_with._keys
            return
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


class FlakySigner(LocalSigner):
    """KMS lỗi theo cờ ``fail`` (bật/tắt giữa chừng); lần ký thăm dò ``b"dxos-kms-probe"`` luôn đạt khi
    ``probe_ok`` (mặc định), để R-1 cho qua mà lần ký thật sau Flowable lỗi (AT-20b). ``public_keys`` luôn
    đạt."""

    def __init__(self, share_keys_with: LocalSigner | None = None) -> None:
        super().__init__(share_keys_with)
        self.fail = False
        self.probe_ok = True

    async def sign(self, key: KeyName, data: bytes, *, key_version: int | None = None) -> SignResult:
        if data == KMS_PROBE and self.probe_ok:
            return await super().sign(key, data, key_version=key_version)
        if self.fail:
            raise KmsUnavailable("OpenBao sealed (giả lập, FlakySigner)")
        return await super().sign(key, data, key_version=key_version)
