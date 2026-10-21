# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client OpenBao transit (API tương thích Vault). Token của lõi chỉ có ``sign`` + đọc khóa công khai."""

import base64
import re

import httpx

from dxos_core.kms.base import KEY_NAMES, KeyName, KmsUnavailable, SignResult

_SIG = re.compile(r"^vault:v(\d+):([A-Za-z0-9+/=]+)$")


class OpenBaoTransit:
    def __init__(self, addr: str, token: str, *, timeout_s: float = 5.0) -> None:
        self.addr, self._token, self._timeout = addr.rstrip("/"), token, timeout_s

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, f"{self.addr}/v1/{path}", json=json,
                                            headers={"X-Vault-Token": self._token})
        except httpx.HTTPError as exc:
            raise KmsUnavailable(f"OpenBao {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise KmsUnavailable(f"OpenBao trả HTTP {resp.status_code} cho {path}")
        try:
            return resp.json()["data"]
        except (ValueError, KeyError) as exc:
            raise KmsUnavailable("OpenBao trả dữ liệu không hợp lệ") from exc

    async def sign(self, key: KeyName, data: bytes, *, key_version: int | None = None) -> SignResult:
        body: dict = {"input": base64.b64encode(data).decode("ascii")}
        if key_version is not None:
            body["key_version"] = key_version
        out = await self._request("POST", f"transit/sign/{key}", body)
        m = _SIG.fullmatch(str(out.get("signature", "")))
        if not m:
            raise KmsUnavailable("chữ ký OpenBao sai định dạng")
        return SignResult(signature=base64.b64decode(m.group(2)), key_version=int(m.group(1)))

    async def health(self) -> None:
        """``GET /v1/sys/health`` (không cần token): 200 là đã khởi tạo, đã mở khóa, đang active.
        Mã khác (503 sealed, 501 chưa khởi tạo, 429 standby…) hay lỗi mạng -> ``KmsUnavailable``."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self.addr}/v1/sys/health")
        except httpx.HTTPError as exc:
            raise KmsUnavailable(f"OpenBao {type(exc).__name__}") from exc
        if resp.status_code != 200:
            reason = {503: "sealed", 501: "not initialized", 429: "standby"}.get(resp.status_code,
                                                                                 f"HTTP {resp.status_code}")
            raise KmsUnavailable(f"OpenBao sys/health: {reason}")

    async def renew_self(self) -> int:
        """Gia hạn token của lõi (token period do init.sh cấp); trả TTL mới (giây)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self.addr}/v1/auth/token/renew-self", json={},
                                         headers={"X-Vault-Token": self._token})
        except httpx.HTTPError as exc:
            raise KmsUnavailable(f"OpenBao {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise KmsUnavailable(f"OpenBao trả HTTP {resp.status_code} khi gia hạn token")
        try:
            return int(resp.json()["auth"]["lease_duration"])
        except (ValueError, KeyError, TypeError) as exc:
            raise KmsUnavailable("OpenBao trả dữ liệu gia hạn không hợp lệ") from exc

    async def public_keys(self) -> dict[KeyName, dict[int, bytes]]:
        result: dict[KeyName, dict[int, bytes]] = {}
        for name in KEY_NAMES:
            out = await self._request("GET", f"transit/keys/{name}")
            if out.get("type") != "ed25519":
                raise KmsUnavailable(f"{name} không phải khóa ed25519")
            result[name] = {int(v): base64.b64decode(k["public_key"]) for v, k in out.get("keys", {}).items()}
        return result
