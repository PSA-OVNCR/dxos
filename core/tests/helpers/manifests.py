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
    "phong-ho-so": ROOT / "apps/phong-ho-so/manifest.yaml",
    "chung-nhan": ROOT / "apps/chung-nhan/manifest.yaml",
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
