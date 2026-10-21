# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kiểm tĩnh trang đối soát tối giản (Plan 02 Task 10; spec 6.2, 13.3, 25.1, 25.4; R-2, AT-25 phần tĩnh).

Trang chỉ có hash tính tại trình duyệt, CSP chặt, mọi giá trị từ API gán bằng ``textContent``. Kiểm bằng
trình duyệt thật (không request nào mang nội dung tệp) để ở Plan 03; kiểm sống qua Caddy xem báo cáo Task 10.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "verify-portal/minimal"
JS = PAGE / "verify.js"
HTML = PAGE / "index.html"
CSS = PAGE / "verify.css"
SPEC = ROOT / "docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md"
CSP = ("default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _unified_sentence() -> str:
    """Câu thống nhất ở spec 25.1 (khối trích dẫn sau "Câu thống nhất"), bỏ ký hiệu in đậm markdown."""
    spec = SPEC.read_text(encoding="utf-8")
    after = spec.split("**Câu thống nhất**", 1)[1]
    quote = next(line for line in after.splitlines() if line.startswith("> "))
    return _flat(quote[2:].replace("**", ""))


def _caddy_block(caddyfile: str, opener: str) -> str:
    """Nội dung trong cặp ngoặc nhọn của khối bắt đầu bằng ``opener`` (Caddyfile không lồng sâu)."""
    start = caddyfile.index(opener)
    skip = len(opener) - 1 if opener.endswith("{") else 0           # opener có thể tự chứa "{$VAR}"
    body = caddyfile[caddyfile.index("{", start + skip) + 1:]
    depth, out = 1, []
    for ch in body:
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            break
        out.append(ch)
    return "".join(out)


# ---------- Bốn test của brief ----------

def test_page_never_uploads_file_contents():
    src = JS.read_text(encoding="utf-8")
    assert "crypto.subtle.digest" in src and "FormData" not in src
    calls = list(re.finditer(r"fetch\(([^;]+)\)", src))
    assert calls, "trang phải gọi fetch"
    for m in calls:
        assert "file" not in m.group(1).lower() and "blob" not in m.group(1).lower()


def test_seal_id_taken_from_fragment_only():
    src = JS.read_text(encoding="utf-8")
    assert "location.hash" in src and "location.search" not in src


def test_caddy_serves_page_with_strict_csp():
    assert "verify-portal/minimal:/srv/verify:ro" in (ROOT / "deploy/compose.yaml").read_text()
    assert "frame-ancestors 'none'" in (ROOT / "deploy/caddy/Caddyfile").read_text()


def test_page_never_builds_html_from_data():
    src = JS.read_text(encoding="utf-8")
    assert "innerHTML" not in src and "insertAdjacentHTML" not in src and "outerHTML" not in src


def test_page_uses_records_management_wording():
    html = HTML.read_text(encoding="utf-8")
    assert "Kiểm tra tính xác thực và toàn vẹn văn bản điện tử" in html
    assert "chữ ký điện tử chuyên dùng" in html and "legal-mapping" in html
    assert "không** tương đương chữ ký tay" not in html          # câu nguyên văn, không giữ ký hiệu markdown
    assert "không tương đương chữ ký tay" in html and "kiểm tra toàn vẹn về kỹ thuật" in html


# ---------- Bổ sung của người điều phối ----------

def test_legal_sentence_is_verbatim_from_spec_25_1():
    sentence = _unified_sentence()
    assert sentence.startswith("Niêm phong số là chữ ký điện tử chuyên dùng") and "**" not in sentence
    assert sentence in _flat(HTML.read_text(encoding="utf-8"))


def test_legal_mapping_link_points_to_github():
    html = HTML.read_text(encoding="utf-8")
    assert 'href="https://github.com/PSA-OVNCR/dxos/blob/main/docs/legal-mapping.md"' in html


def test_page_has_no_dangerous_dom_or_eval_apis():
    src = JS.read_text(encoding="utf-8")
    for banned in ("document.write", "eval(", "new Function", "setTimeout(\"", "setInterval(\"", ".style.",
                   'setAttribute("style"', "setAttribute('style'", "XMLHttpRequest", "sendBeacon",
                   "importScripts", "WebSocket", "localStorage", "sessionStorage", "document.cookie"):
        assert banned not in src, banned
    assert "textContent" in src


def test_html_has_no_inline_code_style_or_form():
    html = HTML.read_text(encoding="utf-8")
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S | re.I):
        assert re.search(r'\bsrc="verify\.js"', m.group(1)) and not m.group(2).strip()
    assert not re.search(r"<style\b", html, re.I)
    assert not re.search(r"\sstyle\s*=", html, re.I)
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)                 # onclick=... bị CSP chặn
    assert not re.search(r"<form\b", html, re.I)
    assert not re.search(r"javascript:", html, re.I)
    assert 'lang="vi"' in html and 'charset="utf-8"' in html.lower()
    assert 'name="viewport"' in html and 'href="verify.css"' in html


