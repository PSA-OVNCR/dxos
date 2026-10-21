# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/keycloak_upgrade.py: lệnh kcadm sinh ra và tính idempotent, trên một Keycloak giả lập (không mạng).

Bản chạy thật (Keycloak 26.3.0, realm v0.1.0) ghi trong báo cáo Task 11 của Plan 02; sau khi chạy thật,
test ``infra`` của tests/infra/test_keycloak_realm.py phải đạt.
"""

import copy
import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("keycloak_upgrade", ROOT / "ops/keycloak_upgrade.py")
ku = importlib.util.module_from_spec(_spec)
sys.modules["keycloak_upgrade"] = ku
_spec.loader.exec_module(ku)

KC_DIR = ROOT / "deploy/keycloak"
PASSWORD = "changeme-test-kc-admin-PW"
CLIENT_SECRET = "changeme-test-installer-SECRET"
WRITE_VERBS = {"create", "update", "delete", "add-roles", "remove-roles"}


def _realm_file(name: str) -> dict:
    return json.loads((KC_DIR / name).read_text(encoding="utf-8"))


def _subst(value):
    """Thay ${DXOS_DOMAIN} như Keycloak làm lúc nạp realm."""
    if isinstance(value, str):
        return value.replace("${DXOS_DOMAIN}", "localhost")
    if isinstance(value, list):
        return [_subst(v) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v) for k, v in value.items()}
    return value


class FakeKeycloak:
    """Keycloak giả: hiểu đúng tập lệnh kcadm mà script dùng, giữ trạng thái realm ``dxos`` trong bộ nhớ.

    ``calls``: (argv, stdin, env) của mọi lệnh; ``writes``: các lệnh làm đổi trạng thái.
    """

    BUILTIN_CLIENTS = ["account", "account-console", "admin-cli", "broker", "realm-management",
                       "security-admin-console"]

    def __init__(self, realm: dict) -> None:
        realm = _subst(copy.deepcopy(realm))
        self.realm = {k: v for k, v in realm.items()
                      if k not in {"roles", "clients", "users", "clientScopes", "defaultDefaultClientScopes",
                                   "defaultOptionalClientScopes"}}
        self.realm.setdefault("adminEventsEnabled", False)
        self.realm.setdefault("adminEventsDetailsEnabled", False)
        self.realm["defaultRole"] = {"id": "dr-1", "name": "default-roles-dxos"}
        self.default_default = list(realm["defaultDefaultClientScopes"])
        # Keycloak 26.3.0 luôn thêm scope offline_access vào default optional scope (đo 21/10/2026).
        self.default_optional = list(realm["defaultOptionalClientScopes"]) + ["offline_access"]
        self.scopes = copy.deepcopy(realm["clientScopes"])
        self.roles = [r["name"] for r in realm["roles"]["realm"]] + ["default-roles-dxos", "offline_access",
                                                                    "uma_authorization"]
        self.clients = []
        for c in realm["clients"]:
            c = copy.deepcopy(c)
            c["id"] = str(uuid.uuid4())
            if "secret" in c:
                c["secret"] = CLIENT_SECRET
            self.clients.append(c)
        for name in self.BUILTIN_CLIENTS:
            self.clients.append({"id": str(uuid.uuid4()), "clientId": name, "publicClient": False})
        self.users = []      # {id, username, realm: set, client: {cid: set}, sa_client, rep}
        for u in realm.get("users", []):
            self.users.append({"id": str(uuid.uuid4()), "username": u["username"],
                               "realm": set(u.get("realmRoles", [])),
                               "client": {k: set(v) for k, v in u.get("clientRoles", {}).items()},
                               "sa_client": u.get("serviceAccountClientId"), "rep": u})
        # Keycloak tạo người dùng service account còn thiếu lúc nạp, kèm role mặc định (đo trên 26.3.0).
        for c in self.clients:
            has_sa = any(u["sa_client"] == c["clientId"] for u in self.users)
            if c.get("serviceAccountsEnabled") and not has_sa:
                self.users.append({"id": str(uuid.uuid4()), "username": f"service-account-{c['clientId']}",
                                   "realm": {"default-roles-dxos"}, "client": {}, "sa_client": c["clientId"],
                                   "rep": {}})
        self.calls: list[tuple[list[str], str | None, dict]] = []
        self.writes: list[list[str]] = []
        self.logged_in = False

    # ---------------------------------------------------------------- runner
    def __call__(self, argv: list[str], stdin: str | None, env: dict[str, str]) -> tuple[int, str, str]:
        self.calls.append((list(argv), stdin, dict(env)))
        idx = next((i for i, a in enumerate(argv) if a.endswith("kcadm.sh")), None)
        if idx is None:      # lệnh dọn dẹp trong container (rm -f tệp cấu hình kcadm)
            return 0, "", ""
        args = argv[idx + 1:]
        verb = args[0]
        if verb == "config":
            self.logged_in = env.get("KC_CLI_PASSWORD") == PASSWORD
            return (0, "", "Logging into ...") if self.logged_in else (1, "", "Invalid user credentials")
        assert self.logged_in, "lệnh trước khi đăng nhập"
        assert "--config" in args
        if verb in WRITE_VERBS:
            self.writes.append(args)
        opts, pos = self._parse(args[1:])
        assert opts.get("-r", ["dxos"])[0] == "dxos"
        handler = getattr(self, "_" + verb.replace("-", "_"))
        try:
            out = handler(pos, opts, stdin)
        except LookupError as exc:
            return 1, "", f"Resource not found for url: {exc}"
        return 0, (json.dumps(out) if out is not None else ""), ""

    @staticmethod
    def _parse(args: list[str]) -> tuple[dict[str, list[str]], list[str]]:
        opts: dict[str, list[str]] = {}
        pos: list[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("-"):
                opts.setdefault(a, []).append(args[i + 1])
                i += 2
            else:
                pos.append(a)
                i += 1
        return opts, pos

    def _client_by(self, key: str, value: str) -> dict:
        for c in self.clients:
            if c.get(key) == value:
                return c
        raise LookupError(value)

    def _user_by(self, key: str, value: str) -> dict:
        for u in self.users:
            if u[key] == value:
                return u
        raise LookupError(value)

    # ---------------------------------------------------------------- verbs
    def _get(self, pos, opts, stdin):
        path = pos[0]
        q = dict(x.split("=", 1) for x in opts.get("-q", []))
        if path == "realms/dxos":
            return self.realm
        if path == "realms/dxos/default-default-client-scopes":
            return [{"name": n} for n in self.default_default]
        if path == "realms/dxos/default-optional-client-scopes":
            return [{"name": n} for n in self.default_optional]
        if path == "roles":
            return [{"name": n} for n in self.roles]
        if path == "client-scopes":
            return self.scopes
        if path == "clients":
            return [c for c in self.clients if "clientId" not in q or c["clientId"] == q["clientId"]]
        if path.startswith("clients/") and path.endswith("/service-account-user"):
            c = self._client_by("id", path.split("/")[1])
            u = self._user_by("sa_client", c["clientId"])
            return {"id": u["id"], "username": u["username"]}
        if path == "users":
            assert q.get("exact") == "true"
            return [{"id": u["id"], "username": u["username"]} for u in self.users
                    if u["username"] == q["username"]]
        if path.startswith("users/") and path.endswith("/role-mappings"):
            u = self._user_by("id", path.split("/")[1])
            out = {}
            if u["realm"]:
                out["realmMappings"] = [{"name": n} for n in sorted(u["realm"])]
            if any(u["client"].values()):
                out["clientMappings"] = {c: {"client": c, "mappings": [{"name": n} for n in sorted(rs)]}
                                         for c, rs in u["client"].items() if rs}
            return out
        raise LookupError(path)

    def _create(self, pos, opts, stdin):
        assert opts["-f"] == ["-"]
        rep = json.loads(stdin)
        if pos[0] == "clients":
            assert rep["clientId"] not in {c["clientId"] for c in self.clients}
            self.clients.append(rep | {"id": str(uuid.uuid4())})
        elif pos[0] == "users":
            # Admin API gán role mặc định cho người dùng mới (import thì không).
            self.users.append({"id": str(uuid.uuid4()), "username": rep["username"],
                               "realm": {"default-roles-dxos"}, "client": {}, "sa_client": None, "rep": rep})
        elif pos[0] == "roles":
            self.roles.append(rep["name"])
        else:
            raise LookupError(pos[0])
        return None

    def _update(self, pos, opts, stdin):
        assert pos == ["realms/dxos"], pos
        for kv in opts["-s"]:
            k, v = kv.split("=", 1)
            self.realm[k] = json.loads(v)
        return None

    def _roles_target(self, opts) -> tuple[dict, set]:
        u = self._user_by("id", opts["--uid"][0]) if "--uid" in opts else \
            self._user_by("username", opts["--uusername"][0])
        if "--cclientid" in opts:
            return u, u["client"].setdefault(opts["--cclientid"][0], set())
        return u, u["realm"]

    def _add_roles(self, pos, opts, stdin):
        _, bucket = self._roles_target(opts)
        bucket.update(opts["--rolename"])
        return None

    def _remove_roles(self, pos, opts, stdin):
        _, bucket = self._roles_target(opts)
        bucket.difference_update(opts["--rolename"])
        return None


def v010(name: str) -> FakeKeycloak:
    """Keycloak đã nạp realm kiểu v0.1.0: realm hiện tại trừ đi các thay đổi của Task 11."""
    realm = _realm_file(name)
    realm["clients"] = [c for c in realm["clients"] if c["clientId"] != "dxos-cli"]
    realm["users"] = [u for u in realm.get("users", []) if u["username"] != "admin2"
                      and not u.get("serviceAccountClientId")]
    realm.pop("adminEventsEnabled", None)
    realm.pop("adminEventsDetailsEnabled", None)
    return FakeKeycloak(realm)


def run(fake: FakeKeycloak, *args: str, environ: dict | None = None) -> tuple[int, str]:
    out = io.StringIO()
    env = {"KEYCLOAK_ADMIN_PASSWORD": PASSWORD, "DXOS_DOMAIN": "localhost"} if environ is None else environ
    rc = ku.main(["--env-file", "/nonexistent/.env", *args], runner=fake, out=out, environ=env)
    return rc, out.getvalue()


def _write_summary(fake: FakeKeycloak) -> list[str]:
    return [" ".join(w[:2]) for w in fake.writes]


# ---------------------------------------------------------------- tests

def test_v010_dev_realm_gets_task11_changes_then_matches_target():
    fake = v010("realm-dxos-dev.json")
    rc, out = run(fake, "--profile", "dev-lite")
    assert rc == 0, out
    cli = next(c for c in fake.clients if c["clientId"] == "dxos-cli")
    target = next(c for c in _realm_file("realm-dxos.json")["clients"] if c["clientId"] == "dxos-cli")
    assert {k: v for k, v in cli.items() if k != "id"} == target
    sa = next(u for u in fake.users if u["sa_client"] == "dxos-installer")
    assert sa["realm"] == set() and sa["client"] == {"realm-management": {"manage-realm"}}
    assert fake.realm["adminEventsEnabled"] is True and fake.realm["adminEventsDetailsEnabled"] is True
    admin2 = next(u for u in fake.users if u["username"] == "admin2")
    assert admin2["realm"] == {"dxos-admin"}
    assert admin2["rep"]["credentials"][0]["value"] == "dev-only-password"
    assert "không còn lệch" in out


def test_second_run_changes_nothing():
    fake = v010("realm-dxos-dev.json")
    assert run(fake, "--profile", "dev-lite")[0] == 0
    first = len(fake.writes)
    assert first > 0
    rc, out = run(fake, "--profile", "dev-lite")
    assert rc == 0 and len(fake.writes) == first, _write_summary(fake)[first:]
    assert "không thay đổi gì" in out


def test_prod_profile_touches_only_task11_items_and_never_creates_users():
    fake = v010("realm-dxos.json")
    rc, out = run(fake)
    assert rc == 0, out
    verbs = sorted(_write_summary(fake))
    assert verbs == ["add-roles -r", "create clients", "remove-roles -r", "update realms/dxos"], verbs
    assert not [u for u in fake.users if not u["sa_client"]]
    upd = next(w for w in fake.writes if w[0] == "update")
    assert set(upd[upd.index("-s") + 1::2]) >= {"adminEventsEnabled=true", "adminEventsDetailsEnabled=true"}


def test_service_account_role_commands():
    fake = v010("realm-dxos.json")
    run(fake)
    sa = next(u for u in fake.users if u["sa_client"] == "dxos-installer")
    add = next(w for w in fake.writes if w[0] == "add-roles")
    assert add[add.index("--uid") + 1] == sa["id"]
    assert add[add.index("--cclientid") + 1] == "realm-management"
    assert add[add.index("--rolename") + 1] == "manage-realm" and add.count("--rolename") == 1
    rm = next(w for w in fake.writes if w[0] == "remove-roles")
    assert rm[rm.index("--rolename") + 1] == "default-roles-dxos" and "--cclientid" not in rm


def test_docker_mode_keeps_password_out_of_argv_and_output():
    fake = v010("realm-dxos.json")
    rc, out = run(fake, "--container", "dxos-keycloak-1")
    assert rc == 0
    for argv, stdin, _env in fake.calls:
        if argv[-3:-1] == ["rm", "-f"]:
            continue
        assert argv[:3] == ["docker", "exec", "-i"], argv
        assert "/opt/keycloak/bin/kcadm.sh" in argv
        assert not any(PASSWORD in a for a in argv) and PASSWORD not in (stdin or "")
    login = [c for c in fake.calls if "config" in c[0] and "credentials" in c[0]]
    assert len(login) == 1
    argv, _, env = login[0]
    assert argv[argv.index("-e") + 1] == "KC_CLI_PASSWORD" and env == {"KC_CLI_PASSWORD": PASSWORD}
    assert argv[argv.index("--server") + 1] == "http://localhost:8080/auth"
    assert argv[argv.index("--realm") + 1] == "master" and argv[argv.index("--user") + 1] == "admin"
    assert all(c[2] == {} for c in fake.calls if c is not login[0])   # chỉ lệnh đăng nhập nhận mật khẩu
    assert PASSWORD not in out and CLIENT_SECRET not in out
    # Tệp cấu hình kcadm (chứa token) bị xóa trong container sau khi chạy.
    config = login[0][0][login[0][0].index("--config") + 1]
    assert fake.calls[-1][0] == ["docker", "exec", "dxos-keycloak-1", "rm", "-f", config]


def test_direct_kcadm_mode():
    fake = v010("realm-dxos.json")
    rc, _ = run(fake, "--kcadm", "/opt/kc/bin/kcadm.sh", "--server", "http://127.0.0.1:58180/auth")
    assert rc == 0
    assert all(c[0][0] == "/opt/kc/bin/kcadm.sh" for c in fake.calls)
    login = next(c for c in fake.calls if "credentials" in c[0])
    assert login[0][login[0].index("--server") + 1] == "http://127.0.0.1:58180/auth"


def test_kcadm_path_from_env():
    fake = v010("realm-dxos.json")
    rc, _ = run(fake, environ={"KEYCLOAK_ADMIN_PASSWORD": PASSWORD, "DXOS_KCADM": "/x/kcadm.sh"})
    assert rc == 0 and fake.calls[0][0][0] == "/x/kcadm.sh"


def test_extra_default_optional_scope_is_still_drift_except_offline_access():
    fake = v010("realm-dxos.json")
    fake.default_optional.append("microprofile-jwt")
    rc, out = run(fake)
    assert rc == 2 and "defaultOptionalClientScopes" in out and "microprofile-jwt" in out


def test_drift_it_cannot_fix_is_printed_not_changed():
    fake = v010("realm-dxos.json")
    spa = next(c for c in fake.clients if c["clientId"] == "dxos-spa")
    spa["directAccessGrantsEnabled"] = True
    spa["defaultClientScopes"] = ["basic", "roles"]
    fake.realm["accessTokenLifespan"] = 3600
    rc, out = run(fake)
    assert rc == 2
    assert "dxos-spa" in out and "directAccessGrantsEnabled" in out and "dxos-api-audience" in out
    assert "accessTokenLifespan" in out
    assert spa["directAccessGrantsEnabled"] is True     # không tự sửa client có sẵn
    assert not [w for w in fake.writes if w[:2] == ["update", "clients"] or "dxos-spa" in " ".join(w)]


def test_missing_confidential_client_is_reported_not_created():
    fake = v010("realm-dxos.json")
    fake.clients = [c for c in fake.clients if c["clientId"] != "apisix"]
    rc, out = run(fake)
    assert rc == 2 and "apisix" in out
    assert "apisix" not in {c["clientId"] for c in fake.clients}


def test_existing_human_user_extra_role_is_reported_not_removed():
    fake = v010("realm-dxos-dev.json")
    u = next(u for u in fake.users if u["username"] == "chuyen_vien1")
    u["realm"].add("dxos-admin")
    rc, out = run(fake, "--profile", "dev-lite")
    assert rc == 2 and "chuyen_vien1" in out and "dxos-admin" in u["realm"]


def test_missing_admin_password_is_an_error_without_any_call(tmp_path):
    fake = v010("realm-dxos.json")
    rc, out = run(fake, environ={})
    assert rc == 1 and fake.calls == [] and "KEYCLOAK_ADMIN_PASSWORD" in out


def test_password_read_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"# x\nKEYCLOAK_ADMIN_PASSWORD={PASSWORD}\nDXOS_DOMAIN=localhost\n", encoding="utf-8")
    fake = v010("realm-dxos.json")
    out = io.StringIO()
    rc = ku.main(["--env-file", str(env_file)], runner=fake, out=out, environ={})
    assert rc == 0, out.getvalue()


def test_wrong_password_is_an_error():
    fake = v010("realm-dxos.json")
    rc, out = run(fake, environ={"KEYCLOAK_ADMIN_PASSWORD": "wrong"})
    assert rc == 1 and not fake.writes and "wrong" not in out


@pytest.mark.parametrize("profile", ["prod", "dev-lite"])
def test_already_current_realm_needs_nothing(profile):
    name = "realm-dxos.json" if profile == "prod" else "realm-dxos-dev.json"
    fake = FakeKeycloak(_realm_file(name))
    rc, out = run(fake, "--profile", profile)
    assert rc == 0 and fake.writes == [] and "không thay đổi gì" in out
