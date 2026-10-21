# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test vòng sửa 1: refresh token, kiểm issuer, thư mục cấu hình symlink, thời gian device flow, URL."""

import importlib.util
import json
import os
import stat
import time
from pathlib import Path

import httpx
import pytest
import respx
from dxos_cli.auth import load_token, save_token
from dxos_cli.main import main

_spec = importlib.util.spec_from_file_location(
    "dxos_cli_test_support", Path(__file__).with_name("conftest.py")
)
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
SUBMITTED = _support.SUBMITTED

SRV = "https://admin.example.test"
ISS = "https://example.test/auth/realms/dxos"
DEVICE = f"{ISS}/protocol/openid-connect/auth/device"
TOKEN = f"{ISS}/protocol/openid-connect/token"
DISCOVERY = f"{ISS}/.well-known/openid-configuration"
APPS = f"{SRV}/admin/v1/apps"
PROBLEM_NS = "https://dxos.dev/problems/"


def _discovery(issuer=ISS):
    respx.get(DISCOVERY).mock(
        return_value=httpx.Response(
            200, json={"issuer": issuer, "device_authorization_endpoint": DEVICE, "token_endpoint": TOKEN}
        )
    )


def _device(interval=0, expires_in=60):
    respx.post(DEVICE).mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dev-code-secret",
                "user_code": "ABCD",
                "verification_uri": "https://x/device",
                "interval": interval,
                "expires_in": expires_in,
            },
        )
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Ghi token đã lưu cho SRV (mặc định access hết hạn, refresh còn hạn) và cô lập XDG_CONFIG_HOME."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)

    def put(**over):
        rec = {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": time.time() - 5,
            "refresh_expires_at": time.time() + 3600,
            "server": SRV,
            "issuer": ISS,
        } | over
        rec = {k: v for k, v in rec.items() if v is not None}
        save_token(rec)
        return rec

    return put


def _stored(tmp_path):
    return json.loads((tmp_path / "dxos/token.json").read_text())


# ---------------------------------------------------------------- refresh token (A)


@respx.mock
def test_login_stores_refresh_token_and_its_expiry(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    _device()
    respx.post(TOKEN).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "acc",
                "refresh_token": "ref",
                "expires_in": 300,
                "refresh_expires_in": 1800,
            },
        )
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    stored = _stored(tmp_path)
    assert stored["refresh_token"] == "ref"
    assert stored["refresh_expires_at"] > time.time() + 1700
    assert stat.S_IMODE((tmp_path / "dxos/token.json").stat().st_mode) == 0o600


@respx.mock
def test_login_refresh_expires_in_zero_means_no_expiry(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    _device()
    respx.post(TOKEN).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "acc", "refresh_token": "ref", "expires_in": 300, "refresh_expires_in": 0},
        )
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert "refresh_expires_at" not in _stored(tmp_path)


@respx.mock
def test_expired_access_token_is_refreshed_before_the_request(store, tmp_path, capsys):
    store()
    _discovery()
    refresh = respx.post(TOKEN).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 300,
                "refresh_expires_in": 1800,
            },
        )
    )
    apps = respx.get(APPS).mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 0
    form = dict(httpx.QueryParams(refresh.calls.last.request.content.decode()))
    assert form == {"grant_type": "refresh_token", "refresh_token": "old-refresh", "client_id": "dxos-cli"}
    assert apps.calls.last.request.headers["authorization"] == "Bearer new-access"
    stored = _stored(tmp_path)
    assert stored["access_token"] == "new-access" and stored["refresh_token"] == "new-refresh"
    assert stored["server"] == SRV and stored["issuer"] == ISS and stored["expires_at"] > time.time() + 200
    assert stat.S_IMODE((tmp_path / "dxos/token.json").stat().st_mode) == 0o600
    cap = capsys.readouterr()
    for secret in ("old-access", "old-refresh", "new-access", "new-refresh"):
        assert secret not in cap.out + cap.err


@respx.mock
def test_refresh_keeps_old_refresh_token_when_not_rotated(store, tmp_path):
    store()
    _discovery()
    respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "new-access", "expires_in": 300})
    )
    respx.get(APPS).mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 0
    assert _stored(tmp_path)["refresh_token"] == "old-refresh"


