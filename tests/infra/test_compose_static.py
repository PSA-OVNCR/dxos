# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tra tĩnh cấu hình compose so với ma trận mạng (spec 6.2, AT-01 phần tĩnh, AT-24).

Chỉ cần CLI `docker compose` (không cần daemon). Không có CLI thì bỏ qua.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
MATRIX = DEPLOY / "network-matrix.yaml"
PRODUCTION_PROFILES = ["p16", "p8"]


def _compose_config(*overlays: str) -> dict:
    if shutil.which("docker") is None:
        pytest.skip("cần CLI docker compose")
    cmd = ["docker", "compose", "-p", "dxos", "--env-file", str(ROOT / ".env.example")]
    for name in overlays:
        cmd += ["-f", str(DEPLOY / name)]
    cmd += ["config", "--format", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if proc.returncode != 0 and "is not a docker command" in proc.stderr:
        pytest.skip("cần plugin docker compose v2")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def matrix() -> dict:
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=PRODUCTION_PROFILES)
def compose_cfg(request) -> dict:
    return _compose_config("compose.yaml", f"compose.{request.param}.yaml")


@pytest.fixture(scope="module")
def dev_lite_cfg() -> dict:
    return _compose_config("compose.yaml", "compose.dev-lite.yaml")


def test_every_service_is_in_matrix(compose_cfg, matrix):
    assert set(compose_cfg["services"]) == set(matrix["membership"])


def test_membership_matches_matrix(compose_cfg, matrix):
    for svc, nets in matrix["membership"].items():
        assert set(compose_cfg["services"][svc]["networks"]) == set(nets), svc


def test_only_caddy_publishes_ports(compose_cfg):
    assert {s for s, d in compose_cfg["services"].items() if d.get("ports")} == {"caddy"}


def test_internal_flags(compose_cfg, matrix):
    assert set(compose_cfg["networks"]) == set(matrix["networks"])
    for net, spec in matrix["networks"].items():
        assert compose_cfg["networks"][net].get("internal", False) == spec["internal"], net


def test_no_dev_only_service_in_production(compose_cfg):  # AT-24
    assert not [
        s
        for s, d in compose_cfg["services"].items()
        if (d.get("labels") or {}).get("dxos.dev-only") == "true"
    ]


def test_every_service_restarts_and_has_healthcheck(compose_cfg):
    for svc, d in compose_cfg["services"].items():
        assert d.get("restart") == "unless-stopped", svc
        assert d.get("healthcheck", {}).get("test"), svc


@pytest.mark.xfail(
    strict=True,
    reason="digest chưa ghim: chạy `python ops/pin_images.py` trên máy có Docker rồi bỏ xfail",
)
def test_images_pinned_by_digest(compose_cfg):
    assert all("@sha256:" in d["image"] for d in compose_cfg["services"].values() if "image" in d)


def test_dev_lite_replaces_clamav_with_labelled_fake_av(dev_lite_cfg, matrix):
    clamav = dev_lite_cfg["services"]["clamav"]
    assert clamav["labels"]["dxos.dev-only"] == "true"
    assert "build" in clamav and "image" not in clamav
    # dev-lite vẫn giữ nguyên phân vùng mạng
    for svc, nets in matrix["membership"].items():
        assert set(dev_lite_cfg["services"][svc]["networks"]) == set(nets), svc


def test_matrix_probes_reference_known_networks_and_services(matrix):
    for p in matrix["probes"]:
        assert p["from"] in matrix["networks"], p
        host, port = p["to"].rsplit(":", 1)
        assert host in matrix["membership"] and port.isdigit(), p
        assert p["expect"] in {"open", "closed"}, p


def test_matrix_probes_agree_with_membership(matrix):
    """Probe kỳ vọng `open` khi và chỉ khi đích nằm trong mạng xuất phát."""
    for p in matrix["probes"]:
        host = p["to"].rsplit(":", 1)[0]
        reachable = p["from"] in matrix["membership"][host]
        assert (p["expect"] == "open") == reachable, p


def test_integration_compose_binds_only_loopback():
    """compose.test.yaml (integration test) chỉ mở cổng trên 127.0.0.1 và đánh dấu dev-only."""
    cfg = _compose_config("compose.test.yaml")
    assert {"core-db", "openbao", "clamav", "seaweedfs"} <= set(cfg["services"])
    for svc, d in cfg["services"].items():
        assert (d.get("labels") or {}).get("dxos.dev-only") == "true", svc
        for p in d.get("ports", []):
            assert p.get("host_ip") == "127.0.0.1", (svc, p)
