# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đăng nhập device flow (RFC 8628) với client công khai ``dxos-cli`` và lưu token.

Quy tắc an toàn:
- Token chỉ lưu trong ``$XDG_CONFIG_HOME/dxos/token.json`` (0600, thư mục 0700, ghi nguyên tử), kèm
  ``server`` và ``issuer`` nơi nó được cấp; không bao giờ dùng cho server khác. Refresh token không được giữ.
- Không in hay ghi log access token, refresh token, device code.
- ``DXOS_TOKEN`` (CI, e2e) được dùng cho mọi server và không có hạn.
"""

import json
import os
import re
import time
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx

from dxos_cli.errors import EXIT_LOGIN, EXIT_SERVER, CliError
from dxos_cli.urls import check_endpoint, normalize_server

CLIENT_ID = "dxos-cli"
SCOPE = "openid"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
DEFAULT_INTERVAL = 5
SLOW_DOWN_STEP = 5
_TOKEN_CHARS = re.compile(r"^[\x21-\x7e]+$")  # ASCII in được, không khoảng trắng/điều khiển: chặn chèn header


# ---------------------------------------------------------------- lưu token


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "")
    if not base or not os.path.isabs(base):  # XDG: đường dẫn tương đối không hợp lệ
        base = str(Path.home() / ".config")
    return Path(base) / "dxos"


def token_path() -> Path:
    return config_dir() / "token.json"


def save_token(token: dict) -> Path:
    """Ghi token nguyên tử: tệp tạm tạo sẵn 0600 trong cùng thư mục rồi ``os.replace``; thư mục cha 0700."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    target = directory / "token.json"
    payload = json.dumps(token, ensure_ascii=False, sort_keys=True).encode("utf-8")
    tmp = directory / f".token.json.{os.getpid()}.{os.urandom(6).hex()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def load_token() -> dict | None:
    """Đọc token đã lưu; ``None`` nếu chưa có hoặc tệp hỏng (coi như chưa đăng nhập)."""
    try:
        data = json.loads(token_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    ok = (
        isinstance(data.get("access_token"), str)
        and data["access_token"]
        and isinstance(data.get("server"), str)
        and isinstance(data.get("expires_at"), int | float)
        and not isinstance(data.get("expires_at"), bool)
    )
    return data if ok else None


def _check_token_chars(token: str, where: str) -> str:
    if not _TOKEN_CHARS.match(token):
        raise CliError(f"{where} chứa ký tự không hợp lệ cho token")
    return token


def stored_server() -> str | None:
    tok = load_token()
    return tok["server"] if tok else None


def resolve_token(server: str) -> str:
    """Token cho ``server`` (đã chuẩn hóa): ``DXOS_TOKEN`` rồi tệp đã lưu. Mọi lỗi xác thực là mã thoát 3."""
    env = os.environ.get("DXOS_TOKEN", "").strip()
    if env:
        return _check_token_chars(env, "DXOS_TOKEN")
    hint = f"chạy lại dxos login --server {server}"
    tok = load_token()
    if tok is None:
        raise CliError(f"Chưa đăng nhập: {hint}", EXIT_LOGIN)
    if tok["server"] != server:
        raise CliError(
            f"Token đã lưu được cấp cho {tok['server']}, không dùng cho {server}: {hint}", EXIT_LOGIN
        )
    if time.time() >= tok["expires_at"]:
        raise CliError(f"Token đã hết hạn: {hint}", EXIT_LOGIN)
    return _check_token_chars(tok["access_token"], "Token đã lưu")


# ---------------------------------------------------------------- device flow


def derive_issuer(server: str) -> str:
    """``https://admin.<miền>`` thành ``https://<miền>/auth/realms/dxos``; host khác cần ``--issuer``."""
    parts = urlsplit(server)
    host = parts.hostname or ""
    if not host.startswith("admin.") or len(host) == len("admin."):
        raise CliError(
            "Không suy ra được issuer (host của --server không bắt đầu bằng 'admin.'): truyền --issuer "
            "https://<miền>/auth/realms/dxos"
        )
    port = f":{parts.port}" if parts.port else ""
    return f"https://{host.removeprefix('admin.')}{port}/auth/realms/dxos"


def _post_form(client: httpx.Client, url: str, data: dict) -> httpx.Response:
    try:
        return client.post(url, data=data)
    except httpx.HTTPError as exc:
        raise CliError(f"Lỗi mạng khi gọi {url}: {type(exc).__name__}", EXIT_SERVER) from exc


def _json_obj(resp: httpx.Response, what: str) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise CliError(
            f"{what} trả về nội dung không phải JSON object (HTTP {resp.status_code})", EXIT_SERVER
        )
    return data


def _discover(client: httpx.Client, issuer: str) -> tuple[str, str]:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        raise CliError(f"Lỗi mạng khi đọc {url}: {type(exc).__name__}", EXIT_SERVER) from exc
    if resp.status_code >= 500:
        raise CliError(f"Issuer trả HTTP {resp.status_code} khi đọc {url}", EXIT_SERVER)
    if resp.status_code != 200:
        raise CliError(f"Issuer trả HTTP {resp.status_code} khi đọc {url}")
    doc = _json_obj(resp, "Issuer")
    device, token = doc.get("device_authorization_endpoint"), doc.get("token_endpoint")
    if not isinstance(device, str) or not isinstance(token, str):
        raise CliError(
            "Issuer không công bố device_authorization_endpoint/token_endpoint (dxos-cli đã bật device flow?)"
        )
    return (
        check_endpoint(device, what="device_authorization_endpoint"),
        check_endpoint(token, what="token_endpoint"),
    )


def device_login(server: str, issuer: str | None, verify, *, announce) -> dict:
    """Chạy device flow, lưu token và trả về ``{"server", "issuer", "expires_at"}`` (không chứa token)."""
    server = normalize_server(server)
    issuer = check_endpoint(issuer, what="--issuer") if issuer else derive_issuer(server)
    with httpx.Client(
        timeout=httpx.Timeout(15.0, connect=5.0), verify=verify, follow_redirects=False
    ) as client:
        device_ep, token_ep = _discover(client, issuer)
        resp = _post_form(client, device_ep, {"client_id": CLIENT_ID, "scope": SCOPE})
        if resp.status_code >= 500:
            raise CliError(f"Máy chủ định danh trả HTTP {resp.status_code}", EXIT_SERVER)
        if resp.status_code != 200:
            raise CliError(f"Máy chủ định danh từ chối yêu cầu device flow (HTTP {resp.status_code})")
        grant = _json_obj(resp, "Máy chủ định danh")
        try:
            device_code, user_code = grant["device_code"], grant["user_code"]
            interval = float(grant.get("interval", DEFAULT_INTERVAL))
            expires_in = float(grant.get("expires_in", 600))
        except (KeyError, TypeError, ValueError) as exc:
            raise CliError(
                "Phản hồi device flow thiếu hoặc sai device_code/user_code/interval/expires_in"
            ) from exc
        uri = grant.get("verification_uri_complete")
        if isinstance(uri, str) and uri:
            announce(
                f"Mở liên kết sau trong trình duyệt và xác nhận đăng nhập: {uri}\n(mã xác nhận: {user_code})"
            )
        else:
            announce(f"Mở {grant.get('verification_uri')} trong trình duyệt và nhập mã: {user_code}")
        deadline = monotonic() + expires_in
        interval = max(interval, 0.0)
        while True:
            sleep(interval)
            if monotonic() >= deadline:
                raise CliError(
                    "Hết thời gian chờ xác nhận đăng nhập (mã device đã hết hạn): chạy lại dxos login"
                )
            resp = _post_form(
                client,
                token_ep,
                {"grant_type": DEVICE_GRANT, "device_code": device_code, "client_id": CLIENT_ID},
            )
            if resp.status_code == 200:
                break
            if resp.status_code >= 500:
                raise CliError(f"Máy chủ định danh trả HTTP {resp.status_code} khi lấy token", EXIT_SERVER)
            try:
                error = resp.json().get("error")
            except (ValueError, AttributeError):
                error = None
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += SLOW_DOWN_STEP
                continue
            if error == "expired_token":
                raise CliError("Mã device đã hết hạn: chạy lại dxos login")
            if error == "access_denied":
                raise CliError("Đăng nhập bị từ chối")
            raise CliError(
                f"Đăng nhập thất bại ({error if isinstance(error, str) and len(error) < 60 else 'lỗi lạ'})"
            )
        body = _json_obj(resp, "Máy chủ định danh")
    access = body.get("access_token")
    expires_in_tok = body.get("expires_in")
    if not isinstance(access, str) or not access:
        raise CliError("Máy chủ định danh không trả access_token")
    _check_token_chars(access, "access_token nhận được")
    if isinstance(expires_in_tok, bool) or not isinstance(expires_in_tok, int | float) or expires_in_tok <= 0:
        raise CliError("Máy chủ định danh không trả expires_in hợp lệ")
    record = {
        "access_token": access,
        "expires_at": time.time() + float(expires_in_tok),
        "server": server,
        "issuer": issuer,
    }
    save_token(record)
    return {"server": server, "issuer": issuer, "expires_at": record["expires_at"]}
