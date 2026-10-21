# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/pin_images.py: tìm tham chiếu image và ghim digest (resolver giả, không cần Docker)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("pin_images", ROOT / "ops/pin_images.py")
pin_images = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pin_images)

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64


def _tree(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "compose.yaml").write_text(
        "services:\n"
        "  a:\n    image: postgres:17-alpine\n"
        "  b:\n    image: caddy:2.10@" + D2 + "\n"
        "  c:\n    image: !reset null\n"
        "  d:\n    image: postgres:17-alpine   # trùng\n",
        encoding="utf-8",
    )
    (tmp_path / "matrix.yaml").write_text("probe_image: busybox:1.37\n", encoding="utf-8")
    (tmp_path / "x" / "Dockerfile").write_text("FROM python:3.12-slim\nRUN true\n", encoding="utf-8")
    return tmp_path


def test_find_refs_skips_pinned_and_null(tmp_path):
    refs = pin_images.find_refs(_tree(tmp_path))
    assert sorted({r for _, r in refs}) == ["busybox:1.37", "postgres:17-alpine", "python:3.12-slim"]


def test_pin_rewrites_every_occurrence_once_per_ref(tmp_path):
    root = _tree(tmp_path)
    asked = []

    def resolver(ref):
        asked.append(ref)
        return D1

    pinned = pin_images.pin(root, resolver)
    assert sorted(asked) == ["busybox:1.37", "postgres:17-alpine", "python:3.12-slim"]
    assert pinned == {r: D1 for r in asked}
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("postgres:17-alpine@" + D1) == 2
    assert "caddy:2.10@" + D2 in compose and "image: !reset null" in compose
    assert (root / "matrix.yaml").read_text(encoding="utf-8") == f"probe_image: busybox:1.37@{D1}\n"
    assert (root / "x" / "Dockerfile").read_text(encoding="utf-8").startswith(
        f"FROM python:3.12-slim@{D1}\n"
    )
    assert pin_images.find_refs(root) == []  # chạy lại không còn gì để ghim


def test_digest_format_is_validated(tmp_path):
    root = _tree(tmp_path)
    try:
        pin_images.pin(root, lambda ref: "latest")
    except ValueError as e:
        assert "digest" in str(e)
    else:
        raise AssertionError("phải từ chối digest sai định dạng")


def test_script_image_variables_are_pinned_too(tmp_path):
    (tmp_path / "web.sh").write_text(
        "set -eu\nNODE_IMAGE=node:22-bookworm-slim\n"
        "PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.63.0-noble  # ghim\nOTHER_IMAGE=busybox:1.37\n",
        encoding="utf-8")
    assert sorted(r for _, r in pin_images.find_refs(tmp_path)) == [
        "mcr.microsoft.com/playwright:v1.63.0-noble", "node:22-bookworm-slim"]
    pin_images.pin(tmp_path, lambda ref: D1)
    text = (tmp_path / "web.sh").read_text(encoding="utf-8")
    assert f"NODE_IMAGE=node:22-bookworm-slim@{D1}\n" in text
    assert f"PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.63.0-noble@{D1}  # ghim\n" in text
    assert "OTHER_IMAGE=busybox:1.37\n" in text                     # biến khác không bị đụng


def test_repo_script_images_are_found_by_default_roots():
    found = {r for sub in ("ops", "deploy") for _, r in pin_images.find_refs(ROOT / sub)}
    # Chưa ghim: có trong danh sách chờ ghim; đã ghim: không còn. Cả hai trạng thái đều hợp lệ, nhưng mọi ref
    # còn lại phải thuộc hai image của Task 10 (deploy/ đã ghim hết từ Plan 01).
    assert found <= {"node:22-bookworm-slim", "mcr.microsoft.com/playwright:v1.63.0-noble"}
