# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Lỗi của CLI và mã thoát (0 thành công; 1 lỗi 4xx/đầu vào sai; 2 lỗi mạng hoặc 5xx; 3 chưa đăng nhập)."""

EXIT_OK = 0
EXIT_CLIENT = 1
EXIT_SERVER = 2
EXIT_LOGIN = 3


class CliError(Exception):
    """Lỗi dừng lệnh: ``message`` in ra stderr (nếu có), ``code`` là mã thoát."""

    def __init__(self, message: str, code: int = EXIT_CLIENT) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
