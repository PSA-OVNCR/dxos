# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/vuot_rao.py`` (Plan 03 Task 11): bảng thử vượt rào chạy trên một stack giả (``httpx.MockTransport``).

Stack giả (``FakeStack``) cài đúng các luật mà bảng thử kiểm: chỉ người tạo sửa được, tự duyệt bị chặn, rà PII
trước khi ban hành, niêm phong khóa sửa, ``:check`` chỉ nhận JSON... Tham số ``leak`` cho một kịch bản "lọt":
máy chủ giả trả 200 đúng chỗ mà bảng thử mong bị chặn, bảng thử phải ghi ❌ và thoát mã 1.
Lần chạy thật trên stack dev là việc V28 của trưởng nhóm.
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
_spec = importlib.util.spec_from_file_location("vuot_rao", ROOT / "ops/vuot_rao.py")
vuot_rao = importlib.util.module_from_spec(_spec)
sys.modules["vuot_rao"] = vuot_rao                     # dataclass cần module đã đăng ký
_spec.loader.exec_module(vuot_rao)

ALL = [f"V{i}" for i in range(1, 11)]
PROBLEM = "application/problem+json"
ROLES = {
    "chuyen_vien1": {"chuyen_vien"}, "chuyen_vien_tp1": {"chuyen_vien", "truong_phong"},
    "truong_phong1": {"truong_phong"}, "giam_doc1": {"giam_doc"}, "van_thu1": {"van_thu"},
    "can_bo_clb1": {"can_bo_clb"}, "truong_clb1": {"truong_clb"}, "admin1": set(),
}
APP_OF = {"chuyen_vien": "phong-ho-so", "truong_phong": "phong-ho-so", "giam_doc": "phong-ho-so",
          "van_thu": "phong-ho-so", "can_bo_clb": "chung-nhan", "truong_clb": "chung-nhan"}
READ_A = {"truong_phong", "giam_doc", "van_thu", "nhan_vien"}
TASK_ROLE = {"duyet_noi_dung": "truong_phong", "ban_hanh": "giam_doc"}
RECORDS = re.compile(r"^/api/v1/apps/([a-z-]+)/collections/van_ban/records(?:/([0-9a-f-]+))?"
                     r"(:pii-review|/attachments|/workflow:start)?$")
COMPLETE = re.compile(r"^/api/v1/apps/([a-z-]+)/tasks/([0-9a-f-]+):complete$")


def problem(status: int, slug: str, **ext) -> httpx.Response:
    return httpx.Response(status, json={"type": f"https://dxos.dev/problems/{slug}", "title": slug,
                                        "status": status, **ext}, headers={"content-type": PROBLEM})


