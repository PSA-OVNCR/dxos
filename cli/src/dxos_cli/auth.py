# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đăng nhập device flow (RFC 8628) với client công khai ``dxos-cli`` và lưu token.

Quy tắc an toàn:
- Token chỉ lưu trong ``$XDG_CONFIG_HOME/dxos/token.json`` (0600, thư mục 0700, ghi nguyên tử), kèm
  ``server`` và ``issuer`` nơi nó được cấp; không bao giờ dùng cho server khác. Refresh token lưu cùng tệp,
  chỉ dùng để làm mới qua token endpoint của đúng issuer đó (tìm lại bằng discovery, kiểm ``issuer`` khớp).
- Thư mục ``dxos`` không được là symlink: mở bằng ``O_NOFOLLOW`` rồi thao tác qua ``dir_fd``
  (không bị chuyển hướng ghi hay chmod).
- Không in hay ghi log access token, refresh token, device code.
- ``DXOS_TOKEN`` (CI, e2e) được dùng cho mọi server và không có hạn.
"""

import contextlib
import errno
import json
import math
import os
import re
import stat as stat_mod
import time
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx

from dxos_cli.errors import EXIT_LOGIN, EXIT_SERVER, CliError
from dxos_cli.urls import check_endpoint, normalize_server

CLIENT_ID = "dxos-cli"
SCOPE = "openid"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REFRESH_GRANT = "refresh_token"
DEFAULT_INTERVAL = 5
MIN_INTERVAL = 1
MAX_INTERVAL = 60
SLOW_DOWN_STEP = 5
STORE_NAME = "token.json"
_MAX_STORE_NAME = 64 * 1024
_SECURE_DIR = (
    os.open in os.supports_dir_fd
    and os.rename in os.supports_dir_fd  # os.replace nhận cùng dir_fd nhưng không có trong tập này
    and os.mkdir in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
)
_TOKEN_CHARS = re.compile(r"^[\x21-\x7e]+$")  # ASCII in được, không khoảng trắng/điều khiển: chặn chèn header


# ---------------------------------------------------------------- lưu token


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "")
    if not base or not os.path.isabs(base):  # XDG: đường dẫn tương đối không hợp lệ
        base = str(Path.home() / ".config")
    return Path(base) / "dxos"


def token_path() -> Path:
    return config_dir() / STORE_NAME


def _symlink_error() -> CliError:
    return CliError(
        "Thư mục cấu hình dxos là symlink hoặc không phải thư mục: từ chối dùng "
        "(xóa hoặc thay bằng thư mục thật quyền 0700)"
    )


def _open_config_dir(create: bool) -> int | None:
    """Mở thư mục ``dxos`` bằng ``O_NOFOLLOW`` (symlink bị từ chối); ``None`` nếu chưa có và không ``create``.

    Thư mục cha (``$XDG_CONFIG_HOME``) được phép là symlink (dotfiles); chỉ ``dxos`` thì không.
    """
    directory = config_dir()
    base = directory.parent
    if create:
        base.mkdir(parents=True, exist_ok=True)
    try:
        base_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return None
    try:
        if create:
            with contextlib.suppress(FileExistsError):
                os.mkdir(directory.name, 0o700, dir_fd=base_fd)
        try:
            return os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise _symlink_error() from exc
            raise
    finally:
        os.close(base_fd)


def _write_payload(fd: int, payload: bytes) -> None:
    with os.fdopen(fd, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())


def save_token(token: dict) -> Path:
    """Ghi token nguyên tử: tệp tạm tạo sẵn 0600 trong thư mục ``dxos`` rồi ``os.replace``; thư mục 0700.

    Trên POSIX mọi thao tác đi qua ``dir_fd`` của thư mục đã mở bằng ``O_NOFOLLOW``, nên symlink không chuyển
    hướng việc ghi hay chmod; ``token.json`` là symlink thì bị thay bằng tệp thường (không theo liên kết).
    """
    payload = json.dumps(token, ensure_ascii=False, sort_keys=True).encode("utf-8")
    tmp_name = f".{STORE_NAME}.{os.getpid()}.{os.urandom(6).hex()}"
    if not _SECURE_DIR:  # nền tảng không có dir_fd (Windows): kiểm symlink theo đường dẫn
        directory = config_dir()
        if directory.is_symlink():
            raise _symlink_error()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = directory / tmp_name
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _write_payload(fd, payload)
            os.replace(tmp, directory / STORE_NAME)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return directory / STORE_NAME
    dfd = _open_config_dir(create=True)
    if dfd is None:  # chỉ xảy ra khi thư mục bị xóa giữa chừng
        raise CliError("Không mở được thư mục cấu hình dxos")
    try:
        os.fchmod(dfd, 0o700)
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        try:
            _write_payload(fd, payload)
            os.replace(tmp_name, STORE_NAME, src_dir_fd=dfd, dst_dir_fd=dfd)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_name, dir_fd=dfd)
            raise
        with contextlib.suppress(OSError):
            os.fsync(dfd)
    finally:
        os.close(dfd)
    return token_path()


def _read_token_file() -> bytes | None:
    if not _SECURE_DIR:
        directory = config_dir()
        if directory.is_symlink():
            return None
        try:
            return (directory / STORE_NAME).read_bytes()
        except OSError:
            return None
    try:
        dfd = _open_config_dir(create=False)
    except (CliError, OSError):
        return None
    if dfd is None:
        return None
    try:
        fd = os.open(STORE_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
        with os.fdopen(fd, "rb") as fh:
            if not stat_mod.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return None
            return fh.read(_MAX_STORE_NAME)
    except OSError:
        return None
    finally:
        os.close(dfd)


def _number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def load_token() -> dict | None:
    """Đọc token đã lưu; ``None`` nếu chưa có, tệp hỏng hoặc thư mục/tệp là symlink (chưa đăng nhập)."""
    raw = _read_token_file()
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    ok = (
        isinstance(data.get("access_token"), str)
        and data["access_token"]
        and isinstance(data.get("server"), str)
        and _number(data.get("expires_at"))
    )
    if not ok:
        return None
    for key, kind in (("refresh_token", str), ("issuer", str)):  # trường tùy chọn sai kiểu thì bỏ
        if key in data and not (isinstance(data[key], kind) and data[key]):
            del data[key]
    if "refresh_expires_at" in data and not _number(data["refresh_expires_at"]):
        del data["refresh_expires_at"]
    return data


def _check_token_chars(token: str, where: str) -> str:
    if not _TOKEN_CHARS.match(token):
        raise CliError(f"{where} chứa ký tự không hợp lệ cho token")
    return token


def stored_server() -> str | None:
    tok = load_token()
    return tok["server"] if tok else None


@dataclass
class Credentials:
    """Token đang dùng và bản ghi đã lưu (``None`` khi token đến từ ``DXOS_TOKEN``: không làm mới được)."""

    token: str
    record: dict | None


def resolve_credentials(server: str, verify) -> Credentials:
    """Token cho ``server`` (đã chuẩn hóa): ``DXOS_TOKEN`` rồi tệp đã lưu; hết hạn thì làm mới.

    Mọi lỗi xác thực là mã thoát 3; token hết hạn mà không có refresh token còn hạn thì không gọi mạng.
    """
    env = os.environ.get("DXOS_TOKEN", "").strip()
    if env:
        return Credentials(_check_token_chars(env, "DXOS_TOKEN"), None)
    hint = f"chạy lại dxos login --server {server}"
    tok = load_token()
    if tok is None:
        raise CliError(f"Chưa đăng nhập: {hint}", EXIT_LOGIN)
    if tok["server"] != server:
        raise CliError(
            f"Token đã lưu được cấp cho {tok['server']}, không dùng cho {server}: {hint}", EXIT_LOGIN
        )
    if time.time() >= tok["expires_at"]:
        tok = refresh_session(tok, verify)
    return Credentials(_check_token_chars(tok["access_token"], "Token đã lưu"), tok)


# ---------------------------------------------------------------- device flow và làm mới token


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


def _http(verify, base_url: str) -> httpx.Client:
    """Client cho máy chủ định danh: không redirect; http (chỉ loopback) thì không đi qua proxy môi trường."""
    return httpx.Client(
        timeout=httpx.Timeout(15.0, connect=5.0),
        verify=verify,
        follow_redirects=False,
        trust_env=not base_url.startswith("http://"),
    )


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
    """Đọc discovery của ``issuer``; ``issuer`` trong tài liệu phải khớp đúng (chống nhầm issuer)."""
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
    doc_issuer = doc.get("issuer")
    if not isinstance(doc_issuer, str) or doc_issuer.rstrip("/") != issuer.rstrip("/"):
        raise CliError(f"Tài liệu discovery tại {url} khai issuer không khớp issuer đã cấu hình: từ chối")
    device, token = doc.get("device_authorization_endpoint"), doc.get("token_endpoint")
    if not isinstance(device, str) or not isinstance(token, str):
        raise CliError(
            "Issuer không công bố device_authorization_endpoint/token_endpoint (dxos-cli đã bật device flow?)"
        )
    return (
        check_endpoint(device, what="device_authorization_endpoint"),
        check_endpoint(token, what="token_endpoint"),
    )


def _seconds(value, what: str, *, allow_zero: bool) -> float:
    """Số giây hữu hạn từ máy chủ định danh: không nhận chuỗi, bool, NaN, vô hạn, số âm."""
    if not _number(value) or value < 0 or (value == 0 and not allow_zero):
        raise CliError(f"Phản hồi device flow có {what} không hợp lệ")
    return float(value)


def _record_from_grant(body: dict, server: str, issuer: str, previous: dict | None = None) -> dict:
    """Bản ghi token từ phản hồi token endpoint; ``previous`` giữ refresh token nếu không xoay."""
    access = body.get("access_token")
    if not isinstance(access, str) or not access:
        raise CliError("Máy chủ định danh không trả access_token")
    _check_token_chars(access, "access_token nhận được")
    expires_in = body.get("expires_in")
    if not _number(expires_in) or expires_in <= 0:
        raise CliError("Máy chủ định danh không trả expires_in hợp lệ")
    now = time.time()
    record = {
        "access_token": access,
        "expires_at": now + float(expires_in),
        "server": server,
        "issuer": issuer,
    }
    new_refresh = body.get("refresh_token")
    if isinstance(new_refresh, str) and new_refresh:
        record["refresh_token"] = _check_token_chars(new_refresh, "refresh_token nhận được")
        rin = body.get("refresh_expires_in")
        if _number(rin) and rin > 0:  # 0 nghĩa là không hết hạn (offline)
            record["refresh_expires_at"] = now + float(rin)
    elif previous and previous.get("refresh_token"):
        record["refresh_token"] = previous["refresh_token"]
        if "refresh_expires_at" in previous:
            record["refresh_expires_at"] = previous["refresh_expires_at"]
    return record


def refresh_session(rec: dict, verify) -> dict:
    """Làm mới access token bằng refresh token đã lưu, ghi lại nguyên tử và trả bản ghi mới.

    Token endpoint lấy từ discovery của đúng ``issuer`` đã lưu (``issuer`` phải khớp). Bị từ chối
    hoặc dữ liệu sai là mã 3 ("chạy lại dxos login"); lỗi mạng hoặc 5xx là mã 2.
    """
    hint = f"chạy lại dxos login --server {rec['server']}"
    refresh, issuer, expires = rec.get("refresh_token"), rec.get("issuer"), rec.get("refresh_expires_at")
    if not refresh or not issuer:
        raise CliError(f"Token đã hết hạn: {hint}", EXIT_LOGIN)
    if expires is not None and time.time() >= expires:
        raise CliError(f"Phiên đăng nhập đã hết hạn: {hint}", EXIT_LOGIN)
    try:
        issuer = check_endpoint(issuer, what="issuer đã lưu").rstrip("/")
        _check_token_chars(refresh, "refresh token đã lưu")
        with _http(verify, issuer) as client:
            _, token_ep = _discover(client, issuer)
            resp = _post_form(
                client,
                token_ep,
                {"grant_type": REFRESH_GRANT, "refresh_token": refresh, "client_id": CLIENT_ID},
            )
            if resp.status_code >= 500:
                raise CliError(
                    f"Máy chủ định danh trả HTTP {resp.status_code} khi làm mới token", EXIT_SERVER
                )
            if resp.status_code != 200:
                raise CliError("Máy chủ định danh từ chối refresh token")
            new = _record_from_grant(_json_obj(resp, "Máy chủ định danh"), rec["server"], issuer, rec)
    except CliError as exc:
        if exc.code == EXIT_SERVER:
            raise
        raise CliError(f"Không làm mới được token ({exc.message}): {hint}", EXIT_LOGIN) from exc
    save_token(new)
    return new


def device_login(server: str, issuer: str | None, verify, *, announce) -> dict:
    """Chạy device flow, lưu token và trả về ``{"server", "issuer", "expires_at"}`` (không chứa token)."""
    server = normalize_server(server)
    issuer = (check_endpoint(issuer, what="--issuer") if issuer else derive_issuer(server)).rstrip("/")
    with _http(verify, issuer) as client:
        device_ep, token_ep = _discover(client, issuer)
        resp = _post_form(client, device_ep, {"client_id": CLIENT_ID, "scope": SCOPE})
        if resp.status_code >= 500:
            raise CliError(f"Máy chủ định danh trả HTTP {resp.status_code}", EXIT_SERVER)
        if resp.status_code != 200:
            raise CliError(f"Máy chủ định danh từ chối yêu cầu device flow (HTTP {resp.status_code})")
        grant = _json_obj(resp, "Máy chủ định danh")
        device_code, user_code = grant.get("device_code"), grant.get("user_code")
        if not isinstance(device_code, str) or not isinstance(user_code, str) or not device_code:
            raise CliError("Phản hồi device flow thiếu device_code/user_code")
        interval = _seconds(grant.get("interval", DEFAULT_INTERVAL), "interval", allow_zero=True)
        expires_in = _seconds(grant.get("expires_in", 600), "expires_in", allow_zero=False)
        interval = min(max(interval, MIN_INTERVAL), MAX_INTERVAL)
        uri = grant.get("verification_uri_complete")
        if isinstance(uri, str) and uri:
            announce(
                f"Mở liên kết sau trong trình duyệt và xác nhận đăng nhập: {uri}\n(mã xác nhận: {user_code})"
            )
        else:
            announce(f"Mở {grant.get('verification_uri')} trong trình duyệt và nhập mã: {user_code}")
        deadline = monotonic() + expires_in
        timeout_error = CliError(
            "Hết thời gian chờ xác nhận đăng nhập (mã device đã hết hạn): chạy lại dxos login"
        )
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise timeout_error
            sleep(min(interval, remaining))
            if monotonic() >= deadline:  # không hỏi token endpoint sau hạn
                raise timeout_error
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
                interval = min(interval + SLOW_DOWN_STEP, MAX_INTERVAL)
                continue
            if error == "expired_token":
                raise CliError("Mã device đã hết hạn: chạy lại dxos login")
            if error == "access_denied":
                raise CliError("Đăng nhập bị từ chối")
            raise CliError(
                f"Đăng nhập thất bại ({error if isinstance(error, str) and len(error) < 60 else 'lỗi lạ'})"
            )
        record = _record_from_grant(_json_obj(resp, "Máy chủ định danh"), server, issuer)
    save_token(record)
    return {"server": server, "issuer": issuer, "expires_at": record["expires_at"]}
