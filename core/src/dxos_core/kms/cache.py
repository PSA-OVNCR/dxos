# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cache khóa công khai dùng chung cho ``/verify/v1/keys`` và cổng đối soát (Plan 02 Task 8).

- Khóa công khai của một ``(khóa, phiên bản)`` **không bao giờ đổi**: đã biết thì giữ mãi, không hỏi lại KMS.
- Chỉ hỏi KMS khi gặp phiên bản lạ. KMS đang khóa mà phiên bản còn lạ → ``KeysUnavailable`` (route trả 503),
  **không bao giờ** coi là chữ ký sai.
- KMS trả về khóa khác cho phiên bản đã biết → giữ bản đã biết và ghi log ERROR (dấu hiệu bất thường).

Signer được truyền vào mỗi lần gọi (``app.state.signer`` có thể được thay sau khi khởi động).
"""

import logging

from dxos_core.kms.base import KmsUnavailable, Signer

log = logging.getLogger("dxos_core.kms.cache")


class KeysUnavailable(Exception):  # noqa: N818
    """Phiên bản khóa chưa có trong cache và KMS không trả lời."""


class PublicKeyCache:
    def __init__(self) -> None:
        self._keys: dict[str, dict[int, bytes]] = {}

    def _merge(self, fetched: dict) -> None:
        for name, versions in fetched.items():
            known = self._keys.setdefault(name, {})
            for v, key in versions.items():
                old = known.get(v)
                if old is None:
                    known[v] = bytes(key)
                elif old != key:
                    log.error("KMS trả khóa công khai khác cho %s/v%s đã biết: giữ bản đã biết", name, v)

    def snapshot(self) -> dict[str, dict[int, bytes]]:
        return {name: dict(vers) for name, vers in self._keys.items()}

    async def all(self, signer: Signer) -> dict[str, dict[int, bytes]]:
        """Mọi khóa công khai: hỏi KMS để thấy phiên bản mới; KMS khóa thì trả bản đã biết (nếu có)."""
        try:
            self._merge(await signer.public_keys())
        except KmsUnavailable:
            if not any(self._keys.values()):
                raise
            log.warning("KMS không trả lời: /keys phục vụ khóa công khai đã biết")
        return self.snapshot()

    async def get(self, signer: Signer, name: str, version: int) -> bytes | None:
        """Khóa công khai ``name``/``version``; None nếu KMS trả lời mà không có phiên bản đó."""
        key = self._keys.get(name, {}).get(version)
        if key is not None:
            return key
        try:
            self._merge(await signer.public_keys())
        except KmsUnavailable as exc:
            raise KeysUnavailable(f"{name}/v{version} chưa có trong cache và KMS không trả lời") from exc
        return self._keys.get(name, {}).get(version)
