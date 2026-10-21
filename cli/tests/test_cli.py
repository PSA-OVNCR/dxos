# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test CLI ``dxos``: lệnh, mã thoát, ràng buộc token, device flow, an toàn đường dẫn. Dùng respx."""

import ast
import importlib.util
import json
import os
import stat
import time
import tomllib
from pathlib import Path

import httpx
import pytest
import respx
from dxos_cli.auth import save_token
from dxos_cli.main import main

# `pythonpath = core/tests` làm `import conftest` trỏ sang conftest của lõi: nạp conftest CLI theo đường dẫn.
_spec = importlib.util.spec_from_file_location(
    "dxos_cli_test_support", Path(__file__).with_name("conftest.py")
)
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)
BPMN_BYTES, MANIFEST_TEXT = _support.BPMN_BYTES, _support.MANIFEST_TEXT
MANIFEST_WITH_BPMN_PATH, SUBMITTED = _support.MANIFEST_WITH_BPMN_PATH, _support.SUBMITTED

SRV = "https://admin.example.test"
ISS = "https://example.test/auth/realms/dxos"
DEVICE = f"{ISS}/protocol/openid-connect/auth/device"
TOKEN = f"{ISS}/protocol/openid-connect/token"
DISCOVERY = f"{ISS}/.well-known/openid-configuration"
PROBLEM_NS = "https://dxos.dev/problems/"


def _login_token(tmp_path: Path, **over) -> dict:
    tok = {
        "access_token": "stored-token",
        "expires_at": time.time() + 600,
        "server": SRV,
        "issuer": ISS,
    } | over
    return tok


def _mock_discovery() -> None:
    respx.get(DISCOVERY).mock(
        return_value=httpx.Response(
            200, json={"issuer": ISS, "device_authorization_endpoint": DEVICE, "token_endpoint": TOKEN}
        )
    )


def _mock_device(interval=0, expires_in=60) -> None:
    respx.post(DEVICE).mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "dev-code-secret",
                "user_code": "ABCD",
                "verification_uri": "https://x/device",
                "verification_uri_complete": "https://x/device?u=ABCD",
                "interval": interval,
                "expires_in": expires_in,
            },
        )
    )


# ---------------------------------------------------------------- app install


@respx.mock
def test_install_posts_manifest_and_referenced_file(app_dir, token_env):
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json={})
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 0
    req = route.calls.last.request
    body = json.loads(req.content)
    assert set(body) == {"manifest", "files"}
    assert set(body["files"]) == {"bpmn/test-review.bpmn"} and body["manifest"]["app"]["id"] == "test-flow"
    assert body["files"]["bpmn/test-review.bpmn"] == BPMN_BYTES.decode("utf-8")
    assert req.headers["content-type"] == "application/json"
    assert req.headers["authorization"] == "Bearer dummy-token-value"


@respx.mock
def test_install_prints_identity_and_diff(app_dir, token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    diff = {
        "app_id": "test-flow",
        "version": "0.1.0",
        "against": None,
        "roles_added": ["reviewer"],
        "bpmn_sha256": "ef" * 32,
    }
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json=diff)
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 0
    out = capsys.readouterr().out
    assert "test-flow" in out and "0.1.0" in out and SUBMITTED["manifest_sha256"] in out
    assert "reviewer" in out and diff["bpmn_sha256"] in out


@respx.mock
def test_install_json_prints_submitted_and_diff(app_dir, token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json={"roles_added": ["r"]})
    )
    assert main(["--json", "--server", SRV, "app", "install", str(app_dir)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["submitted"] == SUBMITTED and data["diff"] == {"roles_added": ["r"]}


@respx.mock
def test_install_without_workflow_sends_no_files(tmp_path, token_env):
    (tmp_path / "manifest.yaml").write_text(
        "apiVersion: dxos/v1\napp: {id: plain, version: 0.1.0, name: P, spaces: [D]}\nroles: [a]\n",
        encoding="utf-8",
    )
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json={})
    )
    assert main(["--server", SRV, "app", "install", str(tmp_path)]) == 0
    assert json.loads(route.calls.last.request.content)["files"] == {}


