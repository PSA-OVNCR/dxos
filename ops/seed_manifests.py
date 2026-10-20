# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Đưa manifest `test-app`, `phong-ho-so`, `chung-nhan` vào trạng thái ACTIVE (Plan 01 Task 17).

**Chỉ dùng tạm** tới khi có installer ở Plan 02. Hai cách chạy:

    # trên máy có dxos-core (make dev-install), DB truy cập được:
    DXOS_DATABASE_URL=... DXOS_ACTOR_HMAC_KEY_FILE=... python ops/seed_manifests.py

    # trên stack đang chạy (không cần Python trên máy):
    docker compose -p dxos cp apps/phong-ho-so/manifest.yaml trust-core-api:/tmp/phong-ho-so.yaml
    docker compose -p dxos exec trust-core-api python -m dxos_core.registry.seed /tmp/phong-ho-so.yaml
"""

import sys
from pathlib import Path

from dxos_core.registry.seed import main

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = [ROOT / "core/tests/fixtures/manifest-test-app.yaml", ROOT / "apps/phong-ho-so/manifest.yaml",
           ROOT / "apps/chung-nhan/manifest.yaml"]

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or [str(p) for p in DEFAULT]))
