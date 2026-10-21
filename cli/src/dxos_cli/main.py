# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Điểm vào ``dxos``. Mã thoát: 0 thành công; 1 lỗi 4xx/đầu vào sai; 2 lỗi mạng/5xx; 3 chưa đăng nhập."""

import argparse
import sys

from dxos_cli import __version__, commands
from dxos_cli.client import ApiError, clean, format_problem
from dxos_cli.errors import EXIT_CLIENT, EXIT_OK, CliError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        """Lỗi cách dùng là mã thoát 1 (mã 2 dành cho lỗi mạng/5xx)."""
        self.print_usage(sys.stderr)
        self.exit(EXIT_CLIENT, f"{self.prog}: lỗi: {message}\n")


def _common(default) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "--server",
        metavar="URL",
        default=default,
        help="https://admin.<miền> (mặc định: server của token đã lưu bởi dxos login)",
    )
    p.add_argument(
        "--ca-file",
        metavar="PEM",
        dest="ca_file",
        default=default,
        help="tệp CA bổ sung để kiểm chứng TLS (CA nội bộ của Caddy khi dev)",
    )
    p.add_argument("--json", action="store_true", default=default, help="in JSON thô thay cho bảng/văn bản")
    return p


def _id_type(fn):
    def conv(value: str) -> str:
        try:
            return fn(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    conv.__name__ = fn.__name__
    return conv


def _limit(value: str) -> int:
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit phải là số nguyên") from exc
    if not 1 <= n <= 1000:
        raise argparse.ArgumentTypeError("--limit phải trong khoảng 1..1000")
    return n


def build_parser() -> argparse.ArgumentParser:
    top = _Parser(
        prog="dxos",
        description="CLI quản trị DX-OS Trust Core.",
        parents=[_common(None)],
        epilog="Mã thoát: 0 thành công; 1 lỗi 4xx/đầu vào; 2 lỗi mạng hoặc 5xx; 3 chưa đăng nhập.",
    )
    top.set_defaults(json=False)
    top.add_argument("--version", action="version", version=f"dxos {__version__}")
    sub = top.add_subparsers(dest="cmd", required=True, parser_class=_Parser, metavar="LỆNH")
    shared = _common(argparse.SUPPRESS)

    p = sub.add_parser(
        "login", parents=[shared], help="đăng nhập bằng device flow (Keycloak, client dxos-cli)"
    )
    p.add_argument(
        "--issuer", metavar="URL", help="https://<miền>/auth/realms/dxos (mặc định suy từ host admin.<miền>)"
    )
    p.set_defaults(func=commands.login)

    app = sub.add_parser("app", parents=[shared], help="vòng đời ứng dụng").add_subparsers(
        dest="sub", required=True, parser_class=_Parser, metavar="LỆNH"
    )
    p = app.add_parser(
        "install", parents=[shared], help="nộp manifest.yaml và tệp BPMN, in diff quyền để người khác duyệt"
    )
    p.add_argument("app_dir", metavar="THƯ-MỤC-APP")
    p.set_defaults(func=commands.app_install)
    p = app.add_parser("list", parents=[shared], help="liệt kê các phiên bản app")
    p.set_defaults(func=commands.app_list)
    p = app.add_parser("diff", parents=[shared], help="diff quyền của một phiên bản so với phiên bản ACTIVE")
    p.add_argument("app_id", type=_id_type(commands.app_id_arg))
    p.add_argument("version", type=_id_type(commands.version_arg))
    p.set_defaults(func=commands.app_diff)
    p = app.add_parser(
        "approve", parents=[shared], help="duyệt một phiên bản PENDING (người duyệt phải khác người nộp)"
    )
    p.add_argument("app_id", type=_id_type(commands.app_id_arg))
    p.add_argument("version", type=_id_type(commands.version_arg))
    p.set_defaults(func=commands.app_approve)
    p = app.add_parser("disable", parents=[shared], help="vô hiệu hóa phiên bản ACTIVE của app")
    p.add_argument("app_id", type=_id_type(commands.app_id_arg))
    p.set_defaults(func=commands.app_disable)

    p = sub.add_parser(
        "health", parents=[shared], help="sức khỏe các thành phần (mã thoát 0 khi yêu cầu thành công)"
    )
    p.set_defaults(func=commands.health)

    quarantine = sub.add_parser("quarantine", parents=[shared], help="tệp bị cách ly").add_subparsers(
        dest="sub", required=True, parser_class=_Parser, metavar="LỆNH"
    )
    p = quarantine.add_parser("list", parents=[shared], help="liệt kê tệp nhiễm/bị từ chối, mới nhất trước")
    p.add_argument("--limit", type=_limit, metavar="N", help="1..1000 (mặc định của server: 100)")
    p.set_defaults(func=commands.quarantine_list)

    ledger = sub.add_parser("ledger", parents=[shared], help="sổ cái").add_subparsers(
        dest="sub", required=True, parser_class=_Parser, metavar="LỆNH"
    )
    p = ledger.add_parser(
        "status", parents=[shared], help="kích thước, STH mới nhất, neo gần nhất, kết quả kiểm chuỗi"
    )
    p.set_defaults(func=commands.ledger_status)

    anchor = sub.add_parser("anchor", parents=[shared], help="neo STH").add_subparsers(
        dest="sub", required=True, parser_class=_Parser, metavar="LỆNH"
    )
    p = anchor.add_parser("run", parents=[shared], help="lập STH ngay và xếp việc đẩy lên repo neo")
    p.set_defaults(func=commands.anchor_run)
    return top


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (EXIT_OK if exc.code is None else EXIT_CLIENT)
    try:
        return args.func(args)
    except ApiError as exc:
        if args.json:
            print(commands.dump_json(exc.problem if exc.problem is not None else {"status": exc.status}))
        else:
            print(format_problem(exc.status, exc.problem))
        return exc.code
    except CliError as exc:
        if exc.message:
            print(clean(exc.message), file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"Lỗi tệp: {type(exc).__name__}: {clean(exc)}", file=sys.stderr)
        return EXIT_CLIENT
    except KeyboardInterrupt:
        print("Đã hủy.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
