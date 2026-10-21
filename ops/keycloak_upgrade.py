# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đưa realm ``dxos`` đã có sẵn lên cấu hình hiện tại của deploy/keycloak (Plan 02 Task 11). Idempotent.

Vì sao cần: compose chạy ``start --import-realm`` và Keycloak **bỏ qua** import khi realm đã tồn tại, nên một
stack đã chạy từ v0.1.0 (VPS, dev stack) không tự nhận thay đổi của realm-dxos.json.

    python ops/keycloak_upgrade.py                          # hồ sơ p8/p16: so với realm-dxos.json
    python ops/keycloak_upgrade.py --profile dev-lite       # so với realm-dxos-dev.json (thêm admin2...)
    python ops/keycloak_upgrade.py --kcadm /đường/dẫn/kcadm.sh --server http://127.0.0.1:58180/auth

Mặc định chạy ``kcadm.sh`` trong container keycloak qua ``docker exec`` (``--container``, mặc định
``dxos-keycloak-1`` theo ``make up``). ``--kcadm`` (hoặc biến ``DXOS_KCADM``) chạy thẳng một kcadm.sh cục bộ.
Đăng nhập bằng tài khoản bootstrap admin (realm master): ``KEYCLOAK_ADMIN_PASSWORD`` lấy từ biến môi trường
hoặc từ ``.env``. Mật khẩu chỉ đi qua biến môi trường ``KC_CLI_PASSWORD`` của kcadm, không bao giờ nằm trong
tham số dòng lệnh hay trong output.

Việc script **tự sửa** (chỉ thêm, không ghi đè cấu hình có sẵn):
- tạo realm role, client công khai (ví dụ ``dxos-cli``) và người dùng dev còn thiếu (người dùng chỉ có ở
  dev-lite);
- đặt role của service account (``dxos-installer``) đúng như tệp realm: thêm ``manage-realm``, gỡ role thừa
  (realm v0.1.0 tự gán ``default-roles-dxos`` cho service account);
- bật admin events (``adminEventsEnabled``, ``adminEventsDetailsEnabled``).

Sau đó đọc lại realm, so với tệp realm và **in phần lệch không tự sửa** (client có sẵn khác cấu hình, client
bảo mật còn thiếu vì cần secret, role thừa của người dùng thường...). Mã thoát: 0 khớp, 2 còn lệch, 1 lỗi.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
KC_DIR = ROOT / "deploy" / "keycloak"
REALM = "dxos"
PROFILES = {"prod": "realm-dxos.json", "dev-lite": "realm-dxos-dev.json"}
KCADM_IN_CONTAINER = "/opt/keycloak/bin/kcadm.sh"
# /tmp của container keycloak (không phải của máy chủ); tệp chứa token admin ngắn hạn, bị xóa sau khi chạy.
CONFIG_IN_CONTAINER = "/tmp/dxos-kcadm-upgrade.config"  # noqa: S108
SERVER_IN_CONTAINER = "http://localhost:8080/auth"   # KC_HTTP_RELATIVE_PATH=/auth
EVENT_KEYS = ("adminEventsEnabled", "adminEventsDetailsEnabled")
# Khóa cấp realm được kiểm riêng (không có trong GET realms/<realm>).
REALM_SEPARATE_KEYS = {"roles", "clients", "users", "clientScopes", "defaultDefaultClientScopes",
                       "defaultOptionalClientScopes"}
# Mục Keycloak 26.3.0 luôn tự thêm khi nạp realm, kể cả realm mới nạp từ tệp (đo 21/10/2026): client scope
# ``offline_access`` (gắn với role offline_access) là default optional scope của realm. Không tính là lệch.
KEYCLOAK_ADDED = {"defaultOptionalClientScopes": {"offline_access"}}
CLIENT_SET_KEYS = ("redirectUris", "webOrigins", "defaultClientScopes", "optionalClientScopes")
CLIENT_SKIP_KEYS = {"secret", "id"}

# runner(argv, stdin, env_thêm) -> (mã thoát, stdout, stderr)
Runner = Callable[[list[str], "str | None", dict[str, str]], tuple[int, str, str]]


class UpgradeError(RuntimeError):
    """Lỗi chạy kcadm hoặc cấu hình; thông báo không chứa mật khẩu."""


