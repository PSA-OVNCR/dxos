# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Sinh deploy/keycloak/realm-dxos-dev.json = realm production + phần bổ sung chỉ cho dev/test.

    python ops/build_dev_realm.py          # ghi lại tệp dev
    python ops/build_dev_realm.py --check  # thoát 1 nếu tệp dev đã lệch

Keycloak chỉ nạp một tệp cho mỗi realm, nên bản dev phải là realm đầy đủ. Sinh tự động
để bản dev không trôi khỏi bản production (test_dev_realm_is_production_plus_dev_additions).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

KC_DIR = Path(__file__).resolve().parents[1] / "deploy" / "keycloak"


def build(prod: dict, overlay: dict) -> dict:
    realm = copy.deepcopy(prod)
    realm["displayName"] = f"{prod.get('displayName', prod['realm'])} (DEV)"
    realm["roles"]["realm"] += [
        {"name": r, "description": "Vai trò ứng dụng mẫu (DEV-ONLY; production do installer tạo)"}
        for r in overlay["roles"]
    ]
    # Giữ người dùng của production (service account dxos-installer) rồi thêm người dùng dev.
    realm["users"] = realm.get("users", []) + [
        {
            "username": name,
            "enabled": True,
            "email": f"{name}@dev.dxos.invalid",
            "emailVerified": True,
            "firstName": name,
            "lastName": "Dev",
            "credentials": [
                {"type": "password", "value": overlay["password"], "temporary": False}
            ],
            "realmRoles": list(roles),
        }
        for name, roles in overlay["users"].items()
    ]
    realm["clients"] = realm["clients"] + [copy.deepcopy(overlay["test_client"])]
    return realm


def render(realm: dict) -> str:
    return json.dumps(realm, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    prod = json.loads((KC_DIR / "realm-dxos.json").read_text(encoding="utf-8"))
    overlay = json.loads((KC_DIR / "dev-overlay.json").read_text(encoding="utf-8"))
    out = render(build(prod, overlay))
    target = KC_DIR / "realm-dxos-dev.json"
    if args.check:
        same = target.exists() and target.read_text(encoding="utf-8") == out
        print("realm-dxos-dev.json khớp" if same else "realm-dxos-dev.json LỆCH")
        return 0 if same else 1
    target.write_text(out, encoding="utf-8", newline="\n")
    print(f"đã ghi {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
