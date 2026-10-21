# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""API quản trị ``/admin/v1/*`` chỉ tới được qua host admin (spec 12.3; Plan 02 Task 12 fix 1).

Ba lớp, mỗi lớp tự đủ:
- Caddy: host công khai trả 404 cho ``/admin`` (không chuyển tới APISIX); host admin kiểm IP trước mọi handle.
- APISIX: route duy nhất khớp ``/admin/v1/*`` là ``admin-v1`` và nó ràng buộc ``host: ${{DXOS_ADMIN_HOST}}``.
- Compose: chỉ Caddy mở cổng ra ngoài; APISIX không gọi trực tiếp được (không giả mạo được header Host).
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CADDY = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")


def _block(text: str, opener: str) -> str:
    """Nội dung trong cặp ngoặc nhọn của khối bắt đầu bằng ``opener``."""
    start = text.index(opener)
    skip = len(opener) - 1 if opener.endswith("{") else 0
    body = text[text.index("{", start + skip) + 1:]
    depth, out = 1, []
    for ch in body:
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            break
        out.append(ch)
    return "".join(out)


def test_public_host_answers_404_for_admin_api_before_gateway():
    public = _block(CADDY, "{$DXOS_DOMAIN} {")
    m = re.search(r"^\s*@(\w+)\s+path\s+(/admin/\*\s+/admin|/admin\s+/admin/\*)\s*$", public, re.M)
    assert m, "host công khai phải có matcher path /admin/* /admin"
    handler = _block(public, f"handle @{m.group(1)}")
    assert 'respond "Not Found" 404' in handler and "reverse_proxy" not in handler
    assert public.index(f"handle @{m.group(1)}") < public.index("import gateway_routes")


def test_admin_host_still_routes_admin_api_behind_ip_allow_list():
    admin = _block(CADDY, "{$DXOS_ADMIN_HOST} {")
    assert "import gateway_routes" in admin and "/admin/*" in _block(CADDY, "(gateway_routes)")
    assert admin.index("handle @blocked") < admin.index("import gateway_routes")
    assert not re.search(r"path\s+[^\n]*/admin", admin)


def test_apisix_admin_route_is_bound_to_admin_host():
    text = (ROOT / "deploy/apisix/apisix.yaml").read_text(encoding="utf-8").replace("#END", "")
    routes = yaml.safe_load(text)["routes"]
    covering = [r for r in routes if r.get("uri") in {"/*", "/admin/*", "/admin/v1/*"}
                or any(u in {"/*", "/admin/*", "/admin/v1/*"} for u in r.get("uris", []))]
    assert [r["id"] for r in covering] == ["admin-v1"]
    assert covering[0]["host"] == "${{DXOS_ADMIN_HOST}}" and "hosts" not in covering[0]


def test_only_caddy_publishes_ports():
    services = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text(encoding="utf-8"))["services"]
    assert [name for name, svc in services.items() if svc.get("ports")] == ["caddy"]
