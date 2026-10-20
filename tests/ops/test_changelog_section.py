# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test trích mục CHANGELOG cho release notes."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("changelog_section", ROOT / "ops/changelog_section.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

SAMPLE = """# Changelog

## [Unreleased]
- việc đang làm

## [0.2.0] - 2026-11-16
### Added
- B

## [0.1.0] - 2026-11-09
### Added
- A
"""


def test_extracts_exact_section():
    assert cs.section(SAMPLE, "0.2.0") == "## [0.2.0] - 2026-11-16\n### Added\n- B\n"
    assert cs.section(SAMPLE, "0.1.0") == "## [0.1.0] - 2026-11-09\n### Added\n- A\n"


def test_missing_version():
    assert cs.section(SAMPLE, "9.9.9") is None
    assert cs.section(SAMPLE, "0.1") is None


def test_real_changelog_has_unreleased():
    assert cs.section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), "Unreleased")