class FakeStack:
    """Một stack giả đủ cho 10 kịch bản. ``leak``: tập mã kịch bản mà máy chủ giả để lọt."""

    def __init__(self, leak: set[str] | None = None, *, token_status: int = 200) -> None:
        self.leak = leak or set()
        self.token_status = token_status
        self.requests: list[httpx.Request] = []
        self.records: dict[str, dict] = {}
        self.uploads: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.ledger: list[dict] = []
        self.transport = httpx.MockTransport(self.handle)

    # ------------------------------------------------------------------ tiện ích
    @staticmethod
    def user(req: httpx.Request) -> str | None:
        auth = req.headers.get("authorization", "")
        return auth.removeprefix("Bearer tok-") if auth.startswith("Bearer tok-") else None

    def roles(self, user: str | None, app: str) -> set[str]:
        return {r for r in ROLES.get(user or "", set()) if APP_OF[r] == app}

    def deny(self, user: str | None, app: str | None, subject: str) -> None:
        n = len(self.ledger)
        self.ledger.append({"idx": 100 + n, "ts": f"2026-10-22T03:{n:02d}:05.5Z", "type": "policy.denied",
                            "app_id": app, "subject": subject, "actor_ref": "ab" * 8})

    @staticmethod
    def version(req: httpx.Request) -> int | str:
        m = re.fullmatch(r'"(\d+)"', req.headers.get("if-match", ""))
        return int(m[1]) if m else "bad"

    # ------------------------------------------------------------------ định tuyến
    def handle(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path, user = req.url.path, self.user(req)
        if path.endswith("/openid-connect/token"):
            form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            assert form["client_id"] == "dxos-test" and form["grant_type"] == "password"
            return httpx.Response(200, json={"access_token": f"tok-{form['username']}", "expires_in": 300})
        if path.startswith("/verify/v1/seals/") and path.endswith(":check"):
            if req.headers.get("content-type", "").split(";")[0] == "application/json":
                return httpx.Response(200, json={"match": False})
            if "V7" in self.leak:
                return httpx.Response(200, json={"match": False})
            return problem(415, "unsupported-media-type")
        if path == "/admin/v1/apps" and req.method == "POST":
            return self.submit(req, user)
        if path == "/admin/v1/ledger/entries":
            return self.ledger_entries(req, user)
        if m := re.fullmatch(r"/api/v1/uploads/([0-9a-f-]+)", path):
            up = self.uploads.get(m[1])
            if up is None:
                return problem(404, "not-found")
            body = {"status": up["status"]}
            clean = up["status"] == "CLEAN"
            body.update({"sha256": up["sha"]} if clean else {"reason": "Eicar-Test-Signature"})
            return httpx.Response(200, json=body)
        if m := re.fullmatch(r"/api/v1/objects/([0-9a-f]{64})", path):
            return self.get_object(m[1], user)
        if m := COMPLETE.match(path):
            return self.complete(req, user, m[1], m[2])
        if m := re.fullmatch(r"/api/v1/apps/([a-z-]+)/tasks", path):
            return self.inbox(user, m[1])
        if m := RECORDS.match(path):
            return self.records_api(req, user, *m.groups())
        return problem(404, "not-found")

    def submit(self, req: httpx.Request, user: str | None) -> httpx.Response:
        if user != "admin1":
            return problem(403, "forbidden")
        manifest = httpx.Response(200, content=req.content).json()["manifest"]
        weakened = "optional" in str(manifest)
        if weakened and "V9" not in self.leak:
            return problem(422, "manifest-invalid", code="FLOOR_WEAKENED", path="/collections/item")
        return httpx.Response(202, json={"app_id": manifest["app"]["id"], "status": "PENDING"})

    def ledger_entries(self, req: httpx.Request, user: str | None) -> httpx.Response:
        if user != "admin1":
            return problem(403, "forbidden")
        assert req.url.params["type"] == "policy.denied" and req.url.params["limit"] == "20"
        return httpx.Response(200, json={"items": list(reversed(self.ledger))[:20]})

    def get_object(self, sha: str, user: str | None) -> httpx.Response:
        owner_ok = any(up["sha"] == sha and up["status"] == "CLEAN" for up in self.uploads.values())
        if owner_ok or "V8" in self.leak:
            return httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
        self.deny(user, None, "read")
        return problem(404, "not-found")

    def records_api(self, req: httpx.Request, user: str | None, app: str, rid: str | None,
                    action: str | None) -> httpx.Response:
        mine = self.roles(user, app)
        if rid is None:
            if req.method == "POST":
                if "chuyen_vien" not in mine:
                    return problem(403, "forbidden")
                rid = str(uuid.uuid4())
                self.records[rid] = {"owner": user, "version": 1, "seal_state": "NONE", "wf": None,
                                     "reviewed": False}
                return httpx.Response(201, json={"id": rid, "version": 1})
            leak = ("V3" in self.leak and user == "can_bo_clb1") or ("V4" in self.leak and user == "admin1")
            if not mine and not leak:
                self.deny(user, app, "list")
                return problem(403, "forbidden")
            return httpx.Response(200, json={"items": []})
        rec = self.records.get(rid)
        if rec is None:
            return problem(404, "not-found")
        can_read = user == rec["owner"] or bool(mine & READ_A)
        if action == "/attachments":
            return self.upload(req, rec, rid, user)
        if action == "/workflow:start":
            return self.start(req, rec, user)
        if action == ":pii-review":
            if not (mine & {"giam_doc", "van_thu"}) or not can_read:
                self.deny(user, app, "not_pii_reviewer")
                return problem(404, "not-found")
            rec["reviewed"], rec["version"] = True, rec["version"] + 1
            return httpx.Response(200, json={"id": rid, "version": rec["version"]})
        if req.method == "GET":
            if not can_read and not ("V2" in self.leak and user == "chuyen_vien1"):
                self.deny(user, app, "read")
                return problem(404, "not-found")
            return httpx.Response(200, json={"id": rid, "version": rec["version"],
                                             "seal_state": rec["seal_state"]})
        return self.patch(req, rec, user)

    def patch(self, req: httpx.Request, rec: dict, user: str | None) -> httpx.Response:
        if self.version(req) == "bad":
            return problem(400, "bad-request")
        if user != rec["owner"]:
            self.deny(user, "phong-ho-so", "update")
            return problem(404, "not-found")
        if rec["seal_state"] != "NONE" and "V5" not in self.leak:
            return problem(409, "record-sealed", detail=f"seal_state={rec['seal_state']}")
        rec["version"] += 1
        return httpx.Response(200, json={"version": rec["version"]})

    def upload(self, req: httpx.Request, rec: dict, rid: str, user: str | None) -> httpx.Response:
        if user != rec["owner"]:
            return problem(404, "not-found")
        assert req.headers["content-type"].startswith("multipart/form-data")
        data = req.content
        infected = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data
        uid = str(uuid.uuid4())
        self.uploads[uid] = {"status": "INFECTED" if infected else "CLEAN", "rid": rid,
                             "sha": hashlib.sha256(data).hexdigest()}
        rec["clean"] = rec.get("clean", 0) + (0 if infected else 1)
        return httpx.Response(202, json={"upload_id": uid, "status": "STAGING"})

    def start(self, req: httpx.Request, rec: dict, user: str | None) -> httpx.Response:
        if self.version(req) != rec["version"]:
            return problem(409, "version-conflict")
        if user != rec["owner"]:
            return problem(404, "not-found")
        if not rec.get("clean"):
            return problem(409, "attachments-not-clean")
        rec["wf"], rec["version"] = "running", rec["version"] + 1
        rid = next(k for k, v in self.records.items() if v is rec)
        self.open_task(rid, "duyet_noi_dung")
        return httpx.Response(200, json={"version": rec["version"], "wf_state": "running"})

    def open_task(self, rid: str, key: str) -> None:
        self.tasks[str(uuid.uuid4())] = {"record_id": rid, "task_key": key, "app": "phong-ho-so"}

    def inbox(self, user: str | None, app: str) -> httpx.Response:
        mine = self.roles(user, app)
        if not mine:
            return problem(403, "forbidden")
        items = [{"task_id": tid, "task_key": t["task_key"], "record_id": t["record_id"],
                  "name": t["task_key"], "collection": "van_ban", "created": "2026-10-22T10:00:00.000+07:00"}
                 for tid, t in self.tasks.items() if t["app"] == app and TASK_ROLE[t["task_key"]] in mine]
        return httpx.Response(200, json={"items": items})

    def complete(self, req: httpx.Request, user: str | None, app: str, task_id: str) -> httpx.Response:
        task = self.tasks.get(task_id)
        mine = self.roles(user, app)
        foreign_ok = "V10" in self.leak and user == "truong_clb1"
        if task is None or (task["app"] != app and not foreign_ok):
            self.deny(user, app, "not_task_role")
            return problem(404, "not-found")
        rec = self.records[task["record_id"]]
        if self.version(req) == "bad":
            return problem(428 if "if-match" not in req.headers else 400, "precondition-required")
        if self.version(req) != rec["version"]:
            return problem(409, "version-conflict")
        if TASK_ROLE[task["task_key"]] not in mine and not foreign_ok:
            self.deny(user, app, "not_task_role")
            return problem(404, "not-found")
        if task["task_key"] == "duyet_noi_dung" and user == rec["owner"] and "V1" not in self.leak:
            return problem(403, "guard-failed", guard="not_same_actor:creator", reason="same_actor")
        if task["task_key"] == "ban_hanh" and not rec["reviewed"] and "V6" not in self.leak:
            return problem(409, "guard-failed", guard="pii_reviewed", reason="pii_not_reviewed")
        del self.tasks[task_id]
        rec["version"] += 1
        if task["task_key"] == "duyet_noi_dung":
            self.open_task(task["record_id"], "ban_hanh")
        else:
            rec["seal_state"] = "SEALED"
        return httpx.Response(200, json={"record": {"version": rec["version"]},
                                         "seal_state": rec["seal_state"]})


# ---------------------------------------------------------------------- chạy bảng thử
def run(stack: FakeStack, *argv: str, environ: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    env = {"DXOS_E2E_PASSWORD": "mat-khau-thu"} | (environ or {})
    code = vuot_rao.main(list(argv), transport=stack.transport, environ=env, stdout=out, stderr=err,
                         sleep=lambda _s: None)
    return code, out.getvalue(), err.getvalue()


def rows(text: str) -> dict[str, list[str]]:
    """Bảng kết quả → ``{"V1": [cột...]}``."""
    found = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"V\d+", cells[0]) and len(cells) == 5:
            found[cells[0]] = cells
    return found


def test_all_blocked_prints_table_and_exits_0():
    stack = FakeStack()
    code, out, err = run(stack)
    assert code == 0, (out, err)
    assert "| # | Hành vi tấn công | Kỳ vọng | Thực tế | Kết quả |" in out
    table = rows(out)
    assert list(table) == ALL
    assert all(r[4] == "✅" for r in table.values()), out
    assert "403 guard-failed (same_actor)" in table["V1"][3]
    assert "409 guard-failed (pii_reviewed)" in table["V6"][3]
    assert table["V8"][3].startswith("INFECTED")


def test_expectations_column_matches_the_brief():
    _, out, _ = run(FakeStack())
    table = rows(out)
    assert table["V1"][2] == "403 guard-failed (same_actor)"
    assert table["V2"][2] == "404"
    assert table["V3"][2] == "403"
    assert table["V4"][2] == "403"
    assert table["V5"][2] == "409 record-sealed"
    assert table["V6"][2] == "409 guard-failed (pii_reviewed)"
    assert table["V7"][2] == "415"
    assert table["V8"][2] == "INFECTED; đọc tệp → 404"
    assert table["V9"][2] == "422 manifest-invalid"
    assert table["V10"][2] == "404"


@pytest.mark.parametrize("vid", ALL)
def test_leak_is_marked_and_exit_code_1(vid):
    stack = FakeStack(leak={vid})
    code, out, err = run(stack)
    assert code == 1, (out, err)
    table = rows(out)
    assert table[vid][4] == "❌", out
    assert {k for k, r in table.items() if r[4] == "✅"} == set(ALL) - {vid}, out


@pytest.mark.parametrize("vid", ALL)
def test_only_runs_one_scenario_independently(vid):
    stack = FakeStack()
    code, out, err = run(stack, "--only", vid)
    assert code == 0, (out, err)
    assert list(rows(out)) == [vid]


def test_only_accepts_a_list_and_rejects_unknown_ids():
    code, out, _ = run(FakeStack(), "--only", "V3,V1")
    assert code == 0 and list(rows(out)) == ["V1", "V3"]
    stack = FakeStack()
    code, _, err = run(stack, "--only", "V11")
    assert code == 2 and "V11" in err
    assert stack.requests == []


def test_v5_seals_through_the_whole_workflow_before_editing():
    stack = FakeStack()
    run(stack, "--only", "V5")
    sealed = [r for r in stack.records.values() if r["seal_state"] == "SEALED"]
    assert len(sealed) == 1
    assert sealed[0]["reviewed"] is True


def test_v8_never_writes_the_raw_eicar_string_into_the_request_log_or_output():
    stack = FakeStack()
    _, out, err = run(stack, "--only", "V8")
    assert "EICAR-STANDARD-ANTIVIRUS-TEST-FILE" not in out + err   # chỉ ở bộ nhớ, không in ra
    infected = [u for u in stack.uploads.values() if u["status"] == "INFECTED"]
    assert len(infected) == 1


def test_v9_posts_the_weakened_manifest_straight_to_the_admin_api_with_admin_token():
    stack = FakeStack()
    run(stack, "--only", "V9")
    posts = [r for r in stack.requests if r.method == "POST" and r.url.path == "/admin/v1/apps"]
    assert len(posts) == 1
    assert posts[0].url.host == "admin.localhost"
    assert posts[0].headers["authorization"] == "Bearer tok-admin1"
    body = httpx.Response(200, content=posts[0].content).json()
    assert set(body) == {"manifest", "files"}
    assert "optional" in str(body["manifest"]) and "quarantine" in str(body["manifest"])


def test_v7_sends_the_pdf_bytes_with_pdf_content_type_without_token():
    stack = FakeStack()
    run(stack, "--only", "V7")
    check = [r for r in stack.requests if r.url.path.endswith(":check")]
    assert len(check) == 1
    assert check[0].headers["content-type"] == "application/pdf"
    assert check[0].content.startswith(b"%PDF")
    assert "authorization" not in check[0].headers


def test_if_match_is_always_quoted():
    stack = FakeStack()
    code, out, _ = run(stack, "--only", "V1,V5,V6,V10")
    assert code == 0, out
    sent = [r.headers["if-match"] for r in stack.requests if "if-match" in r.headers]
    assert sent and all(re.fullmatch(r'"\d+"', h) for h in sent)


def test_ledger_leaves_are_listed_in_vietnam_time_newest_first():
    stack = FakeStack()
    code, out, _ = run(stack, "--only", "V2,V3")
    assert code == 0, out
    assert "policy.denied" in out
    # ts giả 2026-10-22T03:00:05.5Z → 10:00:05 giờ Việt Nam (UTC+7)
    assert "22/10/2026 10:00:05" in out
    assert "idx" in out and "phong-ho-so" in out
    pos = [out.index(f"| {d['idx']} |") for d in stack.ledger]
    assert pos == sorted(pos, reverse=True)                  # lá mới nhất (idx lớn) in trước


def test_at_most_20_ledger_leaves_are_requested():
    stack = FakeStack()
    run(stack, "--only", "V2")
    asked = [r for r in stack.requests if r.url.path == "/admin/v1/ledger/entries"]
    assert len(asked) == 1 and asked[0].url.host == "admin.localhost"
    assert dict(asked[0].url.params) == {"type": "policy.denied", "limit": "20"}


def test_ledger_unreadable_when_all_blocked_exits_2():
    stack = FakeStack()
    stack.ledger_entries = lambda req, user: problem(500, "internal")           # type: ignore[method-assign]
    code, out, err = run(stack, "--only", "V2")
    assert code == 2
    assert "✅" in out and "sổ cái" in (out + err)


# ---------------------------------------------------------------------- cấu hình và kết nối
def test_remote_domain_without_allow_remote_exits_2_and_sends_nothing():
    stack = FakeStack()
    code, out, err = run(stack, environ={"DXOS_DOMAIN": "example.vn"})
    assert code == 2
    assert "--allow-remote" in err
    assert stack.requests == []
    assert out == ""


def test_remote_base_flag_without_allow_remote_exits_2_and_sends_nothing():
    stack = FakeStack()
    code, _, err = run(stack, "--base", "https://example.vn", "--admin-base", "https://admin.localhost")
    assert code == 2 and "--allow-remote" in err
    assert stack.requests == []
    stack = FakeStack()
    code, _, err = run(stack, "--admin-base", "https://admin.example.vn")
    assert code == 2 and "--allow-remote" in err
    assert stack.requests == []


def test_allow_remote_runs_against_the_remote_host():
    stack = FakeStack()
    code, out, _ = run(stack, "--allow-remote", "--only", "V2", environ={"DXOS_DOMAIN": "example.vn"})
    assert code == 0, out
    hosts = {r.url.host for r in stack.requests}
    assert hosts == {"example.vn", "admin.example.vn"}


def test_localhost_variants_do_not_need_allow_remote():
    stack = FakeStack()
    code, _, _ = run(stack, "--base", "https://127.0.0.1", "--admin-base", "https://admin.localhost",
                     "--only", "V3")
    assert code == 0


def test_keycloak_refusal_exits_2_without_leaking_the_password():
    stack = FakeStack(token_status=401)
    code, out, err = run(stack)
    assert code == 2
    assert "dxos-test" in err
    assert "mat-khau-thu" not in out + err


def test_password_comes_from_env_never_argv_and_defaults_to_dev_password():
    stack = FakeStack()
    code, _, _ = run(stack, "--only", "V2", environ={"DXOS_E2E_PASSWORD": ""})
    assert code == 0
    first = stack.requests[0]
    assert first.url.path.endswith("/openid-connect/token")
    assert "password=dev-only-password" in first.content.decode()
    assert "--password" not in {a for a in vuot_rao.build_parser().format_help().split()}


def test_connection_error_exits_2():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("không kết nối được", request=request)
    out, err = io.StringIO(), io.StringIO()
    code = vuot_rao.main([], transport=httpx.MockTransport(boom), environ={}, stdout=out, stderr=err,
                         sleep=lambda _s: None)
    assert code == 2
    assert "kết nối" in err.getvalue()


def test_setup_failure_is_marked_not_run_and_exits_2():
    stack = FakeStack()
    real = stack.records_api

    def broken(req, user, app, rid, action):
        if req.method == "POST" and rid is None:
            return problem(500, "internal")
        return real(req, user, app, rid, action)
    stack.records_api = broken                                                   # type: ignore[method-assign]
    code, out, _ = run(stack, "--only", "V2")
    assert code == 2
    assert rows(out)["V2"][4] == "⚠️"


def test_missing_ca_file_exits_2(tmp_path):
    stack = FakeStack()
    code, _, err = run(stack, "--ca-file", str(tmp_path / "khong-co.crt"))
    assert code == 2 and "ca-file" in err
    assert stack.requests == []


# ---------------------------------------------------------------------- phần còn lại
def test_v9_manifest_differs_from_a_valid_one_only_by_the_weakened_quarantine():
    """Nếu manifest V9 sai ở chỗ khác thì 422 không chứng minh được gì về sàn kiểm dịch."""
    from dxos_core.registry.validator import ManifestError, validate_manifest

    stack = FakeStack()
    run(stack, "--only", "V9")
    post = next(r for r in stack.requests if r.url.path == "/admin/v1/apps")
    manifest = httpx.Response(200, content=post.content).json()["manifest"]
    with pytest.raises(ManifestError) as exc:
        validate_manifest(manifest)
    assert exc.value.code == "FLOOR_WEAKENED"
    del manifest["collections"]["item"]["attachments"]["quarantine"]
    assert validate_manifest(manifest).app.id == "vuot-rao-v9"


def test_blocked_for_the_wrong_reason_is_not_counted_as_blocked():
    stack = FakeStack()
    real = stack.complete

    def other_reason(req, user, app, task_id):
        resp = real(req, user, app, task_id)
        return problem(403, "forbidden") if resp.status_code == 403 else resp
    stack.complete = other_reason                                                # type: ignore[method-assign]
    code, out, _ = run(stack, "--only", "V1")
    assert code == 1
    assert rows(out)["V1"][3] == "403 forbidden" and rows(out)["V1"][4] == "❌"


def test_script_runs_as_a_program_and_refuses_remote_without_flag():
    import subprocess

    done = subprocess.run([sys.executable, str(ROOT / "ops/vuot_rao.py")], check=False, capture_output=True,
                          text=True, env={"DXOS_DOMAIN": "example.vn", "PATH": ""}, timeout=60)
    assert done.returncode == 2
    assert "--allow-remote" in done.stderr
    assert done.stdout == ""
