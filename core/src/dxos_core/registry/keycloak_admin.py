# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client Admin API Keycloak của installer (service account ``dxos-installer``, Plan 02 Task 11).

Service account chỉ có client role ``realm-management/manage-realm`` (P2-D12): Keycloak 26 cần quyền này để
tạo realm role, nhưng quyền đó rộng hơn nhiều (đổi được cả realm). Vì vậy client này cố ý hẹp:

- ``ensure_app_roles`` chỉ gọi ``POST {admin}/roles`` (tạo realm role). Tên role luôn do client dựng là
  ``app:<app_id>:<role>`` và phải khớp đúng mẫu ``_APP_ROLE`` mà lõi dùng khi đọc token (``identity/jwt.py``).
  Tên sai -> ``ValueError`` trước mọi request (kể cả request lấy token). Role đã có (409) không phải lỗi.
- ``default_role_composites`` chỉ đọc (``GET`` realm và composite của role mặc định), cho ``/admin/v1/health``
  kiểm ``default-roles-dxos`` không chứa ``dxos-admin`` hay ``app:*``.

Token lấy bằng ``client_credentials``, cache tới trước ``expires_in`` một khoảng an toàn. Mạng lỗi, 5xx, 401,
403, mã lạ hay phản hồi sai dạng -> ``IdpAdminUnavailable`` (API trả 503). Thông báo lỗi, log và ``repr``
không bao giờ chứa secret, token hay nội dung phản hồi của Keycloak.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from dxos_core.identity.jwt import _APP_ROLE
from dxos_core.settings import read_secret

if TYPE_CHECKING:
    from dxos_core.settings import Settings

# Làm mới token khi còn ít hơn chừng này giây (tránh gửi token sắp hết hạn).
_EXPIRY_MARGIN_S = 30.0
# Id role của Keycloak (uuid) đặt vào đường dẫn: chỉ chữ, số, gạch ngang.
_ROLE_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class IdpAdminUnavailable(Exception):  # noqa: N818 (tên theo plan)
    """Không gọi được Admin API Keycloak (mạng, 5xx, 401/403, phản hồi sai dạng) -> API trả 503."""


def _app_role_names(app_id: str, roles: Sequence[str]) -> list[str]:
    """Dựng ``app:<app_id>:<role>`` cho từng role, bỏ trùng, giữ thứ tự; tên nào sai mẫu -> ``ValueError``."""
    if isinstance(roles, str):
        raise TypeError("roles phải là danh sách tên, không phải một chuỗi")
    out: list[str] = []
    for role in roles:
        if not isinstance(app_id, str) or not isinstance(role, str):
            raise ValueError("app_id và tên role phải là chuỗi")
        name = f"app:{app_id}:{role}"
        m = _APP_ROLE.fullmatch(name)
        # Kiểm lại từng phần: chặn trường hợp role chứa ':' làm dịch ranh giới app_id/role.
        if not m or m.group(1) != app_id or m.group(2) != role:
            raise ValueError("tên role ứng dụng không hợp lệ")
        if name not in out:
            out.append(name)
    return out


def _check_url(url: str, what: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"{what} phải là URL http(s)")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError(f"{what} không được chứa thông tin đăng nhập")
    return url.rstrip("/")


