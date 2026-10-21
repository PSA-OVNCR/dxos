# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tĩnh việc phục vụ các SPA Tầng 2 (Plan 03 Task 10): Caddy ``handle /apps/*``, volume ``apps-static``,
``make web-build`` và hai script chạy bằng Docker. Kiểm sống header qua Caddy thật ở
``test_caddy_admin_allowlist_live.py``."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
APPS_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'none'")
SHA = r"@sha256:[0-9a-f]{64}"


def _block(text: str, opener: str) -> str:
    start = text.index(opener)
    body = text[text.index("{", start) + 1:]
    depth, out = 1, []
    for ch in body:
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            break
        out.append(ch)
    return "".join(out)


def _generic() -> str:
    return _block(CADDYFILE, "handle /apps/* {")


def test_generic_apps_handle_sets_csp_and_hardening_headers():
    block = _generic()
    assert "root * /srv\n" in block and "file_server" in block
    assert f'Content-Security-Policy "{APPS_CSP}"' in block
    assert "X-Content-Type-Options nosniff" in block and "Referrer-Policy no-referrer" in block
    assert CADDYFILE.count("handle /apps/* {") == 1


def test_generic_apps_handle_cache_rules():
    block = _generic()
    assert re.search(r"@no_cache path [^\n]*\*\.html", block)
    assert 'header @no_cache Cache-Control "no-cache"' in block
    assert "@hashed path /apps/*/assets/*" in block
    assert 'header @hashed Cache-Control "public, max-age=31536000, immutable"' in block


def test_verify_routes_keep_their_stricter_csp_and_come_with_their_own_handlers():
    verify = _block(CADDYFILE, "handle_path /apps/verify/*")
    lite = _block(CADDYFILE, "handle_path /apps/verify-lite/*")
    assert "default-src 'none'" in verify and "default-src 'none'" in lite
    assert APPS_CSP not in verify and APPS_CSP not in lite
    assert "'unsafe-inline'" not in CADDYFILE and "'unsafe-eval'" not in CADDYFILE
    assert 'header @hashed Cache-Control "public, max-age=31536000, immutable"' in verify
    assert "@hashed path /assets/*" in verify               # handle_path đã cắt /apps/verify


def test_apps_static_volume_is_mounted_read_only_into_caddy():
    compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
    assert "apps-static:/srv/apps:ro" in compose
    assert re.search(r"^  apps-static:", compose, re.M)


def test_web_build_docker_runs_one_shot_node_container_into_the_named_volume():
    sh = (ROOT / "ops/web_build_docker.sh").read_text(encoding="utf-8")
    assert re.search(r"^NODE_IMAGE=node:22-bookworm-slim(" + SHA + r")?\s*$", sh, re.M)
    assert "APPS_VOLUME=dxos_apps-static" in sh and '-v "$APPS_VOLUME":/out' in sh
    assert '-v "$REPO":/src:ro' in sh
    assert "docker run --rm" in sh
    assert "npm i -g npm@11.6.2" in sh
    assert "sh /work/ops/build_web.sh /out" in sh
    for excluded in ("node_modules", ".git", "dist"):
        assert excluded in sh
    assert "VITE_ANCHOR_RAW_BASE" in sh and "DXOS_BUILD_COMMIT" in sh
    assert "docker compose" not in sh                         # không thêm dịch vụ vào compose


def test_web_live_runs_in_the_pinned_playwright_image_and_is_opt_in():
    sh = (ROOT / "ops/web_live.sh").read_text(encoding="utf-8")
    assert re.search(r"^PLAYWRIGHT_IMAGE=mcr\.microsoft\.com/playwright:v1\.63\.0-noble(" + SHA + r")?\s*$",
                     sh, re.M)
    assert "--add-host=host.docker.internal:host-gateway" in sh
    assert "NODE_EXTRA_CA_CERTS=/out/caddy-root.crt" in sh
    assert "DXOS_WEB_LIVE=1" in sh


def test_makefile_has_web_build_and_web_live_targets():
    make = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^web-build:\n\tbash ops/web_build_docker\.sh", make, re.M)
    assert re.search(r"^web-live:\n\tbash ops/web_live\.sh", make, re.M)
    assert "web-build" in make.split(".PHONY:")[1].split("\n\n")[0]


def test_image_scripts_are_covered_by_pin_images():
    pin = (ROOT / "ops/pin_images.py").read_text(encoding="utf-8")
    assert "NODE_IMAGE" in pin and "PLAYWRIGHT_IMAGE" in pin
