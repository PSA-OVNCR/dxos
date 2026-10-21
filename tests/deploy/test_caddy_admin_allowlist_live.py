# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Host quản trị của Caddy thật chỉ nhận IP trong ``DXOS_ADMIN_ALLOWED_IPS`` (spec 6.2; fix round 0 Task 10).

Chạy Caddyfile THẬT của repo bằng binary ``caddy`` (``CADDY_BIN`` hoặc có trên PATH; không có thì bỏ qua),
http trên cổng cục bộ, không cần Docker. Lỗi cũ: ``respond @blocked`` bị Caddy xếp sau mọi ``handle`` nên
IP ngoài danh sách vẫn vào được host quản trị.
"""

import http.client
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CADDY = os.environ.get("CADDY_BIN") or shutil.which("caddy")
pytestmark = pytest.mark.skipif(not CADDY, reason="cần binary caddy (CADDY_BIN) để kiểm sống Caddyfile")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int, host: str, path: str) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers={"Host": f"{host}:{port}"})
        return conn.getresponse().status
    finally:
        conn.close()


@pytest.fixture
def run_caddy(tmp_path):
    procs = []

    def start(allowed: str) -> int:
        port = _free_port()
        (tmp_path / "srv/apps").mkdir(parents=True, exist_ok=True)
        (tmp_path / "srv/apps/other.txt").write_text("ok\n")
        text = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
        text = text.replace("root * /srv/verify", f"root * {ROOT}/verify-portal/minimal")
        text = text.replace("root * /srv\n", f"root * {tmp_path}/srv\n")
        cfg = tmp_path / f"Caddyfile.{port}"
        cfg.write_text("{\n\tadmin off\n\tauto_https off\n}\n" + text, encoding="utf-8")
        env = {**os.environ, "HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "data"),
               "XDG_CONFIG_HOME": str(tmp_path / "config"),
               "DXOS_DOMAIN": f"http://localhost:{port}", "DXOS_ADMIN_HOST": f"http://admin.localhost:{port}",
               "DXOS_ADMIN_ALLOWED_IPS": allowed}
        log = open(tmp_path / f"caddy-{port}.log", "w")
        procs.append(subprocess.Popen([CADDY, "run", "--config", str(cfg), "--adapter", "caddyfile"], env=env,
                                      stdout=log, stderr=subprocess.STDOUT))
        for _ in range(100):
            try:
                _get(port, "localhost", "/apps/other.txt")
                return port
            except OSError:
                time.sleep(0.1)
        raise AssertionError((tmp_path / f"caddy-{port}.log").read_text())

    yield start
    for p in procs:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()


BLOCKED_PATHS = ("/", "/apps/other.txt", "/apps/verify/", "/auth/realms/dxos", "/admin/v1/ledger/status",
                 "/api/v1/apps", "/verify/v1/seals/AAAAAAAAAAAAAAAAAAAAAAAAAA")


def test_ip_outside_allow_list_gets_403_on_every_admin_path(run_caddy):
    port = run_caddy("203.0.113.7/32")                     # 127.0.0.1 không thuộc danh sách
    for path in BLOCKED_PATHS:
        assert _get(port, "admin.localhost", path) == 403, path
    assert _get(port, "localhost", "/apps/other.txt") == 200   # host công khai không bị ảnh hưởng


def test_ip_inside_allow_list_passes_on_admin_host(run_caddy):
    port = run_caddy("127.0.0.1/32")
    assert _get(port, "admin.localhost", "/apps/other.txt") == 200
    assert _get(port, "admin.localhost", "/") == 404       # tới được fallback, không bị 403
    assert _get(port, "admin.localhost", "/apps/verify/") == 200
