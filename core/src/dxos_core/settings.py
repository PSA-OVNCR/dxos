# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cấu hình trust-core, đọc từ biến môi trường tiền tố ``DXOS_``.

Bí mật (khóa S3, token OpenBao, khóa HMAC) không đặt trong biến môi trường mà
đọc từ tệp (Docker secret ở ``/run/secrets/...``); Settings chỉ giữ đường dẫn.
"""

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Tên tổ chức mặc định: còn giá trị này thì lõi từ chối niêm phong (spec 25.3), để tên giữ chỗ không bị ghi
# vĩnh viễn vào tuyên bố khóa chỉ-thêm. dxos_core.seal.keys dùng lại hằng này.
ORG_NAME_DEFAULT = "Tổ chức chưa cấu hình"


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
    # Flowable REST (Plan 02 Task 4). Không đặt flowable_password_file thì mọi thao tác workflow trả 503.
    flowable_url: str = "http://flowable:8080/flowable-rest/service"
    flowable_user: str = "rest-admin"
    flowable_password_file: Path | None = None
    # Múi giờ tính năm cho số văn bản đánh lại theo năm (spec 25.4). Biến môi trường DXOS_TIMEZONE.
    timezone: str = "Asia/Ho_Chi_Minh"
    # Tuyên bố khóa seal-key (spec 25.3; Plan 02 Task 6 tạo trường, Task 7 dùng để dựng tuyên bố).
    # Biến môi trường DXOS_ORG_NAME, DXOS_ORG_ID, DXOS_SEAL_KEY_VALIDITY_DAYS, DXOS_SEAL_PURPOSE,
    # DXOS_KEY_POLICY_URL. Tên tổ chức là cấu hình triển khai, không phải định danh app (không vi phạm I3).
    org_name: str = ORG_NAME_DEFAULT
    org_id: str | None = None
    # Tối đa 10 năm (NĐ 23/2025 Điều 7 khoản 4).
    seal_key_validity_days: int = Field(3650, ge=1, le=3650)
    seal_purpose: str = "Niêm phong văn bản và bản ghi do tổ chức ban hành qua DX-OS Trust Core"
    key_policy_url: str | None = None
    # Niêm phong (Plan 02 Task 7). public_base_url: gốc của verify_url (DXOS_PUBLIC_BASE_URL).
    # sth_after_seal: xếp việc lập STH + neo ngay sau mỗi lần niêm phong (DXOS_STH_AFTER_SEAL).
    public_base_url: str = "https://localhost"
    sth_after_seal: bool = True

    @field_validator("org_name", "seal_purpose", mode="before")
    @classmethod
    def _blank_is_default(cls, v: object, info) -> object:
        """Compose truyền ``${DXOS_ORG_NAME:-}``: chuỗi rỗng nghĩa là "chưa đặt", dùng mặc định. Nhờ vậy tên
        rỗng không bao giờ lọt vào tuyên bố khóa (tên mặc định thì lõi từ chối niêm phong)."""
        if isinstance(v, str) and not v.strip():
            return cls.model_fields[info.field_name].default
        return v

    @field_validator("org_id", "key_policy_url", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"múi giờ không hợp lệ: {v!r}") from exc
        return v


def org_configured(settings: Settings) -> bool:
    """Tên tổ chức đã được đặt thật: không phải ``ORG_NAME_DEFAULT``, không rỗng, không bắt đầu bằng
    ``changeme`` (giá trị giữ chỗ của ``.env.example``; không phân biệt hoa thường, sau khi bỏ khoảng trắng).

    Một chỗ kiểm duy nhất cho R-1, tuyên bố khóa và trạng thái quản trị: tên đã vào tuyên bố khóa (chỉ-thêm,
    đã neo) thì không sửa được.
    """
    name = settings.org_name.strip()
    return bool(name) and name != ORG_NAME_DEFAULT and not name.casefold().startswith("changeme")


def read_secret(path: Path) -> str:
    """Đọc một bí mật từ tệp, bỏ khoảng trắng/xuống dòng ở hai đầu. Tệp rỗng là lỗi."""
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"tệp bí mật rỗng: {path}")
    return value
