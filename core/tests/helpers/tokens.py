# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: phát JWT giống Keycloak realm `dxos` bằng khóa RSA sinh lúc chạy test.

Dùng chung cho test identity, PDP, Records API, upload (Plan 01 Task 10, 12, 13, 14).
Khóa chỉ tồn tại trong bộ nhớ của tiến trình test.
"""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://localhost/auth/realms/dxos"
AUDIENCE = "dxos-api"
JWKS_URL = "http://keycloak.invalid/auth/realms/dxos/protocol/openid-connect/certs"
KID = "test-kid-1"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks() -> dict[str, Any]:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def make_token(sub: str, roles: list[str], /, **overrides: Any) -> str:
    """Token RS256 hợp lệ; ``overrides`` ghi đè claim (giá trị ``None`` thì bỏ claim).

    Khóa đặc biệt: ``alg`` (RS256 | HS256 | none), ``kid``, ``wrong_key=True`` (ký bằng khóa khác).
    """
    alg = overrides.pop("alg", "RS256")
    kid = overrides.pop("kid", KID)
    wrong_key = overrides.pop("wrong_key", False)
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": sub, "iat": now, "nbf": now, "exp": now + 300,
        "realm_access": {"roles": list(roles)}, "azp": "dxos-spa",
    }
    for k, v in overrides.items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    headers = {"kid": kid} if kid else {}
    if alg == "none":
        return jwt.encode(claims, None, algorithm="none", headers=headers)
    if alg == "HS256":
        return jwt.encode(claims, "changeme-hmac-secret-for-alg-confusion-test", algorithm="HS256",
                          headers=headers)
    return jwt.encode(claims, _OTHER_KEY if wrong_key else _KEY, algorithm="RS256", headers=headers)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
