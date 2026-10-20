# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Che trường PII trong bản ghi trả về (F4). Bản rõ chỉ trả cho ``reveal_roles`` và được ghi ledger."""

import unicodedata

from dxos_core.registry.model import CollectionSpec

_KEEP_ENDS = frozenset({"CCCD", "PHONE", "BANK_ACCOUNT"})


def mask_value(v: str, pii: str) -> str:
    if pii in _KEEP_ENDS:
        if len(v) <= 4:
            return "*" * len(v)
        return v[:2] + "*" * (len(v) - 4) + v[-2:]
    if pii == "EMAIL":
        local, at, domain = v.partition("@")
        if not at:
            return "***"
        return (local[:1] + "***@" + domain) if local else "***@" + domain
    if pii == "NAME":
        words = unicodedata.normalize("NFC", v).split()
        return " ".join(w[0] + "." for w in words)
    raise ValueError(f"loại PII không hỗ trợ: {pii!r}")


def mask_record(data: dict, spec: CollectionSpec, can_reveal: bool) -> dict:
    """Bản sao của ``data`` với trường PII đã che (trừ khi ``can_reveal``). Không sửa ``data``."""
    out = dict(data)
    if can_reveal:
        return out
    for name, field in spec.fields.items():
        if field.pii and isinstance(out.get(name), str):
            out[name] = mask_value(out[name], field.pii)
    return out


def pii_fields_present(data: dict, spec: CollectionSpec) -> list[str]:
    """Tên các trường PII đang có giá trị (để ghi ``field.revealed``)."""
    return sorted(n for n, f in spec.fields.items() if f.pii and data.get(n) not in (None, ""))
