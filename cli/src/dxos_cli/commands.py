# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Các lệnh ``dxos``. Mỗi hàm nhận ``argparse.Namespace`` và trả mã thoát; lỗi dừng lệnh là ``CliError``.

Dữ liệu từ server luôn qua ``clean`` trước khi in ra terminal. Với ``--json``, in nguyên JSON (ASCII an toàn).
"""

import json
import os
import re
import sys
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import quote

import yaml

from dxos_cli import auth
from dxos_cli.client import AdminClient, clean, make_verify
from dxos_cli.errors import EXIT_LOGIN, EXIT_OK, EXIT_SERVER, CliError
from dxos_cli.urls import normalize_server

MAX_BODY = 1024 * 1024  # trần thân yêu cầu của server (1 MiB), Task 12
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")  # pattern app.id của schema manifest
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")

DIFF_SECTIONS = (
    ("roles_added", "Vai trò thêm"),
    ("collections_added", "Collection thêm"),
    ("fields_added", "Trường thêm"),
    ("access", "Quyền truy cập (giá trị mới)"),
    ("pii_reveal_roles", "Vai trò xem PII"),
    ("pii_erase_roles", "Vai trò xóa PII"),
    ("seal", "Niêm phong"),
    ("verify", "Xác minh công khai"),
    ("tasks", "Task quy trình (giá trị mới)"),
    ("labels", "Nhãn"),
    ("sequences", "Số thứ tự"),
    ("bpmn_sha256", "BPMN sha256"),
)
_DIFF_HEADER_KEYS = frozenset({"app_id", "version", "against"})


# ---------------------------------------------------------------- đầu ra


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)


def out(line: str = "") -> None:
    print(line)


def _cell(v: Any, width: int | None = None) -> str:
    s = "-" if v is None else clean(v)
    return s if width is None or len(s) <= width else s[:width]


def table(rows: list[dict], columns: list[tuple[str, str, int | None]]) -> None:
    """In bảng cột căn trái. ``columns`` là (khóa, tiêu đề, độ rộng tối đa)."""
    cells = [[_cell(r.get(k), w) for k, _, w in columns] for r in rows]
    heads = [h for _, h, _ in columns]
    widths = [
        max(len(heads[i]), *(len(c[i]) for c in cells)) if cells else len(heads[i]) for i in range(len(heads))
    ]
    out("  ".join(h.ljust(w) for h, w in zip(heads, widths, strict=True)).rstrip())
    for c in cells:
        out("  ".join(v.ljust(w) for v, w in zip(c, widths, strict=True)).rstrip())


def _empty(v: Any) -> bool:
    if v is None or v == [] or v == {}:
        return True
    return isinstance(v, dict) and all(_empty(x) for x in v.values())


def _fmt_value(v: Any, indent: str) -> list[str]:
    if isinstance(v, str):
        return [clean(v)]
    text = clean(json.dumps(v, ensure_ascii=False, sort_keys=True, indent=2 if isinstance(v, dict) else None))
    return [(indent + ln if i else ln) for i, ln in enumerate(text.split("\n"))]


def format_diff(diff: dict) -> list[str]:
    """Diff quyền để người duyệt xem. Mọi khóa server trả về đều được in (khóa lạ không bị giấu)."""
    lines: list[str] = []
    if "against" in diff:
        against = diff["against"]
        lines.append(
            f"So với phiên bản ACTIVE: {clean(against)}"
            if against
            else "So với: chưa có phiên bản ACTIVE (cài mới)"
        )
    known = {k for k, _ in DIFF_SECTIONS}
    extra = [(k, k) for k in sorted(diff) if k not in known and k not in _DIFF_HEADER_KEYS]
    for key, label in (*DIFF_SECTIONS, *extra):
        if key in diff and not _empty(diff[key]):
            first, *rest = _fmt_value(diff[key], "    ")
            lines.append(f"- {label}: {first}")
            lines.extend("    " + ln if not ln.startswith("    ") else ln for ln in rest)
    if not any(ln.startswith("- ") for ln in lines):
        lines.append("(không có thay đổi quyền hay cấu hình để duyệt)")
    return lines


# ---------------------------------------------------------------- tiện ích dùng chung


def _client(args) -> AdminClient:
    server = args.server or auth.stored_server()
    if not server:
        if os.environ.get("DXOS_TOKEN", "").strip():
            raise CliError("Thiếu --server (DXOS_TOKEN không gắn với server nào)")
        raise CliError("Chưa đăng nhập: chạy dxos login --server https://admin.<miền>", EXIT_LOGIN)
    return AdminClient(server, ca_file=args.ca_file)


def _seg(value: str) -> str:
    return quote(value, safe="")


def app_id_arg(value: str) -> str:
    if not ID_RE.match(value):
        raise ValueError("app id phải khớp ^[a-z][a-z0-9-]{1,30}$")
    return value


def version_arg(value: str) -> str:
    if not VERSION_RE.match(value):
        raise ValueError("version phải có dạng X.Y.Z")
    return value


def _server_ids(obj: Any) -> tuple[str, str]:
    """app_id và version trong phản hồi của server, kiểm lại trước khi ghép vào đường dẫn."""
    try:
        app_id, version = obj["app_id"], obj["version"]
    except (KeyError, TypeError) as exc:
        raise CliError("Phản hồi của server thiếu app_id/version", EXIT_SERVER) from exc
    if not (
        isinstance(app_id, str)
        and isinstance(version, str)
        and ID_RE.match(app_id)
        and VERSION_RE.match(version)
    ):
        raise CliError("Phản hồi của server có app_id/version sai định dạng", EXIT_SERVER)
    return app_id, version


# ---------------------------------------------------------------- login


def login(args) -> int:
    server = args.server
    if not server:
        raise CliError("dxos login cần --server https://admin.<miền>")
    server = normalize_server(server)
    verify = make_verify(args.ca_file)

    def announce(text: str) -> None:
        print(text, file=sys.stderr if args.json else sys.stdout)

    info = auth.device_login(server, args.issuer, verify, announce=announce)
    if args.json:
        out(dump_json(info))
    else:
        left = max(0, int(info["expires_at"] - time()))
        out(f"Đã đăng nhập vào {info['server']}.")
        out(f"Token hết hạn sau khoảng {left // 60} phút; khi đó chạy lại dxos login.")
    return EXIT_OK


# ---------------------------------------------------------------- app install


def _reject_path(rel: Any) -> None:
    if (
        not isinstance(rel, str)
        or not rel
        or rel.startswith("/")
        or "\\" in rel
        or "\x00" in rel
        or _WINDOWS_DRIVE.match(rel)
        or any(seg in ("", ".", "..") for seg in rel.split("/"))
    ):
        raise CliError(
            f"Đường dẫn tệp trong manifest không hợp lệ (tương đối, dùng '/', không '..'): {clean(repr(rel))}"
        )


def read_inside(root: Path, rel: str, *, what: str) -> bytes:
    """Đọc ``rel`` trong thư mục app ``root`` (đã resolve); thoát ra ngoài hoặc > 1 MiB thì từ chối."""
    _reject_path(rel)
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise CliError(f"{what} '{clean(rel)}' nằm ngoài thư mục app (kể cả qua symlink)")
    if not target.is_file():
        raise CliError(f"{what} '{clean(rel)}' không tồn tại hoặc không phải tệp thường")
    if target.stat().st_size > MAX_BODY:
        raise CliError(f"{what} '{clean(rel)}' lớn hơn 1 MiB (trần của server)")
    with target.open("rb") as fh:
        data = fh.read(MAX_BODY + 1)
    if len(data) > MAX_BODY:
        raise CliError(f"{what} '{clean(rel)}' lớn hơn 1 MiB (trần của server)")
    return data


def _check_json_types(v: Any, path: str = "") -> None:
    """Manifest gửi đi phải là JSON thuần: từ chối kiểu YAML như ngày/giờ hay khóa không phải chuỗi."""
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str):
                raise CliError(
                    f"Manifest có khóa không phải chuỗi tại {path or '/'}: {clean(repr(k))} (dùng dấu nháy)"
                )
            _check_json_types(x, f"{path}/{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _check_json_types(x, f"{path}/{i}")
    elif not (v is None or isinstance(v, str | int | float | bool)):
        raise CliError(
            f"Manifest có giá trị YAML không phải JSON tại {path or '/'} ({type(v).__name__}; dùng dấu nháy)"
        )


def load_app(app_dir: str) -> bytes:
    """Đọc manifest.yaml và tệp nó tham chiếu (``workflow.bpmn``); trả thân cho ``POST /admin/v1/apps``."""
    root = Path(app_dir)
    if not root.is_dir():
        raise CliError(f"Không phải thư mục: {clean(app_dir)}")
    root = root.resolve()
    raw = read_inside(root, "manifest.yaml", what="Tệp")
    try:
        manifest = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CliError(f"manifest.yaml không đọc được (YAML/UTF-8): {type(exc).__name__}") from exc
    if not isinstance(manifest, dict):
        raise CliError("manifest.yaml phải là một mapping YAML")
    _check_json_types(manifest)
    files: dict[str, str] = {}
    workflow = manifest.get("workflow")
    if isinstance(workflow, dict) and "bpmn" in workflow:
        rel = workflow["bpmn"]
        _reject_path(rel)
        content = read_inside(root, rel, what="Tệp BPMN")
        try:
            files[rel] = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CliError(f"Tệp BPMN '{clean(rel)}' không phải UTF-8") from exc
    try:
        body = json.dumps(
            {"manifest": manifest, "files": files}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise CliError(f"Không mã hóa được manifest thành JSON: {type(exc).__name__}") from exc
    if len(body) > MAX_BODY:
        raise CliError(f"Thân yêu cầu {len(body)} byte vượt trần 1 MiB của server")
    return body


def app_install(args) -> int:
    body = load_app(args.app_dir)
    with _client(args) as c:
        submitted = c.request("POST", "/admin/v1/apps", content=body)
        app_id, version = _server_ids(submitted)
        diff = c.request("GET", f"/admin/v1/apps/{_seg(app_id)}/versions/{_seg(version)}/diff")
    if args.json:
        out(dump_json({"submitted": submitted, "diff": diff}))
        return EXIT_OK
    out("Đã nộp, đang chờ duyệt (PENDING):")
    for key in ("app_id", "version", "status", "manifest_sha256"):
        out(f"  {key}: {clean(submitted.get(key))}")
    for path, digest in sorted((submitted.get("files") or {}).items()):
        out(f"  tệp {clean(path)}: sha256 {clean(digest)}")
    out()
    out("Thay đổi cần duyệt:")
    for ln in format_diff(diff if isinstance(diff, dict) else {}):
        out("  " + ln)
    out()
    out(f"Người duyệt (khác người nộp) chạy: dxos app approve {app_id} {version}")
    return EXIT_OK


# ---------------------------------------------------------------- app list / diff / approve / disable


def app_list(args) -> int:
    with _client(args) as c:
        rows = c.request("GET", "/admin/v1/apps")
    if args.json:
        out(dump_json(rows))
        return EXIT_OK
    if not isinstance(rows, list):
        raise CliError("Phản hồi danh sách app sai định dạng", EXIT_SERVER)
    if not rows:
        out("(chưa có app nào)")
        return EXIT_OK
    table(
        [r for r in rows if isinstance(r, dict)],
        [
            ("app_id", "APP", None),
            ("version", "VERSION", None),
            ("status", "STATUS", None),
            ("submitted_by_ref", "NỘP", 8),
            ("approved_by_ref", "DUYỆT", 8),
            ("manifest_sha256", "SHA256", 12),
            ("created_at", "TẠO LÚC", None),
        ],
    )
    return EXIT_OK


def app_diff(args) -> int:
    with _client(args) as c:
        diff = c.request("GET", f"/admin/v1/apps/{_seg(args.app_id)}/versions/{_seg(args.version)}/diff")
    if args.json:
        out(dump_json(diff))
        return EXIT_OK
    out(f"Diff {clean(args.app_id)} {clean(args.version)}:")
    for ln in format_diff(diff if isinstance(diff, dict) else {}):
        out("  " + ln)
    return EXIT_OK


def app_approve(args) -> int:
    body = json.dumps({"version": args.version}).encode("utf-8")
    with _client(args) as c:
        res = c.request("POST", f"/admin/v1/apps/{_seg(args.app_id)}:approve", content=body)
    if args.json:
        out(dump_json(res))
        return EXIT_OK
    out(f"Đã duyệt {clean(res.get('app_id'))} {clean(res.get('version'))}: {clean(res.get('status'))}")
    for key in ("manifest_sha256", "deployment_id", "rendered_sha256"):
        out(f"  {key}: {_cell(res.get(key))}")
    if res.get("self_approved"):
        out("  CẢNH BÁO: người nộp tự duyệt (DXOS_ALLOW_SELF_APPROVAL đang bật) — chỉ dùng cho dev/demo.")
    return EXIT_OK


def app_disable(args) -> int:
    with _client(args) as c:
        res = c.request("POST", f"/admin/v1/apps/{_seg(args.app_id)}:disable")
    if args.json:
        out(dump_json(res))
        return EXIT_OK
    out(f"Đã vô hiệu hóa {clean(res.get('app_id'))} {clean(res.get('version'))}: {clean(res.get('status'))}")
    return EXIT_OK


# ---------------------------------------------------------------- health / quarantine / ledger / anchor


def is_problem_value(v: Any) -> bool:
    """Vấn đề khi giá trị là ``down: …`` hoặc ``expired``; ``ok``/``none`` thì không."""
    return isinstance(v, str) and (v == "expired" or v == "down" or v.startswith("down:"))


def health(args) -> int:
    with _client(args) as c:
        res = c.request("GET", "/admin/v1/health")
    if args.json:
        out(dump_json(res))
        return EXIT_OK
    if not isinstance(res, dict):
        raise CliError("Phản hồi health sai định dạng", EXIT_SERVER)
    bad = []
    for key, val in res.items():
        if isinstance(val, dict):
            shown = ", ".join(f"{clean(k)}={_cell(v)}" for k, v in val.items())
        else:
            shown = _cell(val)
        flagged = is_problem_value(val)
        if flagged:
            bad.append(clean(key))
        out(f"{'!' if flagged else ' '} {clean(key)}: {shown}")
    out()
    out("Có thành phần lỗi: " + ", ".join(bad) if bad else "Mọi thành phần báo ổn.")
    return EXIT_OK


def quarantine_list(args) -> int:
    params = {"limit": args.limit} if args.limit is not None else None
    with _client(args) as c:
        rows = c.request("GET", "/admin/v1/quarantine", params=params)
    if args.json:
        out(dump_json(rows))
        return EXIT_OK
    if not isinstance(rows, list):
        raise CliError("Phản hồi quarantine sai định dạng", EXIT_SERVER)
    if not rows:
        out("(không có tệp nào bị cách ly)")
        return EXIT_OK
    table(
        [r for r in rows if isinstance(r, dict)],
        [
            ("created_at", "LÚC", None),
            ("status", "TRẠNG THÁI", None),
            ("app_id", "APP", None),
            ("upload_id", "UPLOAD", None),
            ("sha256", "SHA256", 12),
            ("reason", "LÝ DO", 60),
        ],
    )
    return EXIT_OK


def ledger_status(args) -> int:
    with _client(args) as c:
        res = c.request("GET", "/admin/v1/ledger/status")
    if args.json:
        out(dump_json(res))
        return EXIT_OK
    if not isinstance(res, dict):
        raise CliError("Phản hồi ledger status sai định dạng", EXIT_SERVER)
    out(f"tree_size: {_cell(res.get('tree_size'))}")
    sth = res.get("latest_sth")
    out(
        "latest_sth: "
        + ("(chưa có)" if not sth else _kv(sth, ("tree_size", "root_hash", "ts", "key_version")))
    )
    anchor = res.get("last_anchor")
    out(
        "last_anchor: "
        + ("(chưa có)" if not anchor else _kv(anchor, ("tree_size", "repo", "commit_sha", "anchored_at")))
    )
    out(f"pending_anchor_jobs: {_cell(res.get('pending_anchor_jobs'))}")
    verify = res.get("verify") or {}
    if verify.get("ok") is True:
        out("verify: ok")
    else:
        out(f"! verify: LỖI, mục sai đầu tiên idx={_cell(verify.get('first_bad_idx'))}")
    return EXIT_OK


def anchor_run(args) -> int:
    with _client(args) as c:
        res = c.request("POST", "/admin/v1/anchor:run")
    if args.json:
        out(dump_json(res))
        return EXIT_OK
    out("Đã lập STH và xếp việc neo:")
    out("  " + _kv(res, ("tree_size", "root_hash", "ts", "key_version", "anchor_job_id")))
    return EXIT_OK


def _kv(obj: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(obj, dict):
        return _cell(obj)
    return " ".join(f"{k}={_cell(obj.get(k))}" for k in keys)
