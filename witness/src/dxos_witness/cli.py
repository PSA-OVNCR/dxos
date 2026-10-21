# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Dòng lệnh ``dxos-witness``.

    dxos-witness sync --server https://dxos.example --anchor-dir ./dxos-transparency-log --state-dir ./state
    dxos-witness verify-bundle dxos-seal-<id>.json [--anchor-dir ./dxos-transparency-log] [--file tep-goc.pdf]

Mã thoát của ``sync``: 0 khi ``OK``/``FIRST_RUN``; 2 khi phát hiện bất thường hoặc không kiểm được.
Mã thoát của ``verify-bundle``: 0 khi ``VALID`` và khóa đã ghim từ repo neo; 3 khi ``VALID`` nhưng chưa ghim
(không có ``--anchor-dir``); 2 khi ``INVALID`` hoặc không đọc được đầu vào.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from dxos_witness.bundle import verify_bundle
from dxos_witness.sync import WitnessError, sync


def _pull(anchor_dir: Path) -> None:
    if (anchor_dir / ".git").is_dir():
        subprocess.run(["git", "-C", str(anchor_dir), "pull", "-q", "--ff-only"], check=True)  # noqa: S603, S607


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"khóa JSON trùng: {k!r}")
        out[k] = v
    return out


def _file_sha256(path: Path) -> str:
    """SHA-256 của tệp, tính ngay tại máy này; tệp không được gửi đi đâu."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_bundle_cmd(args: argparse.Namespace) -> int:
    try:
        bundle = json.loads(args.bundle.read_bytes().decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError) as exc:
        print(f"INVALID MALFORMED: không đọc được gói {args.bundle}: {exc}")
        return 2
    try:
        file_sha256 = None if args.file is None else _file_sha256(args.file)
    except OSError as exc:
        print(f"ERROR không đọc được --file {args.file}: {exc}")
        return 2
    r = verify_bundle(bundle, anchor_dir=args.anchor_dir, file_sha256=file_sha256)
    print(f"{r.status} {r.detail}")
    if r.issuer is not None:
        print(f"Niêm phong bởi: {r.issuer}")
    if r.status != "VALID":
        return 2
    if not r.pinned:
        print("CẢNH BÁO: khóa chưa ghim. Kết quả chỉ cho thấy gói tự nhất quán; chạy lại với --anchor-dir")
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dxos-witness", description="Witness độc lập cho ledger DX-OS")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="kiểm STH mới nhất so với lần trước và repo neo")
    s.add_argument("--server", required=True, help="địa chỉ DX-OS, ví dụ https://dxos.example")
    s.add_argument("--anchor-dir", required=True, type=Path, help="bản clone repo neo dxos-transparency-log")
    s.add_argument("--state-dir", required=True, type=Path, help="thư mục lưu STH đã kiểm")
    s.add_argument("--no-pull", action="store_true", help="không chạy git pull trong --anchor-dir")
    v = sub.add_parser("verify-bundle", help="kiểm ngoại tuyến gói bằng chứng niêm phong (.json)")
    v.add_argument("bundle", type=Path, help="tệp gói dxos-seal-<id>.json tải từ trang đối soát")
    v.add_argument("--anchor-dir", type=Path, default=None,
                   help="bản clone repo neo dxos-transparency-log (ghim khóa); không git pull")
    v.add_argument("--file", type=Path, default=None,
                   help="tệp gốc để đối chiếu: chỉ tính SHA-256 tại máy, không gửi đi đâu")
    args = parser.parse_args(argv)
    if args.cmd == "verify-bundle":
        return _verify_bundle_cmd(args)
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
