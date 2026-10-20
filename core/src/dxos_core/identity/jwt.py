# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm access token của Keycloak realm ``dxos``.

- Chỉ chấp nhận **RS256** (chặn ``none`` và nhầm lẫn thuật toán HS256/RS256).
- Bắt buộc ``iss``, ``aud`` (chứa ``dxos-api``), ``exp``, ``sub``; kiểm ``nbf`` nếu có.
- Khóa lấy từ JWKS nội bộ, cache ``cache_ttl_s``; gặp ``kid`` lạ thì tải lại tối đa một lần mỗi 30 giây
  (Keycloak xoay khóa) để kẻ gửi token rác không biến lõi thành công cụ dội vào Keycloak.
- Vai trò lấy từ ``realm_access.roles`` (D3); ``dxos-admin`` là quản trị nền tảng, không mặc nhiên đọc
  được dữ liệu app (D4, xử lý ở PDP).
"""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

ADMIN_ROLE = "dxos-admin"
_ALGORITHMS = ["RS256"]
_FORCED_REFRESH_MIN_INTERVAL_S = 30.0
_APP_ROLE = re.compile(r"^app:([a-z][a-z0-9-]{1,62}):([a-z][a-z0-9_]{0,62})$")


@dataclass(frozen=True)
class Principal:
    sub: str
    roles: frozenset[str]
    is_admin: bool


class AuthError(Exception):
    """Token không hợp lệ (→ 401)."""


class IdpUnavailable(AuthError):
    """Không lấy được JWKS từ Keycloak (→ 503)."""


def app_roles(p: Principal, app_id: str) -> frozenset[str]:
    """Tên vai trò (đã bỏ tiền tố ``app:<id>:``) của đúng ``app_id``; vai trò sai dạng bị bỏ qua."""
    out = set()
    for role in p.roles:
        m = _APP_ROLE.fullmatch(role)
        if m and m.group(1) == app_id:
            out.add(m.group(2))
    return frozenset(out)


class JwksVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str, cache_ttl_s: int = 300) -> None:
        self.jwks_url, self.issuer, self.audience, self.cache_ttl_s = jwks_url, issuer, audience, cache_ttl_s
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._last_forced = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.jwks_url)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IdpUnavailable(f"không tải được JWKS: {type(exc).__name__}") from exc
        keys = {}
        for jwk in data.get("keys", []):
            if jwk.get("kty") == "RSA" and jwk.get("use", "sig") == "sig" and jwk.get("kid"):
                try:
                    keys[jwk["kid"]] = jwt.PyJWK.from_dict(jwk, algorithm="RS256").key
                except jwt.PyJWKError:
                    continue
        self._keys, self._fetched_at = keys, time.monotonic()

    async def _key_for(self, kid: str) -> Any:
        async with self._lock:
            now = time.monotonic()
            if not self._keys or now - self._fetched_at > self.cache_ttl_s:
                await self._fetch()
            elif kid not in self._keys and now - self._last_forced > _FORCED_REFRESH_MIN_INTERVAL_S:
                self._last_forced = now
                await self._fetch()
            key = self._keys.get(kid)
        if key is None:
            raise AuthError("kid không có trong JWKS")
        return key

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("token sai định dạng") from exc
        if header.get("alg") not in _ALGORITHMS:
            raise AuthError("chỉ chấp nhận RS256")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise AuthError("token thiếu kid")
        key = await self._key_for(kid)
        try:
            claims = jwt.decode(
                token, key, algorithms=_ALGORITHMS, audience=self.audience, issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]}, leeway=10,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"token bị từ chối: {type(exc).__name__}") from exc
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise AuthError("sub không hợp lệ")
        raw_roles = (claims.get("realm_access") or {}).get("roles")
        roles = frozenset(r for r in raw_roles if isinstance(r, str)) if isinstance(raw_roles, list) \
            else frozenset()
        return Principal(sub=sub, roles=roles, is_admin=ADMIN_ROLE in roles)