def subprocess_runner(argv: list[str], stdin: str | None, env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True,  # noqa: S603
                          env={**os.environ, **env}, check=False, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


class Kcadm:
    """Gọi kcadm.sh trong container (``docker exec``) hoặc trực tiếp; mọi lệnh dùng chung một tệp cấu hình."""

    def __init__(self, runner: Runner, *, container: str | None, kcadm: str | None, config: str) -> None:
        self.runner, self.container, self.kcadm, self.config = runner, container, kcadm, config

    def argv(self, args: list[str], *, with_password: bool = False) -> list[str]:
        if self.kcadm:
            return [self.kcadm, *args]
        # `-e KC_CLI_PASSWORD` không kèm giá trị: docker lấy giá trị từ môi trường của chính nó.
        env = ["-e", "KC_CLI_PASSWORD"] if with_password else []
        return ["docker", "exec", "-i", *env, self.container, KCADM_IN_CONTAINER, *args]

    def run(self, args: list[str], *, stdin: str | None = None) -> str:
        rc, out, err = self.runner(self.argv([*args, "--config", self.config]), stdin, {})
        if rc != 0:
            raise UpgradeError(f"kcadm {' '.join(args[:2])} lỗi: {_last_line(err)}")
        return out

    def get(self, path: str, *query: str) -> Any:
        args = ["get", path, "-r", REALM]
        for q in query:
            args += ["-q", q]
        out = self.run(args)
        try:
            return json.loads(out)
        except ValueError:
            raise UpgradeError(f"kcadm get {path}: output không phải JSON") from None

    def login(self, server: str, user: str, password: str) -> None:
        args = ["config", "credentials", "--server", server, "--realm", "master", "--user", user,
                "--config", self.config]
        rc, _, err = self.runner(self.argv(args, with_password=True), None, {"KC_CLI_PASSWORD": password})
        if rc != 0:
            raise UpgradeError(f"đăng nhập kcadm thất bại: {_last_line(err).replace(password, '***')}")

    def cleanup(self) -> str | None:
        """Xóa tệp cấu hình kcadm trong container (chứa token admin). Trả lời cảnh báo nếu không xóa được;
        không bao giờ ném lỗi, để không che lỗi gốc của lần chạy."""
        if self.kcadm:
            return None   # chế độ trực tiếp: thư mục tạm do Python tự xóa
        try:
            rc, _, err = self.runner(["docker", "exec", self.container, "rm", "-f", self.config], None, {})
        except (OSError, subprocess.SubprocessError) as exc:
            return f"không xóa được {self.config} trong {self.container}: {type(exc).__name__}: {exc}"
        if rc != 0:
            return f"không xóa được {self.config} trong {self.container} (mã {rc}): {_last_line(err)}"
        return None


def _last_line(text: str) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and "JAVA_TOOL_OPTIONS" not in ln]
    return lines[-1].strip()[:300] if lines else "(không có thông báo)"


def _subst(value: Any, domain: str | None) -> Any:
    """Thay ``${DXOS_DOMAIN}`` như Keycloak làm lúc nạp realm; giá trị còn ``${`` (secret) thì không so."""
    if isinstance(value, str) and domain is not None:
        return value.replace("${DXOS_DOMAIN}", domain)
    if isinstance(value, list):
        return [_subst(v, domain) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, domain) for k, v in value.items()}
    return value


def _has_placeholder(value: Any) -> bool:
    return "${" in json.dumps(value, ensure_ascii=False)


