# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm trang đối soát tối giản bằng Chromium thật (Plan 02 Task 10, Step 3). OPT-IN: bỏ qua trừ khi đặt
``DXOS_TEST_BROWSER=1`` và có ``node`` + module ``playwright`` + binary ``caddy`` (``CADDY_BIN``).

Dựng niêm phong thật bằng harness ``flow``, chạy uvicorn (app thật) + Caddy với Caddyfile THẬT của repo
(http, cổng cục bộ), rồi chạy ``tests/deploy/browser/*.js``. Ví dụ:

    DXOS_TEST_BROWSER=1 CADDY_BIN=/đường/dẫn/caddy PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \\
    DXOS_SHOT_DIR=docs/evidence python -m pytest core/tests/integration/test_verify_page_browser.py -s

``DXOS_SHOT_DIR`` (mặc định: thư mục tạm) là nơi ghi ảnh chụp ``verify-page-*.png``.
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import uvicorn
from dxos_core.ledger.sth import make_sth

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]
BROWSER = ROOT / "tests/deploy/browser"
CADDY = os.environ.get("CADDY_BIN") or shutil.which("caddy")


def _node_path() -> str | None:
    """NODE_PATH để ``require("playwright")`` được; None nếu không tìm thấy module."""
    node = shutil.which("node")
    if node is None:
        return None
    candidates = [os.environ.get("NODE_PATH", "")]
    npm = shutil.which("npm")
    if npm:
        out = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=30)
        candidates.append(out.stdout.strip())
    for cand in filter(None, (c for joined in candidates for c in joined.split(os.pathsep))):
        probe = subprocess.run([node, "-e", "require.resolve('playwright')"],
                               env={**os.environ, "NODE_PATH": cand}, capture_output=True)
        if probe.returncode == 0:
            return cand
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _run(*cmd, env=None, cwd=None) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec(*cmd, env=env, cwd=cwd, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode, out.decode("utf-8", "replace")


@pytest.fixture
def browser_env():
    """NODE_PATH có ``playwright``; bỏ qua (không lỗi) khi chưa opt-in hoặc thiếu node/playwright/caddy."""
    if os.environ.get("DXOS_TEST_BROWSER") != "1":
        pytest.skip("opt-in: đặt DXOS_TEST_BROWSER=1 (cần node + playwright + caddy)")
    if not CADDY:
        pytest.skip("cần binary caddy (CADDY_BIN)")
    node_path = _node_path()
    if node_path is None:
        pytest.skip("cần node và module playwright (npm i -g playwright; NODE_PATH)")
    return node_path


async def test_verify_page_in_real_browser(browser_env, flow, local_signer, tmp_path):
    work = tmp_path / "work"
    (work / "srv/apps").mkdir(parents=True)
    (work / "srv/apps/other.txt").write_text("ok\n")
    shots = Path(os.environ.get("DXOS_SHOT_DIR") or tmp_path / "shots")
    shots.mkdir(parents=True, exist_ok=True)

    # Các trạng thái niêm phong thật. Thứ tự quan trọng: STH phủ mọi thứ trước nó, nên bản ghi "chưa có STH
    # phủ" tạo sau STH, và SEAL_PENDING tạo sau cùng (giai đoạn B) vì các bước khác tự niêm phong job chờ.
    sid_file, original = await flow.sealed_with_file()
    sid_revoked = await flow.revoked_seal_id()
    await flow.install_verify_policy("0.2.0", require_file=False)
    sid_nofile, _ = await flow.sealed_ids()
    async with flow.db.acquire() as c:
        await make_sth(c, local_signer)
    sid_waiting, _ = await flow.sealed_ids()
    view = (await flow.api.get(f"/verify/v1/seals/{sid_waiting}")).json()
    assert view["inclusion"]["tree_size"] is None and view["signature_valid"] is True
    modified = bytearray(original)
    modified[-10] ^= 1
    (work / "original.pdf").write_bytes(original)
    (work / "modified.pdf").write_bytes(bytes(modified))

    uv_port, caddy_port = _free_port(), _free_port()
    text = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
    text = text.replace("apisix:9080", f"127.0.0.1:{uv_port}")
    text = text.replace("root * /srv/verify", f"root * {ROOT}/verify-portal/minimal")
    text = text.replace("root * /srv\n", f"root * {work}/srv\n")
    (work / "Caddyfile").write_text("{\n\tadmin off\n\tauto_https off\n}\n" + text, encoding="utf-8")
    base = f"http://localhost:{caddy_port}"
    ids = {"file": sid_file, "revoked": sid_revoked, "nofile": sid_nofile, "waiting": sid_waiting,
           "base": base}
    (work / "ids.json").write_text(json.dumps(ids))

    server = uvicorn.Server(uvicorn.Config(flow.api.app, host="127.0.0.1", port=uv_port, lifespan="off",
                                           log_level="warning"))
    server_task = asyncio.create_task(server.serve())
    env = {**os.environ, "HOME": str(work), "XDG_DATA_HOME": str(work / "data"),
           "XDG_CONFIG_HOME": str(work / "config"), "DXOS_DOMAIN": f"http://localhost:{caddy_port}",
           "DXOS_ADMIN_HOST": f"http://admin.localhost:{caddy_port}",
           "DXOS_ADMIN_ALLOWED_IPS": "127.0.0.1/32"}
    caddy = subprocess.Popen([CADDY, "run", "--config", str(work / "Caddyfile"), "--adapter", "caddyfile"],
                             env=env, stdout=open(work / "caddy.log", "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            await asyncio.sleep(0.2)
            rc, _out = await _run("curl", "-s", "-o", "/dev/null", f"{base}/apps/other.txt")
            if rc == 0:
                break
        js_env = {**os.environ, "NODE_PATH": browser_env, "DXOS_BROWSER_DIR": str(work),
                  "DXOS_SHOT_DIR": str(shots)}
        rc, out = await _run("node", str(BROWSER / "verify_page_checks.js"), env=js_env)
        print(out)
        assert rc == 0, out
        # Giai đoạn B: SEAL_PENDING.
        sid_pending = await flow.seal_id_of(await flow.pending_record())
        assert (await flow.api.get(f"/verify/v1/seals/{sid_pending}")).json() == {
            "seal_id": sid_pending, "status": "SEAL_PENDING"}
        (work / "ids.json").write_text(json.dumps({**ids, "pending": sid_pending}))
        rc, out = await _run("node", str(BROWSER / "verify_page_pending.js"), env=js_env)
        print(out)
        assert rc == 0, out
    finally:
        caddy.terminate()
        try:
            caddy.wait(10)
        except subprocess.TimeoutExpired:
            caddy.kill()
        server.should_exit = True
        await server_task
