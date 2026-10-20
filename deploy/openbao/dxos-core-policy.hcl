# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
# Policy của token trust-core (spec 11.6): chỉ ký bằng 2 khóa và đọc khóa công khai.
# Không xuất khóa, không xoay khóa, không xóa, không đọc cấu hình hệ thống.
path "transit/sign/seal-key" {
  capabilities = ["update"]
}

path "transit/sign/sth-key" {
  capabilities = ["update"]
}

path "transit/keys/seal-key" {
  capabilities = ["read"]
}

path "transit/keys/sth-key" {
  capabilities = ["read"]
}

# Token của lõi là token period (init.sh): phải tự gia hạn được, và tự xem được thông tin của mình.
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