def _kv(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class Upgrade:
    def __init__(self, kc: Kcadm, target: dict, *, domain: str | None) -> None:
        self.kc, self.target, self.domain = kc, _subst(target, domain), domain
        self.actions: list[str] = []
        self.drift: list[str] = []

    # ------------------------------------------------------------ đọc
    def _clients(self) -> dict[str, dict]:
        return {c["clientId"]: c for c in self.kc.get("clients", "max=1000")}

    def _user_id(self, username: str) -> str | None:
        rows = self.kc.get("users", f"username={username}", "exact=true")
        return rows[0]["id"] if rows else None

    def _mappings(self, uid: str) -> tuple[set[str], dict[str, set[str]]]:
        m = self.kc.get(f"users/{uid}/role-mappings")
        realm = {r["name"] for r in m.get("realmMappings", [])}
        clients = {c: {r["name"] for r in v.get("mappings", [])}
                   for c, v in m.get("clientMappings", {}).items()}
        return realm, {c: rs for c, rs in clients.items() if rs}

    def _sa_user(self, clients: dict[str, dict], client_id: str) -> dict | None:
        c = clients.get(client_id)
        if c is None or not c.get("serviceAccountsEnabled"):
            return None
        return self.kc.get(f"clients/{c['id']}/service-account-user")

    # ------------------------------------------------------------ sửa
    def apply(self) -> None:
        realm = self.kc.get(f"realms/{REALM}")
        if not isinstance(realm, dict) or realm.get("realm") != REALM:
            raise UpgradeError(f"không đọc được realm {REALM}")

        live_roles = {r["name"] for r in self.kc.get("roles")}
        for role in self.target["roles"]["realm"]:
            if role["name"] not in live_roles:
                self.kc.run(["create", "roles", "-r", REALM, "-f", "-"], stdin=_kv(role))
                self.actions.append(f"tạo realm role {role['name']}")

        clients = self._clients()
        for c in self.target["clients"]:
            if c["clientId"] in clients:
                continue
            if c.get("secret") or not c.get("publicClient"):
                continue   # client bảo mật cần secret thật: báo lệch ở bước so, không tự tạo
            if _has_placeholder(c):
                continue   # còn ${...} chưa thay (ví dụ thiếu DXOS_DOMAIN): báo lệch, không tạo giá trị sai
            self.kc.run(["create", "clients", "-r", REALM, "-f", "-"], stdin=_kv(c))
            self.actions.append(f"tạo client {c['clientId']}")

        clients = self._clients()
        for u in self.target.get("users", []):
            if u.get("serviceAccountClientId"):
                self._fix_service_account(clients, u)
            else:
                self._fix_user(u)

        want = {k: self.target[k] for k in EVENT_KEYS if k in self.target}
        changed = {k: v for k, v in want.items() if realm.get(k) != v}
        if changed:
            sets: list[str] = []
            for k, v in changed.items():
                sets += ["-s", f"{k}={_kv(v)}"]
            self.kc.run(["update", f"realms/{REALM}", *sets])
            self.actions.append("bật " + ", ".join(changed))

    def _fix_service_account(self, clients: dict[str, dict], u: dict) -> None:
        sa = self._sa_user(clients, u["serviceAccountClientId"])
        if sa is None:
            return   # báo ở bước so
        realm_now, clients_now = self._mappings(sa["id"])
        want_realm = set(u.get("realmRoles", []))
        want_clients = {c: set(rs) for c, rs in u.get("clientRoles", {}).items()}
        base = ["-r", REALM, "--uid", sa["id"]]
        if want_realm - realm_now:
            self.kc.run(["add-roles", *base, *_rolenames(want_realm - realm_now)])
            self.actions.append(f"{sa['username']}: thêm realm role {sorted(want_realm - realm_now)}")
        if realm_now - want_realm:
            self.kc.run(["remove-roles", *base, *_rolenames(realm_now - want_realm)])
            self.actions.append(f"{sa['username']}: gỡ realm role {sorted(realm_now - want_realm)}")
        for cid in sorted(set(want_clients) | set(clients_now)):
            want, now = want_clients.get(cid, set()), clients_now.get(cid, set())
            if want - now:
                self.kc.run(["add-roles", *base, "--cclientid", cid, *_rolenames(want - now)])
                self.actions.append(f"{sa['username']}: thêm {cid}/{sorted(want - now)}")
            if now - want:
                self.kc.run(["remove-roles", *base, "--cclientid", cid, *_rolenames(now - want)])
                self.actions.append(f"{sa['username']}: gỡ {cid}/{sorted(now - want)}")

    def _fix_user(self, u: dict) -> None:
        uid = self._user_id(u["username"])
        if uid is None:
            if _has_placeholder(u):
                return   # còn ${...} chưa thay: báo lệch ở bước so, không tạo
            rep = {k: v for k, v in u.items() if k not in {"realmRoles", "clientRoles", "groups"}}
            self.kc.run(["create", "users", "-r", REALM, "-f", "-"], stdin=_kv(rep))
            self.actions.append(f"tạo người dùng {u['username']}")
            uid = self._user_id(u["username"])
            if uid is None:
                raise UpgradeError(f"tạo người dùng {u['username']} xong nhưng không đọc lại được")
            created = True
        else:
            created = False
        realm_now, _ = self._mappings(uid)
        want = set(u.get("realmRoles", []))
        missing = want - realm_now
        if missing:
            self.kc.run(["add-roles", "-r", REALM, "--uid", uid, *_rolenames(missing)])
            self.actions.append(f"{u['username']}: thêm realm role {sorted(missing)}")
        # Admin API gán role mặc định (default-roles-dxos) cho người dùng tạo mới, còn import thì không. Người
        # dùng do chính lần chạy này tạo thì đưa về đúng role của tệp; người dùng có sẵn thì không gỡ gì.
        extra = realm_now - want
        if created and extra:
            self.kc.run(["remove-roles", "-r", REALM, "--uid", uid, *_rolenames(extra)])
            self.actions.append(f"{u['username']}: gỡ realm role {sorted(extra)} (Admin API tự gán khi tạo)")

    # ------------------------------------------------------------ so
    def compare(self) -> None:
        realm = self.kc.get(f"realms/{REALM}")
        for k, v in self.target.items():
            if k in REALM_SEPARATE_KEYS or _has_placeholder(v):
                continue
            if k not in realm:
                self.drift.append(f"realm.{k}: Keycloak không trả khóa này (không kiểm được)")
            elif realm[k] != v:
                self.drift.append(f"realm.{k}: đang {_kv(realm[k])}, cấu hình {_kv(v)}")
        for key, path in (("defaultDefaultClientScopes", "default-default-client-scopes"),
                          ("defaultOptionalClientScopes", "default-optional-client-scopes")):
            if key in self.target:
                now = {s["name"] for s in self.kc.get(f"realms/{REALM}/{path}")}
                now -= KEYCLOAK_ADDED.get(key, set()) - set(self.target[key])
                if now != set(self.target[key]):
                    self.drift.append(f"realm.{key}: đang {sorted(now)}, cấu hình {sorted(self.target[key])}")

        roles = {r["name"] for r in self.kc.get("roles")}
        for role in self.target["roles"]["realm"]:
            if role["name"] not in roles:
                self.drift.append(f"realm role {role['name']}: thiếu")

        scopes = {s["name"]: s for s in self.kc.get("client-scopes")}
        for s in self.target.get("clientScopes", []):
            live = scopes.get(s["name"])
            if live is None:
                self.drift.append(f"client scope {s['name']}: thiếu")
                continue
            live_mappers = {m["name"]: m for m in live.get("protocolMappers", [])}
            for m in s.get("protocolMappers", []):
                lm = live_mappers.get(m["name"])
                if lm is None or lm.get("protocolMapper") != m["protocolMapper"]:
                    self.drift.append(f"client scope {s['name']}: mapper {m['name']} thiếu hoặc khác loại")
                    continue
                for ck, cv in m.get("config", {}).items():
                    if lm.get("config", {}).get(ck) != cv:
                        self.drift.append(f"client scope {s['name']}: mapper {m['name']}.{ck} khác")

        clients = self._clients()
        for c in self.target["clients"]:
            live = clients.get(c["clientId"])
            if live is None:
                if c.get("secret"):
                    why = " (client bảo mật: tạo tay với secret từ .env)"
                elif _has_placeholder(c):
                    why = " (cấu hình còn ${...} chưa thay: đặt DXOS_DOMAIN trong .env rồi chạy lại)"
                else:
                    why = ""
                self.drift.append(f"client {c['clientId']}: thiếu{why}")
                continue
            self.drift += _client_drift(c, live)

        for u in self.target.get("users", []):
            self._user_drift(clients, u)

    def _user_drift(self, clients: dict[str, dict], u: dict) -> None:
        name = u["username"]
        if u.get("serviceAccountClientId"):
            sa = self._sa_user(clients, u["serviceAccountClientId"])
            if sa is None:
                self.drift.append(f"{name}: client {u['serviceAccountClientId']} không bật service account")
                return
            if sa.get("username") != name:
                self.drift.append(f"{name}: service account tên khác ({sa.get('username')})")
            realm_now, clients_now = self._mappings(sa["id"])
            want_clients = {c: set(rs) for c, rs in u.get("clientRoles", {}).items()}
            if realm_now != set(u.get("realmRoles", [])) or clients_now != want_clients:
                self.drift.append(f"{name}: role đang {sorted(realm_now)} {_sorted_map(clients_now)}, "
                                  f"cấu hình {sorted(u.get('realmRoles', []))} {_sorted_map(want_clients)}")
            return
        uid = self._user_id(name)
        if uid is None:
            self.drift.append(f"người dùng {name}: thiếu")
            return
        realm_now, _ = self._mappings(uid)
        want = set(u.get("realmRoles", []))
        if realm_now != want:
            self.drift.append(f"người dùng {name}: realm role đang {sorted(realm_now)}, "
                              f"cấu hình {sorted(want)}"
                              " (không tự gỡ role của người dùng)")


def _rolenames(names: set[str]) -> list[str]:
    out: list[str] = []
    for n in sorted(names):
        out += ["--rolename", n]
    return out


def _sorted_map(m: dict[str, set[str]]) -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in sorted(m.items())}


