# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: nạp manifest và tạo Principal nhanh."""

import copy
from pathlib import Path

import yaml
from dxos_core.identity.jwt import Principal
from dxos_core.registry.model import Manifest
from dxos_core.registry.validator import validate_manifest

ROOT = Path(__file__).resolve().parents[3]
PATHS = {
    "test-app": ROOT / "core/tests/fixtures/manifest-test-app.yaml",
    "test-flow": ROOT / "core/tests/fixtures/manifest-test-flow.yaml",
}


def raw(name: str) -> dict:
    return copy.deepcopy(yaml.safe_load(PATHS[name].read_text(encoding="utf-8")))


def load(name: str) -> dict:
    """Bản sao dict của manifest ``name`` (như ``raw``), test sửa tự do rồi đưa vào ``validate_manifest``."""
    return raw(name)


def manifest(name: str) -> Manifest:
    return validate_manifest(raw(name))


def P(sub: str, roles: list[str], admin: bool = False) -> Principal:  # noqa: N802 (tên ngắn như plan)
    return Principal(sub, frozenset(roles), admin)


def mutate(doc: dict, change: str, *, version: str | None = None) -> dict:
    """Bản sao ``doc`` (manifest ``test-flow``) với đúng một thay đổi tên ``change`` (luật nâng cấp P2-D14,
    Plan 02 Task 12); ``version`` đặt lại ``app.version``. Tên lạ → ``KeyError``."""
    d = copy.deepcopy(doc)
    if version is not None:
        d["app"]["version"] = version
    doc_fields = d["collections"]["doc"]["fields"]
    pol = d["policies"]
    tasks = d["workflow"]["tasks"]

    def drop_role() -> None:                       # bỏ role author (và chỗ tham chiếu duy nhất tới nó)
        d["roles"].remove("author")
        d["collections"]["doc"]["access"]["create"] = ["role:reviewer"]

    def drop_collection() -> None:                 # collection doc biến mất (nội dung chuyển sang doc2)
        d["collections"]["doc2"] = d["collections"].pop("doc")

    changes = {
        "drop_field": lambda: doc_fields.pop("cccd"),
        "change_type": lambda: doc_fields["title"].update(type="integer"),
        "drop_role": drop_role,
        "drop_collection": drop_collection,
        "new_required_field": lambda: doc_fields.update(note={"type": "string", "required": True}),
        "drop_task_guard": lambda: tasks["review"]["guards"].remove("attachments_clean"),
        "widen_reveal_roles": lambda: pol["pii"]["reveal_roles"].append("reviewer"),
        "widen_revoke_roles": lambda: pol["seal"]["revoke_roles"].append("reviewer"),
        "change_seal": lambda: pol["seal"].update(public_fields=["ref"]),
        "change_verify": lambda: pol["verify"].update(require_file=False),
        "add_optional": lambda: (doc_fields.update(note={"type": "string"}), d["roles"].append("observer")),
        "widen_erase_roles": lambda: pol["pii"]["erase_roles"].append("reviewer"),
        "change_label": lambda: doc_fields["title"].update(label="Tên hồ sơ"),
        "change_sequence": lambda: doc_fields["ref"].update(format="{n:03}/TF-2", reset="never"),
        "none": lambda: None,
    }
    changes[change]()
    return d
