# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Fixture E2E: gọi stack thật qua Caddy → APISIX → trust-core, token thật từ Keycloak (client dxos-test).

Biến môi trường:
- ``DXOS_E2E_BASE`` (mặc định ``https://localhost``) và ``DXOS_E2E_ADMIN_BASE`` (``https://admin.localhost``).
- ``SSL_CERT_FILE``: CA nội bộ của Caddy (ops/e2e/run_e2e.sh tự lấy).
- ``DXOS_E2E_ANCHOR_REMOTE``: repo neo để witness clone (mặc định bare repo trong volume của worker).
- ``DXOS_E2E_REQUIRE=1``: stack không trả lời thì LỖI thay vì bỏ qua (run_e2e.sh đặt sẵn). Không đặt mà stack
  không chạy (ví dụ ``pytest -m e2e`` trên máy không có Docker) thì mọi test E2E được bỏ qua, có ghi lý do.
- ``DXOS_ORG_NAME``: tên tổ chức đặt trong ``.env`` của stack; AT-28 so ``issuer.name`` với giá trị này.
Chạy: ``ops/e2e/run_e2e.sh`` (trong container) hoặc ``pytest -m e2e tests/e2e`` khi tự chuẩn bị môi trường.

Mốc M2 (Plan 02 Task 15) dùng thêm fixture ``stack`` (các bước API chung của ba bộ test M2). Ứng dụng phải đã
được cài bằng CLI (``ops/e2e/install_apps.sh``) trước khi chạy.
"""

import base64
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

BASE = os.environ.get("DXOS_E2E_BASE", "https://localhost")
ADMIN_BASE = os.environ.get("DXOS_E2E_ADMIN_BASE", "https://admin.localhost")
PASSWORD = os.environ.get("DXOS_E2E_PASSWORD", "dev-only-password")
ANCHOR_REMOTE = os.environ.get("DXOS_E2E_ANCHOR_REMOTE", "file:///var/lib/dxos/anchor-remote.git")
ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "core/tests/fixtures/files"

APP_A, COL_A = "phong-ho-so", "van_ban"
APP_B, COL_B = "chung-nhan", "chung_nhan"


@pytest.fixture(scope="session", autouse=True)
def _stack_reachable() -> None:
    """Bỏ qua cả thư mục khi không có stack, trừ khi ``DXOS_E2E_REQUIRE=1`` (khi đó báo lỗi)."""
    try:
        httpx.get(f"{BASE}/verify/v1/keys", timeout=5)
    except httpx.HTTPError as exc:
        problem = f"stack E2E không trả lời ở {BASE}: {type(exc).__name__}"
        if os.environ.get("DXOS_E2E_REQUIRE") == "1":
            pytest.fail(problem + " (DXOS_E2E_REQUIRE=1)")
        pytest.skip(problem)


@pytest.fixture(scope="session")
def base() -> str:
    return BASE


@pytest.fixture(scope="session")
def admin_base() -> str:
    return ADMIN_BASE


@pytest.fixture(scope="session")
def kc_token():
    """``kc_token(user)`` → access token (password grant của client dev ``dxos-test``), lấy lại khi sắp hết
    hạn (realm đặt access token 300 giây, ngắn hơn thời gian chạy của bộ M2)."""
    cache: dict[str, tuple[str, float]] = {}

    def get(user: str) -> str:
        tok, until = cache.get(user, ("", 0.0))
        if time.monotonic() >= until:
            r = httpx.post(f"{BASE}/auth/realms/dxos/protocol/openid-connect/token", timeout=20, data={
                "grant_type": "password", "client_id": "dxos-test", "username": user, "password": PASSWORD,
                "scope": "openid"})
            r.raise_for_status()
            body = r.json()
            tok, until = body["access_token"], time.monotonic() + max(int(body.get("expires_in", 60)) - 60, 5)
            cache[user] = (tok, until)
        return tok
    return get


class Stack:
    """Các bước API dùng chung của E2E M2. Mọi phương thức nhận tên người dùng dev (``chuyen_vien1``...)."""

    APP_A, COL_A, APP_B, COL_B = APP_A, COL_A, APP_B, COL_B
    ORG_NAME = os.environ.get("DXOS_ORG_NAME")

    def __init__(self, token, base: str, admin_base: str) -> None:
        self.token, self.base, self.admin_base = token, base, admin_base

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def clean_pdf() -> bytes:
        return (FILES / "clean-text.pdf").read_bytes()

    @staticmethod
    def eicar() -> bytes:
        raw = base64.b64decode((FILES / "eicar.xor5a.b64").read_text(encoding="ascii").strip())
        return bytes(b ^ 0x5A for b in raw)   # XOR để Windows Defender không nhận ra tệp mẫu

    def h(self, user: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(user)}", **extra}

    @staticmethod
    def records(app: str, col: str) -> str:
        return f"/api/v1/apps/{app}/collections/{col}/records"

    # ------------------------------------------------------------ bản ghi và tệp
    def create(self, app: str, col: str, data: dict, user: str) -> dict:
        r = httpx.post(self.base + self.records(app, col), json=data, headers=self.h(user), timeout=30)
        assert r.status_code == 201, (r.status_code, r.text)
        return r.json()

    def bulk(self, app: str, col: str, rows: list[dict], user: str) -> list[str]:
        r = httpx.post(self.base + self.records(app, col).replace("/records", "/records:bulk"), json=rows,
                       headers=self.h(user), timeout=60)
        assert r.status_code == 200, (r.status_code, r.text)
        results = r.json()["results"]
        assert all(x["ok"] for x in results), results
        return [x["id"] for x in results]

    def get(self, app: str, col: str, rid: str, user: str) -> dict:
        r = httpx.get(f"{self.base}{self.records(app, col)}/{rid}", headers=self.h(user), timeout=30)
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()

    def version(self, app: str, col: str, rid: str, user: str) -> int:
        return self.get(app, col, rid, user)["version"]

    def upload(self, app: str, col: str, rid: str, data: bytes, user: str, name: str = "tep.pdf") -> str:
        r = httpx.post(f"{self.base}{self.records(app, col)}/{rid}/attachments",
                       files={"file": (name, data, "application/pdf")}, headers=self.h(user), timeout=60)
        assert r.status_code == 202, (r.status_code, r.text)
        return r.json()["upload_id"]

    def wait_upload(self, upload_id: str, user: str, timeout_s: float = 180) -> str:
        deadline = time.monotonic() + timeout_s
        while True:
            st = httpx.get(f"{self.base}/api/v1/uploads/{upload_id}", headers=self.h(user),
                           timeout=30).json()["status"]
            if st != "STAGING" or time.monotonic() > deadline:
                return st
            time.sleep(2)

    # ------------------------------------------------------------ quy trình
    def start(self, app: str, col: str, rid: str, user: str) -> httpx.Response:
        v = self.version(app, col, rid, user)
        return httpx.post(f"{self.base}{self.records(app, col)}/{rid}/workflow:start",
                          headers=self.h(user, **{"If-Match": f'"{v}"'}), timeout=60)

    def task(self, app: str, rid: str, user: str, task_key: str, timeout_s: float = 30) -> dict:
        """Task mở ``task_key`` của bản ghi ``rid`` trong hộp việc của ``user`` (chờ Flowable tạo task)."""
        deadline = time.monotonic() + timeout_s
        while True:
            r = httpx.get(f"{self.base}/api/v1/apps/{app}/tasks", params={"assigned": "me"},
                          headers=self.h(user), timeout=30)
            assert r.status_code == 200, (r.status_code, r.text)
            found = [t for t in r.json()["items"] if t["record_id"] == rid and t["task_key"] == task_key]
            if found or time.monotonic() > deadline:
                assert found, f"không thấy task {task_key} của {rid} trong hộp việc của {user}"
                return found[0]
            time.sleep(1)

    def complete(self, app: str, task_id: str, decision: str, user: str, *,
                 version: int | None) -> httpx.Response:
        headers = self.h(user) if version is None else self.h(user, **{"If-Match": f'"{version}"'})
        return httpx.post(f"{self.base}/api/v1/apps/{app}/tasks/{task_id}:complete",
                          json={"decision": decision}, headers=headers, timeout=60)

    def complete_task(self, app: str, col: str, rid: str, task_key: str, decision: str,
                      user: str) -> httpx.Response:
        t = self.task(app, rid, user, task_key)
        return self.complete(app, t["task_id"], decision, user, version=self.version(app, col, rid, user))

    def pii_review(self, app: str, col: str, rid: str, user: str) -> httpx.Response:
        v = self.version(app, col, rid, user)
        return httpx.post(f"{self.base}{self.records(app, col)}/{rid}:pii-review",
                          headers=self.h(user, **{"If-Match": f'"{v}"'}), timeout=30)

    def wait_sealed(self, app: str, col: str, rid: str, user: str, timeout_s: float = 120) -> dict:
        """Chờ ``seal_state = SEALED`` (niêm phong ngay sau task cuối, hoặc job thử lại khi
        ``SEAL_PENDING``)."""
        deadline = time.monotonic() + timeout_s
        while True:
            rec = self.get(app, col, rid, user)
            if rec["seal_state"] == "SEALED" or time.monotonic() > deadline:
                assert rec["seal_state"] == "SEALED", rec
                return rec
            time.sleep(2)

    def seal_id(self, app: str, col: str, rid: str, user: str) -> str:
        r = httpx.get(f"{self.base}{self.records(app, col)}/{rid}/seal", headers=self.h(user), timeout=30)
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()["seal_id"]

    # ------------------------------------------------------------ cổng công khai, neo
    def public(self, seal_id: str) -> httpx.Response:
        return httpx.get(f"{self.base}/verify/v1/seals/{seal_id}", timeout=30)

    def wait_anchored(self, seal_id: str, timeout_s: float = 240) -> dict:
        """Chạy neo ngay rồi chờ tới khi trang công khai báo STH đã neo PHỦ lá của niêm phong."""
        r = httpx.post(f"{self.admin_base}/admin/v1/anchor:run", json={}, headers=self.h("admin1"),
                       timeout=60)
        assert r.status_code == 200, (r.status_code, r.text)
        deadline = time.monotonic() + timeout_s
        while True:
            view = self.public(seal_id).json()
            if view["inclusion"]["anchored"] is not None or time.monotonic() > deadline:
                assert view["inclusion"]["anchored"] is not None, view
                return view
            time.sleep(3)

    @staticmethod
    def clone_anchor(dest: Path) -> Path:
        if (dest / ".git").is_dir():
            subprocess.run(["git", "-C", str(dest), "pull", "-q", "--ff-only"], check=True)  # noqa: S603, S607
        else:
            subprocess.run(["git", "clone", "-q", ANCHOR_REMOTE, str(dest)], check=True)  # noqa: S603, S607
        return dest

    @staticmethod
    def verify_bundle(bundle: Path, anchor_dir: Path,
                      file: Path | None = None) -> subprocess.CompletedProcess:
        cmd = ["dxos-witness", "verify-bundle", str(bundle), "--anchor-dir", str(anchor_dir)]
        if file is not None:
            cmd += ["--file", str(file)]
        out = subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603
        print(out.stdout, out.stderr)
        return out

    # ------------------------------------------------------------ CLI quản trị
    def cli(self, *args: str, user: str = "admin1") -> subprocess.CompletedProcess:
        """``dxos --server <admin> [--ca-file $SSL_CERT_FILE] <args>`` với ``DXOS_TOKEN`` của ``user``."""
        exe = shutil.which("dxos")
        assert exe is not None, "cần CLI dxos (pip install ./cli)"
        cmd = [exe, "--server", self.admin_base]
        if os.environ.get("SSL_CERT_FILE"):
            cmd += ["--ca-file", os.environ["SSL_CERT_FILE"]]
        env = {**os.environ, "DXOS_TOKEN": self.token(user)}
        out = subprocess.run([*cmd, *args], check=False, capture_output=True, text=True, env=env)  # noqa: S603
        print(out.stdout, out.stderr)
        return out


@pytest.fixture(scope="session")
def stack(kc_token, base, admin_base) -> Stack:
    return Stack(kc_token, base, admin_base)
