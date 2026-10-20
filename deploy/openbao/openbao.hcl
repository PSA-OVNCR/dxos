# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
# OpenBao: chỉ nghe trong net-data. TLS tắt vì mạng là internal và chỉ trust-core thấy (spec 6.2).
# Khởi tạo, unseal và bật transit: docs/runbook-openbao.md (init.sh trong cùng thư mục).
storage "file" {
  path = "/openbao/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

disable_mlock = true
ui            = false
api_addr      = "http://openbao:8200"
