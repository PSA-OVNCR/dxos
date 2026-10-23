# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Cấu hình Viewer từ biến môi trường. Viewer không giữ bí mật nào: chỉ biết địa chỉ API và thời hạn gọi."""

import os
from dataclasses import dataclass

DEFAULT_API_BASE = "http://apisix:9080"
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_BYTES = 64 * 1024 * 1024        # trần dung lượng tệp tải về từ API (giữ nguyên trong RAM)


@dataclass(frozen=True)
class Settings:
    api_base: str = DEFAULT_API_BASE
    timeout_s: float = DEFAULT_TIMEOUT_S      # tổng thời gian cho mỗi lần gọi API
    max_bytes: int = DEFAULT_MAX_BYTES

    @classmethod
    def from_env(cls) -> "Settings":
        base = os.environ.get("DXOS_VIEWER_API_BASE", DEFAULT_API_BASE).strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ValueError("DXOS_VIEWER_API_BASE phải bắt đầu bằng http:// hoặc https://")
        return cls(api_base=base, timeout_s=_positive_float("DXOS_VIEWER_TIMEOUT_S", DEFAULT_TIMEOUT_S),
                   max_bytes=int(_positive_float("DXOS_VIEWER_MAX_BYTES", DEFAULT_MAX_BYTES)))


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not 0 < value < float("inf"):
        raise ValueError(f"{name} phải là số dương, nhận {raw!r}")
    return value