def _client_drift(want: dict, live: dict) -> list[str]:
    out: list[str] = []
    cid = want["clientId"]
    for k, v in want.items():
        if k in CLIENT_SKIP_KEYS or _has_placeholder(v):
            continue
        if k in CLIENT_SET_KEYS:
            now = set(live.get(k) or [])
            if now != set(v):
                out.append(f"client {cid}.{k}: đang {sorted(now)}, cấu hình {sorted(v)}")
        elif k == "attributes":
            for ak, av in v.items():
                if _has_placeholder(av):
                    continue
                if (live.get("attributes") or {}).get(ak) != av:
                    out.append(f"client {cid}.attributes.{ak}: đang "
                               f"{_kv((live.get('attributes') or {}).get(ak))}, cấu hình {_kv(av)}")
        elif live.get(k) != v:
            out.append(f"client {cid}.{k}: đang {_kv(live.get(k))}, cấu hình {_kv(v)}")
    return out


def read_env_file(path: Path) -> dict[str, str]:
    """Đọc ``KEY=VALUE`` của .env (bỏ dòng trống, dòng ``#``); không có tệp thì rỗng."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@contextlib.contextmanager
def _config_path(kcadm: str | None) -> Iterator[str]:
    if not kcadm:
        yield CONFIG_IN_CONTAINER
        return
    with tempfile.TemporaryDirectory(prefix="dxos-kcadm-") as d:
        yield str(Path(d) / "kcadm.config")


def main(argv: list[str] | None = None, *, runner: Runner | None = None, out: TextIO | None = None,
         environ: dict[str, str] | None = None) -> int:
    out = out or sys.stdout
    environ = dict(os.environ) if environ is None else environ
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="prod",
                    help="prod (p8/p16, realm-dxos.json) hoặc dev-lite (realm-dxos-dev.json)")
    ap.add_argument("--container", default="dxos-keycloak-1", help="container keycloak cho docker exec")
    ap.add_argument("--kcadm", default=environ.get("DXOS_KCADM"),
                    help="chạy thẳng kcadm.sh này thay vì docker exec (biến DXOS_KCADM)")
    ap.add_argument("--server", default=None,
                    help=f"URL Keycloak cho kcadm (mặc định {SERVER_IN_CONTAINER} trong container)")
    ap.add_argument("--admin-user", default=None,
                    help="bootstrap admin (mặc định KC_BOOTSTRAP_ADMIN_USERNAME hoặc admin)")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = ap.parse_args(argv)

    env = {**read_env_file(args.env_file), **environ}
    password = env.get("KEYCLOAK_ADMIN_PASSWORD")
    if not password:
        print("thiếu KEYCLOAK_ADMIN_PASSWORD (biến môi trường hoặc .env)", file=out)
        return 1
    user = args.admin_user or env.get("KC_BOOTSTRAP_ADMIN_USERNAME") or "admin"
    server = args.server or (SERVER_IN_CONTAINER if not args.kcadm else "http://127.0.0.1:8080/auth")
    target = json.loads((KC_DIR / PROFILES[args.profile]).read_text(encoding="utf-8"))

    with _config_path(args.kcadm) as config:
        kc = Kcadm(runner or subprocess_runner, container=args.container, kcadm=args.kcadm, config=config)
        up = Upgrade(kc, target, domain=env.get("DXOS_DOMAIN"))
        try:
            kc.login(server, user, password)
            up.apply()
            up.compare()
        except (UpgradeError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
            # OSError: ví dụ không có lệnh docker/kcadm. Báo ngắn, không traceback.
            msg = str(exc).replace(password, "***")
            print(f"LỖI: {type(exc).__name__}: {msg}", file=out)
            if up.actions:
                print("Đã sửa trước khi lỗi:", *(f"  - {a}" for a in up.actions), sep="\n", file=out)
            return 1
        finally:
            warning = kc.cleanup()
            if warning:
                print(f"CẢNH BÁO: {warning.replace(password, '***')}", file=out)

    print(f"Realm {REALM} so với {PROFILES[args.profile]}:", file=out)
    if up.actions:
        print("Đã sửa:", *(f"  - {a}" for a in up.actions), sep="\n", file=out)
    else:
        print("Kết quả: không thay đổi gì (realm đã có đủ các mục script tự sửa).", file=out)
    if up.drift:
        print("Lệch còn lại (script không tự sửa, cần xử lý tay):", *(f"  - {d}" for d in up.drift),
              sep="\n", file=out)
        return 2
    print("Realm không còn lệch so với tệp cấu hình.", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
