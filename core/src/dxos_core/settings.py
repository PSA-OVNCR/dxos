# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cấu hình trust-core, đọc từ biến môi trường tiền tố ``DXOS_``.

Bí mật (khóa S3, token OpenBao, khóa HMAC) không đặt trong biến môi trường mà
đọc từ tệp (Docker secret ở ``/run/secrets/...``); Settings chỉ giữ đường dẫn.
"""

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DXOS_", extra="ignore")

    database_url: str
    s3_endpoint: str
    s3_access_key_file: Path
    s3_secret_key_file: Path
    s3_bucket_staging: str = "dxos-staging"
    s3_bucket_objects: str = "dxos-objects"
    s3_bucket_quarantine: str = "dxos-quarantine"
    clamd_host: str = "clamav"
    clamd_port: int = 3310
    openbao_addr: str = "http://openbao:8200"
    openbao_token_file: Path
    keycloak_issuer: str
    keycloak_jwks_url: str
    jwt_audience: str = "dxos-api"
    actor_hmac_key_file: Path
    anchor_repo_dir: Path
    max_upload_mb_default: int = 15
    # Neo STH (Task 16). Không đặt anchor_remote thì không neo (stack vẫn chạy, STH vẫn ký).
    anchor_remote: str | None = None
    anchor_git_ssh_command: str = (
        "ssh -i /run/secrets/anchor-deploy-key -o IdentitiesOnly=yes -o BatchMode=yes"
        " -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4"
        " -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/var/lib/dxos/anchor-known-hosts")
    # Múi giờ tính năm cho số văn bản đánh lại theo năm (spec 25.4). Biến môi trường DXOS_TIMEZONE.
    timezone: str = "Asia/Ho_Chi_Minh"

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"múi giờ không hợp lệ: {v!r}") from exc
        return v


def read_secret(path: Path) -> str:
    """Đọc một bí mật từ tệp, bỏ khoảng trắng/xuống dòng ở hai đầu. Tệp rỗng là lỗi."""
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"tệp bí mật rỗng: {path}")
    return value
