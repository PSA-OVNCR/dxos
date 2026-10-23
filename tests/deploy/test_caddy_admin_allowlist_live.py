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


def _caddy_problem() -> str | None:
    """Lý do không dùng được binary caddy (thiếu, không chạy được, không phải Caddy 2), hoặc None."""
    if not CADDY:
        return "cần binary caddy (CADDY_BIN hoặc trên PATH) để kiểm sống Caddyfile"
    try:
        out = subprocess.run([CADDY, "version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"không chạy được {CADDY}: {exc}"
    if out.returncode != 0 or not out.stdout.startswith("v2."):
        return f"{CADDY} version không trả về Caddy 2: {out.stdout.strip()!r} (mã {out.returncode})"
    return None


def _need_caddy() -> None:
    """Thiếu Caddy: bỏ qua, trừ khi DXOS_REQUIRE_CADDY=1 (job caddy-live của CI) thì LỖI, để CI không xanh vì
    bỏ qua."""
    problem = _caddy_problem()
    if problem is None:
        return
    if os.environ.get("DXOS_REQUIRE_CADDY") == "1":
        pytest.fail(problem + " (DXOS_REQUIRE_CADDY=1)")
    pytest.skip(problem)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fetch(port: int, host: str, path: str) -> tuple[int, dict[str, str]]:
    """Trạng thái và header (tên viết thường) của một GET, không theo chuyển hướng."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers={"Host": f"{host}:{port}"})
        resp = conn.getresponse()
        resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}
    finally:
        conn.close()


def _get(port: int, host: str, path: str) -> int:
    return _fetch(port, host, path)[0]


@pytest.fixture
def run_caddy(tmp_path):
    procs = []

    def start(allowed: str, anchor_origin: str | None = None) -> int:
        port = _free_port()
        (tmp_path / "srv/apps/verify").mkdir(parents=True, exist_ok=True)
        (tmp_path / "srv/apps/other.txt").write_text("ok\n")
        (tmp_path / "srv/apps/verify/index.html").write_text("<!doctype html><title>vue</title>\n")
        (tmp_path / "srv/apps/verify/assets").mkdir(exist_ok=True)
        (tmp_path / "srv/apps/verify/assets/x.js").write_text("// x\n")
        (tmp_path / "srv/apps/phong-ho-so/assets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "srv/apps/phong-ho-so/index.html").write_text("<!doctype html><title>app</title>\n")
        (tmp_path / "srv/apps/phong-ho-so/assets/index-abc123.js").write_text("// app\n")
        (tmp_path / "srv/apps/admin-ui/assets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "srv/apps/admin-ui/index.html").write_text("<!doctype html><title>admin</title>\n")
        (tmp_path / "srv/apps/admin-ui/assets/index-abc123.js").write_text("// admin\n")
        (tmp_path / "srv/apps/BUILD-INFO.json").write_text("{}\n")
        text = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
        text = text.replace("root * /srv/verify-lite", f"root * {ROOT}/verify-portal/minimal")
        text = text.replace("root * /srv/apps/verify", f"root * {tmp_path}/srv/apps/verify")
        text = text.replace("root * /srv/apps/admin-ui", f"root * {tmp_path}/srv/apps/admin-ui")
        text = text.replace("root * /srv\n", f"root * {tmp_path}/srv\n")
        cfg = tmp_path / f"Caddyfile.{port}"
        cfg.write_text("{\n\tadmin off\n\tauto_https off\n}\n" + text, encoding="utf-8")
        env = {**os.environ, "HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "data"),
               "XDG_CONFIG_HOME": str(tmp_path / "config"),
               "DXOS_DOMAIN": f"http://localhost:{port}", "DXOS_ADMIN_HOST": f"http://admin.localhost:{port}",
               "DXOS_ADMIN_ALLOWED_IPS": allowed}
        env.pop("DXOS_ANCHOR_RAW_ORIGIN", None)                  # không đặt = trống (mặc định của compose)
        if anchor_origin is not None:
            env["DXOS_ANCHOR_RAW_ORIGIN"] = anchor_origin
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


BLOCKED_PATHS = ("/", "/apps/other.txt", "/apps/verify/", "/apps/verify-lite/", "/auth/realms/dxos",
                 "/ui", "/ui/", "/ui/index.html", "/ui/assets/index-abc123.js",
                 "/admin/v1/ledger/status", "/api/v1/apps", "/verify/v1/seals/AAAAAAAAAAAAAAAAAAAAAAAAAA")


def test_ip_outside_allow_list_gets_403_on_every_admin_path(run_caddy):
    _need_caddy()
    port = run_caddy("203.0.113.7/32")                     # 127.0.0.1 không thuộc danh sách
    for path in BLOCKED_PATHS:
        assert _get(port, "admin.localhost", path) == 403, path
    assert _get(port, "localhost", "/apps/other.txt") == 200   # host công khai không bị ảnh hưởng


def test_ip_inside_allow_list_passes_on_admin_host(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32")
    assert _get(port, "admin.localhost", "/apps/other.txt") == 200
    assert _get(port, "admin.localhost", "/") == 404       # tới được fallback, không bị 403
    assert _get(port, "admin.localhost", "/apps/verify/") == 200
    assert _get(port, "admin.localhost", "/apps/verify-lite/") == 200
    for path in ("/admin", "/admin/v1/health", "/admin/v1/apps"):      # API quản trị: chỉ host admin
        assert _get(port, "localhost", path) == 404, path


# CSP của cổng Vue khi DXOS_ANCHOR_RAW_ORIGIN trống: khoảng trắng thừa trước ";" vẫn là CSP hợp lệ.
VUE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
           "connect-src 'self' ; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
LITE_CSP = ("default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def test_both_verify_portals_are_served_with_their_own_csp(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32")                       # DXOS_ANCHOR_RAW_ORIGIN không đặt
    for host in ("localhost", "admin.localhost"):
        status, headers = _fetch(port, host, "/apps/verify/")
        assert status == 200 and headers["content-security-policy"] == VUE_CSP, host
        status, headers = _fetch(port, host, "/apps/verify-lite/")
        assert status == 200 and headers["content-security-policy"] == LITE_CSP, host
        assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"
        for bare, target in (("/apps/verify", "/apps/verify/"), ("/apps/verify-lite", "/apps/verify-lite/")):
            status, headers = _fetch(port, host, bare)
            assert status == 308 and headers["location"] == target, (host, bare)


def test_vue_portal_csp_allows_only_the_configured_anchor_origin(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32", anchor_origin="https://raw.githubusercontent.com")
    _, headers = _fetch(port, "localhost", "/apps/verify/")
    assert "connect-src 'self' https://raw.githubusercontent.com; base-uri 'none'" in headers[
        "content-security-policy"]
    _, lite = _fetch(port, "localhost", "/apps/verify-lite/")
    assert lite["content-security-policy"] == LITE_CSP    # trang tối giản không đọc repo neo


# CSP của mọi ứng dụng Tầng 2 dưới /apps/* (handle chung); /apps/verify/ và /apps/verify-lite/ giữ CSP riêng.
APPS_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'none'")


def test_generic_apps_route_has_csp_and_cache_rules_while_verify_routes_keep_their_own(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32")
    for host in ("localhost", "admin.localhost"):
        for path in ("/apps/phong-ho-so/", "/apps/phong-ho-so/index.html", "/apps/BUILD-INFO.json"):
            status, headers = _fetch(port, host, path)
            assert status == 200, (host, path)
            assert headers["content-security-policy"] == APPS_CSP, (host, path)
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["referrer-policy"] == "no-referrer"
            assert headers["cache-control"] == "no-cache", (host, path)
        status, headers = _fetch(port, host, "/apps/phong-ho-so/assets/index-abc123.js")
        assert status == 200 and headers["cache-control"] == "public, max-age=31536000, immutable"
        assert headers["content-security-policy"] == APPS_CSP
        status, headers = _fetch(port, host, "/apps/phong-ho-so")             # thiếu "/" cuối: chuyển hướng
        assert status == 308 and headers["location"] == "/apps/phong-ho-so/"
        assert _get(port, host, "/apps/phong-ho-so/assets/missing.js") == 404
        # Không bị handle chung nuốt: hai route riêng giữ CSP riêng (chặt hơn); cổng Vue cũng cache assets.
        assert _fetch(port, host, "/apps/verify/")[1]["content-security-policy"] == VUE_CSP
        assert _fetch(port, host, "/apps/verify-lite/")[1]["content-security-policy"] == LITE_CSP
        status, headers = _fetch(port, host, "/apps/verify/assets/x.js")
        assert status == 200 and headers["content-security-policy"] == VUE_CSP
        assert headers["cache-control"] == "public, max-age=31536000, immutable"
        assert _fetch(port, host, "/apps/verify/")[1]["cache-control"] == "no-cache"


# CSP riêng của trang quản trị web (Plan 04 Task 10): không inline, không nguồn ngoài.
ADMIN_UI_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def test_admin_ui_is_served_on_the_admin_host_with_its_own_csp_and_cache_rules(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32")
    for path in ("/ui/", "/ui/index.html"):
        status, headers = _fetch(port, "admin.localhost", path)
        assert status == 200, path
        assert headers["content-security-policy"] == ADMIN_UI_CSP, path
        assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-cache", path
    status, headers = _fetch(port, "admin.localhost", "/ui/assets/index-abc123.js")
    assert status == 200 and headers["cache-control"] == "public, max-age=31536000, immutable"
    assert headers["content-security-policy"] == ADMIN_UI_CSP
    assert _get(port, "admin.localhost", "/ui/assets/missing.js") == 404
    status, headers = _fetch(port, "admin.localhost", "/ui")
    assert status == 308 and headers["location"] == "/ui/"


def test_public_host_has_no_ui_and_no_copy_of_the_admin_build(run_caddy):
    _need_caddy()
    port = run_caddy("127.0.0.1/32")
    for path in ("/ui", "/ui/", "/ui/index.html", "/ui/assets/index-abc123.js"):
        assert _get(port, "localhost", path) == 404, path
    # Bản dựng nằm trong volume apps-static nhưng không được phát qua /apps/ trên bất kỳ host nào.
    for host in ("localhost", "admin.localhost"):
        for path in ("/apps/admin-ui", "/apps/admin-ui/", "/apps/admin-ui/index.html",
                     "/apps/admin-ui/assets/index-abc123.js"):
            assert _get(port, host, path) == 404, (host, path)
    assert _get(port, "localhost", "/apps/phong-ho-so/") == 200      # app khác không bị ảnh hưởng
