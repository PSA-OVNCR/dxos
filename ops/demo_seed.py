#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Nạp dữ liệu demo hư cấu qua API thật (Plan 04 Task 13).

    python ops/demo_seed.py [--base https://localhost] [--ca-file F] [--allow-remote]

Tạo trên stack dev đang chạy (App A và App B đã cài):

* App A "Phòng hồ sơ số": 3 văn bản của "Công ty TNHH Sao Mai" (hư cấu), mỗi văn bản kèm một PDF trong
  ``demo/sao-mai/`` có CCCD, số điện thoại (và tài khoản) hư cấu để bước dò PII (S1) có việc để làm. Văn bản 1
  để ở dạng nháp (đã có tệp CLEAN, chưa bắt đầu quy trình); văn bản 2 và 3 đã bắt đầu quy trình, đang chờ
  trưởng phòng duyệt nội dung.
* App B "Chứng nhận số": 12 chứng nhận của "Sự kiện CLB" (hư cấu) nhập từ ``demo/su-kien-clb.csv`` bằng
  ``records:bulk``; 8 chứng nhận đầu đã bắt đầu quy trình (chờ trưởng CLB phê duyệt), 4 chứng nhận cuối để
  nháp.

Seed không duyệt, không niêm phong gì: các bước đó là phần diễn ở buổi demo. Trạng thái từng mục ở
``demo/README.md``.

Chạy lại được nhiều lần: mỗi bản ghi tạo ra có tên bắt đầu bằng ``[DEMO] `` (trích yếu ở App A, tên sự kiện ở
App B). Trước khi tạo, seed đọc danh sách bản ghi hiện có và bỏ qua mục đã có; mục làm dở ở lần trước (chưa có
tệp, chưa bắt đầu quy trình) được làm nốt, không tạo trùng.

Mã thoát: 0 xong; 2 lỗi cấu hình, lỗi kết nối hoặc một bước không như mong đợi (chạy lại sau khi sửa).

Điều kiện: stack có realm dev (client ``dxos-test`` và người dùng dev). Mật khẩu dev chỉ đọc từ biến môi
trường ``DXOS_E2E_PASSWORD`` (mặc định ``dev-only-password``), không bao giờ nhận qua tham số dòng lệnh và
không in ra. Địa chỉ mặc định lấy từ ``DXOS_DOMAIN``; khác ``localhost`` thì phải thêm ``--allow-remote``,
thiếu cờ này thì không gửi request nào. Bản ghi demo nằm lại trên stack; sổ cái chỉ-thêm nên không xóa
được dấu vết.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import ssl
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
CSV_FILE = DEMO / "su-kien-clb.csv"

MARKER = "[DEMO] "
DEFAULT_PASSWORD = "dev-only-password"      # noqa: S105 - mật khẩu của realm dev, ghi trong tài liệu
PROBLEM_BASE = "https://dxos.dev/problems/"
PAGE = 200                                  # giới hạn limit của lõi

APP_A, COL_A, USER_A = "phong-ho-so", "van_ban", "chuyen_vien1"
APP_B, COL_B, USER_B = "chung-nhan", "chung_nhan", "can_bo_clb1"
B_STARTED = 8                               # số chứng nhận đầu của CSV được bắt đầu quy trình


class ConfigError(Exception):
    """Lỗi cấu hình hoặc môi trường: không nạp được (mã thoát 2)."""


class StepError(Exception):
    """Một bước không như mong đợi (mã thoát 2); chạy lại sẽ làm nốt phần còn thiếu."""


@dataclass(frozen=True)
class Doc:
    pdf: str
    start: bool
    data: dict[str, str]


# Số CCCD người liên hệ ở trường nguoi_lien_he_cccd đều hư cấu; PDF đi kèm có số hư cấu riêng.
DOCS = [
    Doc("quy-che-chi-tieu.pdf", False, {
        "loai_van_ban": "Quyết định", "chuc_vu_nguoi_ky": "Giám đốc", "noi_nhan": "Các phòng ban; Lưu: VT",
        "trich_yeu": f"{MARKER}Về việc ban hành Quy chế chi tiêu nội bộ năm 2027 (hư cấu)",
        "nguoi_lien_he_cccd": "079301234567"}),
    Doc("hop-dong-ke-toan.pdf", True, {
        "loai_van_ban": "Hợp đồng", "chuc_vu_nguoi_ky": "Giám đốc", "noi_nhan": "Bên B; Lưu: VT",
        "trich_yeu": f"{MARKER}Hợp đồng cung cấp dịch vụ kế toán thuế năm 2027 (hư cấu)",
        "nguoi_lien_he_cccd": "001185012345"}),
    Doc("thong-bao-tuyen-dung.pdf", True, {
        "loai_van_ban": "Thông báo", "chuc_vu_nguoi_ky": "Trưởng phòng Hành chính",
        "noi_nhan": "Toàn công ty",
        "trich_yeu": f"{MARKER}Thông báo tuyển dụng nhân viên hành chính quý I/2027 (hư cấu)",
        "nguoi_lien_he_cccd": "048200098765"}),
]

# Tiêu đề cột của CSV (nhãn trong manifest App B hoặc tên trường) -> tên trường.
CSV_COLUMNS = {"họ và tên": "ho_ten", "ho_ten": "ho_ten", "sự kiện": "su_kien", "su_kien": "su_kien",
               "ngày cấp": "ngay_cap", "ngay_cap": "ngay_cap", "email": "email"}


# ---------------------------------------------------------------------- tệp demo
def read_pdfs() -> dict[str, bytes]:
    out = {}
    for d in DOCS:
        path = DEMO / "sao-mai" / d.pdf
        if not path.is_file():
            raise ConfigError(f"thiếu tệp demo {path} (chạy từ bản sao đầy đủ của repo; dựng lại bằng"
                              " python demo/make_demo_pdfs.py)")
        out[d.pdf] = path.read_bytes()
    return out


def _iso_date(text: str, line: int) -> str:
    parts = text.replace("-", "/").replace(".", "/").split("/")
    try:
        if len(parts) == 3 and len(parts[0]) == 4:
            y, m, d = (int(x) for x in parts)
        elif len(parts) == 3:
            d, m, y = (int(x) for x in parts)
        else:
            raise ValueError(text)
        return date(y, m, d).isoformat()
    except ValueError as exc:
        raise ConfigError(f"{CSV_FILE.name} dòng {line}: ngày {text!r} không hợp lệ (DD/MM/YYYY)") from exc


def read_csv(path: Path = CSV_FILE) -> list[dict[str, str]]:
    """Các dòng dữ liệu của CSV demo, đã đổi tên cột về tên trường và ngày về ``YYYY-MM-DD``."""
    if not path.is_file():
        raise ConfigError(f"thiếu tệp demo {path} (chạy từ bản sao đầy đủ của repo)")
    try:
        text = unicodedata.normalize("NFC", path.read_bytes().decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path.name} không phải UTF-8") from exc
    table = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not table:
        raise ConfigError(f"{path.name} trống")
    names = []
    for title in table[0]:
        name = CSV_COLUMNS.get(title.strip().lower())
        if name is None:
            raise ConfigError(f"{path.name}: cột lạ {title!r}")
        names.append(name)
    rows = []
    for n, cells in enumerate(table[1:], start=2):
        row = {name: cell.strip() for name, cell in zip(names, cells, strict=False) if cell.strip()}
        if not {"ho_ten", "su_kien", "ngay_cap"} <= row.keys():
            raise ConfigError(f"{path.name} dòng {n}: thiếu họ tên, sự kiện hoặc ngày cấp")
        if not row["su_kien"].startswith(MARKER):
            raise ConfigError(f"{path.name} dòng {n}: tên sự kiện phải bắt đầu bằng {MARKER!r}"
                              " (dấu hiệu để chạy lại không tạo trùng)")
        row["ngay_cap"] = _iso_date(row["ngay_cap"], n)
        rows.append(row)
    if len({(r["ho_ten"], r["su_kien"]) for r in rows}) != len(rows):
        raise ConfigError(f"{path.name}: có hai dòng trùng (họ tên, sự kiện)")
    return rows


# ---------------------------------------------------------------------- phiên làm việc với stack
def describe(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = None
    slug = str(body["type"]).removeprefix(PROBLEM_BASE) if isinstance(body, dict) and "type" in body else ""
    return f"{resp.status_code} {slug}".strip()


@dataclass
class Counts:
    created: int = 0
    existing: int = 0
    uploaded: int = 0
    started: int = 0
    states: list[str] = field(default_factory=list)


class Api:
    def __init__(self, client: httpx.Client, base: str, password: str, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.client, self.base = client, base.rstrip("/")
        self._password, self._sleep, self._clock = password, sleep, clock
        self._tokens: dict[str, tuple[str, float]] = {}

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

    def call(self, method: str, path: str, user: str, *, if_match: int | None = None,
             **kw: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token(user)}"}
        if if_match is not None:
            headers["If-Match"] = f'"{if_match}"'
        return self.client.request(method, self.base + path, headers=headers, **kw)

    @staticmethod
    def need(resp: httpx.Response, status: int, what: str) -> httpx.Response:
        if resp.status_code != status:
            raise StepError(f"{what}: mong {status}, nhận {describe(resp)}")
        return resp

    @staticmethod
    def records(app: str, col: str) -> str:
        return f"/api/v1/apps/{app}/collections/{col}/records"

    def list_all(self, app: str, col: str, user: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": PAGE}
            if cursor:
                params["cursor"] = cursor
            body = self.need(self.call("GET", self.records(app, col), user, params=params), 200,
                             f"{user} liệt kê bản ghi").json()
            items += body["items"]
            cursor = body.get("next_cursor")
            if not cursor:
                return items

    def get(self, app: str, col: str, rid: str, user: str) -> dict[str, Any]:
        return dict(self.need(self.call("GET", f"{self.records(app, col)}/{rid}", user), 200,
                              f"{user} đọc bản ghi").json())

    def start(self, app: str, col: str, rid: str, user: str) -> None:
        version = int(self.get(app, col, rid, user)["version"])
        self.need(self.call("POST", f"{self.records(app, col)}/{rid}/workflow:start", user, if_match=version),
                  200, "bắt đầu quy trình")

    def attachments(self, rid: str, user: str) -> list[dict[str, Any]]:
        r = self.call("GET", f"{self.records(APP_A, COL_A)}/{rid}/attachments", user)
        return list(self.need(r, 200, f"{user} xem tệp đính kèm").json()["items"])

    def upload(self, rid: str, user: str, name: str, data: bytes) -> str:
        r = self.call("POST", f"{self.records(APP_A, COL_A)}/{rid}/attachments", user,
                      files={"file": (name, data, "application/pdf")})
        return str(self.need(r, 202, "tải tệp đính kèm").json()["upload_id"])

    def wait_clean(self, upload_id: str, user: str, timeout_s: float = 180) -> None:
        deadline = self._clock() + timeout_s
        while True:
            r = self.call("GET", f"/api/v1/uploads/{upload_id}", user)
            status = self.need(r, 200, "hỏi trạng thái tệp").json()["status"]
            if status == "CLEAN":
                return
            if status != "STAGING":
                raise StepError(f"PDF demo không CLEAN: {status}")
            if self._clock() > deadline:
                raise StepError("PDF demo vẫn STAGING sau khi hết thời gian chờ (ClamAV chưa trả lời?)")
            self._sleep(2)


# ---------------------------------------------------------------------- App A
def seed_app_a(api: Api, pdfs: dict[str, bytes], out: TextIO) -> Counts:
    counts = Counts()
    have = {r["data"].get("trich_yeu"): r for r in api.list_all(APP_A, COL_A, USER_A)
            if str(r["data"].get("trich_yeu", "")).startswith(MARKER)}
    for d in DOCS:
        title = d.data["trich_yeu"]
        row = have.get(title)
        if row is None:
            r = api.call("POST", api.records(APP_A, COL_A), USER_A, json=d.data)
            row = api.need(r, 201, f"{USER_A} tạo văn bản").json()
            counts.created += 1
        else:
            counts.existing += 1
        rid = str(row["id"])
        wf_state = (api.get(APP_A, COL_A, rid, USER_A) if row.get("wf_state") is None
                    else row).get("wf_state")
        if wf_state is None:                                # đã vào quy trình thì không tải thêm được
            files = api.attachments(rid, USER_A)
            if not any(f["status"] in ("CLEAN", "STAGING") for f in files):
                counts.uploaded += 1
                uid = api.upload(rid, USER_A, d.pdf, pdfs[d.pdf])
            else:
                uid = next(str(f["upload_id"]) for f in files if f["status"] in ("CLEAN", "STAGING"))
            api.wait_clean(uid, USER_A)
            if d.start:
                api.start(APP_A, COL_A, rid, USER_A)
                counts.started += 1
                wf_state = "running"
        state = {"running": "đang chờ trưởng phòng duyệt nội dung",
                 None: "nháp, đã có tệp CLEAN"}.get(wf_state, f"quy trình: {wf_state}")
        counts.states.append(f"- {title}: {state}")
    print(f"App A: {counts.created} văn bản mới, {counts.existing} đã có từ trước; tải {counts.uploaded} tệp,"
          f" bắt đầu quy trình {counts.started}.", file=out)
    return counts


# ---------------------------------------------------------------------- App B
def seed_app_b(api: Api, rows: list[dict[str, str]], out: TextIO) -> Counts:
    counts = Counts()

    def key(r: dict[str, str]) -> tuple[str, str]:
        return r["ho_ten"], r["su_kien"]

    have = {key(r["data"]): r for r in api.list_all(APP_B, COL_B, USER_B)
            if str(r["data"].get("su_kien", "")).startswith(MARKER)}
    todo = [r for r in rows if key(r) not in have]
    counts.existing = len(rows) - len(todo)
    for from_ in range(0, len(todo), 500):                  # giới hạn một lời gọi bulk của lõi
        chunk = todo[from_:from_ + 500]
        r = api.call("POST", api.records(APP_B, COL_B) + ":bulk", USER_B, json=chunk)
        results = api.need(r, 200, f"{USER_B} nhập CSV").json()["results"]
        for row, res in zip(chunk, results, strict=True):
            if not res.get("ok"):
                raise StepError(f"lõi từ chối dòng {row['ho_ten']!r}: {res.get('error', {}).get('title')}")
            have[key(row)] = {"id": res["id"], "wf_state": None}
            counts.created += 1
    for row in rows[:B_STARTED]:
        rec = have[key(row)]
        if api.get(APP_B, COL_B, str(rec["id"]), USER_B).get("wf_state") is None:
            api.start(APP_B, COL_B, str(rec["id"]), USER_B)
            counts.started += 1
    counts.states.append(f"- {B_STARTED} chứng nhận đầu: đang chờ trưởng CLB phê duyệt;"
                         f" {len(rows) - B_STARTED} chứng nhận cuối: nháp")
    print(f"App B: {counts.created} chứng nhận mới, {counts.existing} đã có từ trước;"
          f" bắt đầu quy trình {counts.started}.", file=out)
    return counts


# ---------------------------------------------------------------------- dòng lệnh
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="demo_seed.py", description=__doc__.split("\n\n")[0],
                                epilog="Mật khẩu dev: biến DXOS_E2E_PASSWORD (mặc định dev-only-password).")
    p.add_argument("--base", help="địa chỉ cổng công khai (mặc định https://$DXOS_DOMAIN, hoặc https://localhost)")
    p.add_argument("--ca-file", help="CA của Caddy nội bộ (mặc định biến SSL_CERT_FILE)")
    p.add_argument("--allow-remote", action="store_true",
                   help="cho phép chạy trên máy khác localhost (chỉ khi stack có realm dev)")
    return p


def is_local(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "localhost" or host.endswith(".localhost") or host in ("127.0.0.1", "::1")


def _target(args: argparse.Namespace, environ: dict[str, str]) -> str:
    base = args.base or f"https://{environ.get('DXOS_DOMAIN') or 'localhost'}"
    if not urlsplit(base).hostname:
        raise ConfigError(f"địa chỉ không hợp lệ: {base}")
    if not is_local(base) and not args.allow_remote:
        raise ConfigError(f"{base} không phải localhost: seed cần realm dev (client dxos-test), chỉ chạy trên"
                          " máy khác khi có --allow-remote")
    return base


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
        base = _target(args, env)
        pdfs, rows = read_pdfs(), read_csv()              # thiếu tệp thì dừng trước khi gửi request nào
        client = _client(args.ca_file or env.get("SSL_CERT_FILE"), transport)
    except ConfigError as exc:
        print(f"Lỗi cấu hình: {exc}", file=err)
        return 2
    api = Api(client, base, env.get("DXOS_E2E_PASSWORD") or DEFAULT_PASSWORD, sleep=sleep, clock=clock)
    with client:
        try:
            a = seed_app_a(api, pdfs, out)
            b = seed_app_b(api, rows, out)
        except ConfigError as exc:
            print(f"Lỗi cấu hình: {exc}", file=err)
            return 2
        except StepError as exc:
            print(f"Dừng giữa chừng: {exc}. Chạy lại để làm nốt phần còn thiếu (không tạo trùng).", file=err)
            return 2
        except httpx.TransportError as exc:
            print(f"Lỗi kết nối tới stack: {type(exc).__name__}: {exc}", file=err)
            return 2
    print("\nTrạng thái dữ liệu demo (toàn bộ hư cấu, tên bắt đầu bằng [DEMO]):", file=out)
    for line in [*a.states, *b.states]:
        print(line, file=out)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")      # tiếng Việt trên console Windows
    raise SystemExit(main())
