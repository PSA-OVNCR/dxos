# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test khung trust-core: health, lỗi RFC 7807, cấu hình (Plan 01 Task 8)."""

import json
from pathlib import Path

import pytest
from dxos_core.errors import PROBLEM_BASE, PROBLEM_MEDIA_TYPE, problem
from dxos_core.settings import Settings, read_secret


def test_healthz_ok(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_readyz_is_problem_503_when_db_unreachable(client):
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    body = r.json()
    assert body["type"] == PROBLEM_BASE + "not-ready" and body["status"] == 503
    assert "127.0.0.1" not in json.dumps(body)  # không lộ chi tiết kết nối


def test_unknown_route_is_problem_json(client):
    r = client.get("/khong-co")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert r.json() == {"type": PROBLEM_BASE + "not-found", "title": "Not Found", "status": 404}


def test_method_not_allowed_is_problem_json(client):
    r = client.post("/healthz")
    assert r.status_code == 405
    assert r.json()["type"] == PROBLEM_BASE + "method-not-allowed"
    assert "allow" in {k.lower() for k in r.headers}


def test_problem_helper_shape():
    r = problem(409, "conflict", "Xung đột phiên bản", "version 3 != 4")
    assert r.status_code == 409 and r.media_type == PROBLEM_MEDIA_TYPE
    assert json.loads(r.body) == {
        "type": "https://dxos.dev/problems/conflict",
        "title": "Xung đột phiên bản",
        "status": 409,
        "detail": "version 3 != 4",
    }


def test_problem_omits_empty_detail_and_accepts_full_type_url():
    r = problem(422, PROBLEM_BASE + "schema", "Dữ liệu sai schema")
    assert json.loads(r.body) == {
        "type": PROBLEM_BASE + "schema", "title": "Dữ liệu sai schema", "status": 422}


@pytest.mark.parametrize("bad", ["Not_A_Slug", "", "https://example.com/problems/x", "a/b"])
def test_problem_rejects_bad_type(bad):
    with pytest.raises(ValueError):
        problem(400, bad, "x")


def test_problem_extensions():
    r = problem(422, "schema", "Sai", errors=[{"path": "/a"}])
    assert json.loads(r.body)["errors"] == [{"path": "/a"}]


def test_problem_extension_cannot_override_core_members():
    with pytest.raises(ValueError):
        problem(400, "bad-request", "x", type="https://evil.example/x")


def test_problem_allows_instance_member():
    assert json.loads(problem(404, "not-found", "x", instance="/api/v1/x").body)["instance"] == "/api/v1/x"


def test_settings_from_env_with_prefix(monkeypatch, tmp_path: Path):
    env = {
        "DXOS_DATABASE_URL": "postgresql://u:changeme@db/x",
        "DXOS_S3_ENDPOINT": "http://s3:8333",
        "DXOS_S3_ACCESS_KEY_FILE": str(tmp_path / "a"),
        "DXOS_S3_SECRET_KEY_FILE": str(tmp_path / "b"),
        "DXOS_OPENBAO_TOKEN_FILE": str(tmp_path / "c"),
        "DXOS_KEYCLOAK_ISSUER": "https://localhost/auth/realms/dxos",
        "DXOS_KEYCLOAK_JWKS_URL": "http://keycloak:8080/auth/realms/dxos/protocol/openid-connect/certs",
        "DXOS_ACTOR_HMAC_KEY_FILE": str(tmp_path / "d"),
        "DXOS_ANCHOR_REPO_DIR": str(tmp_path / "anchor"),
        "DXOS_CLAMD_PORT": "13310",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.database_url == "postgresql://u:changeme@db/x"
    assert s.s3_access_key_file == tmp_path / "a" and isinstance(s.anchor_repo_dir, Path)
    assert s.clamd_port == 13310
    # Giá trị mặc định theo Plan 01 Task 8
    assert (s.s3_bucket_staging, s.s3_bucket_objects, s.s3_bucket_quarantine) == (
        "dxos-staging", "dxos-objects", "dxos-quarantine")
    assert (s.clamd_host, s.openbao_addr, s.jwt_audience, s.max_upload_mb_default) == (
        "clamav", "http://openbao:8200", "dxos-api", 15)


def test_settings_has_exactly_planned_fields():
    assert set(Settings.model_fields) == {
        "database_url", "s3_endpoint", "s3_access_key_file", "s3_secret_key_file",
        "s3_bucket_staging", "s3_bucket_objects", "s3_bucket_quarantine",
        "clamd_host", "clamd_port", "openbao_addr", "openbao_token_file",
        "keycloak_issuer", "keycloak_jwks_url", "jwt_audience",
        "actor_hmac_key_file", "anchor_repo_dir", "max_upload_mb_default",
        "anchor_remote", "anchor_git_ssh_command",          # thêm ở Task 16
    }


def test_settings_missing_required_fails(monkeypatch):
    for k in ("DXOS_DATABASE_URL", "DXOS_KEYCLOAK_ISSUER"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError):
        Settings()


def test_read_secret_strips_trailing_newline(secret_file):
    assert read_secret(secret_file) == "changeme-test-secret"


def test_read_secret_rejects_empty(tmp_path):
    p = tmp_path / "empty"
    p.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_secret(p)