@respx.mock
@pytest.mark.parametrize(
    "bad",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "bpmn/../../x.bpmn",
        "..\\x.bpmn",
        "C:\\x.bpmn",
        "bpmn//x.bpmn",
        "./bpmn/test-review.bpmn",
        "",
        "bpmn/\x00x.bpmn",
    ],
)
def test_install_refuses_path_escape(tmp_path, token_env, bad):
    (tmp_path / "manifest.yaml").write_text(MANIFEST_WITH_BPMN_PATH(bad), encoding="utf-8")
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(tmp_path)]) == 1
    assert not route.called


@respx.mock
def test_install_refuses_symlink_to_outside_file(tmp_path, token_env):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    root = tmp_path / "app"
    (root / "bpmn").mkdir(parents=True)
    (root / "manifest.yaml").write_text(MANIFEST_TEXT, encoding="utf-8")
    (root / "bpmn" / "test-review.bpmn").symlink_to(secret)
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(root)]) == 1
    assert not route.called


@respx.mock
def test_install_refuses_symlinked_directory_to_outside(tmp_path, token_env):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test-review.bpmn").write_bytes(BPMN_BYTES)
    root = tmp_path / "app"
    root.mkdir()
    (root / "manifest.yaml").write_text(MANIFEST_TEXT, encoding="utf-8")
    (root / "bpmn").symlink_to(outside, target_is_directory=True)
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(root)]) == 1
    assert not route.called


@respx.mock
def test_install_refuses_manifest_symlink_to_outside(tmp_path, token_env):
    outside = tmp_path / "other.yaml"
    outside.write_text(MANIFEST_TEXT, encoding="utf-8")
    root = tmp_path / "app"
    (root / "bpmn").mkdir(parents=True)
    (root / "bpmn" / "test-review.bpmn").write_bytes(BPMN_BYTES)
    (root / "manifest.yaml").symlink_to(outside)
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(root)]) == 1
    assert not route.called


@respx.mock
def test_install_allows_symlink_that_stays_inside(app_dir, token_env):
    (app_dir / "bpmn" / "alias.bpmn").symlink_to(app_dir / "bpmn" / "test-review.bpmn")
    (app_dir / "manifest.yaml").write_text(MANIFEST_WITH_BPMN_PATH("bpmn/alias.bpmn"), encoding="utf-8")
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json={})
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 0
    assert set(json.loads(route.calls.last.request.content)["files"]) == {"bpmn/alias.bpmn"}


@respx.mock
def test_install_missing_referenced_file_or_dir_exit_1(app_dir, tmp_path, token_env):
    (app_dir / "bpmn" / "test-review.bpmn").unlink()
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    assert main(["--server", SRV, "app", "install", str(tmp_path / "nope")]) == 1
    assert main(["--server", SRV, "app", "install", str(tmp_path)]) == 1  # không có manifest.yaml


