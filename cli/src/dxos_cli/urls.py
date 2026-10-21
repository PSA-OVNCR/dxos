# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Chuẩn hóa và kiểm tra URL gốc (server, issuer): HTTPS bắt buộc, http chỉ cho loopback."""

from urllib.parse import urlsplit

from dxos_cli.errors import CliError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEFAULT_PORTS = {"https": 443, "http": 80}


def check_endpoint(url: str, *, what: str) -> str:
    """Kiểm tra URL đầy đủ: https, hoặc http tới loopback; không userinfo/query/fragment.

    Userinfo, query và fragment được kiểm **trước** mọi thông báo có in lại URL, để không bao giờ in mật khẩu
    hay token nhúng trong URL (kể cả khi URL sai ở chỗ khác).
    """
    url = url.strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # đọc để bắt cổng sai
    except ValueError:
        raise CliError(f"{what} không phải URL hợp lệ") from None  # không in lại URL hay chi tiết lỗi
    if "@" in url or "?" in url or "#" in url or parts.query or parts.fragment:
        raise CliError(f"{what} không được chứa thông tin đăng nhập, query hay fragment")
    if parts.scheme not in ("https", "http") or not host:
        raise CliError(f"{what} phải là URL https://… (nhận được: {_show(url)})")
    if parts.scheme == "http" and host not in LOOPBACK_HOSTS:
        raise CliError(f"{what} phải dùng HTTPS (http chỉ được phép với 127.0.0.1/localhost): {_show(url)}")
    return url


def normalize_server(url: str) -> str:
    """Trả ``scheme://host[:port]`` chuẩn hóa; từ chối URL có đường dẫn khác ``/``."""
    check_endpoint(url, what="--server")
    parts = urlsplit(url.strip())
    if parts.path not in ("", "/"):
        raise CliError(f"--server chỉ gồm scheme://host[:port], không có đường dẫn: {_show(url)}")
    return origin(parts)


def origin(parts) -> str:
    host = parts.hostname
    shown = f"[{host}]" if ":" in host else host
    port = parts.port
    suffix = f":{port}" if port and port != _DEFAULT_PORTS[parts.scheme] else ""
    return f"{parts.scheme}://{shown}{suffix}"


def _show(url: str) -> str:
    return repr(url if len(url) <= 80 else url[:77] + "...")
