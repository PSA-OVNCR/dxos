#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Entrypoint của trust-core-api:
#   1. Chạy migration bằng role dxos_owner, đặt mật khẩu role dxos_core.
#   2. Xóa thông tin đăng nhập của dxos_owner khỏi môi trường rồi exec uvicorn
#      (tiến trình API chỉ còn DSN của dxos_core, quyền tối thiểu).
set -eu

python -m dxos_core.db.migrate
unset DXOS_MIGRATE_DATABASE_URL DXOS_CORE_DB_PASSWORD

exec uvicorn --factory dxos_core.app:create_app --host 0.0.0.0 --port 8000 --no-server-header
