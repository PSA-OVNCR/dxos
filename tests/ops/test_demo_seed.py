# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/demo_seed.py`` (Plan 04 Task 13): nạp dữ liệu demo hư cấu trên stack giả (``MockTransport``).

Stack giả (``FakeStack``) cài các luật mà seed dựa vào: bản ghi App A chỉ chủ thấy, bản ghi App B thấy theo
vai trò, bắt đầu quy trình cần tệp CLEAN và ``If-Match``, ``records:bulk`` từng dòng. Chạy thật trên laptop
là việc V44 của trưởng nhóm.
"""

import hashlib
import importlib.util
import io
import re
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod                            # dataclass cần module đã đăng ký
    spec.loader.exec_module(mod)
    return mod


demo_seed = _load("demo_seed", "ops/demo_seed.py")
make_demo_pdfs = _load("make_demo_pdfs", "demo/make_demo_pdfs.py")

PROBLEM = "application/problem+json"
ROUTE = re.compile(r"^/api/v1/apps/([a-z-]+)/collections/([a-z_]+)/records"
                   r"(?::(bulk)|/([0-9a-f-]+)(/attachments|/workflow:start)?)?$")
OWNERS = {"phong-ho-so": "chuyen_vien1", "chung-nhan": "can_bo_clb1"}
PASSWORD = "mat-khau-thu-nghiem-9f3a"


def problem(status: int, slug: str) -> httpx.Response:
    return httpx.Response(status, json={"type": f"https://dxos.dev/problems/{slug}", "title": slug,
                                        "status": status}, headers={"content-type": PROBLEM})


class FakeStack:
    def __init__(self, *, page: int = 2, fail_upload_once: bool = False, infected: bool = False,
                 token_status: int = 200) -> None:
        self.page, self.fail_upload_once, self.infected = page, fail_upload_once, infected
        self.token_status = token_status
        self.requests: list[httpx.Request] = []
        self.records: dict[str, dict] = {}
        self.uploads: dict[str, dict] = {}
        self.passwords: list[str] = []
        self.transport = httpx.MockTransport(self.handle)

    # -- tiện ích
    @staticmethod
    def user(req: httpx.Request) -> str | None:
        auth = req.headers.get("authorization", "")
        return auth.removeprefix("Bearer tok-") if auth.startswith("Bearer tok-") else None

    def writes(self, since: int = 0) -> list[tuple[str, str]]:
        """(method, path) của mọi request ghi từ request thứ ``since`` (không tính lấy token)."""
        return [(r.method, r.url.path) for r in self.requests[since:]
                if r.method != "GET" and "openid-connect" not in r.url.path]

    def titles(self, app: str) -> list[str]:
        key = "trich_yeu" if app == "phong-ho-so" else "su_kien"
        return [r["data"][key] for r in self.records.values() if r["app"] == app]

    def out(self, rec: dict) -> dict:
        return {"id": rec["id"], "data": rec["data"], "version": rec["version"], "wf_state": rec["wf_state"],
                "seal_state": "NONE", "is_owner": True}

    # -- định tuyến
    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path, user = req.url.path, self.user(req)
        if path.endswith("/openid-connect/token"):
            form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            self.passwords.append(form["password"])
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            assert form["client_id"] == "dxos-test" and form["grant_type"] == "password"
            return httpx.Response(200, json={"access_token": f"tok-{form['username']}", "expires_in": 300})
        if m := re.fullmatch(r"/api/v1/uploads/([0-9a-f-]+)", path):
            up = self.uploads.get(m[1])
            if up is None:
                return problem(404, "not-found")
            return httpx.Response(200, json={"status": up["status"]})
        if m := ROUTE.match(path):
            return self.records_api(req, user, *m.groups())
        return problem(404, "not-found")

    def records_api(self, req: httpx.Request, user: str | None, app: str, col: str, bulk: str | None,
                    rid: str | None, action: str | None) -> httpx.Response:
        if user != OWNERS.get(app):
            return problem(403, "forbidden")
        if bulk:
            return self.bulk(req, app)
        if rid is None:
            if req.method == "POST":
                return self.create(req, app)
            return self.list(req, app)
        rec = self.records.get(rid)
        if rec is None or rec["app"] != app:
            return problem(404, "not-found")
        if action == "/attachments":
            return self.attach(req, rec)
        if action == "/workflow:start":
            return self.start(req, rec)
        return httpx.Response(200, json=self.out(rec))

    def new(self, app: str, data: dict) -> dict:
        rec = {"id": str(uuid.uuid4()), "app": app, "data": data, "version": 1, "wf_state": None, "files": []}
        self.records[rec["id"]] = rec
        return rec

    def create(self, req: httpx.Request, app: str) -> httpx.Response:
        data = httpx.Response(200, content=req.content).json()
        if not data.get("trich_yeu"):
            return problem(422, "schema")
        return httpx.Response(201, json=self.out(self.new(app, data)))

    def bulk(self, req: httpx.Request, app: str) -> httpx.Response:
        rows = httpx.Response(200, content=req.content).json()
        assert isinstance(rows, list) and len(rows) <= 500
        results = []
        for row in rows:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["ngay_cap"])      # ngày đã đổi về ISO
            results.append({"ok": True, "id": self.new(app, row)["id"]})
        return httpx.Response(200, json={"results": results})

    def list(self, req: httpx.Request, app: str) -> httpx.Response:
        assert int(req.url.params["limit"]) <= 200
        items = [r for r in self.records.values() if r["app"] == app]
        start = int(req.url.params.get("cursor", "0"))
        page = items[start:start + self.page]
        more = start + self.page < len(items)
        return httpx.Response(200, json={"items": [self.out(r) for r in page],
                                         "next_cursor": str(start + self.page) if more else None})

    def attach(self, req: httpx.Request, rec: dict) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json={"items": [{"upload_id": u, "status": self.uploads[u]["status"]}
                                                      for u in rec["files"]]})
        if rec["wf_state"] is not None:
            return problem(409, "record-not-open")
        if self.fail_upload_once:
            self.fail_upload_once = False
            return problem(503, "storage-unavailable")
        assert req.headers["content-type"].startswith("multipart/form-data")
        assert req.content.count(b"%PDF-") >= 1
        uid = str(uuid.uuid4())
        self.uploads[uid] = {"status": "INFECTED" if self.infected else "CLEAN",
                             "sha": hashlib.sha256(req.content).hexdigest()}
        rec["files"].append(uid)
        return httpx.Response(202, json={"upload_id": uid, "status": "STAGING"})

    def start(self, req: httpx.Request, rec: dict) -> httpx.Response:
        if req.headers.get("if-match") != f'"{rec["version"]}"':
            return problem(409, "version-conflict")
        clean = any(self.uploads[u]["status"] == "CLEAN" for u in rec["files"])
        if rec["app"] == "phong-ho-so" and not clean:
            return problem(409, "attachments-not-clean")
        rec["wf_state"], rec["version"] = "running", rec["version"] + 1
        return httpx.Response(200, json={"version": rec["version"], "wf_state": "running"})


def seed(stack: FakeStack, *args: str, env: dict[str, str] | None = None):
    out, err = io.StringIO(), io.StringIO()
    environ = {"DXOS_E2E_PASSWORD": PASSWORD, **(env or {})}
    code = demo_seed.main(list(args), transport=stack.transport, environ=environ, stdout=out, stderr=err,
                          sleep=lambda _s: None)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------- idempotency và trạng thái
def test_idempotent_by_marker():
    stack = FakeStack()
    code, out, err = seed(stack)
    assert code == 0, err
    assert len(stack.titles("phong-ho-so")) == 3 and len(stack.titles("chung-nhan")) == 12
    assert all(t.startswith("[DEMO] ") for app in ("phong-ho-so", "chung-nhan") for t in stack.titles(app))
    ids = set(stack.records)

    seen = len(stack.requests)
    code, out, err = seed(stack)
    assert code == 0, err
    assert set(stack.records) == ids                                       # không bản ghi mới
    assert stack.writes(seen) == []                                        # lần 2 không ghi gì lên stack
    assert "3 đã có từ trước" in out and "12 đã có từ trước" in out


def test_leaves_items_in_documented_states():
    stack = FakeStack()
    assert seed(stack)[0] == 0
    a = [r for r in stack.records.values() if r["app"] == "phong-ho-so"]
    assert sorted(r["wf_state"] or "-" for r in a) == ["-", "running", "running"]
    assert all(len(r["files"]) == 1 for r in a)                            # mỗi văn bản đúng một PDF
    draft = next(r for r in a if r["wf_state"] is None)
    assert draft["data"]["trich_yeu"].startswith("[DEMO] Về việc ban hành Quy chế chi tiêu")
    b = [r for r in stack.records.values() if r["app"] == "chung-nhan"]
    assert sum(r["wf_state"] == "running" for r in b) == demo_seed.B_STARTED == 8
    assert sum(r["wf_state"] is None for r in b) == 4


def test_resumes_after_partial_run_without_duplicates():
    stack = FakeStack(fail_upload_once=True)
    code, _, err = seed(stack)
    assert code == 2 and "Chạy lại" in err
    assert len(stack.titles("phong-ho-so")) == 1                           # đã tạo văn bản đầu, chưa có tệp
    assert seed(stack)[0] == 0
    assert len(stack.titles("phong-ho-so")) == 3 and len(stack.titles("chung-nhan")) == 12
    assert all(len(r["files"]) == 1 for r in stack.records.values() if r["app"] == "phong-ho-so")


def test_infected_pdf_stops_with_exit_2():
    code, _, err = seed(FakeStack(infected=True))
    assert code == 2 and "INFECTED" in err


def test_reads_all_pages_when_listing():
    stack = FakeStack(page=1)                                              # mỗi trang một bản ghi
    assert seed(stack)[0] == 0
    seen = len(stack.requests)
    assert seed(stack)[0] == 0 and stack.writes(seen) == []


# ---------------------------------------------------------------------- an toàn
def test_refuses_remote_without_flag():
    stack = FakeStack()
    code, _, err = seed(stack, "--base", "https://dxos.example.com")
    assert code == 2 and "--allow-remote" in err
    assert stack.requests == []                                            # không gửi request nào
    code, _, err = seed(stack, "--base", "https://dxos.example.com", "--allow-remote")
    assert code == 0, err
    assert all(r.url.host == "dxos.example.com" for r in stack.requests)


def test_localhost_family_needs_no_flag():
    for base in ("https://localhost", "https://127.0.0.1", "https://app.localhost"):
        assert demo_seed.is_local(base), base
    assert not demo_seed.is_local("https://localhost.evil.example")


def test_password_never_on_argv_or_stdout():
    stack = FakeStack()
    code, out, err = seed(stack)
    assert code == 0, err
    assert set(stack.passwords) == {PASSWORD}                              # mật khẩu thật sự dùng, từ env
    assert PASSWORD not in out + err
    for r in stack.requests:                                               # chỉ nằm trong thân form lấy token
        assert PASSWORD not in str(r.url)
        assert "openid-connect" in r.url.path or PASSWORD.encode() not in r.content
    # Không có đường nhận mật khẩu qua dòng lệnh.
    with pytest.raises(SystemExit):
        demo_seed.build_parser().parse_args(["--password", PASSWORD])
    options = {o for a in demo_seed.build_parser()._actions for o in a.option_strings}
    assert not any("pass" in o for o in options)
    assert "--password" not in (ROOT / "Makefile").read_text(encoding="utf-8")


def test_wrong_password_is_config_error_without_leak():
    code, out, err = seed(FakeStack(token_status=401))
    assert code == 2 and "Keycloak từ chối" in err and PASSWORD not in out + err


def test_default_password_when_env_missing():
    stack = FakeStack()
    out, err = io.StringIO(), io.StringIO()
    code = demo_seed.main([], transport=stack.transport, environ={}, stdout=out, stderr=err,
                          sleep=lambda _s: None)
    assert code == 0, err.getvalue()
    assert set(stack.passwords) == {"dev-only-password"}


# ---------------------------------------------------------------------- dữ liệu demo
def test_csv_is_fictional_marked():
    raw = demo_seed.CSV_FILE.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                                 # UTF-8 có BOM (Excel tiếng Việt)
    rows = demo_seed.read_csv()
    assert len(rows) == 12
    readme = (ROOT / "demo/README.md").read_text(encoding="utf-8")
    assert "hư cấu" in readme                                              # README nói rõ dữ liệu hư cấu
    text = raw.decode("utf-8-sig")
    assert text.count("hư cấu") >= 12                                      # và mỗi dòng tự mang dấu hiệu
    for row in rows:
        assert row["su_kien"].startswith("[DEMO] ") and "hư cấu" in row["su_kien"]
        assert row["email"].endswith("@example.invalid")                   # không có email thật
    assert "Sự kiện CLB" in rows[0]["su_kien"]


def test_demo_pdfs_are_reproducible():
    built = make_demo_pdfs.build_all()
    assert set(built) == {d.pdf for d in demo_seed.DOCS}
    for name, data in built.items():
        assert data == (ROOT / "demo/sao-mai" / name).read_bytes(), name


def test_demo_pdfs_carry_fictional_pii_for_detection():
    pytest.importorskip("dxos_core")
    from dxos_core.pii import detect_text
    from dxos_core.pii.job import extract

    for name, data in demo_seed.read_pdfs().items():
        text, boxes = extract(data)
        kinds = {f.type for f in detect_text(text, boxes, ("CCCD", "PHONE", "BANK_ACCOUNT"))}
        assert {"CCCD", "PHONE"} <= kinds, name
        assert text.count("hu cau") >= 2, name                             # mỗi số đi kèm chú thích hư cấu


def test_manifest_fields_used_by_seed_exist():
    manifest = (ROOT / "apps/phong-ho-so/manifest.yaml").read_text(encoding="utf-8")
    for d in demo_seed.DOCS:
        assert d.data["trich_yeu"].startswith("[DEMO] ") and "hư cấu" in d.data["trich_yeu"]
        for name in d.data:
            assert f"  {name}:" in manifest or f"      {name}:" in manifest, name
        assert re.fullmatch(r"\d{12}", d.data["nguoi_lien_he_cccd"])


def test_no_real_secrets_or_hosts_in_seed_data():
    blob = ((ROOT / "demo/su-kien-clb.csv").read_text(encoding="utf-8-sig")
            + (ROOT / "demo/README.md").read_text(encoding="utf-8"))
    emails = re.findall(r"[\w.+-]+@[\w.-]+", blob)
    assert emails and all(e.endswith("@example.invalid") for e in emails)
