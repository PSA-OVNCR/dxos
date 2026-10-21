# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Model pydantic của manifest ``dxos/v1`` (spec 9.1). Hình dạng do ``manifest.schema.json`` kiểm trước."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PiiType = Literal["CCCD", "PHONE", "BANK_ACCOUNT", "EMAIL", "NAME"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppInfo(_Strict):
    id: str
    version: str
    name: str
    spaces: list[Literal["H", "P", "D", "I"]]


class FieldSpec(_Strict):
    type: Literal["string", "sequence", "integer", "boolean", "date"]
    required: bool = False
    public: bool = False
    pii: PiiType | None = None
    format: str | None = None
    label: str | None = None                          # nhãn hiển thị ở trang đối soát (spec 25.4)
    reset: Literal["never", "yearly"] = "never"       # chỉ cho type: sequence (spec 25.4)


class AttachmentSpec(_Strict):
    kinds: list[Literal["pdf"]]
    max_mb: int
    min: int = 0
    quarantine: Literal["required"] = "required"


class AccessSpec(_Strict):
    read: list[str]
    create: list[str]
    # Không khai báo thì chủ bản ghi được sửa (và đính kèm tệp) khi bản ghi chưa niêm phong.
    update: list[str] = Field(default_factory=lambda: ["owner"])


class CollectionSpec(_Strict):
    fields: dict[str, FieldSpec]
    attachments: AttachmentSpec | None = None
    access: AccessSpec


class PiiPolicy(_Strict):
    reveal_roles: list[str] = Field(default_factory=list)
    document_detect: list[PiiType] = Field(default_factory=list)
    erase_roles: list[str] = Field(default_factory=list)   # role được gọi :erase-pii (spec 25.2)


class SealPolicy(_Strict):
    on_event: str
    target: list[Literal["record", "attachments"]]
    public_fields: list[str] = Field(default_factory=list)
    revoke_roles: list[str] = Field(default_factory=list)  # mặc định rỗng: không ai được thu hồi (P2-D8)


class VerifyPolicy(_Strict):
    public: bool = False
    require_file: bool = False


class Policies(_Strict):
    pii: PiiPolicy = Field(default_factory=PiiPolicy)
    seal: SealPolicy | None = None
    verify: VerifyPolicy | None = None


class TaskSpec(_Strict):
    role: str
    guards: list[str] = Field(default_factory=list)


class WorkflowSpec(_Strict):
    bpmn: str
    tasks: dict[str, TaskSpec]


class Manifest(_Strict):
    api_version: Literal["dxos/v1"] = Field(alias="apiVersion")
    app: AppInfo
    roles: list[str]
    collections: dict[str, CollectionSpec]
    policies: Policies = Field(default_factory=Policies)
    workflow: WorkflowSpec | None = None
