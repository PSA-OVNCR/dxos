# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tĩnh việc phục vụ trang quản trị web (Plan 04 Task 10): Caddy ``handle_path /ui/*`` CHỈ trong khối
host admin, sau danh sách IP admin, từ ``/srv/apps/admin-ui`` (volume ``apps-static``), CSP riêng không
``unsafe-inline``. Kiểm sống header và mã trạng thái qua Caddy thật ở
``test_caddy_admin_allowlist_live.py``."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
ADMIN_UI_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _block(text: str, opener: str) -> str:
    start = text.index(opener)
    body = text[text.index("{", start + len(opener) - 1 if opener.endswith("{") else start) + 1:]
    depth, out = 1, []
    for ch in body:
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            break
        out.append(ch)
    return "".join(out)


def _code(text: str) -> str:
    """Bỏ dòng chú thích (comment có thể nhắc /ui/)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def _admin() -> str:
    return _block(CADDYFILE, "{$DXOS_ADMIN_HOST} {")


def _public() -> str:
    return _block(CADDYFILE, "{$DXOS_DOMAIN} {")


def test_ui_is_served_from_the_apps_static_volume_with_its_own_csp():
    ui = _block(_admin(), "handle_path /ui/*")
    assert "root * /srv/apps/admin-ui\n" in ui and "file_server" in ui
    assert f'Content-Security-Policy "{ADMIN_UI_CSP}"' in ui
    assert "X-Content-Type-Options nosniff" in ui and "Referrer-Policy no-referrer" in ui
    assert "'unsafe-inline'" not in CADDYFILE and "'unsafe-eval'" not in CADDYFILE
    # handle_path đã cắt /ui nên băm tên tệp nằm ở /assets/*; HTML và JSON luôn hỏi lại.
    assert re.search(r"@no_cache path [^\n]*\*\.html", ui)
    assert 'header @no_cache Cache-Control "no-cache"' in ui
    assert "@hashed path /assets/*" in ui
    assert 'header @hashed Cache-Control "public, max-age=31536000, immutable"' in ui


def test_ui_exists_only_in_the_admin_host_block_behind_the_ip_allow_list():
    admin = _admin()
    assert admin.count("handle_path /ui/*") == 1
    order = [admin.index(x) for x in ("handle @blocked", "handle_path /ui/*", "import gateway_routes")]
    assert order == sorted(order)
    assert CADDYFILE.count("handle_path /ui/*") == 1
    for where, text in (("host công khai", _code(_public())),
                        ("gateway_routes", _code(_block(CADDYFILE, "(gateway_routes) {")))):
        assert not re.search(r"(?<![\w-])/ui(?![\w-])", text), where
        assert "admin-ui" not in text.replace("/apps/admin-ui", ""), where


def test_bare_ui_redirect_cannot_leak_past_the_ip_allow_list():
    """``redir`` ở cấp khối site chạy TRƯỚC mọi ``handle`` (kể cả ``handle @blocked``): IP ngoài danh sách sẽ
    nhận 308 thay vì 403. Chuyển hướng /ui → /ui/ phải nằm trong một ``handle`` sau ``handle @blocked``."""
    admin = _admin()
    top_level = re.sub(r"handle[^\n]*\{(?:[^{}]|\{[^{}]*\})*\}", "", admin)   # bỏ các khối handle
    assert not re.search(r"^\s*redir\s+/ui\b", top_level, re.M)
    m = re.search(r"handle\s+(?:@\w+|/ui)\s*\{[^{}]*redir[^{}]*/ui/[^{}]*\}", admin)
    assert m and admin.index("handle @blocked") < m.start()


def test_the_built_copy_under_apps_is_not_served_to_anyone():
    """Volume apps-static có thư mục admin-ui; handle /apps/* chung sẽ phát nó trên cả hai host. Chặn riêng
    404: trang quản trị chỉ có ở /ui/ trên host admin (base của Vite là /ui/ nên bản ở /apps/admin-ui/ không
    chạy được)."""
    gw = _block(CADDYFILE, "(gateway_routes) {")
    m = re.search(r"@(\w+)\s+path\s+/apps/admin-ui\s+/apps/admin-ui/\*", gw)
    assert m, "thiếu matcher chặn /apps/admin-ui"
    handler = _block(gw, f"handle @{m.group(1)}")
    assert 'respond "Not Found" 404' in handler and "file_server" not in handler


def test_vite_base_matches_the_caddy_prefix_and_keycloak_redirect():
    vite = (ROOT / "admin-ui/vite.config.ts").read_text(encoding="utf-8")
    assert "base: '/ui/'" in vite
    realm = (ROOT / "deploy/keycloak/realm-dxos.json").read_text(encoding="utf-8")
    assert "https://${DXOS_ADMIN_HOST}/ui/*" in realm
