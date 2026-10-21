#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bảng thử vượt rào (Plan 03 Task 11; spec 9.1, H11, P3-D9).

Chạy 10 kịch bản tấn công qua cổng thật (Caddy, APISIX, lõi) bằng token của người dùng dev, in bảng
``| # | Hành vi tấn công | Kỳ vọng | Thực tế | Kết quả |``, rồi 20 lá ``policy.denied`` gần nhất của sổ cái.

    python ops/vuot_rao.py [--base https://localhost] [--admin-base https://admin.localhost]
                           [--ca-file F] [--allow-remote] [--only V1,V3]

Mã thoát: 0 mọi kịch bản bị chặn đúng; 1 có kịch bản lọt (hoặc bị chặn sai cách); 2 lỗi cấu hình hoặc kết nối
(kể cả bước chuẩn bị của một kịch bản lỗi, hoặc không đọc được sổ cái).

Điều kiện (P3-D9): stack có realm dev (client ``dxos-test`` và người dùng dev). Mật khẩu dev đọc từ biến
môi trường ``DXOS_E2E_PASSWORD`` (mặc định ``dev-only-password``), không bao giờ nhận qua tham số dòng lệnh và
không in ra. Địa chỉ mặc định lấy từ ``DXOS_DOMAIN`` (và ``DXOS_ADMIN_HOST``); khác ``localhost`` thì phải
thêm ``--allow-remote``, thiếu cờ này thì không gửi request nào. Mỗi kịch bản tự tạo dữ liệu của nó và độc
lập với các kịch bản khác. Bản ghi tạo ra (tiêu đề "Vượt rào Vn") nằm lại trên stack dev; sổ cái chỉ-thêm
nên không xóa được dấu vết.

EICAR chỉ được giải mã trong bộ nhớ từ ``core/tests/fixtures/files/eicar.xor5a.b64`` (XOR 0x5A), không ghi ra
tệp và không in ra.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import ssl
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "core/tests/fixtures/files"
VN = timezone(timedelta(hours=7))

APP_A, COL_A = "phong-ho-so", "van_ban"
APP_B = "chung-nhan"
CCCD = "079203001235"                       # số giả như tests/e2e: để bước rà PII có việc thật phải làm
ADMIN_USER = "admin1"
DEFAULT_PASSWORD = "dev-only-password"      # noqa: S105 - mật khẩu của realm dev, ghi trong tài liệu
PROBLEM_BASE = "https://dxos.dev/problems/"
OK, LEAK, NOT_RUN = "✅", "❌", "⚠️"


class ConfigError(Exception):
    """Lỗi cấu hình hoặc môi trường: không chạy được bảng thử (mã thoát 2)."""


class StepError(Exception):
    """Một bước chuẩn bị của kịch bản không như mong đợi: kịch bản không chạy được."""


@dataclass(frozen=True)
class Outcome:
    actual: str
    ok: bool


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    expected: str
    run: Callable[[Api], Outcome]


# ---------------------------------------------------------------------- mô tả phản hồi
def slug_of(resp: httpx.Response) -> tuple[str | None, dict[str, Any]]:
    """``(slug, body)`` của một problem+json; ``(None, {})`` khi thân không phải JSON object kiểu problem."""
    try:
        body = resp.json()
    except ValueError:
        return None, {}
    if not isinstance(body, dict) or not str(body.get("type", "")).startswith(PROBLEM_BASE):
        return None, body if isinstance(body, dict) else {}
    return str(body["type"]).removeprefix(PROBLEM_BASE), body


def describe(resp: httpx.Response, ext: str | None = None) -> str:
    """``"403 guard-failed (same_actor)"``: mã, slug (nếu có), rồi giá trị của trường mở rộng ``ext``."""
    slug, body = slug_of(resp)
    text = str(resp.status_code) + (f" {slug}" if slug else "")
    if ext and body.get(ext):
        text += f" ({body[ext]})"
    return text


def judge(resp: httpx.Response, status: int, slug: str | None = None, **ext: str) -> Outcome:
    """Đúng khi mã, slug (nếu đòi) và các trường mở rộng (``guard=``, ``reason=``) đều khớp."""
    got_slug, body = slug_of(resp)
    ok = resp.status_code == status and (slug is None or got_slug == slug)
    ok = ok and all(body.get(k) == v for k, v in ext.items())
    shown = next((k for k in ("reason", "guard", "code") if k in ext), None)
    return Outcome(describe(resp, shown), ok)


# ---------------------------------------------------------------------- phiên làm việc với stack
class Api:
    """Các lời gọi dùng chung của kịch bản; cùng hình dạng với ``Stack`` của tests/e2e/conftest.py."""

    def __init__(self, client: httpx.Client, base: str, admin_base: str, password: str, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.client, self.base, self.admin_base = client, base.rstrip("/"), admin_base.rstrip("/")
        self._password, self._sleep, self._clock = password, sleep, clock
        self._tokens: dict[str, tuple[str, float]] = {}

    # -- token
    def token(self, user: str) -> str:
        tok, until = self._tokens.get(user, ("", 0.0))
        if self._clock() >= until:
            r = self.client.post(f"{self.base}/auth/realms/dxos/protocol/openid-connect/token", data={
                "grant_type": "password", "client_id": "dxos-test", "username": user,
                "password": self._password, "scope": "openid"})
            if r.status_code != 200:
                raise ConfigError(
                    f"Keycloak từ chối cấp token cho {user}: HTTP {r.status_code}. Stack có realm dev (client"
                    " dxos-test, người dùng dev) và DXOS_E2E_PASSWORD đúng không?")
            body = r.json()
            tok = body["access_token"]
            self._tokens[user] = (tok, self._clock() + max(int(body.get("expires_in", 60)) - 60, 5))
        return tok

    def call(self, method: str, url: str, user: str | None = None, *, if_match: int | None = None,
             **kw: Any) -> httpx.Response:
        headers = dict(kw.pop("headers", {}))
        if user is not None:
            headers["Authorization"] = f"Bearer {self.token(user)}"
        if if_match is not None:
            headers["If-Match"] = f'"{if_match}"'
        return self.client.request(method, url, headers=headers, **kw)

    @staticmethod
    def need(resp: httpx.Response, status: int, what: str) -> httpx.Response:
        if resp.status_code != status:
            raise StepError(f"{what}: mong {status}, nhận {describe(resp)}")
        return resp

    # -- bản ghi và tệp
    @staticmethod
    def records(app: str = APP_A, col: str = COL_A) -> str:
        return f"/api/v1/apps/{app}/collections/{col}/records"

    def create(self, user: str, title: str) -> str:
        r = self.call("POST", self.base + self.records(), user,
                      json={"trich_yeu": title, "nguoi_lien_he_cccd": CCCD})
        return str(self.need(r, 201, f"{user} tạo văn bản").json()["id"])

    def version(self, rid: str, user: str) -> int:
        r = self.call("GET", f"{self.base}{self.records()}/{rid}", user)
        return int(self.need(r, 200, f"{user} đọc văn bản").json()["version"])

    def upload(self, rid: str, user: str, data: bytes) -> str:
        r = self.call("POST", f"{self.base}{self.records()}/{rid}/attachments", user,
                      files={"file": ("tep.pdf", data, "application/pdf")})
        return str(self.need(r, 202, "tải tệp đính kèm").json()["upload_id"])

    def wait_upload(self, upload_id: str, user: str, timeout_s: float = 180) -> dict[str, Any]:
        deadline = self._clock() + timeout_s
        while True:
            r = self.call("GET", f"{self.base}/api/v1/uploads/{upload_id}", user)
            body = self.need(r, 200, "hỏi trạng thái tệp").json()
            if body["status"] != "STAGING" or self._clock() > deadline:
                return body
            self._sleep(2)

    # -- quy trình
    def start(self, rid: str, user: str) -> None:
        r = self.call("POST", f"{self.base}{self.records()}/{rid}/workflow:start", user,
                      if_match=self.version(rid, user))
        self.need(r, 200, "bắt đầu quy trình")

    def task(self, app: str, rid: str, user: str, task_key: str, timeout_s: float = 30) -> str:
        deadline = self._clock() + timeout_s
        while True:
            r = self.call("GET", f"{self.base}/api/v1/apps/{app}/tasks", user, params={"assigned": "me"})
            items = self.need(r, 200, f"{user} xem hộp việc").json()["items"]
            found = [t for t in items if t["record_id"] == rid and t["task_key"] == task_key]
            if found:
                return str(found[0]["task_id"])
            if self._clock() > deadline:
                raise StepError(f"không thấy task {task_key} của văn bản trong hộp việc của {user}")
            self._sleep(1)

    def complete(self, app: str, task_id: str, user: str, version: int,
                 decision: str = "approve") -> httpx.Response:
        return self.call("POST", f"{self.base}/api/v1/apps/{app}/tasks/{task_id}:complete", user,
                         if_match=version, json={"decision": decision})

    def complete_ok(self, rid: str, task_key: str, user: str) -> None:
        task_id = self.task(APP_A, rid, user, task_key)
        r = self.complete(APP_A, task_id, user, self.version(rid, user))
        self.need(r, 200, f"{user} hoàn thành {task_key}")

    def pii_review(self, rid: str, user: str) -> None:
        r = self.call("POST", f"{self.base}{self.records()}/{rid}:pii-review", user,
                      if_match=self.version(rid, user))
        self.need(r, 200, f"{user} xác nhận rà PII")

    def wait_sealed(self, rid: str, user: str, timeout_s: float = 120) -> None:
        deadline = self._clock() + timeout_s
        while True:
            r = self.call("GET", f"{self.base}{self.records()}/{rid}", user)
            if self.need(r, 200, "đọc văn bản").json()["seal_state"] == "SEALED":
                return
            if self._clock() > deadline:
                raise StepError("văn bản chưa SEALED sau khi giám đốc ban hành")
            self._sleep(2)

    # -- dữ liệu dùng chung của kịch bản
    def started_record(self, title: str, creator: str = "chuyen_vien_tp1") -> str:
        """Văn bản có một PDF sạch và đã bắt đầu quy trình (đang chờ ``duyet_noi_dung``)."""
        rid = self.create(creator, title)
        up = self.wait_upload(self.upload(rid, creator, clean_pdf()), creator)
        if up["status"] != "CLEAN":
            raise StepError(f"PDF mẫu không CLEAN: {up['status']}")
        self.start(rid, creator)
        return rid


def clean_pdf() -> bytes:
    return _fixture("clean-text.pdf")


def eicar() -> bytes:
    raw = base64.b64decode(_fixture("eicar.xor5a.b64").decode("ascii").strip())
    return bytes(b ^ 0x5A for b in raw)


def _fixture(name: str) -> bytes:
    path = FILES / name
    if not path.is_file():
        raise ConfigError(f"thiếu tệp mẫu {path} (chạy từ bản sao đầy đủ của repo)")
    return path.read_bytes()


# ---------------------------------------------------------------------- 10 kịch bản
def v1(api: Api) -> Outcome:
    rid = api.started_record("Vượt rào V1")
    task_id = api.task(APP_A, rid, "chuyen_vien_tp1", "duyet_noi_dung")     # người tạo kiêm trưởng phòng
    r = api.complete(APP_A, task_id, "chuyen_vien_tp1", api.version(rid, "chuyen_vien_tp1"))
    return judge(r, 403, "guard-failed", reason="same_actor")


def v2(api: Api) -> Outcome:
    rid = api.create("chuyen_vien_tp1", "Vượt rào V2")
    r = api.call("GET", f"{api.base}{api.records()}/{rid}", "chuyen_vien1")
    return judge(r, 404, "not-found")           # slug của lõi; 404 của gateway hay app-not-active không tính


def v3(api: Api) -> Outcome:
    r = api.call("GET", api.base + api.records(), "can_bo_clb1")             # chỉ có vai trò của App B
    return judge(r, 403, "forbidden")


def v4(api: Api) -> Outcome:
    r = api.call("GET", api.base + api.records(), ADMIN_USER)                # dxos-admin không có vai trò app
    return judge(r, 403, "forbidden")


def v5(api: Api) -> Outcome:
    creator = "chuyen_vien_tp1"
    rid = api.started_record("Vượt rào V5", creator)
    api.complete_ok(rid, "duyet_noi_dung", "truong_phong1")
    api.pii_review(rid, "van_thu1")
    api.complete_ok(rid, "ban_hanh", "giam_doc1")
    api.wait_sealed(rid, "giam_doc1")
    r = api.call("PATCH", f"{api.base}{api.records()}/{rid}", creator, if_match=api.version(rid, creator),
                 json={"trich_yeu": "Sửa sau khi niêm phong"})
    return judge(r, 409, "record-sealed")


def v6(api: Api) -> Outcome:
    rid = api.started_record("Vượt rào V6")
    api.complete_ok(rid, "duyet_noi_dung", "truong_phong1")                  # chưa ai rà PII
    task_id = api.task(APP_A, rid, "giam_doc1", "ban_hanh")
    r = api.complete(APP_A, task_id, "giam_doc1", api.version(rid, "giam_doc1"))
    return judge(r, 409, "guard-failed", guard="pii_reviewed")


def v7(api: Api) -> Outcome:
    seal_id = "A" * 26                  # đúng dạng; lõi kiểm Content-Type trước khi tra niêm phong
    r = api.call("POST", f"{api.base}/verify/v1/seals/{seal_id}:check", content=clean_pdf(),
                 headers={"Content-Type": "application/pdf"})
    return judge(r, 415, "unsupported-media-type")


def v8(api: Api) -> Outcome:
    data = eicar()
    rid = api.create("chuyen_vien1", "Vượt rào V8")
    status = api.wait_upload(api.upload(rid, "chuyen_vien1", data), "chuyen_vien1")["status"]
    if status == "STAGING":                     # hết thời gian chờ mà chưa quét xong: chưa kết luận được gì
        raise StepError("tệp EICAR vẫn STAGING sau khi hết thời gian chờ (ClamAV chưa trả lời?)")
    read = api.call("GET", f"{api.base}/api/v1/objects/{hashlib.sha256(data).hexdigest()}", "chuyen_vien1",
                    params={"variant": "original"})
    blocked = judge(read, 404, "not-found")
    return Outcome(f"{status}; đọc tệp → {blocked.actual}", status == "INFECTED" and blocked.ok)


def v9(api: Api) -> Outcome:
    manifest = {
        "apiVersion": "dxos/v1",
        "app": {"id": "vuot-rao-v9", "version": "0.0.1", "name": "Vượt rào V9", "spaces": ["D"]},
        "roles": ["member"],
        "collections": {"item": {
            "fields": {"title": {"type": "string"}},
            "attachments": {"kinds": ["pdf"], "max_mb": 1, "quarantine": "optional"},      # nới sàn kiểm dịch
            "access": {"read": ["owner"], "create": ["role:member"], "update": ["owner"]}}},
    }
    # Gửi thẳng lên API quản trị (không qua CLI): máy chủ tự từ chối, không dựa kiểm tra cục bộ (P2).
    r = api.call("POST", f"{api.admin_base}/admin/v1/apps", ADMIN_USER,
                 json={"manifest": manifest, "files": {}})
    return judge(r, 422, "manifest-invalid", code="FLOOR_WEAKENED")


def v10(api: Api) -> Outcome:
    rid = api.started_record("Vượt rào V10")
    task_id = api.task(APP_A, rid, "truong_phong1", "duyet_noi_dung")
    version = api.version(rid, "truong_phong1")
    r = api.complete(APP_B, task_id, "truong_clb1", version)                # task của App A, đi đường App B
    return judge(r, 404, "not-found")


SCENARIOS = [
    Scenario("V1", "Người tạo tự duyệt văn bản của mình", "403 guard-failed (same_actor)", v1),
    Scenario("V2", "`chuyen_vien1` đọc văn bản của `chuyen_vien_tp1`", "404 not-found", v2),
    Scenario("V3", "Token chỉ có vai trò App B gọi danh sách văn bản App A", "403 forbidden", v3),
    Scenario("V4", "Admin (`admin1`) đọc dữ liệu App A", "403 forbidden", v4),
    Scenario("V5", "Sửa văn bản đã niêm phong", "409 record-sealed", v5),
    Scenario("V6", "Giám đốc ban hành khi chưa rà PII", "409 guard-failed (pii_reviewed)", v6),
    Scenario("V7", "Gửi nguyên tệp PDF tới `:check`", "415 unsupported-media-type", v7),
    Scenario("V8", "Tải EICAR rồi đọc tệp", "INFECTED; đọc tệp → 404 not-found", v8),
    Scenario("V9", "Nộp manifest nới `quarantine`", "422 manifest-invalid", v9),
    Scenario("V10", "Duyệt bằng task của app khác", "404 not-found", v10),
]
SCENARIO_IDS = [s.id for s in SCENARIOS]


# ---------------------------------------------------------------------- chạy và in
@dataclass(frozen=True)
class Result:
    scenario: Scenario
    actual: str
    mark: str


def run_scenarios(api: Api, chosen: list[Scenario]) -> list[Result]:
    results = []
    for s in chosen:
        try:
            out = s.run(api)
            results.append(Result(s, out.actual, OK if out.ok else LEAK))
        except (StepError, KeyError, ValueError, TypeError) as exc:
            results.append(Result(s, f"không chạy được: {exc}", NOT_RUN))
    return results


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_table(results: list[Result]) -> str:
    lines = ["| # | Hành vi tấn công | Kỳ vọng | Thực tế | Kết quả |", "|---|---|---|---|---|"]
    lines += [f"| {r.scenario.id} | {_cell(r.scenario.title)} | {_cell(r.scenario.expected)}"
              f" | {_cell(r.actual)} | {r.mark} |" for r in results]
    blocked = sum(r.mark == OK for r in results)
    lines.append("")
    lines.append(f"Bị chặn đúng: {blocked}/{len(results)}.")
    return "\n".join(lines)


def vn_time(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(VN).strftime("%d/%m/%Y %H:%M:%S")


def fetch_ledger(api: Api) -> list[dict[str, Any]]:
    r = api.call("GET", f"{api.admin_base}/admin/v1/ledger/entries", ADMIN_USER,
                 params={"type": "policy.denied", "limit": 20})
    if r.status_code != 200:
        raise StepError(f"đọc sổ cái: HTTP {describe(r)}")
    return list(r.json()["items"])


def render_ledger(items: list[dict[str, Any]]) -> str:
    lines = [f"{len(items)} lá `policy.denied` gần nhất của sổ cái (mới nhất trước, giờ Việt Nam UTC+7):", "",
             "| idx | Giờ | app_id | subject |", "|---|---|---|---|"]
    lines += [f"| {i['idx']} | {vn_time(i['ts'])} | {_cell(str(i.get('app_id') or '-'))}"
              f" | {_cell(str(i['subject']))} |" for i in items]
    return "\n".join(lines)


# ---------------------------------------------------------------------- dòng lệnh
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vuot_rao.py", description=__doc__.split("\n\n")[0],
                                epilog="Mật khẩu dev: biến DXOS_E2E_PASSWORD (mặc định dev-only-password).")
    p.add_argument("--base", help="địa chỉ cổng công khai (mặc định https://$DXOS_DOMAIN, hoặc https://localhost)")
    p.add_argument("--admin-base", help="địa chỉ cổng quản trị (mặc định https://$DXOS_ADMIN_HOST, hoặc"
                                        " https://admin.$DXOS_DOMAIN)")
    p.add_argument("--ca-file", help="CA của Caddy nội bộ (mặc định biến SSL_CERT_FILE)")
    p.add_argument("--allow-remote", action="store_true",
                   help="cho phép chạy trên máy khác localhost (chỉ khi stack có realm dev, ví dụ VPS đã"
                        " tạm thêm người dùng dev)")
    p.add_argument("--only", help="chỉ chạy các kịch bản này, ví dụ V1,V3")
    return p


def is_local(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "localhost" or host.endswith(".localhost") or host in ("127.0.0.1", "::1")


def _targets(args: argparse.Namespace, environ: dict[str, str]) -> tuple[str, str]:
    domain = environ.get("DXOS_DOMAIN") or "localhost"
    base = args.base or f"https://{domain}"
    admin = args.admin_base or f"https://{environ.get('DXOS_ADMIN_HOST') or 'admin.' + domain}"
    for url in (base, admin):
        if not urlsplit(url).hostname:
            raise ConfigError(f"địa chỉ không hợp lệ: {url}")
        if not is_local(url) and not args.allow_remote:
            raise ConfigError(f"{url} không phải localhost: bảng thử cần realm dev (client dxos-test),"
                              " chỉ chạy trên máy khác khi có --allow-remote")
    return base, admin


def _chosen(only: str | None) -> list[Scenario]:
    if not only:
        return SCENARIOS
    wanted = [x.strip().upper() for x in only.split(",") if x.strip()]
    unknown = [x for x in wanted if x not in SCENARIO_IDS]
    if unknown or not wanted:
        raise ConfigError(f"--only không hợp lệ: {', '.join(unknown) or only}."
                          f" Kịch bản có: {', '.join(SCENARIO_IDS)}")
    return [s for s in SCENARIOS if s.id in wanted]


def _client(ca_file: str | None, transport: httpx.BaseTransport | None) -> httpx.Client:
    if ca_file and not Path(ca_file).is_file():
        raise ConfigError(f"--ca-file không tồn tại: {ca_file}")
    verify: ssl.SSLContext | bool = ssl.create_default_context(cafile=ca_file) if ca_file else True
    return httpx.Client(timeout=60, transport=transport, verify=verify, follow_redirects=False)


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None,
         environ: dict[str, str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None,
         sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.monotonic) -> int:
    out, err = stdout or sys.stdout, stderr or sys.stderr
    env = dict(os.environ if environ is None else environ)
    try:
        args = build_parser().parse_args(argv)
        base, admin = _targets(args, env)
        chosen = _chosen(args.only)
        clean_pdf(), eicar()                      # thiếu tệp mẫu thì dừng trước khi gửi request nào
        client = _client(args.ca_file or env.get("SSL_CERT_FILE"), transport)
    except ConfigError as exc:
        print(f"Lỗi cấu hình: {exc}", file=err)
        return 2
    api = Api(client, base, admin, env.get("DXOS_E2E_PASSWORD") or DEFAULT_PASSWORD, sleep=sleep, clock=clock)
    with client:
        try:
            results = run_scenarios(api, chosen)
            print(render_table(results), file=out)
            ledger_error = None
            try:
                print("\n" + render_ledger(fetch_ledger(api)), file=out)
            except StepError as exc:
                ledger_error = str(exc)
                print(f"\nKhông đọc được sổ cái ({exc}).", file=err)
        except ConfigError as exc:
            print(f"Lỗi cấu hình: {exc}", file=err)
            return 2
        except httpx.TransportError as exc:
            print(f"Lỗi kết nối tới stack: {type(exc).__name__}: {exc}", file=err)
            return 2
    if any(r.mark == LEAK for r in results):
        return 1
    return 2 if ledger_error or any(r.mark == NOT_RUN for r in results) else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")      # tiếng Việt và ✅/❌ trên console Windows
    raise SystemExit(main())
