# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Sinh tài liệu OpenAPI của trust-core-api từ ứng dụng FastAPI (Plan 02 Task 15).

    python ops/openapi.py            # ghi docs/api/openapi.json (make openapi)
    python ops/openapi.py --check    # thoát 1 nếu tệp đã commit khác bản sinh lại

Không cần dịch vụ nào: ``create_app`` chỉ tạo route, không kết nối DB, OpenBao hay Keycloak (lifespan không
chạy). Cấu hình dùng giá trị giả cố định, nên kết quả chỉ phụ thuộc mã nguồn. Đầu ra ổn định: khóa sắp xếp,
thụt 2 dấu cách, UTF-8 giữ nguyên chữ Việt, kết thúc bằng một dòng mới.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/api/openapi.json"

# Giá trị giả, không trỏ tới dịch vụ thật; chỉ để Settings hợp lệ.
_SETTINGS = {
    "database_url": "postgresql://openapi@invalid/openapi",
    "s3_endpoint": "http://invalid:8333",
    "s3_access_key_file": "/nonexistent",
    "s3_secret_key_file": "/nonexistent",
    "openbao_token_file": "/nonexistent",
    "keycloak_issuer": "https://invalid/auth/realms/dxos",
    "keycloak_jwks_url": "http://invalid/auth/realms/dxos/protocol/openid-connect/certs",
    "actor_hmac_key_file": "/nonexistent",
    "anchor_repo_dir": "/nonexistent",
}


def render() -> str:
    from dxos_core.app import create_app
    from dxos_core.settings import Settings

    settings = Settings(_env_file=None, **_SETTINGS)
    spec = create_app(settings).openapi()
    return json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if argv == ["--check"]:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} đã cũ: chạy make openapi rồi commit", file=sys.stderr)
            return 1
        return 0
    if argv:
        print("cách dùng: openapi.py [--check]", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"đã ghi {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