@respx.mock
def test_401_triggers_one_refresh_and_one_retry(store, tmp_path):
    store(expires_at=time.time() + 600)
    _discovery()
    refresh = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "new-access", "expires_in": 300})
    )
    apps = respx.get(APPS).mock(
        side_effect=[
            httpx.Response(401, json={"type": PROBLEM_NS + "unauthorized"}),
            httpx.Response(200, json=[]),
        ]
    )
    assert main(["--server", SRV, "app", "list"]) == 0
    assert refresh.call_count == 1 and apps.call_count == 2
    assert apps.calls[0].request.headers["authorization"] == "Bearer old-access"
    assert apps.calls[1].request.headers["authorization"] == "Bearer new-access"


@respx.mock
def test_401_after_refresh_is_exit_3_without_loop(store):
    store(expires_at=time.time() + 600)
    _discovery()
    refresh = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "new-access", "expires_in": 300})
    )
    apps = respx.get(APPS).mock(return_value=httpx.Response(401, json={"type": PROBLEM_NS + "unauthorized"}))
    assert main(["--server", SRV, "app", "list"]) == 3
    assert refresh.call_count == 1 and apps.call_count == 2


@respx.mock
def test_refresh_rejected_is_exit_3_with_login_hint(store, capsys):
    store()
    _discovery()
    respx.post(TOKEN).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    apps = respx.get(APPS).mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 3
    assert "dxos login --server" in capsys.readouterr().err and not apps.called


@respx.mock
def test_refresh_endpoint_5xx_or_network_error_is_exit_2(store):
    store()
    _discovery()
    respx.post(TOKEN).mock(return_value=httpx.Response(502, text="bad gateway"))
    assert main(["--server", SRV, "app", "list"]) == 2
    respx.post(TOKEN).mock(side_effect=httpx.ConnectError("refused"))
    assert main(["--server", SRV, "app", "list"]) == 2


@respx.mock
def test_expired_refresh_token_is_exit_3_without_network_call(store):
    store(refresh_expires_at=time.time() - 1)
    any_call = respx.route().mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 3
    assert not any_call.called


@respx.mock
def test_refresh_requires_discovery_issuer_to_match_stored_issuer(store):
    store()
    _discovery(issuer="https://evil.example/auth/realms/dxos")
    refresh = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "x", "expires_in": 9})
    )
    assert main(["--server", SRV, "app", "list"]) == 3
    assert not refresh.called


@respx.mock
def test_refresh_never_attempted_for_a_different_server(store):
    store()
    any_call = respx.route().mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", "https://admin.other.test", "app", "list"]) == 3
    assert not any_call.called


@respx.mock
def test_env_token_is_never_refreshed(store, monkeypatch):
    store(expires_at=time.time() + 600)
    monkeypatch.setenv("DXOS_TOKEN", "from-env")
    refresh = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "x", "expires_in": 9})
    )
    respx.get(APPS).mock(return_value=httpx.Response(401, json={"type": PROBLEM_NS + "unauthorized"}))
    assert main(["--server", SRV, "app", "list"]) == 3
    assert not refresh.called


# ---------------------------------------------------------------- issuer mix-up (B)


@respx.mock
@pytest.mark.parametrize("doc_issuer", ["https://evil.example/auth/realms/dxos", None, 5])
def test_discovery_issuer_must_equal_configured_issuer(monkeypatch, tmp_path, doc_issuer):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    doc = {"device_authorization_endpoint": DEVICE, "token_endpoint": TOKEN}
    if doc_issuer is not None:
        doc["issuer"] = doc_issuer
    respx.get(DISCOVERY).mock(return_value=httpx.Response(200, json=doc))
    dev = respx.post(DEVICE).mock(return_value=httpx.Response(200, json={}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert not dev.called and not (tmp_path / "dxos/token.json").exists()


@respx.mock
def test_discovery_issuer_trailing_slash_is_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery(issuer=ISS + "/")
    _device()
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 60}))
    assert main(["login", "--server", SRV, "--issuer", ISS + "/"]) == 0
    assert _stored(tmp_path)["issuer"] == ISS


