# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tra tĩnh cấu hình compose so với ma trận mạng (spec 6.2, AT-01 phần tĩnh, AT-24).

Chỉ cần CLI `docker compose` (không cần daemon). Không có CLI thì bỏ qua.
"""

import json
import re
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
    assert {"core-db", "openbao", "clamav", "seaweedfs", "flowable"} <= set(cfg["services"])
    for svc, d in cfg["services"].items():
        assert (d.get("labels") or {}).get("dxos.dev-only") == "true", svc
        for p in d.get("ports", []):
            assert p.get("host_ip") == "127.0.0.1", (svc, p)


def test_flowable_rest_password_secret_only_for_trust_core_api(compose_cfg):
    """Secret flowable-rest-password chỉ cấp cho trust-core-api (quyền tối thiểu); worker không gọi."""
    def has_secret(d: dict) -> bool:
        secrets = d.get("secrets") or []
        names = secrets if isinstance(secrets, dict) else [x["source"] if isinstance(x, dict) else x
                                                           for x in secrets]
        return "flowable-rest-password" in names

    assert {s for s, d in compose_cfg["services"].items() if has_secret(d)} == {"trust-core-api"}
    api_env = compose_cfg["services"]["trust-core-api"]["environment"]
    assert api_env["DXOS_FLOWABLE_PASSWORD_FILE"] == "/run/secrets/flowable-rest-password"
    assert "DXOS_FLOWABLE_PASSWORD_FILE" not in compose_cfg["services"]["trust-core-worker"]["environment"]
    # Image Flowable chỉ đọc biến môi trường, nên mật khẩu REST (giá trị mẫu trong .env.example)
    # chỉ được nằm ở chính Flowable.
    for svc, d in compose_cfg["services"].items():
        values = [str(v) for v in (d.get("environment") or {}).values()]
        assert svc == "flowable" or not any("changeme-flowable-rest" in v for v in values), svc


def test_installer_client_secret_only_for_trust_core_api(compose_cfg):
    """Secret installer-client-secret (service account manage-realm, Plan 02 Task 11) chỉ cấp cho
    trust-core-api; worker không gọi Admin API Keycloak. Secret lấy từ .env, không có giá trị trong repo."""
    def secret_names(d: dict) -> set[str]:
        secrets = d.get("secrets") or []
        return {x["source"] if isinstance(x, dict) else x for x in secrets}

    holders = {s for s, d in compose_cfg["services"].items() if "installer-client-secret" in secret_names(d)}
    assert holders == {"trust-core-api"}
    api_env = compose_cfg["services"]["trust-core-api"]["environment"]
    assert api_env["DXOS_INSTALLER_CLIENT_SECRET_FILE"] == "/run/secrets/installer-client-secret"
    worker_env = compose_cfg["services"]["trust-core-worker"]["environment"]
    assert "DXOS_INSTALLER_CLIENT_SECRET_FILE" not in worker_env
    raw = yaml.safe_load((DEPLOY / "compose.yaml").read_text(encoding="utf-8"))
    assert raw["secrets"]["installer-client-secret"] == {"environment": "DXOS_INSTALLER_CLIENT_SECRET"}
    # Ngoài trust-core-api (qua tệp secret), chỉ Keycloak nhận giá trị (để thay vào realm lúc nạp).
    for svc, d in compose_cfg["services"].items():
        env = d.get("environment") or {}
        assert svc == "keycloak" or "DXOS_INSTALLER_CLIENT_SECRET" not in env, svc


def test_integration_flowable_is_h2_on_loopback_with_healthcheck():
    cfg = _compose_config("compose.test.yaml")["services"]["flowable"]
    assert cfg["image"].startswith("flowable/flowable-rest:7.1.0@sha256:")
    ports = [(p["host_ip"], p["published"], p["target"]) for p in cfg["ports"]]
    assert ports == [("127.0.0.1", "58080", 8080)]
    assert cfg["healthcheck"]["test"]
    env = cfg.get("environment") or {}
    assert not any("postgres" in str(v).lower() for v in env.values())   # H2, không DB riêng
    assert not [k for k in env if k.startswith("SPRING_DATASOURCE")]   # dùng H2 mặc định của image


def test_keycloak_served_under_same_path_inside_and_outside(compose_cfg):
    """Không cắt tiền tố /auth ở Caddy: nếu cắt, Keycloak sinh token_endpoint thiếu /auth
    (phát hiện khi chạy sống 20/10/2026)."""
    env = compose_cfg["services"]["keycloak"]["environment"]
    assert env["KC_HTTP_RELATIVE_PATH"] == "/auth"
    assert env["KC_HOSTNAME"].endswith("/auth")
    caddyfile = (DEPLOY / "caddy/Caddyfile").read_text(encoding="utf-8")
    assert "handle_path /auth" not in caddyfile
    routes = yaml.safe_load((DEPLOY / "apisix/apisix.yaml").read_text(encoding="utf-8"))["routes"]
    for r in routes:
        oidc = (r.get("plugins") or {}).get("openid-connect")
        if oidc:
            assert oidc["discovery"].startswith("http://keycloak:8080/auth/realms/dxos/"), r["id"]


# Công cụ có sẵn trong từng image (đo trên image đã ghim, 20/10/2026).
IMAGE_TOOLS = {"apisix": {"bash"}, "flowable": {"nc", "wget"}, "keycloak": {"bash"}}


def test_healthcheck_uses_tool_present_in_image(compose_cfg):
    for svc, tools in IMAGE_TOOLS.items():
        test = compose_cfg["services"][svc]["healthcheck"]["test"]
        assert test[0] == "CMD" and test[1] in tools, (svc, test)


def _kc_import_sources(cfg: dict) -> set[str]:
    return {
        Path(v["source"]).name
        for v in cfg["services"]["keycloak"].get("volumes", [])
        if v.get("target", "").startswith("/opt/keycloak/data/import/")
    }


def test_production_imports_only_production_realm(compose_cfg):
    kc = compose_cfg["services"]["keycloak"]
    assert "--import-realm" in kc["command"]
    assert _kc_import_sources(compose_cfg) == {"realm-dxos.json"}
    for var in ("DXOS_DOMAIN", "DXOS_ADMIN_HOST", "APISIX_OIDC_CLIENT_SECRET",
                "DXOS_INSTALLER_CLIENT_SECRET"):
        assert kc["environment"].get(var), var


def test_keycloak_gets_every_variable_the_realm_files_use(compose_cfg, dev_lite_cfg):
    """Keycloak thay ${BIEN} lúc nạp realm từ môi trường của chính nó: thiếu biến thì redirect URI hỏng."""
    root = Path(__file__).resolve().parents[2]
    for name, cfg in (("realm-dxos.json", compose_cfg), ("realm-dxos-dev.json", dev_lite_cfg)):
        text = (root / "deploy/keycloak" / name).read_text(encoding="utf-8")
        used = set(re.findall(r"\$\{([A-Z0-9_]+)\}", text))
        assert {"DXOS_DOMAIN", "DXOS_ADMIN_HOST"} <= used, name
        missing = used - set(cfg["services"]["keycloak"]["environment"])
        assert missing == set(), (name, missing)


def test_dev_lite_imports_dev_realm(dev_lite_cfg):
    assert _kc_import_sources(dev_lite_cfg) == {"realm-dxos-dev.json"}
