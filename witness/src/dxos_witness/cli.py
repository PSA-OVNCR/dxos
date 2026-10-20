# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dòng lệnh ``dxos-witness``.

    dxos-witness sync --server https://dxos.example --anchor-dir ./dxos-transparency-log --state-dir ./state

Mã thoát: 0 khi ``OK``/``FIRST_RUN``; 2 khi phát hiện bất thường hoặc không kiểm được.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from dxos_witness.sync import WitnessError, sync


def _pull(anchor_dir: Path) -> None:
    if (anchor_dir / ".git").is_dir():
        subprocess.run(["git", "-C", str(anchor_dir), "pull", "-q", "--ff-only"], check=True)  # noqa: S603, S607


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dxos-witness", description="Witness độc lập cho ledger DX-OS")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="kiểm STH mới nhất so với lần trước và repo neo")
    s.add_argument("--server", required=True, help="địa chỉ DX-OS, ví dụ https://dxos.example")
    s.add_argument("--anchor-dir", required=True, type=Path, help="bản clone repo neo dxos-transparency-log")
    s.add_argument("--state-dir", required=True, type=Path, help="thư mục lưu STH đã kiểm")
    s.add_argument("--no-pull", action="store_true", help="không chạy git pull trong --anchor-dir")
    args = parser.parse_args(argv)
    try:
        if not args.no_pull:
            _pull(args.anchor_dir)
        r = sync(args.server, args.anchor_dir, args.state_dir)
    except (WitnessError, subprocess.CalledProcessError) as exc:
        print(f"ERROR tree_size=? {exc}")
        return 2
    print(f"{r.status} tree_size={r.tree_size} {r.detail}")
    return 0 if r.status in ("OK", "FIRST_RUN") else 2


if __name__ == "__main__":
    sys.exit(main())