# ---------------------------------------------------------------- thư mục cấu hình symlink (finding 1)


def test_symlinked_config_dir_is_refused_and_target_untouched(tmp_path, monkeypatch):
    base = tmp_path / "cfg"
    base.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    os.chmod(target, 0o755)  # noqa: S103 - cố ý rộng để chứng minh không bị chmod
    (base / "dxos").symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(base))
    with pytest.raises(Exception) as err:  # noqa: PT011 - CliError
        save_token({"access_token": "t", "expires_at": 9e9})
    assert "symlink" in str(err.value)
    assert stat.S_IMODE(target.stat().st_mode) == 0o755 and list(target.iterdir()) == []


def test_login_with_symlinked_config_dir_exits_1_and_writes_nothing(tmp_path, monkeypatch):
    base = tmp_path / "cfg"
    base.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (base / "dxos").symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(base))
    with respx.mock:
        _discovery()
        _device()
        respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 60}))
        assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert list(target.iterdir()) == []


def test_symlinked_config_dir_is_not_read_either(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    (real / "token.json").write_text(
        json.dumps({"access_token": "t", "expires_at": 9e9, "server": SRV}), encoding="utf-8"
    )
    base = tmp_path / "cfg"
    base.mkdir()
    (base / "dxos").symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(base))
    assert load_token() is None


def test_symlinked_token_file_is_replaced_not_followed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "dxos").mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("orig", encoding="utf-8")
    os.chmod(victim, 0o644)
    (tmp_path / "dxos/token.json").symlink_to(victim)
    save_token({"access_token": "t", "expires_at": 9e9})
    path = tmp_path / "dxos/token.json"
    assert not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["access_token"] == "t"
    assert victim.read_text() == "orig" and stat.S_IMODE(victim.stat().st_mode) == 0o644


def test_xdg_config_home_itself_may_be_a_symlink(tmp_path, monkeypatch):
    real = tmp_path / "dotfiles"
    real.mkdir()
    (tmp_path / "cfg").symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_token({"access_token": "t", "expires_at": 9e9})
    assert (real / "dxos/token.json").is_file()


# ---------------------------------------------------------------- thời gian device flow (m1) và client (m2)


@respx.mock
@pytest.mark.parametrize("bad", [-1, "NaN", "Infinity", "-Infinity"])
def test_device_flow_rejects_negative_or_non_finite_interval(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    body = {"device_code": "d", "user_code": "U", "verification_uri": "https://x/d", "expires_in": 60}
    raw = json.dumps(body | {"interval": 1}).replace(
        '"interval": 1', f'"interval": {bad if isinstance(bad, int) else bad}'
    )
    respx.post(DEVICE).mock(
        return_value=httpx.Response(200, content=raw, headers={"content-type": "application/json"})
    )
    tok = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 9})
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert not tok.called


@respx.mock
@pytest.mark.parametrize("bad", [0, -5, "NaN", "Infinity"])
def test_device_flow_rejects_bad_expires_in(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    raw = (
        '{"device_code":"d","user_code":"U","verification_uri":"https://x/d","interval":1,'
        f'"expires_in":{bad}}}'
    )
    respx.post(DEVICE).mock(
        return_value=httpx.Response(200, content=raw, headers={"content-type": "application/json"})
    )
    tok = respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 9})
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert not tok.called


@respx.mock
@pytest.mark.parametrize(("given", "used"), [(0, 1), (0.2, 1), (1000, 60)])
def test_device_flow_clamps_interval_to_1_60(monkeypatch, tmp_path, no_real_sleep, given, used):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    _device(interval=given, expires_in=600)
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 9}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert no_real_sleep == [used]


