# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Bộ quét AT-14 duy nhất: mã lõi phát hành không chứa định danh của bất kỳ ``apps/*/manifest.yaml`` nào.

Hai test dùng chung (``tests/apps`` và ``core/tests/test_manifest_validator.py``) để không có hai bản lệch.
"""

import re
from pathlib import Path

import yaml

# Image lõi (core/Dockerfile) COPY nguyên ``libs/dxos-proof`` và ``core``; Dockerfile.dockerignore loại
# thư mục tests, __pycache__, *.pyc, *.egg-info. Quét đúng phần còn lại.
IMAGE_DIRS = ("libs/dxos-proof", "core")
_SKIPPED_PARTS = {"tests", "__pycache__"}


def identifiers(root: Path) -> set[str]:
    """App id (gạch nối và gạch dưới), tên collection và tên role của mọi ``apps/*/manifest.yaml``."""
    idents: set[str] = set()
    manifests = sorted((root / "apps").glob("*/manifest.yaml"))
    assert len(manifests) >= 2, "không tìm thấy manifest App A/B để lấy định danh"
    for f in manifests:
        m = yaml.safe_load(f.read_text(encoding="utf-8"))
        idents |= {m["app"]["id"], m["app"]["id"].replace("-", "_"), *m["collections"], *m["roles"]}
    return idents


def shipped_files(root: Path) -> list[Path]:
    """Mọi tệp mà image lõi chứa (xem ``IMAGE_DIRS``), trừ thư mục tests và rác biên dịch."""
    files = [p for d in IMAGE_DIRS for p in (root / d).rglob("*")
             if p.is_file() and not (_SKIPPED_PARTS & set(p.relative_to(root).parts))
             and not p.name.endswith(".pyc") and ".egg-info" not in p.as_posix()]
    assert len(files) > 20, "quét rỗng: không thấy mã lõi"
    return files


def scan(root: Path) -> list[tuple[str, str]]:
    """Danh sách ``(đường dẫn tương đối so với repo, định danh)`` bị vi phạm; rỗng là đạt.

    So khớp phân biệt hoa thường và theo ranh giới từ (``\\b``): không phân biệt hoa thường sẽ bắt nhầm từ
    thông thường trong tài liệu.
    """
    idents = identifiers(root)
    return sorted({(p.relative_to(root).as_posix(), i) for p in shipped_files(root) for i in idents
                   if re.search(rf"\b{re.escape(i)}\b", p.read_text(encoding="utf-8", errors="ignore"))})
