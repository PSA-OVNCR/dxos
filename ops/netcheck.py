# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tra phân vùng mạng trên stack đang chạy (AT-01).

Với mỗi probe trong deploy/network-matrix.yaml: chạy một container busybox tạm
gắn vào mạng `<project>_<from>` và thử `nc -z -w 2 <host> <port>`.
Mã thoát 0 nghĩa là `open`. So với `expect`; lệch bất kỳ probe nào thì thoát mã 1.

    python ops/netcheck.py --matrix deploy/network-matrix.yaml --project dxos
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

State = Literal["open", "closed"]
Runner = Callable[[str, str, int, str], bool]


@dataclass(frozen=True)
class ProbeResult:
    src_net: str
    target: str
    expect: State
    actual: State

    @property
    def ok(self) -> bool:
        return self.expect == self.actual


def probe_command(network: str, host: str, port: int, image: str) -> list[str]:
    return ["docker", "run", "--rm", "--network", network, image,
            "nc", "-z", "-w", "2", host, str(port)]


def docker_runner(network: str, host: str, port: int, image: str) -> bool:
    proc = subprocess.run(  # noqa: S603 - lệnh cố định, tham số lấy từ ma trận trong repo
        probe_command(network, host, port, image), capture_output=True, timeout=60, check=False
    )
    return proc.returncode == 0


def run_probes(matrix_path: Path, project: str, *, runner: Runner | None = None,
               workers: int = 8) -> list[ProbeResult]:
    matrix = yaml.safe_load(Path(matrix_path).read_text(encoding="utf-8"))
    image = matrix["probe_image"]
    run = runner or docker_runner

    def one(p: dict) -> ProbeResult:
        host, port = p["to"].rsplit(":", 1)
        is_open = run(f"{project}_{p['from']}", host, int(port), image)
        return ProbeResult(p["from"], p["to"], p["expect"], "open" if is_open else "closed")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, matrix["probes"]))


def render(results: list[ProbeResult]) -> str:
    lines = [f"{'from':<11} {'to':<22} {'expect':<7} {'actual':<7} result", "-" * 60]
    lines += [
        f"{r.src_net:<11} {r.target:<22} {r.expect:<7} {r.actual:<7} {'PASS' if r.ok else 'FAIL'}"
        for r in results
    ]
    bad = sum(not r.ok for r in results)
    lines.append(f"\n{len(results) - bad}/{len(results)} probe đạt")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra ma trận mạng (AT-01)")
    ap.add_argument("--matrix", type=Path, default=Path("deploy/network-matrix.yaml"))
    ap.add_argument("--project", default="dxos")
    args = ap.parse_args(argv)
    results = run_probes(args.matrix, args.project, runner=runner)
    print(render(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
