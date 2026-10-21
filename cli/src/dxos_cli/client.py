# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Client HTTP cho API quản trị ``/admin/v1``: gắn với đúng một server, mang bearer token cấp cho server đó.

- Không theo redirect (token không bao giờ bị chuyển sang host khác).
- ``409 install-in-progress`` được thử lại tối đa 5 lần, cách nhau 2 giây (khóa cài của Task 12 không chờ).
- Mã thoát: 4xx là 1, lỗi mạng và 5xx là 2, 401 là 3 (kèm gợi ý ``dxos login``).
"""

import ssl
import sys
import unicodedata
from time import sleep
from typing import Any

import httpx

from dxos_cli.auth import resolve_token
from dxos_cli.errors import EXIT_CLIENT, EXIT_LOGIN, EXIT_SERVER, CliError
from dxos_cli.urls import normalize_server

RETRY_INSTALL_IN_PROGRESS = 5
RETRY_BACKOFF_S = 2
TIMEOUT = httpx.Timeout(30.0, connect=5.0)
PROBLEM_FIELDS = ("title", "detail", "code", "path", "guard", "reason")


def clean(text: Any) -> str:
    """Bỏ ký tự điều khiển/định dạng (ESC, BEL, bidi…) khỏi chuỗi do server gửi trước khi in ra terminal."""
    return "".join(
        " " if c in "\r\n" else "?" if unicodedata.category(c)[0] == "C" and c != "\t" else c
        for c in str(text)
    )


def make_verify(ca_file: str | None) -> ssl.SSLContext | bool:
    """``--ca-file`` thành ngữ cảnh TLS (thêm CA riêng của dev/VPS); không có thì dùng kho CA mặc định."""
    if not ca_file:
        return True
    try:
        return ssl.create_default_context(cafile=ca_file)
    except (OSError, ssl.SSLError) as exc:
        raise CliError(f"Không đọc được --ca-file {clean(ca_file)}: {type(exc).__name__}") from exc


def is_install_in_progress(status: int, problem: Any) -> bool:
    return (
        status == 409
        and isinstance(problem, dict)
        and isinstance(problem.get("type"), str)
        and problem["type"].endswith("/install-in-progress")
    )


class ApiError(CliError):
    """Lỗi do API trả về: ``problem`` là tài liệu RFC 7807 (hoặc ``None`` nếu thân không phải JSON object)."""

    def __init__(self, status: int, problem: dict | None, code: int) -> None:
        super().__init__("", code)
        self.status = status
        self.problem = problem


class AdminClient:
    def __init__(self, server: str, *, ca_file: str | None = None) -> None:
        self.server = normalize_server(server)
        verify = make_verify(ca_file)
        self._token = resolve_token(self.server)
        loopback_http = self.server.startswith("http://")  # normalize_server chỉ cho phép http với loopback
        self._http = httpx.Client(
            base_url=self.server,
            timeout=TIMEOUT,
            verify=verify,
            follow_redirects=False,
            # http chỉ có với loopback: không đi qua proxy môi trường để token không rời máy.
            trust_env=not loopback_http,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AdminClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _scrub(self, text: str) -> str:
        return clean(text.replace(self._token, "***"))

    def request(
        self, method: str, path: str, *, content: bytes | None = None, params: dict | None = None
    ) -> Any:
        """Gọi API, trả JSON khi 2xx. Lỗi: ``CliError`` (mạng, 401, 3xx) hoặc ``ApiError`` (4xx, 5xx)."""
        headers = {"Content-Type": "application/json"} if content is not None else None
        attempt = 0
        while True:
            try:
                resp = self._http.request(method, path, content=content, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise CliError(
                    f"Lỗi mạng khi gọi {self.server}: {type(exc).__name__}: {self._scrub(str(exc))}",
                    EXIT_SERVER,
                ) from exc
            problem = _problem(resp)
            if resp.is_success:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise CliError(
                        f"Phản hồi {resp.status_code} không phải JSON (qua proxy chăng?)", EXIT_SERVER
                    ) from exc
            if resp.status_code == 401:
                raise CliError(
                    f"Máy chủ từ chối token (401): chạy lại dxos login --server {self.server}", EXIT_LOGIN
                )
            if is_install_in_progress(resp.status_code, problem) and attempt < RETRY_INSTALL_IN_PROGRESS:
                attempt += 1
                print(
                    f"đang có thao tác cài khác, thử lại… ({attempt}/{RETRY_INSTALL_IN_PROGRESS})",
                    file=sys.stderr,
                )
                sleep(RETRY_BACKOFF_S)
                continue
            if 300 <= resp.status_code < 400:
                raise CliError(
                    f"Máy chủ chuyển hướng ({resp.status_code}); CLI không theo redirect: kiểm tra --server",
                    EXIT_SERVER,
                )
            raise ApiError(resp.status_code, problem, EXIT_CLIENT if resp.status_code < 500 else EXIT_SERVER)


def _problem(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def format_problem(status: int, problem: dict | None) -> str:
    """Dạng đọc được của một problem+json: type, rồi title/detail/code/path/guard/reason nếu có."""
    if problem is None:
        return f"Lỗi {status}: máy chủ không trả problem+json"
    lines = [f"Lỗi {status}: {clean(problem.get('type', 'about:blank'))}"]
    lines += [f"  {key}: {clean(problem[key])}" for key in PROBLEM_FIELDS if key in problem]
    return "\n".join(lines)