class KeycloakAdmin:
    def __init__(self, token_url: str, admin_url: str, client_id: str, secret: str, *,
                 timeout_s: float = 10.0, verify: bool | str = True) -> None:
        """``verify``: kiểm chứng chỉ TLS (mặc định có). Trong stack, lõi gọi ``http://keycloak:8080`` trong
        ``net-idp`` nên không dùng; test ``infra`` qua Caddy có thể truyền đường dẫn CA nội bộ."""
        self._token_url = _check_url(token_url, "token_url")
        self._admin_url = _check_url(admin_url, "admin_url")
        self._client_id = client_id
        self._secret = secret
        self._timeout = timeout_s
        self._verify = verify
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = asyncio.Lock()

    def __repr__(self) -> str:
        return f"KeycloakAdmin({self._admin_url!r}, client_id={self._client_id!r})"

    __str__ = __repr__

    # ------------------------------------------------------------ truyền tải
    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, verify=self._verify, trust_env=False)

    async def _access_token(self) -> str:
        async with self._lock:
            if self._token is not None and time.monotonic() < self._token_expires_at:
                return self._token
            try:
                async with self._client() as client:
                    resp = await client.post(self._token_url, data={
                        "grant_type": "client_credentials", "client_id": self._client_id,
                        "client_secret": self._secret})
            except httpx.HTTPError as exc:
                raise IdpAdminUnavailable(f"Keycloak token: {type(exc).__name__}") from None
            if resp.status_code != 200:
                raise IdpAdminUnavailable(f"Keycloak token: HTTP {resp.status_code}")
            try:
                body = resp.json()
            except ValueError:
                raise IdpAdminUnavailable("Keycloak token: phản hồi không phải JSON") from None
            token = body.get("access_token") if isinstance(body, dict) else None
            expires_in = body.get("expires_in") if isinstance(body, dict) else None
            if not isinstance(token, str) or not token or not isinstance(expires_in, int | float) \
                    or isinstance(expires_in, bool):
                raise IdpAdminUnavailable("Keycloak token: phản hồi sai dạng")
            self._token = token
            # Token còn ít hơn biên an toàn thì dùng một lần, không cache.
            self._token_expires_at = time.monotonic() + float(expires_in) - _EXPIRY_MARGIN_S
            return token

    async def _send(self, method: str, path: str, *, ok: tuple[int, ...], **kwargs: Any) -> httpx.Response:
        token = await self._access_token()
        try:
            async with self._client() as client:
                resp = await client.request(method, f"{self._admin_url}{path}",
                                            headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except httpx.HTTPError as exc:
            raise IdpAdminUnavailable(f"Keycloak admin {method} {path}: {type(exc).__name__}") from None
        if resp.status_code == 401:
            async with self._lock:   # token bị thu hồi/hết hạn sớm: lần sau lấy token mới
                if self._token == token:
                    self._token, self._token_expires_at = None, 0.0
        if resp.status_code not in ok:
            raise IdpAdminUnavailable(f"Keycloak admin {method} {path}: HTTP {resp.status_code}")
        return resp

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            raise IdpAdminUnavailable("Keycloak admin: phản hồi không phải JSON") from None

    # ------------------------------------------------------------ API
    async def ensure_app_roles(self, app_id: str, roles: Sequence[str]) -> list[str]:
        """Tạo các realm role ``app:<app_id>:<role>`` còn thiếu; trả các role **vừa tạo** trong lần gọi này.

        Kiểm toàn bộ tên trước khi gửi request đầu tiên (``ValueError``, không gọi mạng).
        """
        names = _app_role_names(app_id, roles)
        created: list[str] = []
        for name in names:
            resp = await self._send("POST", "/roles", ok=(201, 409), json={"name": name})
            if resp.status_code == 201:
                created.append(name)
        return created

    async def default_role_composites(self) -> list[str]:
        """Tên các role (realm và client) gộp trong role mặc định của realm (``default-roles-dxos``)."""
        realm = self._json(await self._send("GET", "", ok=(200,)))
        default_role = realm.get("defaultRole") if isinstance(realm, dict) else None
        role_id = default_role.get("id") if isinstance(default_role, dict) else None
        if not isinstance(role_id, str) or not _ROLE_ID.fullmatch(role_id):
            raise IdpAdminUnavailable("Keycloak admin: realm không có role mặc định hợp lệ")
        rows = self._json(await self._send("GET", f"/roles-by-id/{role_id}/composites", ok=(200,)))
        if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str)
                                                 for r in rows):
            raise IdpAdminUnavailable("Keycloak admin: danh sách composite sai dạng")
        return sorted(r["name"] for r in rows)


def keycloak_admin_from_settings(settings: Settings) -> KeycloakAdmin | None:
    """Client theo cấu hình; ``None`` khi chưa đặt ``installer_client_secret_file`` (duyệt app trả 503).

    Đọc tệp bí mật ở thời điểm dùng. Không đọc được hoặc rỗng -> ``IdpAdminUnavailable`` (không lộ đường dẫn).
    """
    if settings.installer_client_secret_file is None:
        return None
    try:
        secret = read_secret(settings.installer_client_secret_file)
    except (OSError, ValueError):
        raise IdpAdminUnavailable("không đọc được secret của installer") from None
    return KeycloakAdmin(settings.keycloak_token_url, settings.keycloak_admin_url,
                         settings.installer_client_id, secret)


class KeycloakAdminSource:
    """Một ``KeycloakAdmin`` duy nhất cho tiến trình (đặt ở ``app.state.kc_admin``), để cache token có tác
    dụng.

    ``get(settings)`` đọc lại tệp secret mỗi lần (rẻ) và chỉ tạo client mới khi cấu hình hoặc nội dung secret
    đổi (xoay secret không cần khởi động lại). Chưa đặt ``installer_client_secret_file`` → ``None`` (duyệt app
    trả 503); không đọc được tệp → ``IdpAdminUnavailable``. ``fixed(client)``: luôn trả ``client`` (test).
    """

    def __init__(self) -> None:
        self._fixed: object | None = None
        self._client: KeycloakAdmin | None = None
        self._key: tuple | None = None

    @classmethod
    def fixed(cls, client: object) -> KeycloakAdminSource:
        src = cls()
        src._fixed = client
        return src

    def get(self, settings: Settings) -> KeycloakAdmin | None:
        if self._fixed is not None:
            return self._fixed  # type: ignore[return-value]
        if settings.installer_client_secret_file is None:
            return None
        try:
            secret = read_secret(settings.installer_client_secret_file)
        except (OSError, ValueError):
            raise IdpAdminUnavailable("không đọc được secret của installer") from None
        key = (settings.keycloak_token_url, settings.keycloak_admin_url, settings.installer_client_id,
               hashlib.sha256(secret.encode("utf-8")).hexdigest())
        if self._client is None or key != self._key:
            self._client = KeycloakAdmin(settings.keycloak_token_url, settings.keycloak_admin_url,
                                         settings.installer_client_id, secret)
            self._key = key
        return self._client