@respx.mock
def test_slow_down_cannot_push_interval_past_60(monkeypatch, tmp_path, no_real_sleep):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    _device(interval=58, expires_in=600)
    respx.post(TOKEN).mock(
        side_effect=[
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(200, json={"access_token": "t", "expires_in": 9}),
        ]
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert no_real_sleep == [58, 60]


@respx.mock
def test_device_flow_never_sleeps_or_polls_past_the_deadline(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _discovery()
    _device(interval=30, expires_in=40)
    tok = respx.post(TOKEN).mock(return_value=httpx.Response(400, json={"error": "authorization_pending"}))
    clock = {"t": 500.0}
    slept = []
    monkeypatch.setattr("dxos_cli.auth.monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        "dxos_cli.auth.sleep", lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s))
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert (
        slept == [30, 10] and tok.call_count == 1
    )  # lần ngủ thứ hai bị cắt còn 10 s rồi dừng, không hỏi thêm


@respx.mock
def test_device_flow_client_ignores_env_proxy_for_plain_http_loopback(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    seen = []
    real_client = httpx.Client

    def spy(*a, **k):
        seen.append(k.get("trust_env", True))
        return real_client(*a, **k)

    monkeypatch.setattr("dxos_cli.auth.httpx.Client", spy)
    iss = "http://127.0.0.1:18080/auth/realms/dxos"
    respx.get(f"{iss}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": iss,
                "device_authorization_endpoint": f"{iss}/device",
                "token_endpoint": f"{iss}/token",
            },
        )
    )
    respx.post(f"{iss}/device").mock(
        return_value=httpx.Response(
            200,
            json={"device_code": "d", "user_code": "U", "verification_uri": "http://x/d", "expires_in": 60},
        )
    )
    respx.post(f"{iss}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 9})
    )
    assert main(["login", "--server", SRV, "--issuer", iss]) == 0
    assert seen == [False]


# ---------------------------------------------------------------- phản hồi sai kiểu, URL, --ca-file


@respx.mock
@pytest.mark.parametrize("body", [[], "ok", None, 5])
def test_non_object_2xx_body_for_object_commands_is_exit_2(monkeypatch, tmp_path, body):
    monkeypatch.setenv("DXOS_TOKEN", "tok")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.post(f"{SRV}/admin/v1/apps/test-flow:approve").mock(return_value=httpx.Response(200, json=body))
    respx.post(f"{SRV}/admin/v1/apps/test-flow:disable").mock(return_value=httpx.Response(200, json=body))
    respx.post(f"{SRV}/admin/v1/anchor:run").mock(return_value=httpx.Response(200, json=body))
    assert main(["--server", SRV, "app", "approve", "test-flow", "0.1.0"]) == 2
    assert main(["--server", SRV, "app", "disable", "test-flow"]) == 2
    assert main(["--server", SRV, "anchor", "run"]) == 2


@respx.mock
def test_non_object_diff_after_install_is_exit_2(monkeypatch, tmp_path, app_dir):
    monkeypatch.setenv("DXOS_TOKEN", "tok")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.post(APPS).mock(return_value=httpx.Response(202, json=SUBMITTED))
    respx.get(f"{APPS}/test-flow/versions/0.1.0/diff").mock(return_value=httpx.Response(200, json=[1]))
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 2


@pytest.mark.parametrize(
    "server",
    [
        "https://user:hunter2@admin.example.test",
        "ftp://user:hunter2@admin.example.test",
        "http://user:hunter2@evil.example",
        "user:hunter2@admin.example.test",
        "https://user:hunter2@admin.example.test:notaport",
    ],
)
def test_credentials_embedded_in_a_url_are_never_echoed(monkeypatch, tmp_path, capsys, server):
    monkeypatch.setenv("DXOS_TOKEN", "tok")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert main(["--server", server, "app", "list"]) == 1
    cap = capsys.readouterr()
    assert "hunter2" not in cap.out + cap.err


def test_credentials_in_issuer_are_never_echoed(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert main(["login", "--server", SRV, "--issuer", "http://user:hunter2@evil.example/realm"]) == 1
    cap = capsys.readouterr()
    assert "hunter2" not in cap.out + cap.err


def test_ca_file_replaces_the_default_trust_store(tmp_path):
    import datetime
    import ssl

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from dxos_cli.client import make_verify

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "only-ca")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(7)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = tmp_path / "ca.pem"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    ctx = make_verify(str(pem))
    assert isinstance(ctx, ssl.SSLContext) and ctx.cert_store_stats()["x509_ca"] == 1


def test_readme_documents_ctrl_c_and_ca_file_semantics():
    text = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "130" in text and "thay thế" in text
