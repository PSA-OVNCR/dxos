#!/bin/sh
# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Thiết lập transit cho DX-OS trên OpenBao ĐÃ init và ĐÃ unseal (xem docs/runbook-openbao.md).
#   read -rs BAO_TOKEN && export BAO_TOKEN    # root token: không gõ thẳng trên dòng lệnh
#   BAO_ADDR=http://127.0.0.1:8200 sh deploy/openbao/init.sh
# In ra token của trust-core (policy dxos-core) ở dòng cuối. Cuối cùng thu hồi root token,
# trừ khi đặt DXOS_KEEP_ROOT=1 (chỉ dùng cho môi trường thử).
set -eu
: "${BAO_ADDR:?đặt BAO_ADDR}"
: "${BAO_TOKEN:?đặt BAO_TOKEN (root token sau operator init)}"
HERE=$(cd "$(dirname "$0")" && pwd)
BAO=${BAO_BIN:-bao}

if ! "$BAO" secrets list -format=json | grep -q '"transit/"'; then
  "$BAO" secrets enable transit >&2
fi
for key in seal-key sth-key; do
  # exportable=false: khóa riêng không bao giờ rời OpenBao. Tạo lại khóa đã có là no-op.
  "$BAO" write -f "transit/keys/$key" type=ed25519 exportable=false >&2
done
"$BAO" policy write dxos-core "$HERE/dxos-core-policy.hcl" >&2
TOKEN=$("$BAO" token create -policy=dxos-core -no-default-policy -orphan -period=768h -field=token)

if [ "${DXOS_KEEP_ROOT:-0}" != "1" ]; then
  "$BAO" token revoke -self >&2
  echo "Đã thu hồi root token. Tạo lại khi cần bằng: bao operator generate-root" >&2
fi
echo "$TOKEN"