def test_page_loads_nothing_from_other_origins():
    html = HTML.read_text(encoding="utf-8")
    refs = re.findall(r'\b(?:src|href|action)="([^"]+)"', html)
    external = [r for r in refs if re.match(r"(?:[a-z]+:)?//", r)]
    assert external == ["https://github.com/PSA-OVNCR/dxos/blob/main/docs/legal-mapping.md"]
    css = CSS.read_text(encoding="utf-8")
    assert "@import" not in css and "url(" not in css and "http" not in css


def test_every_fetch_url_uses_validated_seal_id():
    src = JS.read_text(encoding="utf-8")
    assert re.search(r"/\^\[A-Z2-7\]\{26\}\$/", src), "seal_id phải khớp ^[A-Z2-7]{26}$ trước khi dùng"
    urls = re.findall(r"fetch\(\s*([^,)]+)", src)
    assert urls
    assert "/verify/v1/seals/" in src and src.count("encodeURIComponent(sealId)") >= 1
    for u in urls:
        assert "location" not in u and "hash" not in u.lower()
    # Đường dẫn tương đối cùng nguồn, không URL tuyệt đối tới nơi khác.
    assert "http://" not in src and "https://" not in src.replace("https://github.com/PSA-OVNCR/dxos", "")


def test_page_text_uses_required_labels_and_states():
    js, html = JS.read_text(encoding="utf-8"), HTML.read_text(encoding="utf-8")
    for text in ("Hợp lệ", "Đã thu hồi", "Chờ niêm phong", "Không hợp lệ", "Không tìm thấy",
                 "Đơn vị niêm phong", "Thời điểm niêm phong", "Đã neo công khai", "Chưa neo công khai",
                 "Tạm thời chưa kiểm được chữ ký, thử lại sau",
                 "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp"):
        assert text in js, text
    assert "(không xác định)" in js
    assert "signature_valid" in js and "inclusion" in js and "public_labels" in js
    assert "dxos-witness verify-bundle --anchor-dir" in html
    assert "văn thư" in html and "tiếp nhận văn bản điện tử đến" in html
    assert "không được gửi đi" in html and "SHA-256" in html   # tệp băm tại trình duyệt


def test_bundle_download_rules():
    js = JS.read_text(encoding="utf-8")
    assert ":check" in js and ":bundle" in js and "/bundle" in js
    # Tên tệp như máy chủ đặt (Content-Disposition) để trang, máy chủ và tài liệu witness thống nhất.
    assert "dxos-seal-" in js and "content-disposition" in js.lower()
    assert ".dxos-bundle.json" not in js
    assert "inclusion.verified" in js                               # nút gói chỉ hiện khi đã có STH phủ lá
    # Chỉ Blob dựng từ PHẢN HỒI của máy chủ (text), không dựng từ tệp người dùng.
    for m in re.finditer(r"new Blob\(([^)]*)\)", js):
        assert "file" not in m.group(1).lower()


def test_caddy_route_for_verify_page():
    caddy = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
    routes = _caddy_block(caddy, "(gateway_routes)")
    assert "redir /apps/verify /apps/verify/ 308" in routes
    block = _caddy_block(routes, "handle_path /apps/verify/*")
    assert "root * /srv/verify" in block and "file_server" in block
    assert f'Content-Security-Policy "{CSP}"' in block
    for hardening in ("X-Content-Type-Options", "Referrer-Policy"):
        assert hardening in block
    # Chỉ trong snippet dùng chung: cả hai host đều có route, và không lặp ngoài snippet.
    assert caddy.count("handle_path /apps/verify/*") == 1
    assert caddy.count("import gateway_routes") == 2


def test_compose_mounts_page_outside_readonly_apps_volume():
    compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
    assert "../verify-portal/minimal:/srv/verify:ro" in compose
    assert "apps-static:/srv/apps:ro" in compose and "/srv/apps/verify" not in compose


# ---------- Fix round 0 ----------

def test_pre_sth_state_is_not_a_bare_valid():
    js, css = JS.read_text(encoding="utf-8"), CSS.read_text(encoding="utf-8")
    assert "Chữ ký hợp lệ — đang chờ công bố vào sổ cái" in js
    assert ".badge.wait" in css                                 # lớp CSS riêng, khác .ok
    # "Hợp lệ" chỉ khi chữ ký đúng VÀ inclusion.verified đúng.
    assert re.search(r'if \(sigOk && verifiedOk\) \{\s*showStatus\("Hợp lệ", "ok"', js)
    assert re.search(r'showStatus\("Chữ ký hợp lệ — đang chờ công bố vào sổ cái", "wait"', js)


def test_admin_allow_list_is_enforced_before_any_handle():
    caddy = (ROOT / "deploy/caddy/Caddyfile").read_text(encoding="utf-8")
    admin = _caddy_block(caddy, "{$DXOS_ADMIN_HOST} {")
    assert "@blocked not remote_ip {$DXOS_ADMIN_ALLOWED_IPS}" in admin
    # `respond` rời rạc bị Caddy xếp SAU mọi `handle` (và `handle {}` cuối khớp tất cả): allow-list vô hiệu.
    assert not re.search(r"^\s*respond\s+@blocked", admin, re.M)
    block = _caddy_block(admin, "handle @blocked")
    assert 'respond "Forbidden" 403' in block
    assert admin.index("handle @blocked") < admin.index("import gateway_routes")
    assert admin.index("handle @blocked") < admin.index("handle /auth/*")