@respx.mock
def test_install_refuses_invalid_yaml_and_non_utf8(app_dir, token_env):
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    (app_dir / "bpmn" / "test-review.bpmn").write_bytes(b"\xff\xfe\x00bad")
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    (app_dir / "manifest.yaml").write_text("a: [unclosed", encoding="utf-8")
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    (app_dir / "manifest.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    (app_dir / "manifest.yaml").write_text(
        "x: !!python/object/apply:os.system ['echo pwned']\n", encoding="utf-8"
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1  # safe_load từ chối
    assert not route.called


@respx.mock
def test_install_refuses_body_over_1mib(app_dir, token_env):
    (app_dir / "bpmn" / "test-review.bpmn").write_text("x" * (1024 * 1024 + 10), encoding="utf-8")
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    assert not route.called


@respx.mock
def test_install_refuses_huge_file_without_reading_it_whole(app_dir, token_env, monkeypatch):
    big = app_dir / "bpmn" / "test-review.bpmn"
    with big.open("wb") as fh:
        fh.truncate(200 * 1024 * 1024)  # tệp thưa 200 MB
    route = respx.post(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(202, json=SUBMITTED))
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    assert not route.called


@respx.mock
def test_4xx_prints_problem_and_exit_1(app_dir, token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps").mock(
        return_value=httpx.Response(
            422,
            json={
                "type": PROBLEM_NS + "manifest-invalid",
                "title": "Manifest invalid",
                "status": 422,
                "detail": "guard lạ",
                "code": "UNKNOWN_GUARD",
                "path": "/workflow/tasks/review/guards/2",
            },
        )
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    out = capsys.readouterr().out
    for needle in ("UNKNOWN_GUARD", "/workflow/tasks/review/guards/2", "manifest-invalid", "guard lạ"):
        assert needle in out


@respx.mock
def test_problem_output_strips_terminal_control_chars(app_dir, token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps").mock(
        return_value=httpx.Response(
            422, json={"type": PROBLEM_NS + "manifest-invalid", "detail": "\x1b[31mđỏ\x07\u202e", "code": "X"}
        )
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out and "\u202e" not in out and "đỏ" in out


# ---------------------------------------------------------------- các lệnh khác


@respx.mock
def test_app_list_table_and_json(token_env, capsys):
    rows = [
        {
            "app_id": "test-flow",
            "version": "0.2.0",
            "status": "PENDING",
            "manifest_sha256": "aa" * 32,
            "submitted_by_ref": "r" * 64,
            "approved_by_ref": None,
            "created_at": "2026-10-21T01:02:03+00:00",
        }
    ]
    respx.get(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(200, json=rows))
    assert main(["--server", SRV, "app", "list"]) == 0
    out = capsys.readouterr().out
    assert "test-flow" in out and "0.2.0" in out and "PENDING" in out
    assert main(["--server", SRV, "app", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == rows


@respx.mock
def test_app_diff_requests_version_path(token_env, capsys):
    route = respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.2.0/diff").mock(
        return_value=httpx.Response(
            200,
            json={
                "app_id": "test-flow",
                "version": "0.2.0",
                "against": "0.1.0",
                "roles_added": ["observer"],
                "fields_added": {"doc": ["note"]},
            },
        )
    )
    assert main(["--server", SRV, "app", "diff", "test-flow", "0.2.0"]) == 0
    out = capsys.readouterr().out
    assert route.called and "observer" in out and "note" in out and "0.1.0" in out


@respx.mock
def test_app_approve_posts_version(token_env, capsys):
    route = respx.post(f"{SRV}/admin/v1/apps/test-flow:approve").mock(
        return_value=httpx.Response(
            200,
            json={
                "app_id": "test-flow",
                "version": "0.1.0",
                "status": "ACTIVE",
                "manifest_sha256": "aa" * 32,
                "self_approved": False,
                "deployment_id": "dep-1",
                "rendered_sha256": "bb" * 32,
            },
        )
    )
    assert main(["--server", SRV, "app", "approve", "test-flow", "0.1.0"]) == 0
    assert json.loads(route.calls.last.request.content) == {"version": "0.1.0"}
    out = capsys.readouterr().out
    assert "ACTIVE" in out and "dep-1" in out


@respx.mock
def test_app_approve_self_approval_403_is_exit_1(token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps/test-flow:approve").mock(
        return_value=httpx.Response(
            403,
            json={
                "type": PROBLEM_NS + "forbidden",
                "title": "Forbidden",
                "status": 403,
                "reason": "self_approval",
            },
        )
    )
    assert main(["--server", SRV, "app", "approve", "test-flow", "0.1.0"]) == 1
    assert "self_approval" in capsys.readouterr().out


@respx.mock
def test_app_disable_posts_without_body(token_env, capsys):
    route = respx.post(f"{SRV}/admin/v1/apps/test-flow:disable").mock(
        return_value=httpx.Response(
            200, json={"app_id": "test-flow", "version": "0.1.0", "status": "DISABLED"}
        )
    )
    assert main(["--server", SRV, "app", "disable", "test-flow"]) == 0
    assert route.calls.last.request.content == b""
    assert "DISABLED" in capsys.readouterr().out


@respx.mock
def test_health_prints_values_as_is_and_flags_only_real_problems(token_env, capsys):
    health = {
        "db": "ok",
        "clamav": "down: timeout",
        "openbao": "ok",
        "flowable": "ok",
        "keycloak_default_roles": "ok",
        "anchor": {"last_tree_size": 3, "last_anchor_age_s": 90},
        "seal_pending": 0,
        "task_intents_stuck": 0,
        "seal_key": "none",
        "org": "ok",
    }
    respx.get(f"{SRV}/admin/v1/health").mock(return_value=httpx.Response(200, json=health))
    assert main(["--server", SRV, "health"]) == 0  # mã thoát 0 khi yêu cầu thành công
    out = capsys.readouterr().out
    assert "down: timeout" in out and "none" in out
    flagged = [line for line in out.splitlines() if line.lstrip().startswith("!")]
    assert len(flagged) == 1 and "clamav" in flagged[0]  # "none" của seal_key là bình thường
    assert main(["--server", SRV, "health", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == health


@respx.mock
def test_health_flags_expired_seal_key(token_env, capsys):
    respx.get(f"{SRV}/admin/v1/health").mock(
        return_value=httpx.Response(200, json={"db": "ok", "seal_key": "expired"})
    )
    assert main(["--server", SRV, "health"]) == 0
    flagged = [x for x in capsys.readouterr().out.splitlines() if x.lstrip().startswith("!")]
    assert len(flagged) == 1 and "seal_key" in flagged[0]


@respx.mock
def test_quarantine_list(token_env, capsys):
    rows = [
        {
            "upload_id": "u1",
            "sha256": "cc" * 32,
            "status": "INFECTED",
            "reason": "Eicar",
            "app_id": "test-flow",
            "created_at": "2026-10-21T00:00:00+00:00",
        }
    ]
    route = respx.get(f"{SRV}/admin/v1/quarantine").mock(return_value=httpx.Response(200, json=rows))
    assert main(["--server", SRV, "quarantine", "list"]) == 0
    assert "INFECTED" in capsys.readouterr().out and "limit" not in str(route.calls.last.request.url)
    assert main(["--server", SRV, "quarantine", "list", "--limit", "5"]) == 0
    assert route.calls.last.request.url.params["limit"] == "5"


def test_quarantine_limit_out_of_range_is_usage_error_exit_1(token_env):
    assert main(["--server", SRV, "quarantine", "list", "--limit", "0"]) == 1
    assert main(["--server", SRV, "quarantine", "list", "--limit", "1001"]) == 1


@respx.mock
def test_ledger_status_and_anchor_run(token_env, capsys):
    status = {
        "tree_size": 7,
        "latest_sth": {"tree_size": 7, "root_hash": "dd" * 32, "ts": "t", "key_version": 1, "signature": "s"},
        "last_anchor": None,
        "pending_anchor_jobs": 1,
        "verify": {"ok": True, "first_bad_idx": None},
    }
    respx.get(f"{SRV}/admin/v1/ledger/status").mock(return_value=httpx.Response(200, json=status))
    run = respx.post(f"{SRV}/admin/v1/anchor:run").mock(
        return_value=httpx.Response(
            200,
            json={
                "tree_size": 7,
                "root_hash": "dd" * 32,
                "ts": "t",
                "key_version": 1,
                "signature": "s",
                "anchor_job_id": 42,
            },
        )
    )
    assert main(["--server", SRV, "ledger", "status"]) == 0
    out = capsys.readouterr().out
    assert "7" in out and "dd" * 32 in out
    assert main(["--server", SRV, "anchor", "run"]) == 0
    assert run.calls.last.request.content == b"" and "42" in capsys.readouterr().out


def test_common_options_accepted_before_and_after_subcommand(token_env):
    with respx.mock:
        respx.get(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(200, json=[]))
        assert main(["app", "list", "--server", SRV, "--json"]) == 0
        assert main(["--json", "--server", SRV, "app", "list"]) == 0


def test_invalid_app_id_or_version_is_usage_error_exit_1(token_env):
    assert main(["--server", SRV, "app", "diff", "../x", "0.1.0"]) == 1
    assert main(["--server", SRV, "app", "approve", "test-flow", "1.0"]) == 1
    assert main(["--server", SRV, "app", "disable", "A B"]) == 1


# ---------------------------------------------------------------- mã thoát và HTTP


@respx.mock
def test_5xx_is_exit_2(token_env):
    respx.get(f"{SRV}/admin/v1/apps").mock(
        return_value=httpx.Response(
            503, json={"type": PROBLEM_NS + "idp-admin-unavailable", "title": "x", "status": 503}
        )
    )
    assert main(["--server", SRV, "app", "list"]) == 2


@respx.mock
def test_network_error_is_exit_2(token_env):
    respx.get(f"{SRV}/admin/v1/apps").mock(side_effect=httpx.ConnectError("connection refused"))
    assert main(["--server", SRV, "app", "list"]) == 2
    respx.get(f"{SRV}/admin/v1/apps").mock(side_effect=httpx.ReadTimeout("slow"))
    assert main(["--server", SRV, "app", "list"]) == 2


@respx.mock
def test_network_error_message_never_contains_token(token_env, capsys):
    respx.get(f"{SRV}/admin/v1/apps").mock(side_effect=httpx.ConnectError("boom Bearer dummy-token-value"))
    assert main(["--server", SRV, "app", "list"]) == 2
    cap = capsys.readouterr()
    assert "dummy-token-value" not in cap.out + cap.err


@respx.mock
def test_non_json_success_body_is_exit_2(token_env):
    respx.get(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(200, text="<html>proxy</html>"))
    assert main(["--server", SRV, "app", "list"]) == 2


@respx.mock
def test_redirect_is_not_followed_and_token_not_forwarded(token_env):
    evil = respx.get("https://evil.example/admin/v1/apps").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{SRV}/admin/v1/apps").mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example/admin/v1/apps"})
    )
    assert main(["--server", SRV, "app", "list"]) == 2
    assert not evil.called


@respx.mock
def test_401_is_exit_3_with_login_hint(token_env, capsys):
    respx.get(f"{SRV}/admin/v1/apps").mock(
        return_value=httpx.Response(401, json={"type": PROBLEM_NS + "unauthorized"})
    )
    assert main(["--server", SRV, "app", "list"]) == 3
    assert "dxos login" in capsys.readouterr().err


@respx.mock
def test_install_in_progress_is_retried_up_to_5_times(token_env, no_real_sleep, capsys):
    busy = httpx.Response(
        409, json={"type": PROBLEM_NS + "install-in-progress", "title": "busy", "status": 409}
    )
    route = respx.post(f"{SRV}/admin/v1/apps/test-flow:disable").mock(
        side_effect=[
            busy,
            busy,
            httpx.Response(200, json={"app_id": "test-flow", "version": "0.1.0", "status": "DISABLED"}),
        ]
    )
    assert main(["--server", SRV, "app", "disable", "test-flow"]) == 0
    assert route.call_count == 3 and no_real_sleep == [2, 2]
    assert "thử lại" in capsys.readouterr().err


@respx.mock
def test_install_in_progress_gives_up_after_5_retries(token_env, no_real_sleep):
    route = respx.post(f"{SRV}/admin/v1/apps/test-flow:disable").mock(
        return_value=httpx.Response(
            409, json={"type": PROBLEM_NS + "install-in-progress", "title": "busy", "status": 409}
        )
    )
    assert main(["--server", SRV, "app", "disable", "test-flow"]) == 1
    assert route.call_count == 6 and no_real_sleep == [2] * 5


@respx.mock
def test_other_409_is_not_retried(token_env, no_real_sleep, capsys):
    route = respx.post(f"{SRV}/admin/v1/apps/test-flow:approve").mock(
        return_value=httpx.Response(
            409, json={"type": PROBLEM_NS + "version-not-newer", "title": "x", "status": 409}
        )
    )
    assert main(["--server", SRV, "app", "approve", "test-flow", "0.1.0"]) == 1
    assert route.call_count == 1 and no_real_sleep == [] and "version-not-newer" in capsys.readouterr().out


@respx.mock
def test_install_in_progress_retry_resends_same_body(app_dir, token_env):
    busy = httpx.Response(
        409, json={"type": PROBLEM_NS + "install-in-progress", "title": "busy", "status": 409}
    )
    route = respx.post(f"{SRV}/admin/v1/apps").mock(side_effect=[busy, httpx.Response(202, json=SUBMITTED)])
    respx.get(f"{SRV}/admin/v1/apps/test-flow/versions/0.1.0/diff").mock(
        return_value=httpx.Response(200, json={})
    )
    assert main(["--server", SRV, "app", "install", str(app_dir)]) == 0
    assert route.calls[0].request.content == route.calls[1].request.content


@respx.mock
@pytest.mark.parametrize(
    "server",
    [
        "http://admin.example.test",
        "ftp://admin.example.test",
        "admin.example.test",
        "http://localhost.evil.test",
        "https://user:pw@admin.example.test",
        "https://admin.example.test/path",
        "https://",
    ],
)
def test_server_must_be_https_and_plain(token_env, server):
    with respx.mock:
        any_call = respx.route().mock(return_value=httpx.Response(200, json=[]))
        assert main(["--server", server, "app", "list"]) == 1
        assert not any_call.called


@respx.mock
@pytest.mark.parametrize("server", ["http://127.0.0.1:9999", "http://localhost:9999", "http://[::1]:9999"])
def test_plain_http_allowed_for_loopback_only(token_env, server):
    respx.get(f"{server}/admin/v1/apps").mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", server, "app", "list"]) == 0


def test_ca_file_missing_is_exit_1(token_env, tmp_path):
    assert main(["--server", SRV, "--ca-file", str(tmp_path / "nope.pem"), "app", "list"]) == 1


# ---------------------------------------------------------------- token


def test_token_file_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_token({"access_token": "t", "expires_at": 9e9})
    assert stat.S_IMODE((tmp_path / "dxos/token.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "dxos").stat().st_mode) == 0o700


def test_token_file_rewrite_stays_private_and_leaves_no_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_token({"access_token": "t1", "expires_at": 9e9})
    os.chmod(tmp_path / "dxos/token.json", 0o644)
    os.chmod(tmp_path / "dxos", 0o755)  # noqa: S103 - cố ý nới quyền để thử việc siết lại
    save_token({"access_token": "t2", "expires_at": 9e9})
    path = tmp_path / "dxos/token.json"
    assert json.loads(path.read_text())["access_token"] == "t2"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["token.json"]


def test_token_temp_file_is_created_private_before_content_is_written(tmp_path, monkeypatch):
    """Tệp tạm phải có quyền 0600 ngay lúc tạo (không có cửa sổ đọc được)."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    modes = []
    real_open = os.open

    def spy(path, flags, mode=0o777, *a, **k):
        if flags & os.O_CREAT:
            modes.append(mode)
        return real_open(path, flags, mode, *a, **k)

    monkeypatch.setattr("dxos_cli.auth.os.open", spy)
    save_token({"access_token": "t", "expires_at": 9e9})
    assert modes and all(m == 0o600 for m in modes)


def test_xdg_config_home_falls_back_to_home_dot_config(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    save_token({"access_token": "t", "expires_at": 9e9})
    assert (tmp_path / ".config/dxos/token.json").is_file()


def test_not_logged_in_exit_3(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    assert main(["--server", SRV, "app", "list"]) == 3


@respx.mock
def test_corrupt_token_file_is_not_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    (tmp_path / "dxos").mkdir()
    (tmp_path / "dxos/token.json").write_text("{not json", encoding="utf-8")
    any_call = respx.route().mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 3 and not any_call.called


@respx.mock
def test_stored_token_is_used_when_server_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    save_token(_login_token(tmp_path))
    route = respx.get(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV + "/", "app", "list"]) == 0  # dấu "/" cuối được chuẩn hóa
    assert route.calls.last.request.headers["authorization"] == "Bearer stored-token"


@respx.mock
def test_stored_token_is_never_sent_to_another_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    save_token(_login_token(tmp_path))
    other = respx.route().mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", "https://admin.other.test", "app", "list"]) == 3
    assert not other.called
    assert "dxos login --server https://admin.other.test" in capsys.readouterr().err


@respx.mock
def test_expired_stored_token_is_exit_3_without_network_call(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    save_token(_login_token(tmp_path, expires_at=time.time() - 5))
    any_call = respx.route().mock(return_value=httpx.Response(200, json=[]))
    assert main(["--server", SRV, "app", "list"]) == 3
    assert not any_call.called and "dxos login" in capsys.readouterr().err


@respx.mock
def test_env_token_wins_over_stored_and_works_for_any_server(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_token(_login_token(tmp_path))
    monkeypatch.setenv("DXOS_TOKEN", "from-env")
    route = respx.get("https://admin.other.test/admin/v1/apps").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert main(["--server", "https://admin.other.test", "app", "list"]) == 0
    assert route.calls.last.request.headers["authorization"] == "Bearer from-env"


def test_env_token_with_control_chars_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("DXOS_TOKEN", "abc\r\nX-Evil: 1")
    assert main(["--server", SRV, "app", "list"]) == 1


@respx.mock
def test_server_defaults_to_the_one_the_stored_token_was_issued_for(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    save_token(_login_token(tmp_path))
    route = respx.get(f"{SRV}/admin/v1/apps").mock(return_value=httpx.Response(200, json=[]))
    assert main(["app", "list"]) == 0 and route.called


def test_no_server_and_no_token_is_exit_3(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("DXOS_TOKEN", raising=False)
    assert main(["app", "list"]) == 3


# ---------------------------------------------------------------- device flow


@respx.mock
def test_device_flow_polls_until_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device()
    tok = respx.post(TOKEN).mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "secret-access", "refresh_token": "secret-refresh", "expires_in": 300},
            ),
        ]
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert tok.call_count == 2
    form = dict(httpx.QueryParams(tok.calls.last.request.content.decode()))
    assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert form["client_id"] == "dxos-cli" and form["device_code"] == "dev-code-secret"
    dev_form = dict(httpx.QueryParams(respx.calls[1].request.content.decode()))
    assert dev_form == {"client_id": "dxos-cli", "scope": "openid"}
    cap = capsys.readouterr()
    assert "https://x/device?u=ABCD" in cap.out and "ABCD" in cap.out
    for secret in ("secret-access", "secret-refresh", "dev-code-secret"):
        assert secret not in cap.out + cap.err
    stored = json.loads((tmp_path / "dxos/token.json").read_text())
    assert stored["access_token"] == "secret-access" and stored["server"] == SRV and stored["issuer"] == ISS
    assert stored["expires_at"] > time.time() + 200
    assert "refresh_token" not in stored
    assert stat.S_IMODE((tmp_path / "dxos/token.json").stat().st_mode) == 0o600


@respx.mock
def test_login_json_never_prints_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device()
    respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "secret-access", "expires_in": 300})
    )
    assert main(["login", "--json", "--server", SRV, "--issuer", ISS]) == 0
    out = capsys.readouterr().out
    assert "secret-access" not in out
    assert json.loads(out)["server"] == SRV


@respx.mock
def test_device_flow_prints_uri_and_code_when_no_complete_uri(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    respx.post(DEVICE).mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "d",
                "user_code": "WXYZ-1234",
                "verification_uri": "https://x/device",
                "expires_in": 60,
                "interval": 0,
            },
        )
    )
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 60}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    out = capsys.readouterr().out
    assert "https://x/device" in out and "WXYZ-1234" in out


@respx.mock
def test_device_flow_honours_interval_and_slow_down(monkeypatch, tmp_path, no_real_sleep):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device(interval=2)
    respx.post(TOKEN).mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(200, json={"access_token": "t", "expires_in": 60}),
        ]
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert no_real_sleep == [2, 2, 7, 7]


@respx.mock
def test_device_flow_default_interval_is_5(monkeypatch, tmp_path, no_real_sleep):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    respx.post(DEVICE).mock(
        return_value=httpx.Response(
            200,
            json={"device_code": "d", "user_code": "U", "verification_uri": "https://x/d", "expires_in": 600},
        )
    )
    respx.post(TOKEN).mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(200, json={"access_token": "t", "expires_in": 60}),
        ]
    )
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 0
    assert no_real_sleep == [5, 5]


@respx.mock
@pytest.mark.parametrize("error", ["expired_token", "access_denied", "invalid_grant", "weird"])
def test_device_flow_stops_on_terminal_errors(monkeypatch, tmp_path, error):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device()
    tok = respx.post(TOKEN).mock(return_value=httpx.Response(400, json={"error": error}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert tok.call_count == 1 and not (tmp_path / "dxos/token.json").exists()


@respx.mock
def test_device_flow_overall_deadline_is_expires_in(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device(interval=5, expires_in=12)
    tok = respx.post(TOKEN).mock(return_value=httpx.Response(400, json={"error": "authorization_pending"}))
    clock = {"t": 1000.0}
    monkeypatch.setattr("dxos_cli.auth.monotonic", lambda: clock["t"])
    monkeypatch.setattr("dxos_cli.auth.sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert 1 <= tok.call_count <= 4 and not (tmp_path / "dxos/token.json").exists()


@respx.mock
def test_device_flow_token_endpoint_5xx_is_exit_2(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device()
    respx.post(TOKEN).mock(return_value=httpx.Response(502, text="bad gateway"))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 2


@respx.mock
def test_device_flow_without_token_in_response_is_exit_1(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    _mock_device()
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"expires_in": 60}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1


@respx.mock
def test_issuer_is_derived_from_admin_host(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    disc = respx.get(DISCOVERY).mock(
        return_value=httpx.Response(
            200, json={"device_authorization_endpoint": DEVICE, "token_endpoint": TOKEN}
        )
    )
    _mock_device()
    respx.post(TOKEN).mock(return_value=httpx.Response(200, json={"access_token": "t", "expires_in": 60}))
    assert main(["login", "--server", SRV]) == 0 and disc.called
    assert json.loads((tmp_path / "dxos/token.json").read_text())["issuer"] == ISS


@respx.mock
def test_issuer_derivation_keeps_port(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    iss = "https://localhost:8443/auth/realms/dxos"
    disc = respx.get(f"{iss}/.well-known/openid-configuration").mock(return_value=httpx.Response(500))
    assert main(["login", "--server", "https://admin.localhost:8443"]) == 2 and disc.called


@respx.mock
def test_issuer_required_when_host_is_not_admin(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    any_call = respx.route().mock(return_value=httpx.Response(200, json={}))
    assert main(["login", "--server", "https://dxos.example.test"]) == 1
    assert not any_call.called


@respx.mock
@pytest.mark.parametrize("issuer", ["http://example.test/auth/realms/dxos", "ftp://x/y", "example.test"])
def test_issuer_must_be_https(monkeypatch, tmp_path, issuer):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    any_call = respx.route().mock(return_value=httpx.Response(200, json={}))
    assert main(["login", "--server", SRV, "--issuer", issuer]) == 1
    assert not any_call.called


@respx.mock
def test_discovery_endpoints_must_be_https(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.get(DISCOVERY).mock(
        return_value=httpx.Response(
            200, json={"device_authorization_endpoint": "http://evil.example/device", "token_endpoint": TOKEN}
        )
    )
    dev = respx.post("http://evil.example/device").mock(return_value=httpx.Response(200, json={}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1
    assert not dev.called


@respx.mock
def test_discovery_missing_endpoints_is_exit_1(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.get(DISCOVERY).mock(return_value=httpx.Response(200, json={"issuer": ISS}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1


@respx.mock
def test_device_authorization_rejected_is_exit_1(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _mock_discovery()
    respx.post(DEVICE).mock(return_value=httpx.Response(400, json={"error": "unauthorized_client"}))
    assert main(["login", "--server", SRV, "--issuer", ISS]) == 1


# ---------------------------------------------------------------- ràng buộc đóng gói


def test_cli_package_does_not_import_dxos_core():
    src = Path(__file__).resolve().parents[1] / "src" / "dxos_cli"
    files = sorted(src.glob("*.py"))
    assert {f.name for f in files} >= {"__init__.py", "main.py", "auth.py", "client.py", "commands.py"}
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(n.split(".")[0] == "dxos_core" for n in names), f.name
    deps = tomllib.loads((src.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    assert sorted(d.split(">")[0] for d in deps) == ["httpx", "pyyaml"]


def test_cli_sources_never_log_or_print_the_token():
    src = Path(__file__).resolve().parents[1] / "src" / "dxos_cli"
    for f in src.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "import logging" not in text, f.name


# ---------------------------------------------------------------- bổ sung: --json lỗi, --ca-file, 5xx


@respx.mock
def test_json_mode_prints_problem_document_on_4xx(token_env, capsys):
    problem = {"type": PROBLEM_NS + "app-not-active", "title": "Not active", "status": 404}
    respx.post(f"{SRV}/admin/v1/apps/test-flow:disable").mock(return_value=httpx.Response(404, json=problem))
    assert main(["--json", "--server", SRV, "app", "disable", "test-flow"]) == 1
    assert json.loads(capsys.readouterr().out) == problem


@respx.mock
def test_5xx_problem_is_printed_on_stdout_with_exit_2(token_env, capsys):
    respx.post(f"{SRV}/admin/v1/apps/test-flow:approve").mock(
        return_value=httpx.Response(
            503,
            json={
                "type": PROBLEM_NS + "idp-admin-unavailable",
                "title": "IdP",
                "status": 503,
                "detail": "kc down",
            },
        )
    )
    assert main(["--server", SRV, "app", "approve", "test-flow", "0.1.0"]) == 2
    assert "idp-admin-unavailable" in capsys.readouterr().out


def test_make_verify_builds_a_tls_context_from_ca_file(tmp_path):
    import datetime
    import ssl

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from dxos_cli.client import make_verify

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = tmp_path / "ca.pem"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    assert isinstance(make_verify(str(pem)), ssl.SSLContext)
    assert make_verify(None) is True
