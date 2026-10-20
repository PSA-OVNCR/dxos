# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/netcheck.py: logic thăm dò và báo cáo (không cần Docker; runner giả)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("netcheck", ROOT / "ops/netcheck.py")
netcheck = importlib.util.module_from_spec(_spec)
sys.modules["netcheck"] = netcheck  # dataclass cần module đã đăng ký
_spec.loader.exec_module(netcheck)

MATRIX = """
networks: {net-a: {internal: true}, net-b: {internal: true}}
membership: {svc: [net-a]}
probe_image: busybox:1.37
probes:
  - {from: net-a, to: "svc:80", expect: open}
  - {from: net-b, to: "svc:80", expect: closed}
"""


def _matrix(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(MATRIX, encoding="utf-8")
    return p


def test_run_probes_uses_project_network_names_and_reports(tmp_path):
    calls = []

    def runner(network, host, port, image):
        calls.append((network, host, port, image))
        return network == "dxos_net-a"

    res = netcheck.run_probes(_matrix(tmp_path), "dxos", runner=runner)
    assert sorted(calls) == [
        ("dxos_net-a", "svc", 80, "busybox:1.37"),
        ("dxos_net-b", "svc", 80, "busybox:1.37"),
    ]
    assert res == [
        netcheck.ProbeResult("net-a", "svc:80", "open", "open"),
        netcheck.ProbeResult("net-b", "svc:80", "closed", "closed"),
    ]
    assert all(r.ok for r in res)


def test_mismatch_is_reported_and_exit_code_nonzero(tmp_path, capsys):
    def leaky(network, host, port, image):
        return True  # mọi thứ đều mở: vi phạm phân vùng

    res = netcheck.run_probes(_matrix(tmp_path), "dxos", runner=leaky)
    assert [r.ok for r in res] == [True, False]
    code = netcheck.main(["--matrix", str(_matrix(tmp_path)), "--project", "dxos"], runner=leaky)
    out = capsys.readouterr().out
    assert code == 1 and "net-b" in out and "FAIL" in out


def test_docker_command_shape():
    cmd = netcheck.probe_command("dxos_net-app", "core-db", 5432, "busybox:1.37@sha256:ab")
    assert cmd == [
        "docker", "run", "--rm", "--network", "dxos_net-app",
        "busybox:1.37@sha256:ab", "nc", "-z", "-w", "2", "core-db", "5432",
    ]
