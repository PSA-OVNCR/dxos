# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture của tests/ops: ``fake_admin`` là API quản trị giả trên 127.0.0.1, đủ các route mà
``ops/e2e/install_apps.sh`` và ``ops/at13_reuse.sh`` gọi qua CLI ``dxos`` thật (dạng JSON theo báo cáo
Plan 02 Task 12)."""

import hashlib
import json
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

APPROVE = re.compile(r"^/admin/v1/apps/([a-z0-9-]+):approve$")
DIFF = re.compile(r"^/admin/v1/apps/([a-z0-9-]+)/versions/([0-9.]+)/diff$")
NOT_FOUND = {"type": "https://dxos.dev/problems/not-found", "title": "Not Found", "status": 404}
SELF_APPROVAL = {"type": "https://dxos.dev/problems/forbidden", "title": "Forbidden", "status": 403,
                 "reason": "self_approval"}
PROBLEM = "application/problem+json"


class FakeAdmin:
    def __init__(self) -> None:
        self.apps: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, str, str]] = []          # (method, path, token)
        self.list_status = 200                               # đặt 500/401 để giả lỗi của GET /admin/v1/apps

    def rows(self) -> list[dict]:
        return [{"app_id": k[0], "version": k[1], "status": v["status"], "manifest_sha256": "0" * 64,
                 "submitted_by_ref": None, "approved_by_ref": None, "created_at": "2026-10-21T00:00:00+00:00"}
                for k, v in sorted(self.apps.items())]


def _server(state: FakeAdmin) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, body: object, ctype: str = "application/json") -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _token(self) -> str:
            return self.headers.get("Authorization", "").removeprefix("Bearer ")

        def do_GET(self) -> None:  # noqa: N802
            state.calls.append(("GET", self.path, self._token()))
            if self.path == "/admin/v1/apps" and state.list_status != 200:
                self._send(state.list_status, {"type": "https://dxos.dev/problems/x", "title": "x",
                                               "status": state.list_status}, PROBLEM)
            elif self.path == "/admin/v1/apps":
                self._send(200, state.rows())
            elif m := DIFF.match(self.path):
                self._send(200, {"app_id": m[1], "version": m[2], "against": None, "roles_added": []})
            else:
                self._send(404, NOT_FOUND, PROBLEM)

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            tok = self._token()
            state.calls.append(("POST", self.path, tok))
            if self.path == "/admin/v1/apps":
                app = body["manifest"]["app"]
                state.apps[(app["id"], app["version"])] = {"status": "PENDING", "by": tok}
                self._send(202, {"app_id": app["id"], "version": app["version"], "status": "PENDING",
                                 "manifest_sha256": hashlib.sha256(b"x").hexdigest(), "files": {}})
            elif m := APPROVE.match(self.path):
                row = state.apps[(m[1], body["version"])]
                if row["by"] == tok:
                    self._send(403, SELF_APPROVAL, PROBLEM)
                    return
                row["status"] = "ACTIVE"
                self._send(200, {"app_id": m[1], "version": body["version"], "status": "ACTIVE",
                                 "manifest_sha256": "0" * 64, "self_approved": False, "deployment_id": "d1",
                                 "rendered_sha256": "1" * 64})
            else:
                self._send(404, NOT_FOUND, PROBLEM)

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.fixture
def fake_admin():
    """``(state, server_url)``; ``state.apps[(id, version)] = {"status", "by"}``; ``state.calls`` ghi mọi
    request."""
    if shutil.which("dxos") is None or shutil.which("sh") is None:
        pytest.skip("cần CLI dxos (make dev-install) và sh")
    state = FakeAdmin()
    srv = _server(state)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield state, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
